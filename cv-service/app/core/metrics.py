"""Fidelity metrics: did the enhancement change *what* is in the photo?

The gate must be independent from the model that produced the image, so
everything here is classical CV, deterministic, and explainable in one sentence.

Calibrated on the real dataset (experiments/scripts/calibrate_gate.py): flow-A
outputs and strong allowed edits on one side, policy violations applied to the
same photos on the other (object removed by inpainting, window replaced, crack
repaired, generative smear). What survived:

- Block-wise normalised cross-correlation (NCC) of the blurred luminance.
  NCC is invariant to local affine intensity changes, and gamma / CLAHE / white
  balance are locally ~affine, so allowed edits score ~1 while a region whose
  content changed drops towards 0. The *minimum* block is the local guardrail
  (allowed >= 0.78 on the dataset, violations <= 0.53).
- Hue histogram correlation after gray-world normalisation of both images, so a
  removed colour cast (allowed) does not count as a colour change.

What was dropped, and why: SSIM with luminance equalisation amplified sensor
noise into "structure"; Canny edge IoU counted texture edges revealed by
brightening as geometry changes. Both rejected flow A on real photos.
Known limit: a thin crack (a few px) is caught only ~half of the time at 32 px
blocks — declared in the README, not hidden.
"""

import cv2
import numpy as np

from app.config import settings
from app.core.image_io import match_size
from app.schemas import FidelityReport


def _luma(img: np.ndarray) -> np.ndarray:
    """Luminance blurred at 'noise scale': sensor grain must not count as structure."""
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)
    return cv2.GaussianBlur(g, (0, 0), settings.structure_sigma)


def block_ncc(a: np.ndarray, b: np.ndarray, block: int | None = None) -> np.ndarray:
    """Normalised cross-correlation per square block, regularised so that two
    flat blocks (nothing to compare) score 1 instead of being undefined."""
    bs = settings.ncc_block_px if block is None else block
    x, y = _luma(a), _luma(b)
    h, w = (x.shape[0] // bs) * bs, (x.shape[1] // bs) * bs
    if h == 0 or w == 0:
        return np.array([[1.0]])
    X = x[:h, :w].reshape(h // bs, bs, w // bs, bs)
    Y = y[:h, :w].reshape(h // bs, bs, w // bs, bs)
    mx, my = X.mean(axis=(1, 3), keepdims=True), Y.mean(axis=(1, 3), keepdims=True)
    sxy = ((X - mx) * (Y - my)).mean(axis=(1, 3))
    sx = np.sqrt(((X - mx) ** 2).mean(axis=(1, 3)))
    sy = np.sqrt(((Y - my) ** 2).mean(axis=(1, 3)))
    c = settings.ncc_regulariser
    return (sxy + c) / (sx * sy + c)


def structure(a: np.ndarray, b: np.ndarray) -> float:
    """Global structural agreement: 10th percentile of block NCC."""
    return float(np.percentile(block_ncc(a, b), 10))


def structure_local_min(a: np.ndarray, b: np.ndarray) -> float:
    """Worst block. Catches a removed object, a replaced window, a repainted wall."""
    return float(block_ncc(a, b).min())


def _gray_world(img: np.ndarray) -> np.ndarray:
    f = img.astype(np.float32)
    means = f.reshape(-1, 3).mean(axis=0)
    return np.clip(f * (means.mean() / np.maximum(means, 1e-6)), 0, 255).astype(np.uint8)


def hue_corr(a: np.ndarray, b: np.ndarray, bins: int = 36) -> float:
    """Hue histogram correlation on the same saturated-pixel set, after removing
    the global illuminant from both images. A white-balance fix therefore scores
    ~1; a replaced sky or repainted wall does not."""
    ha, hb = cv2.cvtColor(_gray_world(a), cv2.COLOR_BGR2HSV), cv2.cvtColor(_gray_world(b), cv2.COLOR_BGR2HSV)
    mask = (_colour_mask(ha) | _colour_mask(hb)).astype(np.uint8)
    if mask.sum() < 0.01 * mask.size:
        return 1.0  # not enough colour to judge
    hist_a = _smooth_circular(cv2.calcHist([ha], [0], mask, [bins], [0, 180]).flatten())
    hist_b = _smooth_circular(cv2.calcHist([hb], [0], mask, [bins], [0, 180]).flatten())
    return float(np.clip(np.corrcoef(hist_a, hist_b)[0, 1], 0.0, 1.0))


def _colour_mask(hsv: np.ndarray) -> np.ndarray:
    return (hsv[..., 1] > 40) & (hsv[..., 2] > 40)


def _smooth_circular(hist: np.ndarray, sigma_bins: float = 1.5) -> np.ndarray:
    """Hue is circular and a 2-degree shift must not flip a bin: blur the
    histogram with a wrap-around Gaussian before correlating."""
    n = hist.size
    k = np.exp(-0.5 * (np.arange(-3, 4) / sigma_bins) ** 2)
    k /= k.sum()
    return np.array([sum(k[j + 3] * hist[(i + j) % n] for j in range(-3, 4)) for i in range(n)])


def fidelity(original: np.ndarray, candidate: np.ndarray) -> FidelityReport:
    """Two blocking conditions: a weighted global score and a local floor.
    Weights and thresholds live in config; they were set from the dataset
    (flow A is faithful by construction and defines what must pass)."""
    candidate = match_size(original, candidate)
    blocks = block_ncc(original, candidate)
    s = float(np.percentile(blocks, 10))
    local_min = float(blocks.min())
    h = hue_corr(original, candidate)
    score = settings.fidelity_w_structure * s + settings.fidelity_w_hue * h
    return FidelityReport(
        structure=round(s, 4),
        structure_local_min=round(local_min, 4),
        hue_corr=round(h, 4),
        score=round(score, 4),
        threshold=settings.fidelity_threshold,
        local_floor=settings.fidelity_local_floor,
        passed=score >= settings.fidelity_threshold and local_min >= settings.fidelity_local_floor,
    )
