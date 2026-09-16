import os
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


def _limit(name: str, default: float) -> float:
    raw = os.environ.get(f"SQLM_MAX_{name}")
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


# Solver knobs that drive runtime. `base_params` is otherwise free-form
# passthrough, and N and ms feed straight into an O(N^3) iteration loop, so an
# unbounded request can pin a worker for hours. Raise the ceilings with
# SQLM_MAX_N / SQLM_MAX_MS when running locally on real hardware.
REQUIRED_BASE_PARAMS = ("N", "ms", "L", "tol")
BASE_PARAM_BOUNDS: dict[str, tuple[float, float]] = {
    "N": (4, _limit("N", 201)),
    "ms": (1, _limit("MS", 500)),
    "L": (1.0, _limit("L", 100.0)),
    "tol": (1e-16, 1e-2),
    "omega": (1e-3, 2.0),
}


def validate_base_params(base_params: dict[str, Any]) -> dict[str, Any]:
    missing = [key for key in REQUIRED_BASE_PARAMS if key not in base_params]
    if missing:
        raise ValueError(f"Missing solver parameters: {', '.join(missing)}.")

    for key, (low, high) in BASE_PARAM_BOUNDS.items():
        if key not in base_params:
            continue
        value = base_params[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"Solver parameter '{key}' must be a number.")
        # Also rejects NaN and infinities, which compare False against both bounds.
        if not low <= value <= high:
            raise ValueError(
                f"Solver parameter '{key}' must be between {low:g} and {high:g}."
            )
    return base_params


class MaterialProperties(BaseModel):
    rho: float
    mu: float | None = None
    k: float
    sigma: float
    cp: float
    is_base_fluid: bool = False


class ComponentsPayload(BaseModel):
    base_fluid: MaterialProperties
    mos2: MaterialProperties
    cu: MaterialProperties


class NanofluidPayload(BaseModel):
    name: str
    display_name: str | None = None
    phi1: float = Field(ge=0.0, lt=0.3)
    phi2: float = Field(ge=0.0, lt=0.3)
    enabled: bool = True

    @model_validator(mode="after")
    def validate_total_phi(self) -> "NanofluidPayload":
        if self.phi1 + self.phi2 >= 0.3:
            raise ValueError("The total nanoparticle volume fraction must be below 0.3.")
        return self


class PairStudyRequest(BaseModel):
    components: ComponentsPayload
    base_params: dict[str, Any]
    nanofluids: list[NanofluidPayload]
    theme_mode: Literal["light", "dark"] = "light"
    quantity_key: Literal["skin_friction", "nusselt", "sherwood"]
    x_param: str
    x_spec: list[float]
    y_param: str
    y_spec: list[float]
    n_points: int = Field(default=7, ge=2, le=41)

    @model_validator(mode="after")
    def validate_request(self) -> "PairStudyRequest":
        validate_base_params(self.base_params)
        if self.x_param == self.y_param:
            raise ValueError("The X and Y parameters must be different.")
        if len(self.x_spec) < 2 or len(self.y_spec) < 2:
            raise ValueError("Each parameter specification must contain at least two values.")
        if not any(item.enabled for item in self.nanofluids):
            raise ValueError("At least one nanofluid must be enabled.")
        return self


class ProfileStudyRequest(BaseModel):
    components: ComponentsPayload
    base_params: dict[str, Any]
    nanofluids: list[NanofluidPayload]
    theme_mode: Literal["light", "dark"] = "light"
    profile_key: Literal["velocity", "temperature", "concentration"]
    param_key: str
    param_values: list[float]
    style_param_key: str | None = None
    style_param_values: list[float] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_request(self) -> "ProfileStudyRequest":
        validate_base_params(self.base_params)
        if len(self.param_values) < 1:
            raise ValueError("At least one parameter value is required.")
        if len(self.param_values) > 20:
            raise ValueError("Use at most 20 parameter values in a single profile study.")
        if self.style_param_values and not self.style_param_key:
            raise ValueError("Provide a style parameter key when style parameter values are set.")
        if self.style_param_key and self.param_key == self.style_param_key:
            raise ValueError("The study parameter and style parameter must be different.")
        if len(self.style_param_values) > 6:
            raise ValueError("Use at most 6 style parameter values in a single profile study.")
        if not any(item.enabled for item in self.nanofluids):
            raise ValueError("At least one nanofluid must be enabled.")
        return self


class ResidualStudyRequest(BaseModel):
    components: ComponentsPayload
    base_params: dict[str, Any]
    nanofluids: list[NanofluidPayload]
    theme_mode: Literal["light", "dark"] = "light"

    @model_validator(mode="after")
    def validate_request(self) -> "ResidualStudyRequest":
        validate_base_params(self.base_params)
        if not any(item.enabled for item in self.nanofluids):
            raise ValueError("At least one nanofluid must be enabled.")
        return self


class SurfaceSummary(BaseModel):
    count: int
    min: float | None
    max: float | None
    mean: float | None


class NanofluidSurface(BaseModel):
    name: str
    display_name: str
    phi1: float
    phi2: float
    grid: list[list[float | None]]
    summary: SurfaceSummary


class PairStudyMeta(BaseModel):
    quantity_key: str
    x_param: str
    x_values: list[float]
    y_param: str
    y_values: list[float]
    n_points: int
    total_runs: int
    successful_runs: int
    failed_runs: int
    elapsed_seconds: float
    saved_files: list[str] = Field(default_factory=list)


class PairStudyResponse(BaseModel):
    meta: PairStudyMeta
    surfaces: list[NanofluidSurface]


class ProfileCurve(BaseModel):
    name: str
    display_name: str
    phi1: float
    phi2: float
    param_value: float
    style_param_value: float | None
    success: bool
    values: list[float] | None


class ProfileStudyMeta(BaseModel):
    profile_key: str
    param_key: str
    param_values: list[float]
    style_param_key: str | None
    style_param_values: list[float]
    eta_values: list[float]
    total_runs: int
    successful_runs: int
    failed_runs: int
    elapsed_seconds: float
    saved_files: list[str] = Field(default_factory=list)


class ProfileStudyResponse(BaseModel):
    meta: ProfileStudyMeta
    curves: list[ProfileCurve]


class ResidualCurve(BaseModel):
    key: str
    label: str
    values: list[float]


class ResidualStudyMeta(BaseModel):
    total_runs: int
    successful_runs: int
    failed_runs: int
    elapsed_seconds: float
    saved_files: list[str] = Field(default_factory=list)


class ResidualNanofluidStudy(BaseModel):
    name: str
    display_name: str
    phi1: float
    phi2: float
    success: bool
    iterations: list[int]
    total_iterations: int
    elapsed_seconds: float
    curves: list[ResidualCurve]
    saved_files: list[str] = Field(default_factory=list)


class ResidualStudyResponse(BaseModel):
    meta: ResidualStudyMeta
    studies: list[ResidualNanofluidStudy]


class ConfigResponse(BaseModel):
    components: dict[str, Any]
    base_params: dict[str, Any]
    nanofluids: list[dict[str, Any]]
    parameter_catalog: dict[str, Any]
    quantity_catalog: dict[str, Any]
    profile_catalog: dict[str, Any]
    default_pair_study: dict[str, Any]
    default_profile_study: dict[str, Any]
    default_residual_study: dict[str, Any]
