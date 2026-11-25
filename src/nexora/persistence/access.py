"""Dataset visibility for API transactions carrying a verified tenant scope."""

from __future__ import annotations

from sqlalchemy import select, true
from sqlalchemy.orm import Session

from nexora.persistence import orm


def dataset_filter(session: Session, dataset_column=orm.Dataset.id):
    tenant = session.info.get("tenant")
    if tenant is None and not session.info.get("demo_scope"):
        return true()
    scope = orm.Dataset.tenant == tenant if tenant is not None else orm.Dataset.tenant.is_(None)
    return scope if dataset_column is orm.Dataset.id else dataset_column.in_(select(orm.Dataset.id).where(scope))


def case_filter(session: Session):
    if session.info.get("tenant") is None and not session.info.get("demo_scope"):
        return true()
    visible_alerts = select(orm.Alert.id).where(dataset_filter(session, orm.Alert.dataset_id))
    return orm.Case.alert_id.in_(visible_alerts)
