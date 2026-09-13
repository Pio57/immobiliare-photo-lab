import cv2
import numpy as np
import pytest


@pytest.fixture
def room() -> np.ndarray:
    """Synthetic 'room': textured walls, a window, strong vertical/horizontal
    edges and a couple of coloured areas. Enough structure for every metric."""
    rng = np.random.default_rng(0)
    img = np.full((480, 640, 3), 150, np.uint8)
    img = (img.astype(np.int16) + rng.integers(-12, 12, img.shape)).clip(0, 255).astype(np.uint8)
    cv2.rectangle(img, (0, 300), (640, 480), (90, 70, 60), -1)  # floor (brownish)
    cv2.rectangle(img, (380, 60), (560, 260), (200, 170, 90), -1)  # window (sky-ish blue in BGR)
    cv2.rectangle(img, (60, 180), (220, 300), (40, 60, 180), -1)  # red sofa
    rug = rng.integers(0, 2, (20, 40), dtype=np.uint8) * 255  # textured rug, 6px checks
    rug = cv2.resize(rug, (240, 120), interpolation=cv2.INTER_NEAREST)
    img[340:460, 200:440] = (np.stack([rug] * 3, -1) * 0.3 + np.array([70, 90, 120])).astype(np.uint8)
    for x in range(0, 640, 80):
        cv2.line(img, (x, 0), (x, 300), (60, 60, 60), 2)  # vertical structure
    cv2.line(img, (0, 300), (640, 300), (30, 30, 30), 3)
    return img


@pytest.fixture
def dark_room(room) -> np.ndarray:
    return (room.astype(np.float32) * 0.3).astype(np.uint8)
