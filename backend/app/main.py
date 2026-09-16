import logging
import os

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

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


# uvicorn configures its own loggers but leaves the root logger bare, so
# without this our records fall through to logging.lastResort and arrive
# unformatted. basicConfig is a no-op when handlers are already installed.
logging.basicConfig(
    level=os.environ.get("SQLM_LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("sqlm.api")


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
    # Preview deployments get a generated hostname per branch, so they can only
    # be matched by pattern. Example: https://.*\.vercel\.app
    allow_origin_regex=os.environ.get("SQLM_CORS_ORIGIN_REGEX") or None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def handle_validation_error(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Return a readable sentence instead of pydantic's nested report.

    The default 422 body is an array of error objects that also echoes the
    entire request payload back. The client renders `detail` directly, so it
    needs a string, and the endpoints already answer bad input with 400.
    """
    messages = [
        str(error.get("msg", "Invalid request.")).removeprefix("Value error, ")
        for error in exc.errors()
    ]
    detail = " ".join(messages) or "Invalid request."
    logger.warning("Rejected %s: %s", request.url.path, detail)
    return JSONResponse(status_code=400, content={"detail": detail})


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
        logger.warning("Rejected study request: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Pair study failed")
        raise HTTPException(
            status_code=500,
            detail="The simulation request failed unexpectedly.",
        ) from exc


@app.post("/api/studies/profile", response_model=ProfileStudyResponse)
def create_profile_study(request: ProfileStudyRequest) -> ProfileStudyResponse:
    try:
        return run_profile_study(request)
    except ValueError as exc:
        logger.warning("Rejected study request: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Profile study failed")
        raise HTTPException(
            status_code=500,
            detail="The profile study request failed unexpectedly.",
        ) from exc


@app.post("/api/studies/residual", response_model=ResidualStudyResponse)
def create_residual_study(request: ResidualStudyRequest) -> ResidualStudyResponse:
    try:
        return run_residual_study(request)
    except ValueError as exc:
        logger.warning("Rejected study request: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Residual study failed")
        raise HTTPException(
            status_code=500,
            detail="The residual study request failed unexpectedly.",
        ) from exc
