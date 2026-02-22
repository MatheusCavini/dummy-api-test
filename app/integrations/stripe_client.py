from datetime import datetime, timezone
from time import sleep

import stripe

from app.config import settings
from app.db.models import Client


RETRYABLE_STRIPE_ERRORS = (
    stripe.error.APIConnectionError,
    stripe.error.APIError,
    stripe.error.RateLimitError,
)


def _configure_stripe() -> None:
    if not settings.stripe_secret_key:
        raise RuntimeError("Missing STRIPE_SECRET_KEY")
    stripe.api_key = settings.stripe_secret_key


def get_or_create_customer(client: Client) -> str:
    _configure_stripe()

    if client.stripe_customer_id:
        customer = stripe.Customer.retrieve(client.stripe_customer_id)
        if customer and not customer.get("deleted"):
            return client.stripe_customer_id

    created_customer = stripe.Customer.create(
        email=client.email,
        name=client.name,
        metadata={"client_id": str(client.id)},
    )
    return created_customer["id"]


def create_checkout_session(client: Client, customer_id: str) -> stripe.checkout.Session:
    _configure_stripe()

    if not settings.stripe_price_base_monthly_id or not settings.stripe_price_metered_id:
        raise RuntimeError("Stripe prices are not configured")
    if not settings.stripe_success_url or not settings.stripe_cancel_url:
        raise RuntimeError("Stripe success/cancel URLs are not configured")

    return stripe.checkout.Session.create(
        mode="subscription",
        customer=customer_id,
        client_reference_id=str(client.id),
        success_url=settings.stripe_success_url,
        cancel_url=settings.stripe_cancel_url,
        line_items=[
            {"price": settings.stripe_price_base_monthly_id, "quantity": 1},
            {"price": settings.stripe_price_metered_id},
        ],
        subscription_data={
            "metadata": {
                "client_id": str(client.id),
            }
        },
        metadata={"client_id": str(client.id)},
    )


def create_portal_session(stripe_customer_id: str, return_url: str) -> stripe.billing_portal.Session:
    _configure_stripe()
    return stripe.billing_portal.Session.create(customer=stripe_customer_id, return_url=return_url)


def extract_metered_subscription_item_id(subscription: dict) -> str | None:
    metered_price_id = settings.stripe_price_metered_id
    if not metered_price_id:
        return None

    items = subscription.get("items", {}).get("data", [])
    for item in items:
        if item.get("price", {}).get("id") == metered_price_id:
            return item.get("id")
    return None


def unix_to_datetime(ts: int | None) -> datetime | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc)


def record_meter_event(subscription_item_id: str, quantity: int, timestamp: datetime | None = None) -> dict | None:
    if quantity <= 0:
        return None

    _configure_stripe()

    event_timestamp = int((timestamp or datetime.now(timezone.utc)).timestamp())
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            return stripe.SubscriptionItem.create_usage_record(
                subscription_item_id,
                quantity=int(quantity),
                timestamp=event_timestamp,
                action="increment",
            )
        except RETRYABLE_STRIPE_ERRORS as exc:
            last_error = exc
            if attempt == 2:
                break
            sleep(2**attempt)

    if last_error:
        raise last_error
    return None
