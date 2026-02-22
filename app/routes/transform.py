from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.core.security import authenticate_api_key
from app.core.usage import increment_usage
from app.core.logger import get_logger
from app.db.database import get_db

router = APIRouter()
logger = get_logger(__name__)

@router.post("/transform")
def transform(
    data: dict,
    authorization: str = Header(None),
    db: Session = Depends(get_db),
):
    api_key, service, auth_error = authenticate_api_key(db, authorization, service_code="ABC-123")
    if auth_error == "service_not_configured":
        logger.error("Transform service is not configured in database")
        raise HTTPException(status_code=503, detail="Service is not configured")
    if auth_error:
        logger.warning("Unauthorized transform request: %s", auth_error)
        raise HTTPException(status_code=401, detail="Invalid API key")

    logger.info("Incoming data: %s", data)
    increment_usage(
        db,
        api_key=api_key,
        service=service,
        endpoint="/transform",
        units=1,
        metadata={"payload_size": len(str(data))},
    )
    transformed_data = transform_data(data)
    logger.info("Transformed data: %s", transformed_data)

    return {"transformed": transformed_data}

def transform_data(data: dict) -> dict:
    return str(data).upper()
