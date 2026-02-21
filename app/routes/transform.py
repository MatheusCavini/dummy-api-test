from fastapi import APIRouter, Header, HTTPException
from app.core.security import validate_api_key
from app.core.usage import increment_usage
from app.core.logger import logger
router = APIRouter()

@router.post("/transform")
def transform(data: dict, authorization: str = Header(None)):
    if not validate_api_key(authorization):
        raise HTTPException(status_code=401, detail="Invalid API key")
    logger.info(f"Incoming data: {data}")
    increment_usage(authorization)
    transformed_data = transform_data(data)
    logger.info(f"Transformed data: {transformed_data}")
    return {"transformed": transformed_data}

def transform_data(data: dict) -> dict:
    return str(data).upper()
