from fastapi import APIRouter, Header, HTTPException
from app.core.security import validate_api_key
from app.core.usage import increment_usage
from app.core.logger import get_logger

router = APIRouter()
logger = get_logger(__name__)

@router.post("/transform")
def transform(data: dict, authorization: str = Header(None)):
    if not validate_api_key(authorization):
        logger.warning("Unauthorized transform request")
        raise HTTPException(status_code=401, detail="Invalid API key")

    logger.info("Incoming data: %s", data)
    increment_usage(authorization)
    transformed_data = transform_data(data)
    logger.info("Transformed data: %s", transformed_data)

    return {"transformed": transformed_data}

def transform_data(data: dict) -> dict:
    return str(data).upper()
