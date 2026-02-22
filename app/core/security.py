import hashlib
import os
import secrets
from datetime import datetime, timezone, timedelta

import jwt
from fastapi import Header, HTTPException
from jwt import PyJWTError
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.core.logger import get_logger
from app.db.models import ApiKey, Client, ClientSession, Service


logger = get_logger(__name__)


BILLABLE_ACTIVE_STATUSES = {"active", "trialing"}


def _extract_bearer_token(auth_header: str | None) -> str | None:
    if not auth_header:
        return None
    if not auth_header.startswith("Bearer "):
        return None
    token = auth_header.replace("Bearer ", "", 1).strip()
    return token or None


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def generate_api_key() -> tuple[str, str, str]:
    raw_key = f"sk_live_{secrets.token_urlsafe(32)}"
    return raw_key, raw_key[:14], hash_api_key(raw_key)


def generate_password_hash(password: str) -> tuple[str, str]:
    salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), 200_000)
    return key.hex(), salt


def verify_password(password: str, salt: str, expected_hash: str) -> bool:
    if not salt or not expected_hash:
        return False
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), 200_000)
    return secrets.compare_digest(key.hex(), expected_hash)


def _client_jwt_secret() -> str:
    if not settings.client_jwt_secret:
        raise RuntimeError("CLIENT_JWT_SECRET is not configured")
    return settings.client_jwt_secret


def authenticate_admin(auth_header: str | None) -> None:
    token = _extract_bearer_token(auth_header)
    if not token:
        logger.warning("Admin auth rejected: missing_or_invalid_auth_header")
        raise HTTPException(status_code=401, detail="Unauthorized")

    expected_token = os.getenv("ADMIN_API_KEY")
    if not expected_token:
        logger.warning("Admin auth rejected: admin_api_key_not_configured")
        raise HTTPException(status_code=401, detail="Unauthorized")

    if not secrets.compare_digest(token, expected_token):
        logger.warning("Admin auth rejected: invalid_admin_api_key")
        raise HTTPException(status_code=401, detail="Unauthorized")


def require_admin(authorization: str | None = Header(None)) -> None:
    authenticate_admin(authorization)


def _is_client_subscription_active(client) -> bool:
    if not client.billing_enabled:
        return False

    if client.subscription_status not in BILLABLE_ACTIVE_STATUSES:
        return False

    if client.subscription_current_period_end and client.subscription_current_period_end <= datetime.now(timezone.utc):
        return False

    return True


def authenticate_api_key(
    db: Session, auth_header: str | None, service_code: str
) -> tuple[ApiKey | None, Service | None, str | None]:
    token = _extract_bearer_token(auth_header)
    if not token:
        return None, None, "missing_or_invalid_auth_header"

    service = (
        db.query(Service)
        .filter(Service.code == service_code, Service.is_active.is_(True))
        .first()
    )
    if not service:
        return None, None, "service_not_configured"

    key_hash = hash_api_key(token)
    api_key = (
        db.query(ApiKey)
        .options(joinedload(ApiKey.client), joinedload(ApiKey.service))
        .filter(ApiKey.key_hash == key_hash, ApiKey.is_active.is_(True))
        .first()
    )
    if not api_key:
        return None, None, "invalid_api_key"
    if not api_key.client.is_active:
        return None, None, "inactive_client"
    if not _is_client_subscription_active(api_key.client):
        return None, None, "subscription_inactive"
    if api_key.service_id and api_key.service_id != service.id:
        return None, None, "api_key_not_allowed_for_service"
    if api_key.service and not api_key.service.is_active:
        return None, None, "inactive_service"

    return api_key, service, None


def create_client_session_token(db: Session, client: Client, *, invalidate_prior: bool = True) -> tuple[str, datetime, ClientSession]:
    secret = _client_jwt_secret()
    if invalidate_prior:
        (
            db.query(ClientSession)
            .filter(ClientSession.client_id == client.id, ClientSession.is_active.is_(True))
            .update({"is_active": False}, synchronize_session=False)
        )
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=settings.client_session_ttl_seconds)
    jti = secrets.token_urlsafe(16)
    session = ClientSession(client_id=client.id, jti=jti, expires_at=expires_at)
    db.add(session)
    db.commit()
    payload = {
        "sub": str(client.id),
        "jti": jti,
        "exp": int(expires_at.timestamp()),
    }
    token = jwt.encode(payload, secret, algorithm=settings.client_jwt_algorithm)
    return token, expires_at, session


def validate_client_jwt(db: Session, token: str) -> tuple[Client, ClientSession]:
    if not token:
        logger.warning("Client JWT validation failed: missing token")
        raise HTTPException(status_code=401, detail="Missing token")
    secret = _client_jwt_secret()
    try:
        payload = jwt.decode(token, secret, algorithms=[settings.client_jwt_algorithm])
    except PyJWTError as exc:
        logger.warning("Client JWT validation failed: %s", exc)
        raise HTTPException(status_code=401, detail="Invalid token")

    jti = payload.get("jti")
    sub = payload.get("sub")
    if not jti or not sub:
        logger.warning("Client JWT missing claims")
        raise HTTPException(status_code=401, detail="Invalid token")

    session = db.query(ClientSession).filter(ClientSession.jti == jti).first()
    now = datetime.now(timezone.utc)
    expires_at = session.expires_at if session else None
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if not session or not session.is_active or (expires_at and expires_at <= now) or (not expires_at):
        logger.warning("Client session expired or not active")
        raise HTTPException(status_code=401, detail="Session expired")

    client = db.query(Client).filter(Client.id == int(sub)).first()
    if not client:
        logger.warning("Client JWT references unknown client")
        raise HTTPException(status_code=401, detail="Client not found")

    return client, session
