from fastapi import APIRouter, Header, HTTPException
from app.core.security import validate_api_key
from app.core.usage import increment_usage

router = APIRouter()

@router.post("/transform")
def transform(data: dict, authorization: str = Header(None)):
    if not validate_api_key(authorization):
        raise HTTPException(status_code=401, detail="Invalid API key")

    increment_usage(authorization)

    return {"transformed": str(data).upper()}
