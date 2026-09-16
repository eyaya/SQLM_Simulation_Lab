import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .config import get_config_payload
from .schemas import (
    ConfigResponse,
    PairStudyRequest,
    PairStudyResponse,
    ProfileStudyRequest,
    ProfileStudyResponse,
    ResidualStudyRequest,
    ResidualStudyResponse,
)
from .simulation import run_pair_study, run_profile_study, run_residual_study


app = FastAPI(
    title="SQLM Simulation API",
    version="0.1.0",
    description="FastAPI wrapper for the Williamson hybrid nanofluid SQLM solver.",
)

DEFAULT_CORS_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:4173",
    "http://127.0.0.1:4173",
]


def _cors_origins() -> list[str]:
    """Browser origins allowed to call the API cross-origin.

    Only relevant when the API is reached directly; requests routed through
    the bundled nginx proxy are same-origin and never preflight.
    """
    configured = os.environ.get("SQLM_CORS_ORIGINS", "").strip()
    if not configured:
        return DEFAULT_CORS_ORIGINS
    return [origin.strip() for origin in configured.split(",") if origin.strip()]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/config", response_model=ConfigResponse)
def read_config() -> ConfigResponse:
    return ConfigResponse(**get_config_payload())


@app.post("/api/studies/pair", response_model=PairStudyResponse)
def create_pair_study(request: PairStudyRequest) -> PairStudyResponse:
    try:
        return run_pair_study(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="The simulation request failed unexpectedly.",
        ) from exc


@app.post("/api/studies/profile", response_model=ProfileStudyResponse)
def create_profile_study(request: ProfileStudyRequest) -> ProfileStudyResponse:
    try:
        return run_profile_study(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="The profile study request failed unexpectedly.",
        ) from exc


@app.post("/api/studies/residual", response_model=ResidualStudyResponse)
def create_residual_study(request: ResidualStudyRequest) -> ResidualStudyResponse:
    try:
        return run_residual_study(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="The residual study request failed unexpectedly.",
        ) from exc
