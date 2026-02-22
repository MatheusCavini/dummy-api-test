from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import generate_api_key
from app.config import settings
from app.db.database import SessionLocal
from app.db.models import ApiKey, Client, PendingApiKeyDelivery, Service
from app.routes.stripe import _handle_checkout_completed


def _ensure_service(db: Session) -> Service:
    service = db.query(Service).filter(Service.code == "transform").first()
    if not service:
        service = Service(code="transform", name="Transform", unit_price=0, is_active=True)
        db.add(service)
        db.commit()
        db.refresh(service)
    return service


def _register_and_login(client: TestClient, monkeypatch) -> tuple[int, str]:
    customer_id = f"cus_{uuid4().hex[:8]}"
    monkeypatch.setattr("app.routes.clients.get_or_create_customer", lambda client_obj: customer_id)
    def fake_checkout_session(client, customer_id):
        return {"url": "https://stripe.test", "id": "sess_123"}
    monkeypatch.setattr("app.routes.clients.create_checkout_session", fake_checkout_session)
    password = "s3cret-pass"
    email = f"client-{uuid4().hex[:8]}@example.com"

    register_resp = client.post("/clients/register", json={"name": "Client Name", "email": email, "password": password})
    assert register_resp.status_code == 201
    client_id = register_resp.json()["client_id"]

    login_resp = client.post("/clients/login", json={"email": email, "password": password})
    assert login_resp.status_code == 200
    return client_id, login_resp.json()["access_token"]


def test_register_and_login_flow(client: TestClient, monkeypatch):
    _, access_token = _register_and_login(client, monkeypatch)
    assert access_token

    me_resp = client.get("/clients/me", headers={"Authorization": f"Bearer {access_token}"})
    assert me_resp.status_code == 200


def test_api_keys_endpoint_returns_pending_raw(client: TestClient, monkeypatch):
    client_id, access_token = _register_and_login(client, monkeypatch)

    db = SessionLocal()
    service = _ensure_service(db)
    raw_key, prefix, key_hash = generate_api_key()
    api_key = ApiKey(client_id=client_id, service_id=service.id, key_hash=key_hash, prefix=prefix)
    db.add(api_key)
    db.flush()
    pending = PendingApiKeyDelivery(
        api_key_id=api_key.id,
        raw_key=raw_key,
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=600),
    )
    db.add(pending)
    db.commit()
    api_key_id = api_key.id
    db.close()

    resp = client.get("/clients/me/api-keys", headers={"Authorization": f"Bearer {access_token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["pending_raw_key"] == raw_key
    assert data["api_keys"]

    db = SessionLocal()
    delivered = db.query(PendingApiKeyDelivery).filter(PendingApiKeyDelivery.api_key_id == api_key_id).first()
    assert delivered and delivered.delivered_at
    db.close()


def test_pricing_plans_requires_jwt(client: TestClient):
    resp = client.get("/clients/pricing-plans")
    assert resp.status_code == 401


def test_pricing_plans_returns_fixed_options(client: TestClient, monkeypatch):
    _, access_token = _register_and_login(client, monkeypatch)
    resp = client.get("/clients/pricing-plans", headers={"Authorization": f"Bearer {access_token}"})
    assert resp.status_code == 200
    payload = resp.json()
    codes = {item["code"] for item in payload}
    assert codes == {"standard", "metered"}


def test_checkout_session_uses_selected_plan(client: TestClient, monkeypatch):
    _, access_token = _register_and_login(client, monkeypatch)
    captured = {"line_items": None}

    def fake_checkout_session(client, customer_id, line_items=None):
        captured["line_items"] = line_items
        return {"url": "https://stripe.test/checkout", "id": "sess_plan"}

    monkeypatch.setattr("app.routes.clients.create_checkout_session", fake_checkout_session)
    resp_standard = client.post(
        "/clients/checkout-session",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"plan_code": "standard"},
    )
    assert resp_standard.status_code == 201
    assert resp_standard.json()["plan_code"] == "standard"
    assert captured["line_items"] == [{"price": settings.stripe_price_base_monthly_id, "quantity": 1}]

    resp_metered = client.post(
        "/clients/checkout-session",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"plan_code": "metered"},
    )
    assert resp_metered.status_code == 201
    assert resp_metered.json()["plan_code"] == "metered"
    assert captured["line_items"] == [
        {"price": settings.stripe_price_base_monthly_id, "quantity": 1},
        {"price": settings.stripe_price_metered_id},
    ]


def test_checkout_session_rejects_invalid_plan(client: TestClient, monkeypatch):
    _, access_token = _register_and_login(client, monkeypatch)
    resp = client.post(
        "/clients/checkout-session",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"plan_code": "enterprise"},
    )
    assert resp.status_code == 400


def test_stripe_checkout_creates_api_key_and_pending(monkeypatch):
    monkeypatch.setattr(settings, "client_default_service_code", "transform")
    db = SessionLocal()
    service = _ensure_service(db)
    client = Client(name="Stripe Client", email=f"stripe-{uuid4().hex[:6]}@example.com")
    db.add(client)
    db.commit()
    db.refresh(client)

    event = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "client_reference_id": str(client.id),
                "customer": "cus_checkout",
                "subscription": "sub_checkout",
            }
        },
    }

    handled = _handle_checkout_completed(db, event)
    assert handled
    db.commit()

    api_key = (
        db.query(ApiKey)
        .filter(ApiKey.client_id == client.id, ApiKey.service_id == service.id)
        .first()
    )
    assert api_key
    pending = db.query(PendingApiKeyDelivery).filter(PendingApiKeyDelivery.api_key_id == api_key.id).first()
    assert pending
    assert pending.raw_key
    assert pending.delivered_at is None
    db.close()
