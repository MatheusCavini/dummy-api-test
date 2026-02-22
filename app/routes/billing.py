from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.security import require_admin
from app.db.database import get_db
from app.db.models import Client, Service, UsageEvent


router = APIRouter(prefix="/billing", tags=["billing"], dependencies=[Depends(require_admin)])


class UsageSummaryRow(BaseModel):
    client_id: int
    client_name: str
    service_id: int
    service_code: str
    total_requests: int
    total_units: int
    total_amount: Decimal


class UsageEventOut(BaseModel):
    id: int
    client_id: int
    service_id: int
    api_key_id: int
    endpoint: str
    units: int
    created_at: datetime


def _time_window(start_date: date | None, end_date: date | None) -> tuple[datetime | None, datetime | None]:
    start_dt = (
        datetime.combine(start_date, time.min).replace(tzinfo=timezone.utc)
        if start_date
        else None
    )
    end_dt = (
        datetime.combine(end_date + timedelta(days=1), time.min).replace(tzinfo=timezone.utc)
        if end_date
        else None
    )
    return start_dt, end_dt


@router.get("/usage/summary", response_model=list[UsageSummaryRow])
def usage_summary(
    client_id: int | None = None,
    service_id: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    db: Session = Depends(get_db),
):
    start_dt, end_dt = _time_window(start_date, end_date)

    query = (
        db.query(
            Client.id.label("client_id"),
            Client.name.label("client_name"),
            Service.id.label("service_id"),
            Service.code.label("service_code"),
            func.count(UsageEvent.id).label("total_requests"),
            func.coalesce(func.sum(UsageEvent.units), 0).label("total_units"),
            func.coalesce(func.sum(UsageEvent.units * Service.unit_price), 0).label("total_amount"),
        )
        .join(Client, Client.id == UsageEvent.client_id)
        .join(Service, Service.id == UsageEvent.service_id)
        .group_by(Client.id, Client.name, Service.id, Service.code)
        .order_by(Client.id, Service.id)
    )

    if client_id:
        query = query.filter(UsageEvent.client_id == client_id)
    if service_id:
        query = query.filter(UsageEvent.service_id == service_id)
    if start_dt:
        query = query.filter(UsageEvent.created_at >= start_dt)
    if end_dt:
        query = query.filter(UsageEvent.created_at < end_dt)

    rows = query.all()
    return [
        UsageSummaryRow(
            client_id=row.client_id,
            client_name=row.client_name,
            service_id=row.service_id,
            service_code=row.service_code,
            total_requests=row.total_requests,
            total_units=row.total_units,
            total_amount=row.total_amount,
        )
        for row in rows
    ]


@router.get("/usage/events", response_model=list[UsageEventOut])
def usage_events(
    client_id: int | None = None,
    service_id: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    start_dt, end_dt = _time_window(start_date, end_date)
    safe_limit = min(max(limit, 1), 1000)

    query = db.query(UsageEvent).order_by(UsageEvent.created_at.desc())
    if client_id:
        query = query.filter(UsageEvent.client_id == client_id)
    if service_id:
        query = query.filter(UsageEvent.service_id == service_id)
    if start_dt:
        query = query.filter(UsageEvent.created_at >= start_dt)
    if end_dt:
        query = query.filter(UsageEvent.created_at < end_dt)

    events = query.limit(safe_limit).all()
    return [
        UsageEventOut(
            id=event.id,
            client_id=event.client_id,
            service_id=event.service_id,
            api_key_id=event.api_key_id,
            endpoint=event.endpoint,
            units=event.units,
            created_at=event.created_at,
        )
        for event in events
    ]
