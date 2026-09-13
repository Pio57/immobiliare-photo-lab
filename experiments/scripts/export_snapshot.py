"""Freeze the experiment for the published site.

The Studio and Esperimento views normally read from cv-service through n8n. Neither is
guaranteed to be up when a reviewer opens the link (the n8n trial ends, the laptop is
off), so this script writes a static copy under frontend/public/snapshot/ that the site
falls back to: the tally, the study list, one JSON per photo with the three versions, and
the images downsized for the web. Re-run after every batch or study session.

Usage (from repo root, cv-service on :8000):
  cv-service\\.venv\\Scripts\\python.exe experiments\\scripts\\export_snapshot.py
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import cv2
import httpx

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "frontend" / "public" / "snapshot"
CV = "http://localhost:8000"
MAX_SIDE = 1280
QUALITY = 84


def shrink(src: Path, dst: Path) -> None:
    img = cv2.imread(str(src))
    h, w = img.shape[:2]
    s = MAX_SIDE / max(h, w)
    if s < 1:
        img = cv2.resize(img, (round(w * s), round(h * s)), interpolation=cv2.INTER_AREA)
    dst.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(dst), img, [cv2.IMWRITE_JPEG_QUALITY, QUALITY])


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "cards").mkdir(parents=True)
    with httpx.Client(timeout=120) as http:
        summary = http.get(f"{CV}/summary").json()
        study = http.get(f"{CV}/study").json()
        (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False), encoding="utf-8")
        (OUT / "study.json").write_text(json.dumps(study, ensure_ascii=False), encoding="utf-8")
        processed = ROOT / "dataset" / "processed"
        for image_id in study["ready"]:
            cards = http.get(f"{CV}/runs/{image_id}/cards").json()
            # images go to files; the JSON keeps relative URLs instead of base64
            orig = processed / f"{image_id}_orig.jpg"
            if not orig.exists():
                raw = next((ROOT / "dataset" / "raw").glob(f"{image_id}.*"))
                shrink(raw, OUT / "img" / f"{image_id}_orig.jpg")
            else:
                shrink(orig, OUT / "img" / f"{image_id}_orig.jpg")
            cards["original"] = f"snapshot/img/{image_id}_orig.jpg"
            for c in cards["cards"]:
                src = processed / f"{image_id}_{c['variant']}.jpg"
                if c.get("output") and src.exists():
                    shrink(src, OUT / "img" / f"{image_id}_{c['variant']}.jpg")
                    c["output"] = f"snapshot/img/{image_id}_{c['variant']}.jpg"
                else:
                    c["output"] = None
            (OUT / "cards" / f"{image_id}.json").write_text(json.dumps(cards, ensure_ascii=False), encoding="utf-8")
    size = sum(p.stat().st_size for p in OUT.rglob("*") if p.is_file()) / 1e6
    print(f"-> {OUT.relative_to(ROOT)}: {len(study['ready'])} photos, {size:.1f} MB")


if __name__ == "__main__":
    main()
