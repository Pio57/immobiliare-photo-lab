"""Data contract shared with n8n and the frontend. See docs/contracts.md.
Keep frontend/src/types.ts aligned with the models below."""

from typing import ClassVar, Literal

from pydantic import BaseModel, Field, model_validator

from app.config import settings


class EnhanceParams(BaseModel):
    """The full space of allowed corrections. This *is* the editorial policy:
    an operation that has no parameter here cannot be requested by anyone,
    including the vision model. Out-of-range values are clamped, not rejected,
    so a slightly over-eager model still produces a usable (bounded) result."""

    gamma: float = Field(1.0, description="Exposure. <1 brightens, >1 darkens.")
    clahe_clip: float = Field(0.0, description="Local contrast (CLAHE clip limit). 0 = off.")
    white_balance: float = Field(0.0, description="Gray-world white balance strength, 0..1.")
    denoise: int = Field(0, description="Non-local-means strength h. 0 = off.")
    rotate_deg: float = Field(0.0, description="Straightening rotation, positive = counter-clockwise.")
    orientation: int = Field(0, description="Lossless quarter-turn, clockwise degrees (0, 90, 180, 270): a photo on its side or upside down.")
    sharpen: float = Field(0.0, description="Unsharp-mask amount, 0..1. Amplifies existing edges, invents none.")
    auto_straighten: bool = Field(False, description="Estimate rotate_deg from dominant vertical lines.")
    recommendation: Literal["apply", "mild", "keep_original"] = Field(
        "apply",
        description="Flow B only: the model's verdict on whether correcting this photo is worth it. "
        "keep_original means every correction costs more than it gives (e.g. brightening a dark, noisy shot).",
    )

    BOUNDS: ClassVar[dict[str, tuple[float, float]]] = {
        "gamma": (0.5, 2.0),
        "clahe_clip": (0.0, 4.0),
        "white_balance": (0.0, 1.0),
        "denoise": (0, 15),
        "rotate_deg": (-settings.max_rotate_deg, settings.max_rotate_deg),
        "sharpen": (0.0, 1.0),
    }

    @model_validator(mode="after")
    def _clamp(self) -> "EnhanceParams":
        for name, (lo, hi) in self.BOUNDS.items():
            value = getattr(self, name)
            setattr(self, name, type(value)(min(max(value, lo), hi)))
        self.orientation = int(round(self.orientation / 90.0)) * 90 % 360  # snap to a quarter turn
        return self

    def is_neutral(self) -> bool:
        return self == EnhanceParams()


class ImageStats(BaseModel):
    """Measured facts about an image, fed to the vision model as hints (flow B)
    and used by the heuristics of flow A."""

    width: int
    height: int
    mean_luminance: float = Field(description="Mean L of LAB, 0..255.")
    contrast_std: float = Field(description="Std of L, higher = more contrast.")
    color_cast: tuple[float, float] = Field(description="Mean (a, b) offset from neutral in LAB.")
    noise_estimate: float = Field(description="High-frequency energy in flat regions, higher = noisier.")
    tilt_deg: float = Field(description="Estimated rotation needed to straighten verticals.")
    noise_after_brightening: float = Field(
        0.0, description="Noise the photo would show once exposure is corrected: the cost side of the trade-off."
    )
    input_warnings: list[str] = Field(default_factory=list, description="low_resolution / heavy_compression: the pipeline cannot fix these.")


class FidelityReport(BaseModel):
    structure: float = Field(description="10th percentile of block-wise NCC on blurred luminance.")
    structure_local_min: float = Field(description="Worst block NCC. Local damage detector.")
    hue_corr: float = Field(description="Hue histogram correlation after gray-world normalisation.")
    score: float = Field(description="0.7 * structure + 0.3 * hue_corr, see config.")
    threshold: float
    local_floor: float
    passed: bool = Field(description="score >= threshold AND structure_local_min >= local_floor.")


class ImageRequest(BaseModel):
    """Either an inline image (live flow) or an id from dataset/raw (batch flow).
    `save_as` writes the output to dataset/processed/<save_as>.jpg so the
    orchestrator never has to carry pixels around."""

    image_b64: str | None = None
    image_id: str | None = None
    save_as: str | None = None
    return_image: bool = True
    max_side: int | None = Field(None, description="Override the processing size, e.g. 1024 for an inline data URI.")


class ApplyRequest(ImageRequest):
    params: EnhanceParams


class FidelityRequest(BaseModel):
    """Original: inline or by dataset id. Candidate: inline or a URL the service
    fetches itself (generative outputs live on the provider's CDN)."""

    original_b64: str | None = None
    image_id: str | None = None
    candidate_b64: str | None = None
    candidate_url: str | None = None
    save_as: str | None = None


class PrepareResponse(BaseModel):
    turns: list[str] = Field(default_factory=list, description="The photo at 0/90/180/270 deg clockwise, 512 px JPEG base64: the orientation question of D2.")
    """Entry point of every flow: one upload becomes a bounded JPEG plus its stats,
    plus the heuristic diagnosis (D1) — free, so it doubles as the fallback when a
    model diagnosis fails."""

    image_id: str
    image_b64: str
    stats: ImageStats
    heuristic_params: EnhanceParams
    heuristic_defects: list[str]


class GateResponse(BaseModel):
    """Generative flow: fetch the model's output and gate it in one call, so the
    orchestrator never has to carry the image bytes itself."""

    image_id: str | None = None
    image_b64: str
    fidelity: FidelityReport
    latency_ms: int
    measured_changes: dict[str, float] = Field(
        default_factory=dict,
        description="What the generative output changed, measured after the fact: a black box "
        "cannot report its decisions, so they are read off the pixels (luminance, cast, noise, sharpness, tilt, size).",
    )


class EnhanceResponse(BaseModel):
    image_b64: str | None = None
    output_path: str | None = None
    params: EnhanceParams
    fidelity: FidelityReport
    stats: ImageStats
    latency_ms: int
    crop_pct: float = Field(0.0, description="Area lost to the straightening crop, percent of the input.")
    suggested_conservative_params: EnhanceParams | None = Field(
        None, description="Only set when the fidelity gate failed: a halfway-to-neutral retry."
    )


VariantId = Literal["A", "B", "C"]
