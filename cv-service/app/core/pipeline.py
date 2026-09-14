"""Deterministic enhancement pipeline.

Flow A and flow B both go through `apply(img, params)`. They differ only in who
fills `EnhanceParams`: `auto_params` (heuristics) or the vision model (JSON).
Nothing in this module generates pixels that were not in the input."""

import math

import cv2
import numpy as np

from app.config import settings
from app.schemas import EnhanceParams, ImageStats

TILT_MIN_LINES = 6
TILT_MIN_CONSENSUS = 0.55  # fraction of lines within 2 deg of the median
TILT_MIN_DEG = 1.0  # below this, do nothing: not worth the crop
TILT_H_MIN_LINES = 8  # horizontals fallback: stricter on every count
TILT_H_MIN_CONSENSUS = 0.7
TILT_ONE_SIDED_MAX = 3.0  # with witnesses on one side only, larger angles are not trusted
TILT_H_MIN_DEG = 3.0  # perspective residuals on horizontals are small; real tilt that shows there is not
TILT_LSD_MIN_DEG = 3.0  # second opinion from the longest segments: below this it is not worth a crop
TILT_LSD_TOP = 8  # longest LSD segments consulted
TILT_LSD_SPREAD = 8.0  # they must agree within this many degrees, all leaning the same way
TILT_BEYOND_MARGIN = 2.0  # past limit + margin the roll is reported as measured, not clipped: reshoot

# ------------------------------------------------------------------- input


def trim_uniform_borders(img: np.ndarray, max_fraction: float = 0.25, tol: float = 2.0) -> np.ndarray:
    """Crop letterbox bars (screenshots, forwarded images). A crop is allowed by
    policy, and without it exposure is measured on grey bars instead of the room.
    Deliberately strict so a flat floor or a blown-out window is never mistaken
    for a bar: bars must be near-perfectly uniform, not white, and present on
    *both* opposite edges (letterboxing is symmetric)."""
    h, w = img.shape[:2]
    rows = img.reshape(h, -1)
    cols = img.transpose(1, 0, 2).reshape(w, -1)

    def run(stds, means, limit):
        n = 0
        while n < limit and stds[n] < tol and means[n] < 200:
            n += 1
        return n

    r_std, r_mean = rows.std(axis=1), rows.mean(axis=1)
    c_std, c_mean = cols.std(axis=1), cols.mean(axis=1)
    top, bottom = run(r_std, r_mean, int(h * max_fraction)), run(r_std[::-1], r_mean[::-1], int(h * max_fraction))
    left, right = run(c_std, c_mean, int(w * max_fraction)), run(c_std[::-1], c_mean[::-1], int(w * max_fraction))
    if min(top, bottom) < 0.02 * h:
        top = bottom = 0
    if min(left, right) < 0.02 * w:
        left = right = 0
    if top + bottom + left + right == 0:
        return img
    return img[top : h - bottom, left : w - right]


def input_warnings(img: np.ndarray, encoded_bytes: int | None) -> list[str]:
    """Things the pipeline cannot fix and the user should know before judging the output."""
    h, w = img.shape[:2]
    warnings = []
    if max(h, w) < 1000:
        warnings.append(f"low_resolution:{w}x{h}")
    if encoded_bytes is not None and encoded_bytes / (h * w) < 0.15:
        warnings.append(f"heavy_compression:{encoded_bytes / (h * w):.2f}_bytes_per_pixel")
    return warnings


# --------------------------------------------------------------------------- ops


def apply_levels(img: np.ndarray, black_pct: float = 0.5, white_pct: float = 99.7) -> np.ndarray:
    """Anchor the black and white points on the luminance histogram. A phone JPEG
    rarely has a true black (~10-25); a brightening gamma lifts that to grey and
    the photo looks veiled. Measured on a 540 px screenshot: black 12 -> 3,
    fidelity local minimum 0.81 -> 0.90, once the levels are set first."""
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    L = lab[..., 0].astype(np.float32)
    lo, hi = np.percentile(L, black_pct), np.percentile(L, white_pct)
    if hi - lo < 32:  # nearly flat image: nothing to anchor
        return img
    lab[..., 0] = np.clip((L - lo) * 255.0 / (hi - lo), 0, 255).astype(np.uint8)
    return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)


def apply_gamma(img: np.ndarray, gamma: float) -> np.ndarray:
    if abs(gamma - 1.0) < 1e-3:
        return img
    lut = np.array([((i / 255.0) ** gamma) * 255 for i in range(256)], dtype=np.uint8)
    levelled = apply_levels(img)
    if gamma > 1.0:
        # Darkening an overexposed photo per channel pulls the pale tones towards their
        # hue (a cream wall turns orange): the curve goes on the luminance only.
        lab = cv2.cvtColor(levelled, cv2.COLOR_BGR2LAB).astype(np.float32)
        L_old = np.maximum(lab[..., 0], 1.0)
        L_new = cv2.LUT(lab[..., 0].astype(np.uint8), lut).astype(np.float32)
        # chroma follows the luminance halfway: a darker wall does not become a more
        # saturated one (LAB keeps a, b fixed, which reads as a colour boost)
        k = np.sqrt(L_new / L_old)[..., None]
        lab[..., 1:] = 128.0 + (lab[..., 1:] - 128.0) * k
        lab[..., 0] = L_new
        return cv2.cvtColor(np.clip(lab, 0, 255).astype(np.uint8), cv2.COLOR_LAB2BGR)
    return cv2.LUT(levelled, lut)


def apply_sharpen(img: np.ndarray, amount: float, sigma: float = 1.2) -> np.ndarray:
    """Unsharp mask: the image plus `amount` times its own high frequencies.
    Nothing is invented — an edge that is not there gets no stronger. Runs last,
    after denoise (which softens) and rotation (whose interpolation softens)."""
    if amount <= 0:
        return img
    blur = cv2.GaussianBlur(img, (0, 0), sigma)
    return cv2.addWeighted(img, 1 + amount, blur, -amount, 0)


def apply_clahe(img: np.ndarray, clip: float, grid: int = 8) -> np.ndarray:
    if clip <= 0:
        return img
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    clahe = cv2.createCLAHE(clipLimit=clip, tileGridSize=(grid, grid))
    lab[..., 0] = clahe.apply(lab[..., 0])
    return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)


def apply_white_balance(img: np.ndarray, strength: float) -> np.ndarray:
    """Gray-world, blended with the input by `strength`."""
    if strength <= 0:
        return img
    f = img.astype(np.float32)
    means = f.reshape(-1, 3).mean(axis=0)
    gains = means.mean() / np.maximum(means, 1e-6)
    balanced = np.clip(f * gains, 0, 255)
    out = f * (1 - strength) + balanced * strength
    return out.astype(np.uint8)


def apply_denoise(img: np.ndarray, h: int) -> np.ndarray:
    """Non-local means. Chroma is denoised ~3x harder than luminance: colour
    speckle is the ugliest part of a brightened night shot and colour carries
    almost no detail, while luminance grain cannot be removed without smoothing
    the wall texture the editorial policy exists to protect."""
    if h <= 0:
        return img
    # The strength is specified for a 1600 px photo. On a small one the same h
    # eats the texture (patches cover more of the scene), so it scales down.
    scale = min(1.0, max(0.5, max(img.shape[:2]) / settings.max_side))
    h_eff = max(1.0, h * scale)
    return cv2.fastNlMeansDenoisingColored(img, None, h_eff, min(30.0, h_eff * 3), 7, 21)


def _consensus(devs: list[float], weights: list[float], pos: list[float], span: float, min_lines: int,
               min_consensus: float, max_split: float) -> float | None:
    """Weighted median of the deviations if the lines agree: enough of them, most
    within 2 deg of the median, and the two outer thirds (by `pos` along `span`)
    leaning the same way. Perspective makes the outer thirds disagree; tilt does not."""
    if len(devs) < min_lines:
        return None
    d, wgt, x = np.array(devs), np.array(weights), np.array(pos)
    median = _weighted_median(d, wgt)
    if np.mean(np.abs(d - median) < 2.0) < min_consensus:
        return None
    lo, hi = x < span / 3, x > 2 * span / 3
    if lo.sum() >= 2 and hi.sum() >= 2:
        ml, mh = _weighted_median(d[lo], wgt[lo]), _weighted_median(d[hi], wgt[hi])
        if (ml * mh < 0 and abs(ml - mh) > 2.0) or abs(ml - mh) > max_split:
            return None  # keystone, not tilt
    # Lines on one side only (a wardrobe on the left, a bare wall on the right) cannot
    # tell a roll from a wide-angle keystone: both lean the same way there. A small
    # correction is harmless either way; a large one on that evidence is a gamble
    # (img_002: 11 verticals at -10 deg, all in the left half, perspective not tilt).
    if (x.max() < span / 2 or x.min() > span / 2) and abs(median) > TILT_ONE_SIDED_MAX:
        return None
    return float(median)


def estimate_tilt(img: np.ndarray) -> float:
    """Rotation (deg, positive = counter-clockwise) that would straighten the
    dominant lines. Near-vertical lines first (walls, door frames): they are the
    reliable witnesses. Near-horizontal lines only as a fallback when there are
    no verticals to speak of, and under stricter rules: in a room they converge
    with perspective (bed edges, floor), so they vote for rotations that are not
    there unless the whole picture agrees (top and bottom thirds within 3 deg)
    and the tilt is large. Calibrated on the dataset: false positives of 4-10 deg
    on straight photos came from 3-4 stray lines or from perspective, never from
    real tilt; the fallback was added for a phone photo of a bed against a plain
    wall (17 horizontals at -10 deg, zero verticals)."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 60, 160)
    h, w = img.shape[:2]
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=80, minLineLength=int(h * 0.15), maxLineGap=10)
    if lines is None:
        return 0.0
    vert: tuple[list, list, list] = ([], [], [])
    horiz: tuple[list, list, list] = ([], [], [])
    for x1, y1, x2, y2 in lines[:, 0]:
        angle = math.degrees(math.atan2(y2 - y1, x2 - x1))
        if angle < 0:
            angle += 180  # -> [0, 180): vertical == 90, horizontal == 0 or 180
        length = math.hypot(x2 - x1, y2 - y1)
        dev_v = angle - 90
        dev_h = angle if angle <= 90 else angle - 180
        if abs(dev_v) <= 15:
            vert[0].append(dev_v); vert[1].append(length); vert[2].append((x1 + x2) / 2)
        elif abs(dev_h) <= 15:
            horiz[0].append(dev_h); horiz[1].append(length); horiz[2].append((y1 + y2) / 2)
    median = _consensus(*vert, span=w, min_lines=TILT_MIN_LINES, min_consensus=TILT_MIN_CONSENSUS, max_split=90.0)
    if median is None and len(vert[0]) < TILT_MIN_LINES:
        median = _consensus(*horiz, span=h, min_lines=TILT_H_MIN_LINES, min_consensus=TILT_H_MIN_CONSENSUS, max_split=3.0)
        if median is not None and abs(median) < TILT_H_MIN_DEG:
            median = None
    if median is None or abs(median) < TILT_MIN_DEG:
        # Nothing usable from Hough: second opinion from the longest segments (LSD),
        # which also sees rolls beyond the windows above. A value past the rotation
        # limit is returned as measured: the callers turn it into "tilt, reshoot"
        # instead of a half correction.
        roll = estimate_strong_roll(img)
        if roll is None:
            return 0.0
        median = roll
    limit = settings.max_rotate_deg
    if abs(median) > limit + TILT_BEYOND_MARGIN:
        return float(median)
    return float(np.clip(median, -limit, limit))


def estimate_strong_roll(img: np.ndarray) -> float | None:
    """Roll read off the longest line segments (LSD follows low-contrast wall corners
    and ceiling lines that Canny + Hough miss). The longest few segments of a room are
    architectural; when, outliers dropped, they all lean the same way by 3 deg or more
    and agree with each other, the photo is rolled, not keystoned. Bench on the 24
    dataset photos: no false positive above 3 deg (img_006 splits -25/-5 and fails the
    spread test; img_025 stops at 2.9); img_024 -10, a 23-deg phone shot -23.5."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    detected = cv2.createLineSegmentDetector(cv2.LSD_REFINE_STD).detect(gray)[0]
    if detected is None:
        return None
    h, w = gray.shape
    margin = 0.015 * max(h, w)
    devs = []
    for x1, y1, x2, y2 in detected[:, 0]:
        # A screenshot or a framed photo carries its own edges: perfectly axis-aligned
        # segments hugging the border are the frame, not the room.
        on_border = min(x1, x2) < margin or max(x1, x2) > w - margin or min(y1, y2) < margin or max(y1, y2) > h - margin
        if on_border and abs(x2 - x1) < 2 or on_border and abs(y2 - y1) < 2:
            continue
        angle = math.degrees(math.atan2(y2 - y1, x2 - x1))
        if angle < 0:
            angle += 180
        dev_v = angle - 90
        dev_h = angle if angle <= 90 else angle - 180
        dev = dev_v if abs(dev_v) <= 30 else (dev_h if abs(dev_h) <= 30 else None)
        if dev is not None:
            devs.append((math.hypot(x2 - x1, y2 - y1), dev))
    if len(devs) < TILT_LSD_TOP:
        return None
    devs.sort(key=lambda t: -t[0])
    top = np.array([d for _, d in devs[:TILT_LSD_TOP]])
    median = float(np.median(top))
    kept = np.sort(np.abs(top - median).argsort()[: TILT_LSD_TOP - 2])  # drop the two outliers
    core = top[kept]
    if (core.max() - core.min()) > TILT_LSD_SPREAD or np.any(core * median <= 0):
        return None
    median = float(np.median(core))
    return median if abs(median) >= TILT_LSD_MIN_DEG else None


def _weighted_median(values: np.ndarray, weights: np.ndarray) -> float:
    order = np.argsort(values)
    cum = np.cumsum(weights[order])
    return float(values[order][np.searchsorted(cum, cum[-1] / 2)])


def turn(img: np.ndarray, orientation: int) -> np.ndarray:
    """Lossless quarter turn, `orientation` degrees clockwise. No crop, no resampling:
    the fix for a photo that arrived on its side or upside down."""
    codes = {90: cv2.ROTATE_90_CLOCKWISE, 180: cv2.ROTATE_180, 270: cv2.ROTATE_90_COUNTERCLOCKWISE}
    code = codes.get(int(orientation) % 360)
    return img if code is None else cv2.rotate(img, code)


def rotate_and_crop(img: np.ndarray, deg: float) -> np.ndarray:
    """Rotate about the centre, then crop to the largest axis-aligned rectangle
    with no black borders. Deterministic, so it can be replayed on the original
    to build an aligned reference for the fidelity metrics."""
    if abs(deg) < 0.05:
        return img
    h, w = img.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2, h / 2), deg, 1.0)
    rotated = cv2.warpAffine(img, m, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    cw, ch = _max_inscribed_rect(w, h, math.radians(deg))
    x0, y0 = int((w - cw) / 2), int((h - ch) / 2)
    return rotated[y0 : y0 + int(ch), x0 : x0 + int(cw)]


def _max_inscribed_rect(w: float, h: float, angle: float) -> tuple[float, float]:
    """Largest axis-aligned rectangle inside a w x h rectangle rotated by `angle`."""
    if w <= 0 or h <= 0:
        return 0, 0
    width_is_longer = w >= h
    side_long, side_short = (w, h) if width_is_longer else (h, w)
    sin_a, cos_a = abs(math.sin(angle)), abs(math.cos(angle))
    if side_short <= 2.0 * sin_a * cos_a * side_long or abs(sin_a - cos_a) < 1e-10:
        x = 0.5 * side_short
        wr, hr = (x / sin_a, x / cos_a) if width_is_longer else (x / cos_a, x / sin_a)
    else:
        cos_2a = cos_a * cos_a - sin_a * sin_a
        wr, hr = (w * cos_a - h * sin_a) / cos_2a, (h * cos_a - w * sin_a) / cos_2a
    return wr, hr


# ----------------------------------------------------------------------- driver


def apply(img: np.ndarray, params: EnhanceParams) -> tuple[np.ndarray, EnhanceParams]:
    """Run the pipeline. Returns the output and the *resolved* params (auto
    straightening replaced by the concrete angle) so the run is reproducible.

    A `keep_original` verdict is honoured here and nowhere else: the decision is
    the model's, the enforcement is deterministic."""
    resolved = params.model_copy()
    if resolved.recommendation == "keep_original":
        return img, EnhanceParams(recommendation="keep_original")
    if resolved.recommendation == "mild":
        resolved = conservative(resolved)
        resolved.recommendation = "mild"
    if resolved.auto_straighten:
        resolved.rotate_deg = estimate_tilt(img)
        resolved.auto_straighten = False
    # Denoise comes AFTER the tone curve on purpose: in a dark photo the sensor
    # noise is compressed into a few levels, so denoising first removes almost
    # nothing and the gamma then amplifies what is left. v2 had it the other way
    # round, which is why brightened evening shots came out grainy.
    out = turn(img, resolved.orientation)
    out = apply_white_balance(out, resolved.white_balance)
    out = apply_gamma(out, resolved.gamma)
    out = apply_clahe(out, resolved.clahe_clip)
    out = apply_denoise(out, resolved.denoise)
    out = rotate_and_crop(out, resolved.rotate_deg)
    out = apply_sharpen(out, resolved.sharpen)
    return out, resolved


def aligned_reference(original: np.ndarray, params: EnhanceParams) -> np.ndarray:
    """The original, geometrically transformed like the output. Straightening
    is allowed by policy, so the fidelity gate compares against this, not the raw input."""
    return rotate_and_crop(turn(original, params.orientation), params.rotate_deg)


# -------------------------------------------------------------------- analysis


def analyze(img: np.ndarray) -> ImageStats:
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    L, a, b = lab[..., 0], lab[..., 1].astype(np.float32) - 128, lab[..., 2].astype(np.float32) - 128
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # noise: residual after a median filter, measured where the image is flat
    residual = cv2.absdiff(gray, cv2.medianBlur(gray, 5)).astype(np.float32)
    flat = cv2.Laplacian(gray, cv2.CV_32F).__abs__() < 8
    noise = float(residual[flat].mean()) if flat.any() else 0.0
    target_gamma = gamma_for_target(float(L.mean()))
    return ImageStats(
        noise_after_brightening=round(noise * max(target_gamma * max(min(float(L.mean()) / 255.0, 0.12), 0.02) ** (target_gamma - 1), 1.0), 3),
        width=int(img.shape[1]),
        height=int(img.shape[0]),
        mean_luminance=round(float(L.mean()), 2),
        contrast_std=round(float(L.std()), 2),
        color_cast=(round(float(a.mean()), 2), round(float(b.mean()), 2)),
        noise_estimate=round(noise, 3),
        tilt_deg=round(estimate_tilt(img), 2),
    )


def gamma_for_target(mean_luminance: float, target: float = 125.0, max_gain: float = 2.2) -> float:
    """Gamma that maps the current mean to the target, capped so a very dark
    photo is lifted but not forced to daylight in one step."""
    m = min(max(mean_luminance, 1.0), 254.0) / 255.0
    g = math.log(target / 255.0) / math.log(m)
    lo, hi = EnhanceParams.BOUNDS["gamma"]
    g = min(max(g, lo), hi)
    # Darkening has a ceiling of its own: what is clipped stays white whatever the
    # curve, so past 1.5 the photo only gains contrast (measured on a flash-lit kitchen).
    if g > 1.0:
        g = min(g, 1.5)
    # cap the gain at the mean: slope of x^g at m is g * m^(g-1)
    while g < 1.0 and g * m ** (g - 1) > max_gain:
        g += 0.02
    return round(g, 2)


def predicted_noise(stats: ImageStats, gamma: float, shadow_level: float = 0.12) -> float:
    """Noise after brightening. Measured at a shadow level, not at the mean:
    grain shows up in the dark areas, where the gamma curve is steepest."""
    level = min(max(min(stats.mean_luminance / 255.0, shadow_level), 0.02), 0.99)
    gain = gamma * level ** (gamma - 1)
    return stats.noise_estimate * max(gain, 1.0)


# Diagnosis vocabulary, shared by the heuristic diagnoser, the vision prompt and
# dataset/raw/labels.csv (which uses `tungsten_cast` for `color_cast`; aggregate.py maps it).
DEFECTS = ("underexposed", "overexposed", "backlit", "color_cast", "noise", "tilt", "rotated", "compressed", "low_resolution")


def heuristic_defects(stats: ImageStats, params: EnhanceParams) -> list[str]:
    """The deterministic diagnoser (D1): names what the heuristics decided to correct,
    in the same vocabulary the vision diagnosers use, so all of them can be scored
    against the hand labels. `backlit` is deliberately absent: the numbers cannot
    tell a bright window from a well-lit room, only a model that sees the photo can."""
    found = []
    if params.gamma < 0.9:
        found.append("underexposed")
    if params.gamma > 1.1:
        found.append("overexposed")
    if params.white_balance > 0:
        found.append("color_cast")
    if params.denoise > 0 and stats.noise_estimate >= 2.0:
        found.append("noise")
    if abs(params.rotate_deg) >= TILT_MIN_DEG or abs(stats.tilt_deg) > settings.max_rotate_deg:
        found.append("tilt")
    for w in stats.input_warnings:
        if w.startswith("heavy_compression"):
            found.append("compressed")
        if w.startswith("low_resolution"):
            found.append("low_resolution")
    return found


def auto_params(img: np.ndarray, stats: ImageStats | None = None) -> EnhanceParams:
    """Flow A: fixed heuristics, no model in the loop. Deliberately simple —
    it is the baseline the agentic flow has to beat.

    v2 (after the first real phone photos): exposure aims at a target mean
    instead of fixed steps, and denoise is sized on the noise *after* the gain,
    because the synthetic dataset had no shadow noise and v1 never denoised."""
    s = stats or analyze(img)
    gamma = 1.0
    if s.mean_luminance < 118 or s.mean_luminance > 200:
        gamma = gamma_for_target(s.mean_luminance)
    clahe = 2.0 if s.contrast_std < 45 else 1.0
    cast = math.hypot(*s.color_cast)
    # gray-world overshoots on scenes with a dominant colour (wood, plants): cap it
    wb = 0.0 if cast < 4 else min(0.7, (cast - 4) / 12)
    noise_after = predicted_noise(s, gamma)
    denoise = 0 if noise_after < 2.0 else min(15, int(round(noise_after * 1.5)))
    # A compressed or tiny input: brightening reveals the JPEG 8x8 blocks and CLAHE
    # amplifies them. Capping gamma (v4) kept the photo dark, which is not a
    # correction. Measured on a WhatsApp photo (0.10 B/px): wall blockiness 7.3
    # with denoise 0, 2.0 with denoise 4, gate still 0.98. So: keep the exposure
    # fix, tame local contrast, and always deblock. Real-ESRGAN as a pre-step
    # reached the same blockiness at 1000x the cost and invented texture
    # (experiments/flow-d.json).
    compressed = any(w.startswith(("heavy_compression", "low_resolution")) for w in s.input_warnings)
    if compressed:
        # CLAHE off, not merely capped: on a flat wall it amplifies the 16-32 px
        # quantisation blotches (measured: mottling 1.28 with 0, 1.93 with clip 1).
        clahe = 0.0
        denoise = max(denoise, 4)
    # Denoise and small inputs both read as soft: a light unsharp mask gives the
    # crispness back without inventing anything. Kept low on compressed input,
    # where it would redraw the block edges.
    sharpen = 0.0 if denoise == 0 and not s.input_warnings else (0.2 if compressed else 0.5)
    return EnhanceParams(
        sharpen=sharpen,
        gamma=gamma,
        clahe_clip=clahe,
        white_balance=round(wb, 2),
        denoise=denoise,
        # a roll beyond the limit is reported, not half-corrected (see estimate_strong_roll)
        rotate_deg=s.tilt_deg if abs(s.tilt_deg) <= settings.max_rotate_deg else 0.0,
    )


def conservative(params: EnhanceParams) -> EnhanceParams:
    """Halfway back to neutral on every axis. Used by the self-check loop of
    flow B when the fidelity gate fails."""
    neutral = EnhanceParams()
    return EnhanceParams(
        gamma=(params.gamma + neutral.gamma) / 2,
        clahe_clip=params.clahe_clip / 2,
        white_balance=params.white_balance / 2,
        denoise=params.denoise // 2,
        rotate_deg=params.rotate_deg / 2,
        sharpen=params.sharpen / 2,
        orientation=params.orientation,  # a quarter turn is right or wrong, never "milder"
    )
