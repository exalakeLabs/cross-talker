from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from cross_talker.config import get_settings
from cross_talker.exceptions import ConfigurationError, ProviderCallError
from cross_talker.factory import build_cross_talker
from cross_talker.models import (
    CrossTalkRequest,
    CrossTalkResponse,
    HealthResponse,
    StoredRun,
)
from cross_talker.orchestrator import CrossTalker
from cross_talker.storage import SQLiteRepository

app = FastAPI(
    title="Cross Talker",
    version="0.1.0",
    description="Cross-check prompts across multiple model services.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[],
    allow_origin_regex=(
        r"^https?://(?:localhost|127\.0\.0\.1|"
        r"192\.168\.4\.(?:25[0-5]|2[0-4]\d|1?\d?\d)):3000$"
    ),
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@lru_cache
def get_repository() -> SQLiteRepository:
    return SQLiteRepository(get_settings().database_path)


@lru_cache
def get_cross_talker() -> CrossTalker:
    return build_cross_talker(get_settings(), repository=get_repository())


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        configured_providers=settings.providers,
        max_rounds=settings.max_rounds,
    )


@app.post("/v1/cross-talk", response_model=CrossTalkResponse)
async def cross_talk(
    request: CrossTalkRequest,
    service: Annotated[CrossTalker, Depends(get_cross_talker)],
) -> CrossTalkResponse:
    try:
        return await service.ask(
            request.prompt,
            rounds=request.rounds,
            providers=request.providers,
        )
    except ConfigurationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ProviderCallError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/v1/runs", response_model=list[StoredRun])
async def list_runs(
    repository: Annotated[SQLiteRepository, Depends(get_repository)],
    limit: int = 50,
) -> list[StoredRun]:
    if not 1 <= limit <= 500:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 500")
    return await repository.list_runs(limit)


@app.get("/v1/runs/{run_id}", response_model=StoredRun)
async def get_run(
    run_id: str,
    repository: Annotated[SQLiteRepository, Depends(get_repository)],
) -> StoredRun:
    run = await repository.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return run
