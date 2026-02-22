from datetime import datetime, timezone
from typing import NamedTuple

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.core.security import (
    create_client_session_token,
    generate_password_hash,
    validate_client_jwt,
    verify_password,
)
from app.db.database import get_db
from app.db.models import ApiKey, Client, ClientSession, PendingApiKeyDelivery
from app.integrations.stripe_client import create_checkout_session, get_or_create_customer
from app.routes.admin import ApiKeyOut, ClientOut


class AuthenticatedClient(NamedTuple):
    client: Client
    session_id: str


def _extract_bearer_token(auth_header: str | None) -> str | None:
    if not auth_header:
        return None
    if not auth_header.startswith("Bearer "):
        return None
    token = auth_header.replace("Bearer ", "", 1).strip()
    return token or None


router = APIRouter(tags=["clients"])


def get_current_client(
    authorization: str | None = Header(None), db: Session = Depends(get_db)
) -> AuthenticatedClient:
    token = _extract_bearer_token(authorization)
    client, session = validate_client_jwt(db, token or "")
    return AuthenticatedClient(client=client, session_id=session.jti)


def _consume_pending_raw_key(db: Session, client: Client) -> str | None:
    now = datetime.now(timezone.utc)
    pending = (
        db.query(PendingApiKeyDelivery)
        .join(ApiKey)
        .filter(
            ApiKey.client_id == client.id,
            PendingApiKeyDelivery.delivered_at.is_(None),
            PendingApiKeyDelivery.expires_at > now,
        )
        .order_by(PendingApiKeyDelivery.created_at.desc())
        .first()
    )
    if not pending:
        return None
    pending.delivered_at = now
    db.commit()
    return pending.raw_key


class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    password: str = Field(min_length=8)


class RegisterResponse(BaseModel):
    client_id: int
    checkout_url: str
    session_id: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_at: datetime
    pending_raw_key: str | None = None


class ApiKeysResponse(BaseModel):
    api_keys: list[ApiKeyOut]
    pending_raw_key: str | None = None


class PricingPlanOut(BaseModel):
    code: str
    label: str
    description: str
    price_ids: list[str]


class CheckoutPlanRequest(BaseModel):
    plan_code: str = "standard"


class CheckoutPlanResponse(BaseModel):
    checkout_url: str
    session_id: str
    plan_code: str


def _build_pricing_plans() -> dict[str, dict]:
    if not settings.stripe_price_base_monthly_id:
        raise HTTPException(status_code=500, detail="Missing STRIPE_PRICE_BASE_MONTHLY_ID")
    if not settings.stripe_price_metered_id:
        raise HTTPException(status_code=500, detail="Missing STRIPE_PRICE_METERED_ID")

    return {
        "standard": {
            "label": "Standard",
            "description": "Base monthly subscription",
            "price_ids": [settings.stripe_price_base_monthly_id],
            "line_items": [{"price": settings.stripe_price_base_monthly_id, "quantity": 1}],
        },
        "metered": {
            "label": "Metered",
            "description": "Base monthly plus metered usage",
            "price_ids": [settings.stripe_price_base_monthly_id, settings.stripe_price_metered_id],
            "line_items": [
                {"price": settings.stripe_price_base_monthly_id, "quantity": 1},
                {"price": settings.stripe_price_metered_id},
            ],
        },
    }


@router.post("/clients/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
def register_client(payload: RegisterRequest, db: Session = Depends(get_db)):
    existing = db.query(Client).filter(Client.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    password_hash, password_salt = generate_password_hash(payload.password)
    client = Client(
        name=payload.name,
        email=payload.email,
        password_hash=password_hash,
        password_salt=password_salt,
    )
    db.add(client)
    db.commit()
    db.refresh(client)

    customer_id = get_or_create_customer(client)
    if client.stripe_customer_id != customer_id:
        client.stripe_customer_id = customer_id
        db.commit()

    session = create_checkout_session(client=client, customer_id=customer_id)
    return RegisterResponse(
        client_id=client.id,
        checkout_url=session["url"],
        session_id=session["id"],
    )


@router.post("/clients/login", response_model=LoginResponse)
def login_client(payload: LoginRequest, db: Session = Depends(get_db)):
    client = db.query(Client).filter(Client.email == payload.email).first()
    if not client or not verify_password(payload.password, client.password_salt or "", client.password_hash or ""):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    access_token, expires_at, _ = create_client_session_token(db, client)
    pending_raw_key = _consume_pending_raw_key(db, client)
    return LoginResponse(
        access_token=access_token,
        expires_at=expires_at,
        pending_raw_key=pending_raw_key,
    )


@router.post("/clients/logout")
def logout_client(auth: AuthenticatedClient = Depends(get_current_client), db: Session = Depends(get_db)):
    session = (
        db.query(ClientSession)
        .filter(ClientSession.client_id == auth.client.id, ClientSession.jti == auth.session_id)
        .first()
    )
    if session:
        session.is_active = False
        db.commit()
    return {"detail": "Logged out"}


@router.get("/clients/me", response_model=ClientOut)
def read_client(auth: AuthenticatedClient = Depends(get_current_client)):
    return auth.client


@router.get("/clients/pricing-plans", response_model=list[PricingPlanOut])
def list_pricing_plans(auth: AuthenticatedClient = Depends(get_current_client)):
    _ = auth
    plans = _build_pricing_plans()
    return [
        PricingPlanOut(
            code=code,
            label=plan["label"],
            description=plan["description"],
            price_ids=plan["price_ids"],
        )
        for code, plan in plans.items()
    ]


@router.post("/clients/checkout-session", response_model=CheckoutPlanResponse, status_code=status.HTTP_201_CREATED)
def create_client_checkout_session(
    payload: CheckoutPlanRequest,
    auth: AuthenticatedClient = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    plans = _build_pricing_plans()
    plan = plans.get(payload.plan_code)
    if not plan:
        raise HTTPException(status_code=400, detail="Invalid plan_code")

    customer_id = auth.client.stripe_customer_id or get_or_create_customer(auth.client)
    if auth.client.stripe_customer_id != customer_id:
        auth.client.stripe_customer_id = customer_id
        db.commit()

    session = create_checkout_session(
        client=auth.client,
        customer_id=customer_id,
        line_items=plan["line_items"],
    )
    return CheckoutPlanResponse(
        checkout_url=session["url"],
        session_id=session["id"],
        plan_code=payload.plan_code,
    )


@router.get("/clients/me/api-keys", response_model=ApiKeysResponse)
def list_client_api_keys(auth: AuthenticatedClient = Depends(get_current_client), db: Session = Depends(get_db)):
    api_keys = (
        db.query(ApiKey)
        .filter(ApiKey.client_id == auth.client.id)
        .order_by(ApiKey.created_at.desc())
        .all()
    )
    pending_raw_key = _consume_pending_raw_key(db, auth.client)
    return ApiKeysResponse(api_keys=api_keys, pending_raw_key=pending_raw_key)
