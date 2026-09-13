"""Calibrate the fidelity gate on the real dataset. Results in docs/gate-calibration.md.

'Allowed' = every flow-A output (faithful by construction) plus the allowed
synthetic ops. 'Forbidden' = policy violations applied to the same raw photos:
object removed by inpainting, window replaced, crack repaired, generative smear.
Prints per-metric separation so thresholds are chosen from data, not guessed.

Usage (from cv-service, venv active):  python ../experiments/scripts/calibrate_gate.py
"""
import csv, sys
from pathlib import Path
import cv2, numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "cv-service"))
from app.core import pipeline, metrics
from app.core.image_io import resize_max
from app.schemas import EnhanceParams

ROOT = Path(__file__).resolve().parents[2]
rows = list(csv.DictReader(open(ROOT / "dataset/raw/labels.csv", encoding="utf-8")))
rng = np.random.default_rng(0)

def forbidden_variants(img):
    h, w = img.shape[:2]
    out = {}
    # object removed: inpaint a 10% area box in the lower-middle (furniture zone)
    m = np.zeros((h, w), np.uint8); bw, bh = int(w*0.32), int(h*0.32)
    x0, y0 = int(w*0.34), int(h*0.5); m[y0:y0+bh, x0:x0+bw] = 255
    out["object_removed"] = cv2.inpaint(img, m, 5, cv2.INPAINT_TELEA)
    # window replaced: brightest 8% region -> flat sky gradient
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY); thr = np.percentile(gray, 92)
    mask = cv2.dilate((gray >= thr).astype(np.uint8), np.ones((15,15),np.uint8))[..., None].astype(bool)
    sky = np.zeros_like(img); sky[..., 0] = np.linspace(230, 180, h)[:, None]; sky[..., 1] = 190; sky[..., 2] = 140
    out["window_replaced"] = np.where(mask, sky, img).astype(np.uint8)
    # crack repaired: the 'original' has a crack, the candidate does not
    cracked = img.copy(); pts = np.cumsum(rng.integers(-6, 7, (40, 2)), axis=0) + [int(w*0.6), int(h*0.15)]
    cv2.polylines(cracked, [pts.astype(np.int32)], False, (25, 25, 30), 3)
    out["crack_repaired"] = ("cracked_original", cracked)
    # generative smear: strong bilateral + slight warp
    out["generative_smear"] = cv2.stylization(img, sigma_s=60, sigma_r=0.45)
    return out

def report(name, original, candidate):
    f = metrics.fidelity(original, candidate)
    return dict(name=name, score=f.score, structure=f.structure, local_min=f.structure_local_min, hue=f.hue_corr, passed=f.passed)


def main():
    allowed, forbidden = [], []
    for r in rows:
        img = resize_max(cv2.imread(str(ROOT / "dataset/raw" / r["filename"])))
        out, res = pipeline.apply(img, pipeline.auto_params(img))
        allowed.append(report(f"A {r['image_id']}", pipeline.aligned_reference(img, res), out))
        strong, res2 = pipeline.apply(img, EnhanceParams(gamma=0.6, clahe_clip=3.0, white_balance=1.0, denoise=8))
        allowed.append(report(f"strong {r['image_id']}", pipeline.aligned_reference(img, res2), strong))
        for k, v in forbidden_variants(img).items():
            if isinstance(v, tuple): forbidden.append(report(f"{k} {r['image_id']}", v[1], img))
            else: forbidden.append(report(f"{k} {r['image_id']}", img, v))

    def dist(rs, key): 
        v = np.array([x[key] for x in rs]); return f"min {v.min():.3f} p10 {np.percentile(v,10):.3f} med {np.median(v):.3f} p90 {np.percentile(v,90):.3f} max {v.max():.3f}"
    for key in ("score", "structure", "local_min", "hue"):
        print(f"{key:6s} allowed   {dist(allowed, key)}")
        print(f"{'':6s} forbidden {dist(forbidden, key)}")
        for kind in ("object_removed", "window_replaced", "crack_repaired", "generative_smear"):
            print(f"{'':6s}   {kind:17s} {dist([x for x in forbidden if x['name'].startswith(kind)], key)}")
    print(f"\ngate: allowed pass {sum(x['passed'] for x in allowed)}/{len(allowed)} | forbidden pass {sum(x['passed'] for x in forbidden)}/{len(forbidden)}")


if __name__ == "__main__":
    main()
