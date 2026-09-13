"""Base64 <-> ndarray helpers. JSON+base64 is the lowest-friction transport for n8n."""

import base64

import cv2
import numpy as np

from app.config import settings


def decode_b64(data: str) -> np.ndarray:
    """Accepts raw base64 or a data URL. Returns a BGR image."""
    if "," in data[:64] and data.startswith("data:"):
        data = data.split(",", 1)[1]
    buf = np.frombuffer(base64.b64decode(data), dtype=np.uint8)
    img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("payload is not a decodable image")
    return img


def encode_b64(img: np.ndarray, quality: int | None = None) -> str:
    q = settings.jpeg_quality if quality is None else quality
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, q])
    if not ok:
        raise ValueError("could not encode image")
    return base64.b64encode(buf.tobytes()).decode("ascii")


def resize_max(img: np.ndarray, max_side: int | None = None) -> np.ndarray:
    """Downscale so the long side is <= max_side. Never upscales."""
    limit = settings.max_side if max_side is None else max_side
    h, w = img.shape[:2]
    scale = limit / max(h, w)
    if scale >= 1.0:
        return img
    return cv2.resize(img, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA)


def match_size(reference: np.ndarray, other: np.ndarray) -> np.ndarray:
    """Resize `other` to the shape of `reference` (generative outputs may differ by a few px)."""
    if reference.shape[:2] == other.shape[:2]:
        return other
    h, w = reference.shape[:2]
    return cv2.resize(other, (w, h), interpolation=cv2.INTER_AREA)
