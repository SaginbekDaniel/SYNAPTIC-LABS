"""Recorded synthetic benchmark runs for the Evaluation screen (read-only)."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends

from nexora.api import schemas
from nexora.application import evaluation_service
from nexora.settings import Settings, get_settings

router = APIRouter(prefix="/api/v1/evaluation", tags=["evaluation"])
SettingsDep = Annotated[Settings, Depends(get_settings)]


@router.get("/runs", response_model=schemas.BenchmarkRunList)
def list_runs(settings: SettingsDep) -> Any:
    return evaluation_service.list_runs(Path(settings.benchmark_results_dir))


@router.get("/runs/{label}", response_model=schemas.BenchmarkReport)
def get_run(label: str, settings: SettingsDep) -> Any:
    return evaluation_service.get_run(Path(settings.benchmark_results_dir), label)
