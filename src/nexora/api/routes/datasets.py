from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, Query, Request, Response, UploadFile
from fastapi.routing import APIRoute
from starlette.concurrency import run_in_threadpool

from nexora.api import schemas
from nexora.api.deps import SessionDep, enforce_authentication, parse_uuid
from nexora.application import ingest_service, queries
from nexora.application.errors import Forbidden, Invalid, PayloadTooLarge
from nexora.evaluation.generator import SUITES, suite_families
from nexora.ingest.csv_adapter import CsvSchemaError, read_csv_rows

router = APIRouter(prefix="/api/v1", tags=["datasets"])


@router.get("/datasets", response_model=schemas.DatasetPage)
def list_datasets(session: SessionDep, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)) -> Any:
    return queries.list_datasets(session, limit, offset)


@router.get("/datasets/{dataset_id}", response_model=schemas.Dataset)
def get_dataset(dataset_id: str, session: SessionDep) -> Any:
    return queries.dataset_dict(session, queries.get_dataset(session, parse_uuid(dataset_id, "dataset_id")))


@router.get("/datasets/{dataset_id}/overview", response_model=schemas.Overview)
def overview(dataset_id: str, session: SessionDep) -> Any:
    return queries.overview(session, parse_uuid(dataset_id, "dataset_id"))


class _CsvImportRoute(APIRoute):
    """Refuses CSV imports while ``allow_csv_import`` is off, *before* the upload is read.

    FastAPI parses a multipart body before it runs any dependency, so a dependency could only refuse
    after receiving up to ``max_upload_bytes``. This handler runs first: it authenticates exactly like the
    global dependency (anonymous callers still get 401 and learn nothing about the setting; writes still
    need origin + CSRF), then refuses. With the setting on, the normal route runs unchanged.
    """

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()

        async def gated(request: Request) -> Response:
            if not request.app.state.settings.allow_csv_import:
                await run_in_threadpool(enforce_authentication, request)
                raise Forbidden(
                    "CSV_IMPORT_DISABLED",
                    "CSV import is disabled on this deployment: it holds synthetic data only",
                )
            return await handler(request)

        return gated


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


# Registered explicitly: the route-class override (the pre-body gate) is not available on @router.post.
router.add_api_route(
    "/datasets/import",
    import_csv,
    methods=["POST"],
    response_model=schemas.ImportResult,
    status_code=201,
    route_class_override=_CsvImportRoute,
)


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
