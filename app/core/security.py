import hashlib
import os
import secrets
from datetime import datetime, timezone

from fastapi import Header, HTTPException
from sqlalchemy.orm import Session, joinedload

from app.core.logger import get_logger
from app.db.models import ApiKey, Service


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
