from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func
from sqlalchemy.orm import Session
import stripe

from app.config import settings
from app.core.security import require_admin
from app.db.database import get_db
from app.db.models import Client, StripeEventLog, UsageEvent
from app.integrations.stripe_client import (
    create_checkout_session,
    create_portal_session,
    extract_metered_subscription_item_id,
    get_or_create_customer,
    record_meter_event,
    unix_to_datetime,
)


admin_router = APIRouter(
    prefix="/billing/stripe",
    tags=["stripe"],
    dependencies=[Depends(require_admin)],
)
router = APIRouter(tags=["stripe"])


class CheckoutSessionRequest(BaseModel):
    client_id: int


class CheckoutSessionResponse(BaseModel):
    checkout_url: str
    session_id: str


class PortalSessionRequest(BaseModel):
    client_id: int
    return_url: str | None = None


class PortalSessionResponse(BaseModel):
    portal_url: str


class UsageSyncRequest(BaseModel):
    client_id: int | None = None
    dry_run: bool = False


class UsageSyncRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    client_id: int
    synced_units: int
    synced_until: datetime
    dry_run: bool


def _client_by_stripe_ids(db: Session, customer_id: str | None, subscription_id: str | None) -> Client | None:
    if subscription_id:
        found = db.query(Client).filter(Client.stripe_subscription_id == subscription_id).first()
        if found:
            return found
    if customer_id:
        return db.query(Client).filter(Client.stripe_customer_id == customer_id).first()
    return None


def _update_client_subscription_state(client: Client, subscription: dict) -> None:
    client.stripe_subscription_id = subscription.get("id")
    client.subscription_status = subscription.get("status")
    client.subscription_current_period_end = unix_to_datetime(subscription.get("current_period_end"))
    client.stripe_metered_subscription_item_id = extract_metered_subscription_item_id(subscription)


def _handle_checkout_completed(db: Session, event: dict) -> bool:
    payload = event.get("data", {}).get("object", {})
    client_id_raw = payload.get("client_reference_id") or payload.get("metadata", {}).get("client_id")
    if not client_id_raw:
        return False

    client = db.query(Client).filter(Client.id == int(client_id_raw)).first()
    if not client:
        return False

    client.stripe_customer_id = payload.get("customer")
    if payload.get("subscription"):
        client.stripe_subscription_id = payload.get("subscription")
    return True


def _handle_subscription_event(db: Session, event: dict) -> bool:
    subscription = event.get("data", {}).get("object", {})
    client = _client_by_stripe_ids(
        db,
        customer_id=subscription.get("customer"),
        subscription_id=subscription.get("id"),
    )
    if not client:
        metadata_client_id = subscription.get("metadata", {}).get("client_id")
        if metadata_client_id:
            client = db.query(Client).filter(Client.id == int(metadata_client_id)).first()
    if not client:
        return False

    client.stripe_customer_id = subscription.get("customer")
    _update_client_subscription_state(client, subscription)
    if event.get("type") == "customer.subscription.deleted":
        client.subscription_status = "canceled"
    return True


def _handle_invoice_paid(db: Session, event: dict) -> bool:
    invoice = event.get("data", {}).get("object", {})
    client = _client_by_stripe_ids(
        db,
        customer_id=invoice.get("customer"),
        subscription_id=invoice.get("subscription"),
    )
    if not client:
        return False

    client.subscription_status = "active"
    return True


def _handle_invoice_failed(db: Session, event: dict) -> bool:
    invoice = event.get("data", {}).get("object", {})
    client = _client_by_stripe_ids(
        db,
        customer_id=invoice.get("customer"),
        subscription_id=invoice.get("subscription"),
    )
    if not client:
        return False

    client.subscription_status = "past_due"
    return True


def _dispatch_event(db: Session, event: dict) -> bool:
    event_type = event.get("type")

    if event_type == "checkout.session.completed":
        return _handle_checkout_completed(db, event)
    if event_type in {"customer.subscription.created", "customer.subscription.updated", "customer.subscription.deleted"}:
        return _handle_subscription_event(db, event)
    if event_type == "invoice.paid":
        return _handle_invoice_paid(db, event)
    if event_type == "invoice.payment_failed":
        return _handle_invoice_failed(db, event)
    if event_type == "invoice.finalized":
        return True

    return False


@admin_router.post("/checkout-session", response_model=CheckoutSessionResponse, status_code=status.HTTP_201_CREATED)
def create_checkout(payload: CheckoutSessionRequest, db: Session = Depends(get_db)):
    client = db.query(Client).filter(Client.id == payload.client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    customer_id = get_or_create_customer(client)
    if client.stripe_customer_id != customer_id:
        client.stripe_customer_id = customer_id
        db.commit()

    session = create_checkout_session(client=client, customer_id=customer_id)
    return CheckoutSessionResponse(checkout_url=session["url"], session_id=session["id"])


@admin_router.post("/portal-session", response_model=PortalSessionResponse, status_code=status.HTTP_201_CREATED)
def create_portal(payload: PortalSessionRequest, db: Session = Depends(get_db)):
    client = db.query(Client).filter(Client.id == payload.client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    customer_id = client.stripe_customer_id or get_or_create_customer(client)
    if client.stripe_customer_id != customer_id:
        client.stripe_customer_id = customer_id
        db.commit()

    return_url = payload.return_url or settings.stripe_success_url
    if not return_url:
        raise HTTPException(status_code=500, detail="Missing return URL configuration")

    portal_session = create_portal_session(customer_id, return_url)
    return PortalSessionResponse(portal_url=portal_session["url"])


@admin_router.post("/sync-usage", response_model=list[UsageSyncRow])
def sync_usage(payload: UsageSyncRequest, db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)

    query = db.query(Client).filter(
        Client.stripe_subscription_id.isnot(None),
        Client.stripe_metered_subscription_item_id.isnot(None),
        Client.subscription_status.in_(["active", "trialing"]),
    )
    if payload.client_id:
        query = query.filter(Client.id == payload.client_id)

    clients = query.all()
    results: list[UsageSyncRow] = []

    for client in clients:
        start = client.usage_synced_until or datetime.fromtimestamp(0, tz=timezone.utc)
        total_units = (
            db.query(func.coalesce(func.sum(UsageEvent.units), 0))
            .filter(
                UsageEvent.client_id == client.id,
                UsageEvent.created_at > start,
                UsageEvent.created_at <= now,
            )
            .scalar()
        )

        units = int(total_units or 0)
        if units > 0 and not payload.dry_run:
            record_meter_event(
                subscription_item_id=client.stripe_metered_subscription_item_id,
                quantity=units,
                timestamp=now,
            )

        if not payload.dry_run:
            client.usage_synced_until = now

        results.append(
            UsageSyncRow(
                client_id=client.id,
                synced_units=units,
                synced_until=now,
                dry_run=payload.dry_run,
            )
        )

    if not payload.dry_run:
        db.commit()

    return results


@router.post("/stripe/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: str | None = Header(default=None, alias="Stripe-Signature"),
    db: Session = Depends(get_db),
):
    if not settings.stripe_webhook_secret:
        raise HTTPException(status_code=500, detail="Stripe webhook secret is not configured")

    payload = await request.body()

    try:
        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=stripe_signature,
            secret=settings.stripe_webhook_secret,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid payload: {exc}") from exc
    except stripe.error.SignatureVerificationError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid signature: {exc}") from exc

    existing = db.query(StripeEventLog).filter(StripeEventLog.event_id == event["id"]).first()
    if existing:
        return {"status": "duplicate"}

    log_row = StripeEventLog(
        event_id=event["id"],
        event_type=event["type"],
        status="ignored",
    )
    db.add(log_row)
    db.commit()
    db.refresh(log_row)

    try:
        handled = _dispatch_event(db, event)
        log_row.status = "processed" if handled else "ignored"
        log_row.processed_at = datetime.now(timezone.utc)
        db.commit()
        return {"status": log_row.status}
    except Exception as exc:
        db.rollback()
        failed_log = db.query(StripeEventLog).filter(StripeEventLog.id == log_row.id).first()
        if failed_log:
            failed_log.status = "failed"
            failed_log.error_message = str(exc)[:1000]
            failed_log.processed_at = datetime.now(timezone.utc)
            db.commit()
        raise HTTPException(status_code=500, detail="Failed to process webhook event") from exc
