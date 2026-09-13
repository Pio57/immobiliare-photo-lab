"""HTTP surface. Thin: decode, call core, encode. No business logic here."""

import base64
import time
from pathlib import Path

import cv2
import httpx
import numpy as np
from fastapi import APIRouter, HTTPException

from app.api.dataset import raw_image_path
from app.config import settings

from app.core import pipeline
from app.core.image_io import decode_b64, encode_b64, resize_max
from app.core.metrics import fidelity
from app.schemas import (
    ApplyRequest,
    EnhanceParams,
    EnhanceResponse,
    FidelityReport,
    FidelityRequest,
    ImageRequest,
    GateResponse,
    ImageStats,
    PrepareResponse,
)

router = APIRouter()


def _load(b64: str, max_side: int | None = None):
    """Decode, drop letterbox bars, bound the size. Also remembers the encoded
    size on the array so input warnings can reason about compression."""
    try:
        raw = decode_b64(b64)
        trimmed = pipeline.trim_uniform_borders(raw)
        img = resize_max(trimmed, max_side)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    # Both keys are always written: an id can be reused after the previous array
    # is freed, and a stale entry would attach the wrong warning to a new photo.
    _encoded_bytes[id(img)] = len(b64) * 3 // 4
    _trimmed[id(img)] = (f"letterbox_trimmed:{raw.shape[1]}x{raw.shape[0]}->{trimmed.shape[1]}x{trimmed.shape[0]}"
                         if trimmed.shape[:2] != raw.shape[:2] else None)
    for table in (_encoded_bytes, _trimmed):
        while len(table) > 64:
            del table[next(iter(table))]
    return img


_encoded_bytes: dict[int, int] = {}
_trimmed: dict[int, str | None] = {}


def _stats(img) -> ImageStats:
    # /enhance measures once for the heuristics and once for the response: the
    # second call must see the same warnings, so the side tables are read, not popped.
    stats = pipeline.analyze(img)
    stats.input_warnings = pipeline.input_warnings(img, _encoded_bytes.get(id(img)))
    if _trimmed.get(id(img)):
        stats.input_warnings.append(_trimmed[id(img)])
    if abs(stats.tilt_deg) > settings.max_rotate_deg:  # rolled beyond what a rotation can fix: reshoot
        stats.input_warnings.append(f"tilt_beyond_range:{stats.tilt_deg:+.1f}deg")
    return stats


def _load_request(req: ImageRequest):
    if req.image_b64:
        return _load(req.image_b64, req.max_side)
    if req.image_id:
        return _load(base64.b64encode(raw_image_path(req.image_id).read_bytes()).decode("ascii"), req.max_side)
    raise HTTPException(status_code=422, detail="image_b64 or image_id required")


def _run(img, params: EnhanceParams, started: float, req: ImageRequest) -> EnhanceResponse:
    stats = _stats(img)
    out, resolved = pipeline.apply(img, params)
    report = fidelity(pipeline.aligned_reference(img, resolved), out)
    output_path = None
    if req.save_as:
        dest = Path(settings.repo_root) / "dataset" / "processed" / f"{req.save_as}.jpg"
        dest.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(dest), out, [cv2.IMWRITE_JPEG_QUALITY, settings.jpeg_quality])
        output_path = f"dataset/processed/{req.save_as}.jpg"
    # Straightening costs pixels: the largest border-free rectangle inside the
    # rotated frame. 10 deg on a 3:4 photo drops ~27% of the area. Reported, never hidden.
    crop_pct = round(100.0 * (1 - (out.shape[0] * out.shape[1]) / (img.shape[0] * img.shape[1])), 1)
    return EnhanceResponse(
        image_b64=encode_b64(out) if req.return_image else None,
        output_path=output_path,
        params=resolved,
        fidelity=report,
        crop_pct=max(crop_pct, 0.0),
        stats=stats,
        latency_ms=int((time.perf_counter() - started) * 1000),
        suggested_conservative_params=None if report.passed else pipeline.conservative(resolved),
    )


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.post("/analyze", response_model=ImageStats)
def analyze(req: ImageRequest) -> ImageStats:
    """Measured facts about the image. Flow B passes these to the vision model as hints."""
    return _stats(_load_request(req))


@router.post("/prepare", response_model=PrepareResponse)
def prepare(req: ImageRequest) -> PrepareResponse:
    """Resize once (phone photos are 4000px+), measure, and hand back a base64 the
    orchestrator can forward to the vision model and to /enhance and /apply."""
    img = _load_request(req)
    stats = _stats(img)
    params = pipeline.auto_params(img, stats)
    image_id = req.image_id or f"live_{int(time.time() * 1000)}"
    if req.save_as:  # the product keeps the prepared original next to the outputs, for the async result
        dest = Path(settings.repo_root) / "dataset" / "processed" / f"{req.save_as}.jpg"
        dest.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(dest), img, [cv2.IMWRITE_JPEG_QUALITY, settings.jpeg_quality])
    return PrepareResponse(image_id=image_id, image_b64=encode_b64(img), stats=stats,
                           heuristic_params=params, heuristic_defects=pipeline.heuristic_defects(stats, params))


@router.post("/turns")
def turns(req: ImageRequest) -> dict:
    """The photo turned four ways (0, 90, 180, 270 clockwise), as small thumbnails, for
    the orientation question of flow D2: a model that cannot say by how much a photo is
    rotated picks the upright one out of four without fail."""
    img = _load_request(ImageRequest(image_b64=req.image_b64, image_id=req.image_id, max_side=req.max_side or 512))
    return {"turns": [{"deg": deg, "image_b64": encode_b64(pipeline.turn(img, deg))} for deg in (0, 90, 180, 270)]}


@router.post("/enhance", response_model=EnhanceResponse)
def enhance(req: ImageRequest) -> EnhanceResponse:
    """Flow A: heuristic parameters, deterministic pipeline, fidelity gate."""
    started = time.perf_counter()
    img = _load_request(req)
    return _run(img, pipeline.auto_params(img, _stats(img)), started, req)


@router.post("/apply", response_model=EnhanceResponse)
def apply(req: ApplyRequest) -> EnhanceResponse:
    """Flow B: parameters chosen by the vision model, same pipeline, same gate."""
    started = time.perf_counter()
    return _run(_load_request(req), req.params, started, req)


@router.post("/gate_remote", response_model=GateResponse)
def gate_remote(req: FidelityRequest) -> GateResponse:
    """Flow C/C2 in the live product: download the model's output, gate it, and
    return both the image and the verdict."""
    started = time.perf_counter()
    if not req.candidate_url:
        raise HTTPException(status_code=422, detail="candidate_url required")
    original = _load_request(ImageRequest(image_b64=req.original_b64, image_id=req.image_id))
    try:
        res = httpx.get(req.candidate_url, timeout=90, follow_redirects=True)
        res.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"could not fetch candidate: {exc}") from exc
    candidate = _load(base64.b64encode(res.content).decode("ascii"))
    if req.save_as:
        dest = Path(settings.repo_root) / "dataset" / "processed" / f"{req.save_as}.jpg"
        dest.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(dest), candidate, [cv2.IMWRITE_JPEG_QUALITY, settings.jpeg_quality])
    return GateResponse(
        image_b64=encode_b64(candidate),
        fidelity=fidelity(original, candidate),
        latency_ms=int((time.perf_counter() - started) * 1000),
        image_id=req.image_id,
        measured_changes=_measured_changes(original, candidate),
    )


def _sharpness(img) -> float:
    return float(cv2.Laplacian(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), cv2.CV_32F).var())


def _measured_changes(original, candidate) -> dict[str, float]:
    """Deltas between two photos, in the units the modules use, so a generative
    output can be described in the same rows as a modular one."""
    a, b = pipeline.analyze(original), pipeline.analyze(candidate)
    return {
        "luminance_delta": round(b.mean_luminance - a.mean_luminance, 1),
        "contrast_delta": round(b.contrast_std - a.contrast_std, 1),
        "cast_before": round(float(np.hypot(*a.color_cast)), 1),
        "cast_after": round(float(np.hypot(*b.color_cast)), 1),
        "noise_before": round(a.noise_estimate, 2),
        "noise_after": round(b.noise_estimate, 2),
        "sharpness_ratio": round(_sharpness(candidate) / max(_sharpness(original), 1e-6), 2),
        "tilt_before": a.tilt_deg,
        "tilt_after": b.tilt_deg,
        "scale": round(max(candidate.shape[:2]) / max(original.shape[:2]), 2),
    }


@router.post("/fidelity", response_model=FidelityReport)
def fidelity_endpoint(req: FidelityRequest) -> FidelityReport:
    """Standalone gate for outputs produced elsewhere (flow C)."""
    original = _load_request(ImageRequest(image_b64=req.original_b64, image_id=req.image_id))
    if req.candidate_b64:
        candidate_b64 = req.candidate_b64
    elif req.candidate_url:
        try:
            res = httpx.get(req.candidate_url, timeout=60, follow_redirects=True)
            res.raise_for_status()
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"could not fetch candidate: {exc}") from exc
        candidate_b64 = base64.b64encode(res.content).decode("ascii")
    else:
        raise HTTPException(status_code=422, detail="candidate_b64 or candidate_url required")
    candidate = _load(candidate_b64)
    if req.save_as:
        dest = Path(settings.repo_root) / "dataset" / "processed" / f"{req.save_as}.jpg"
        dest.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(dest), candidate, [cv2.IMWRITE_JPEG_QUALITY, settings.jpeg_quality])
    return fidelity(original, candidate)
