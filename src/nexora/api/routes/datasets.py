from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from sqlalchemy.orm import Session

from nexora.api import schemas
from nexora.api.deps import get_session, parse_uuid
from nexora.application import ingest_service, queries
from nexora.application.errors import Invalid, PayloadTooLarge
from nexora.evaluation.generator import SUITES
from nexora.ingest.csv_adapter import CsvSchemaError, read_csv_rows

router = APIRouter(prefix="/api/v1", tags=["datasets"])
SessionDep = Annotated[Session, Depends(get_session)]


@router.get("/datasets", response_model=schemas.DatasetPage)
def list_datasets(session: SessionDep, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)) -> Any:
    return queries.list_datasets(session, limit, offset)


@router.get("/datasets/{dataset_id}", response_model=schemas.Dataset)
def get_dataset(dataset_id: str, session: SessionDep) -> Any:
    return queries.dataset_dict(session, queries.get_dataset(session, parse_uuid(dataset_id, "dataset_id")))


@router.get("/datasets/{dataset_id}/overview", response_model=schemas.Overview)
def overview(dataset_id: str, session: SessionDep) -> Any:
    return queries.overview(session, parse_uuid(dataset_id, "dataset_id"))


@router.post("/datasets/import", response_model=schemas.ImportResult, status_code=201)
async def import_csv(
    request: Request,
    session: SessionDep,
    file: Annotated[UploadFile, File()],
    name: Annotated[str, Form(min_length=1, max_length=120)],
    boundary_account_ids: Annotated[str, Form(max_length=20000)] = "",
) -> Any:
    settings = request.app.state.settings
    content = await file.read(settings.max_upload_bytes + 1)
    if len(content) > settings.max_upload_bytes:
        raise PayloadTooLarge("UPLOAD_TOO_LARGE", f"file exceeds {settings.max_upload_bytes} bytes")
    try:
        rows, digest = read_csv_rows(content, max_rows=settings.max_csv_rows)
    except CsvSchemaError as exc:
        raise Invalid(exc.code, str(exc)) from exc
    boundary = sorted({b.strip() for b in boundary_account_ids.replace("\n", ",").split(",") if b.strip()})
    has_ts = any(isinstance(r.get("occurred_at"), str) and str(r.get("occurred_at")).strip() for _, r in rows)
    has_day = any(not (isinstance(r.get("occurred_at"), str) and str(r.get("occurred_at")).strip()) for _, r in rows)
    precision = "mixed" if has_ts and has_day else ("timestamp" if has_ts else "day")
    ds = ingest_service.create_dataset(
        session,
        name=name,
        source_kind="csv",
        time_precision=precision,
        coverage_contract={
            "source": "csv",
            "boundary_account_ids": boundary,
            "upstream_observed": None,
            "declared_complete": False,
        },
        description=None,
        authorized_use_note="Uploaded by operator; operator is responsible for authorised use.",
        manifest_sha256=digest,
    )
    batch, report = ingest_service.ingest_rows(
        session,
        dataset=ds,
        rows=rows,
        source_id=f"csv:{digest[:16]}",
        content_sha256=digest,
        file_name=None,
        is_synthetic=False,
    )
    session.flush()
    return {
        "dataset": queries.dataset_dict(session, ds),
        "batch_id": str(batch.id),
        "report": report.as_dict(),
    }


@router.get("/lab/suites", response_model=list[schemas.LabSuite], tags=["lab"])
def lab_suites() -> Any:
    return [
        {
            "id": sid,
            "description": spec["description"],
            "scenario_families": [f for f, _ in spec["scenarios"]],
        }
        for sid, spec in SUITES.items()
    ]


@router.post("/lab/datasets", response_model=schemas.ImportResult, status_code=201, tags=["lab"])
def create_synthetic(body: schemas.SyntheticDatasetRequest, session: SessionDep) -> Any:
    if body.suite not in SUITES:
        raise Invalid("UNKNOWN_SUITE", "unknown synthetic suite", {"suite": body.suite, "available": sorted(SUITES)})
    ds, batch, report = ingest_service.create_synthetic_dataset(
        session, suite=body.suite, seed=body.seed, precision=body.precision
    )
    session.flush()
    return {
        "dataset": queries.dataset_dict(session, ds),
        "batch_id": str(batch.id),
        "report": report.as_dict(),
    }
