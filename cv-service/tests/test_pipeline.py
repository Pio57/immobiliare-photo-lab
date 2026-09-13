import cv2
import numpy as np

from app.core import pipeline
from app.schemas import EnhanceParams


def _rotate(img, deg):
    h, w = img.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2, h / 2), deg, 1.0)
    return cv2.warpAffine(img, m, (w, h), borderMode=cv2.BORDER_REPLICATE)


def test_params_are_clamped_not_rejected():
    p = EnhanceParams(gamma=9.0, clahe_clip=-1, white_balance=3, denoise=99, rotate_deg=45)
    assert (p.gamma, p.clahe_clip, p.white_balance, p.denoise, p.rotate_deg) == (2.0, 0.0, 1.0, 15, 10.0)


def test_tilt_estimate_has_the_right_sign(room):
    tilted = _rotate(room, 3.0)  # verticals now lean; a -3 rotation would fix them
    est = pipeline.estimate_tilt(tilted)
    assert abs(est + 3.0) < 0.75, est


def test_auto_straighten_resolves_to_concrete_angle(room):
    out, resolved = pipeline.apply(_rotate(room, 3.0), EnhanceParams(auto_straighten=True))
    assert resolved.auto_straighten is False
    assert abs(resolved.rotate_deg + 3.0) < 0.75
    assert out.shape[0] < room.shape[0]  # cropped borders


def test_aligned_reference_matches_output_geometry(room):
    params = EnhanceParams(gamma=0.7, rotate_deg=4.0)
    out, resolved = pipeline.apply(room, params)
    ref = pipeline.aligned_reference(room, resolved)
    assert ref.shape == out.shape


def test_auto_params_brighten_dark_images(dark_room, room):
    assert pipeline.auto_params(dark_room).gamma < 1.0
    assert pipeline.auto_params(room).gamma >= 0.9


def test_conservative_moves_halfway_to_neutral():
    p = EnhanceParams(gamma=0.6, clahe_clip=4, white_balance=1, denoise=10, rotate_deg=-8)
    c = pipeline.conservative(p)
    assert (c.gamma, c.clahe_clip, c.white_balance, c.denoise, c.rotate_deg) == (0.8, 2.0, 0.5, 5, -4.0)


def test_neutral_params_are_a_noop(room):
    out, _ = pipeline.apply(room, EnhanceParams())
    assert np.array_equal(out, room)


def test_letterbox_bars_are_trimmed(room):
    framed = np.full((room.shape[0] + 160, room.shape[1], 3), 90, np.uint8)
    framed[80:-80] = room
    assert pipeline.trim_uniform_borders(framed).shape == room.shape
    assert pipeline.trim_uniform_borders(room).shape == room.shape


def test_input_warnings_flag_small_and_compressed_images(room):
    small = cv2.resize(room, (540, 960))
    assert any(w.startswith("low_resolution") for w in pipeline.input_warnings(small, 30_000))
    assert any(w.startswith("heavy_compression") for w in pipeline.input_warnings(small, 30_000))
    assert pipeline.input_warnings(cv2.resize(room, (1600, 1200)), 600_000) == []
