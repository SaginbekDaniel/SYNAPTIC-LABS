from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from nexora.api import schemas
from nexora.application import evaluation

router = APIRouter(prefix="/api/v1", tags=["evaluation"])


@router.get(
    "/evaluation",
    response_model=schemas.EvaluationReport,
    responses={404: {"model": schemas.ErrorEnvelope}, 500: {"model": schemas.ErrorEnvelope}},
)
def get_evaluation(request: Request) -> Any:
    """Latest benchmark run on SYNTHETIC data (artifact of ``scripts/run_benchmark.py``)."""
    return evaluation.load_report(request.app.state.settings.benchmark_artifact)
