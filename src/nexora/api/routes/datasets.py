from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, Header, Query, Request, Response, UploadFile

from nexora.api import schemas
from nexora.api.deps import SessionDep, parse_uuid, source_scope
from nexora.application import csv_imports, ingest_service, queries
from nexora.application.errors import Invalid, PayloadTooLarge
from nexora.evaluation.generator import SUITES, suite_families

router = APIRouter(prefix="/api/v1", tags=["datasets"])


@router.get("/datasets", response_model=schemas.DatasetPage)
def list_datasets(session: SessionDep, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)) -> Any:
    return queries.list_datasets(session, limit, offset)


def upload_payload(
    request: Request,
    file: Annotated[UploadFile, File()],
    name: Annotated[str, Form(min_length=1, max_length=120)],
    boundary_account_ids: Annotated[str, Form(max_length=20000)] = "",
    idempotency_key: Annotated[
        str | None, Header(alias="Idempotency-Key", min_length=1, max_length=128, pattern=r"^[!-~]+$")
    ] = None,
) -> csv_imports.CsvPayload:
    maximum = request.app.state.settings.max_upload_bytes
    content = file.file.read(maximum + 1)
    if len(content) > maximum:
        raise PayloadTooLarge("UPLOAD_TOO_LARGE", f"file exceeds {maximum} bytes")
    return csv_imports.CsvPayload.prepare(content, name, boundary_account_ids, idempotency_key)


UploadDep = Annotated[csv_imports.CsvPayload, Depends(upload_payload)]
SourceDep = Annotated[str, Depends(source_scope)]


@router.post(
    "/datasets/import",
    response_model=schemas.ImportResult,
    status_code=201,
    responses={409: {"model": schemas.ErrorEnvelope}},
)
def import_csv(request: Request, session: SessionDep, who: SourceDep, payload: UploadDep) -> Any:
    return csv_imports.persist_csv(session, payload, scope=who, max_rows=request.app.state.settings.max_csv_rows)


@router.post(
    "/datasets/import-jobs",
    response_model=schemas.CsvImportJob,
    status_code=202,
    responses={409: {"model": schemas.ErrorEnvelope}},
)
def queue_csv_import(
    request: Request, response: Response, session: SessionDep, who: SourceDep, payload: UploadDep
) -> Any:
    job = csv_imports.enqueue_csv(session, payload, scope=who, max_rows=request.app.state.settings.max_csv_rows)
    response.headers["Location"] = f"/api/v1/datasets/import-jobs/{job.id}"
    return job


@router.get("/datasets/import-jobs/{job_id}", response_model=schemas.CsvImportJob)
def csv_import_status(job_id: str, session: SessionDep, who: SourceDep) -> Any:
    return csv_imports.get_csv_job(session, parse_uuid(job_id, "job_id"), who)


@router.post("/datasets/import-jobs/{job_id}/cancel", response_model=schemas.CsvImportJob)
def cancel_csv_import(job_id: str, session: SessionDep, who: SourceDep) -> Any:
    return csv_imports.cancel_csv_job(session, parse_uuid(job_id, "job_id"), who)


@router.get("/datasets/{dataset_id}", response_model=schemas.Dataset)
def get_dataset(dataset_id: str, session: SessionDep) -> Any:
    return queries.dataset_dict(session, queries.get_dataset(session, parse_uuid(dataset_id, "dataset_id")))


@router.get("/datasets/{dataset_id}/overview", response_model=schemas.Overview)
def overview(dataset_id: str, session: SessionDep) -> Any:
    return queries.overview(session, parse_uuid(dataset_id, "dataset_id"))


@router.get("/lab/suites", response_model=list[schemas.LabSuite], tags=["lab"])
def lab_suites() -> Any:
    return [
        {
            "id": sid,
            "description": spec["description"],
            "scenario_families": suite_families(sid),
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
