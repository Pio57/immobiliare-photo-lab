"""Local filesystem bridge for the orchestrator.

n8n Cloud cannot read dataset/raw/ or write experiments/runs/ on this machine,
so the service that already runs here exposes both. Prototype-grade: no auth
beyond the obscurity of the ngrok URL. Tighten before any real deployment."""

import base64
import csv
import json
from pathlib import Path

import cv2
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from app.config import settings

router = APIRouter(prefix="/dataset", tags=["dataset"])
runs_router = APIRouter(prefix="/runs", tags=["runs"])
processed_router = APIRouter(prefix="/processed", tags=["dataset"])


def _root() -> Path:
    return Path(settings.repo_root).resolve()


def _labels() -> list[dict]:
    path = _root() / "dataset" / "raw" / "labels.csv"
    if not path.exists():
        raise HTTPException(404, "dataset/raw/labels.csv not found")
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


@router.get("")
def list_images(limit: int | None = None, skip_done: bool = False) -> dict:
    """Ids and labels only. `skip_done` makes an interrupted batch resumable:
    images that already have experiments/runs/<id>.json are left out."""
    rows = _labels()
    if skip_done:
        rows = [r for r in rows if not (_root() / "experiments" / "runs" / f"{r['image_id']}.json").exists()]
    return {"count": len(rows), "images": rows[:limit] if limit else rows}


def raw_image_path(image_id: str) -> Path:
    row = next((r for r in _labels() if r["image_id"] == image_id), None)
    if row is None:
        raise HTTPException(404, f"unknown image_id {image_id}")
    return _root() / "dataset" / "raw" / row["filename"]


@router.get("/{image_id}")
def get_image(image_id: str) -> dict:
    row = next(r for r in _labels() if r["image_id"] == image_id)
    data = raw_image_path(image_id).read_bytes()
    return {"image_id": image_id, "labels": row, "image_b64": base64.b64encode(data).decode("ascii")}


def _serve(path: Path, max_side: int | None) -> Response:
    """JPEG bytes, optionally downscaled. The judge sees images at thumbnail-like
    size (the product's real surface is the SERP thumbnail) and costs half the tokens."""
    if not max_side:
        return FileResponse(path, media_type="image/jpeg")
    img = cv2.imread(str(path))
    h, w = img.shape[:2]
    scale = max_side / max(h, w)
    if scale < 1:
        img = cv2.resize(img, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 88])
    return Response(content=buf.tobytes(), media_type="image/jpeg")


@router.get("/{image_id}/file")
def get_image_file(image_id: str, max_side: int | None = None) -> Response:
    """Raw JPEG, so vision models can be given a URL instead of a base64 payload."""
    return _serve(raw_image_path(image_id), max_side)


@processed_router.get("/{name}")
def get_processed(name: str, max_side: int | None = None) -> Response:
    path = _root() / "dataset" / "processed" / f"{Path(name).stem}.jpg"
    if not path.exists():
        raise HTTPException(404, f"no processed image {name}")
    return _serve(path, max_side)


class RunRecord(BaseModel):
    image_id: str
    variants: list[dict]
    judge: list[dict] = []
    source: str = "batch"  # 'live' when the record comes from an upload in the Prova view
    order: list[str] = []  # live: the blind order the versions are shown in
    input_warnings: list[str] = []
    heuristic_defects: list[str] = []
    latency_ms: int = 0


@runs_router.post("/{image_id}")
def save_run(image_id: str, record: RunRecord) -> dict:
    """One JSON per image in experiments/runs/. Output images arrive as base64 in
    variants[].image_b64 and are written to dataset/processed/ instead of the JSON."""
    processed = _root() / "dataset" / "processed"
    processed.mkdir(parents=True, exist_ok=True)
    payload = record.model_dump()
    for v in payload["variants"]:
        # pixels never live in the JSON: an inline image is written next to the others
        b64 = v.pop("image_b64", None) or v.pop("output_b64", None)
        v.pop("output_b64", None)
        out = processed / f"{image_id}_{v['variant']}.jpg"
        if b64 and not out.exists():
            out.write_bytes(base64.b64decode(b64))
        if out.exists():
            v["output_path"] = str(out.relative_to(_root())).replace("\\", "/")
    dest = _root() / "experiments" / "runs" / f"{image_id}.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"saved": str(dest.relative_to(_root())).replace("\\", "/"), "variants": [v["variant"] for v in payload["variants"]]}
