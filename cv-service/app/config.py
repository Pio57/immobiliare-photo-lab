"""Runtime configuration. Every tunable that affects a metric lives here so the
experiment can be reproduced from a single place."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")

    # Fidelity gate, calibrated on the dataset (experiments/scripts/calibrate_gate.py).
    # Global score: allowed edits >= 0.96, violations reach 0.84. Outputs below never reach the user.
    fidelity_threshold: float = 0.90
    # Worst 32px block: allowed >= 0.75, violations <= 0.32 (thin cracks only partly caught).
    fidelity_local_floor: float = 0.65
    fidelity_w_structure: float = 0.7
    fidelity_w_hue: float = 0.3

    # Structure is compared at this Gaussian scale (px): above sensor noise, below content.
    structure_sigma: float = 1.5
    ncc_block_px: int = 32
    # Regulariser in the NCC denominator: two flat blocks (std ~0) must compare as equal.
    ncc_regulariser: float = 150.0

    # Processing resolution. Metrics and pipeline both run at this size.
    max_side: int = 1600
    jpeg_quality: int = 90

    # Hard bound for straightening, regardless of what any caller asks.
    max_rotate_deg: float = 10.0

    # Repo root, for the dataset/runs filesystem bridge used by n8n Cloud.
    repo_root: str = str(Path(__file__).resolve().parents[2])


settings = Settings()
