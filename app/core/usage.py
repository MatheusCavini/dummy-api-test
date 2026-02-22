import json

from sqlalchemy.orm import Session

from app.db.models import ApiKey, Service, UsageEvent


def increment_usage(
    db: Session,
    api_key: ApiKey,
    service: Service,
    endpoint: str,
    units: int = 1,
    metadata: dict | None = None,
) -> UsageEvent:
    event = UsageEvent(
        client_id=api_key.client_id,
        api_key_id=api_key.id,
        service_id=service.id,
        endpoint=endpoint,
        units=max(units, 1),
        metadata_json=json.dumps(metadata) if metadata else None,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event
