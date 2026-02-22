from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.security import generate_api_key, require_admin
from app.db.database import get_db
from app.db.models import ApiKey, Client, Service


router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


class ClientCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    email: str = Field(min_length=3, max_length=255)


class ClientUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    email: str | None = Field(default=None, min_length=3, max_length=255)
    is_active: bool | None = None


class ClientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str
    is_active: bool
    created_at: datetime


class ServiceCreate(BaseModel):
    code: str = Field(min_length=2, max_length=100)
    name: str = Field(min_length=1, max_length=255)
    unit_price: Decimal = Field(ge=0)
    is_active: bool = True


class ServiceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    unit_price: Decimal | None = Field(default=None, ge=0)
    is_active: bool | None = None


class ServiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    unit_price: Decimal
    is_active: bool
    created_at: datetime


class ApiKeyCreate(BaseModel):
    service_code: str | None = None


class ApiKeyOut(BaseModel):
    id: int
    prefix: str
    client_id: int
    service_id: int | None
    is_active: bool
    created_at: datetime
    revoked_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class ApiKeyCreateOut(BaseModel):
    key_id: int
    api_key: str
    prefix: str
    client_id: int
    service_code: str | None
    created_at: datetime


@router.post("/clients", response_model=ClientOut, status_code=status.HTTP_201_CREATED)
def create_client(payload: ClientCreate, db: Session = Depends(get_db)):
    existing_client = db.query(Client).filter(Client.email == payload.email).first()
    if existing_client:
        raise HTTPException(status_code=400, detail="Email already exists")

    client = Client(name=payload.name, email=payload.email)
    db.add(client)
    db.commit()
    db.refresh(client)
    return client


@router.get("/clients", response_model=list[ClientOut])
def list_clients(db: Session = Depends(get_db)):
    return db.query(Client).order_by(Client.created_at.desc()).all()


@router.patch("/clients/{client_id}", response_model=ClientOut)
def update_client(client_id: int, payload: ClientUpdate, db: Session = Depends(get_db)):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    if payload.email and payload.email != client.email:
        duplicate = db.query(Client).filter(Client.email == payload.email).first()
        if duplicate:
            raise HTTPException(status_code=400, detail="Email already exists")
        client.email = payload.email
    if payload.name is not None:
        client.name = payload.name
    if payload.is_active is not None:
        client.is_active = payload.is_active

    db.commit()
    db.refresh(client)
    return client


@router.post("/services", response_model=ServiceOut, status_code=status.HTTP_201_CREATED)
def create_service(payload: ServiceCreate, db: Session = Depends(get_db)):
    existing_service = db.query(Service).filter(Service.code == payload.code).first()
    if existing_service:
        raise HTTPException(status_code=400, detail="Service code already exists")

    service = Service(
        code=payload.code,
        name=payload.name,
        unit_price=payload.unit_price,
        is_active=payload.is_active,
    )
    db.add(service)
    db.commit()
    db.refresh(service)
    return service


@router.get("/services", response_model=list[ServiceOut])
def list_services(db: Session = Depends(get_db)):
    return db.query(Service).order_by(Service.created_at.desc()).all()


@router.patch("/services/{service_id}", response_model=ServiceOut)
def update_service(service_id: int, payload: ServiceUpdate, db: Session = Depends(get_db)):
    service = db.query(Service).filter(Service.id == service_id).first()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")

    if payload.name is not None:
        service.name = payload.name
    if payload.unit_price is not None:
        service.unit_price = payload.unit_price
    if payload.is_active is not None:
        service.is_active = payload.is_active

    db.commit()
    db.refresh(service)
    return service


@router.post("/clients/{client_id}/api-keys", response_model=ApiKeyCreateOut, status_code=status.HTTP_201_CREATED)
def create_api_key(client_id: int, payload: ApiKeyCreate, db: Session = Depends(get_db)):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    service = None
    if payload.service_code:
        service = db.query(Service).filter(Service.code == payload.service_code).first()
        if not service:
            raise HTTPException(status_code=404, detail="Service not found")

    raw_key, prefix, key_hash = generate_api_key()
    key = ApiKey(
        client_id=client.id,
        service_id=service.id if service else None,
        key_hash=key_hash,
        prefix=prefix,
    )
    db.add(key)
    db.commit()
    db.refresh(key)

    return ApiKeyCreateOut(
        key_id=key.id,
        api_key=raw_key,
        prefix=key.prefix,
        client_id=key.client_id,
        service_code=service.code if service else None,
        created_at=key.created_at,
    )


@router.get("/clients/{client_id}/api-keys", response_model=list[ApiKeyOut])
def list_client_api_keys(client_id: int, db: Session = Depends(get_db)):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    return db.query(ApiKey).filter(ApiKey.client_id == client_id).order_by(ApiKey.created_at.desc()).all()


@router.post("/api-keys/{api_key_id}/revoke", response_model=ApiKeyOut)
def revoke_api_key(api_key_id: int, db: Session = Depends(get_db)):
    api_key = db.query(ApiKey).filter(ApiKey.id == api_key_id).first()
    if not api_key:
        raise HTTPException(status_code=404, detail="API key not found")
    if not api_key.is_active:
        return api_key

    api_key.is_active = False
    api_key.revoked_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(api_key)
    return api_key
