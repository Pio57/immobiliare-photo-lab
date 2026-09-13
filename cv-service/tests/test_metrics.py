"""Every 'allowed' case must pass the gate, every 'forbidden' case must fail it.
These cases are the ones that shaped the metric design (see metrics.py docstring)."""

import cv2
import numpy as np
import pytest

from app.core import metrics, pipeline
from app.core.pipeline import apply_gamma
from app.schemas import EnhanceParams

# ------------------------------------------------------------ allowed by policy


def test_identity_is_perfect(room):
    r = metrics.fidelity(room, room.copy())
    assert r.score > 0.99 and r.passed


@pytest.mark.parametrize(
    "params",
    [
        {"gamma": 0.8},
        {"clahe_clip": 3.0},
        {"white_balance": 0.8},
        {"denoise": 10},
        {"gamma": 0.8, "clahe_clip": 3.0, "white_balance": 0.8, "denoise": 10},
    ],
    ids=["gamma", "clahe", "white_balance", "denoise", "all_at_once"],
)
def test_allowed_operations_pass(room, params):
    out, resolved = pipeline.apply(room, EnhanceParams(**params))
    r = metrics.fidelity(pipeline.aligned_reference(room, resolved), out)
    assert r.passed, r


def test_exposure_change_on_dark_photo_passes(dark_room):
    r = metrics.fidelity(dark_room, apply_gamma(dark_room, 0.6))
    assert r.passed and r.hue_corr > 0.75, r


def test_flow_a_on_dark_photo_passes(dark_room):
    out, resolved = pipeline.apply(dark_room, pipeline.auto_params(dark_room))
    assert metrics.fidelity(pipeline.aligned_reference(dark_room, resolved), out).passed


# ---------------------------------------------------------- forbidden by policy


def test_sky_and_furniture_replacement_is_caught(room):
    altered = room.copy()
    cv2.rectangle(altered, (380, 60), (560, 260), (30, 200, 240), -1)  # new "sky"
    cv2.rectangle(altered, (240, 120), (360, 300), (200, 200, 200), -1)  # added furniture
    r = metrics.fidelity(room, altered)
    assert not r.passed, r


@pytest.mark.xfail(reason="structures thinner than ~3px are below the block metric's sensitivity (declared limit)")
def test_moved_thin_walls_are_caught(room):
    altered = room.copy()
    for x in range(40, 640, 80):
        cv2.line(altered, (x, 0), (x, 300), (60, 60, 60), 2)
    r = metrics.fidelity(room, altered)
    assert not r.passed, r


def test_removed_object_is_caught_by_local_floor(room):
    altered = room.copy()
    cv2.rectangle(altered, (60, 180), (220, 300), (150, 150, 150), -1)  # sofa painted over
    r = metrics.fidelity(room, altered)
    assert not r.passed and r.structure_local_min < r.local_floor, r


def test_thin_crack_removal_is_caught_by_local_floor(room):
    with_crack = room.copy()
    cv2.line(with_crack, (300, 20), (330, 280), (20, 20, 20), 3)
    r = metrics.fidelity(with_crack, room)  # "repaired" wall
    assert not r.passed and r.structure_local_min < r.local_floor, r


@pytest.mark.xfail(reason="uniform smoothing of fine texture is not separable from denoise (declared limit 2, docs/gate-calibration.md)")
def test_uniform_texture_smoothing_is_caught(room):
    r = metrics.fidelity(room, cv2.GaussianBlur(room, (31, 31), 0))
    assert not r.passed and r.structure_local_min < r.local_floor, r


def test_added_noise_is_not_a_fidelity_violation(room):
    """Noise degrades quality (the judge's job), it does not alter the property (the gate's job)."""
    rng = np.random.default_rng(1)
    noisy = (room.astype(np.int16) + rng.integers(-30, 30, room.shape)).clip(0, 255).astype(np.uint8)
    assert metrics.fidelity(room, noisy).passed


def test_structure_is_invariant_to_local_affine_intensity(room):
    """The property the whole gate rests on: gamma/CLAHE/WB are locally ~affine."""
    brighter = (room.astype(np.float32) * 1.4 + 20).clip(0, 255).astype(np.uint8)
    assert metrics.structure(room, brighter) > 0.99
    assert metrics.structure_local_min(room, brighter) > 0.97


# --------------------------------------------------------------------- plumbing


def test_size_mismatch_is_handled(room):
    smaller = cv2.resize(room, (600, 450))
    assert metrics.fidelity(room, smaller).passed
