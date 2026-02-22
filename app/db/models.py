from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    api_keys: Mapped[list["ApiKey"]] = relationship("ApiKey", back_populates="client", cascade="all, delete-orphan")
    usage_events: Mapped[list["UsageEvent"]] = relationship("UsageEvent", back_populates="client")


class Service(Base):
    __tablename__ = "services"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    code: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    unit_price: Mapped[Numeric] = mapped_column(Numeric(12, 4), nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    api_keys: Mapped[list["ApiKey"]] = relationship("ApiKey", back_populates="service")
    usage_events: Mapped[list["UsageEvent"]] = relationship("UsageEvent", back_populates="service")


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), nullable=False, index=True)
    service_id: Mapped[int | None] = mapped_column(ForeignKey("services.id"), nullable=True, index=True)
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    prefix: Mapped[str] = mapped_column(String(32), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    revoked_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    client: Mapped["Client"] = relationship("Client", back_populates="api_keys")
    service: Mapped["Service | None"] = relationship("Service", back_populates="api_keys")
    usage_events: Mapped[list["UsageEvent"]] = relationship("UsageEvent", back_populates="api_key")


class UsageEvent(Base):
    __tablename__ = "usage_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), nullable=False, index=True)
    api_key_id: Mapped[int] = mapped_column(ForeignKey("api_keys.id"), nullable=False, index=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"), nullable=False, index=True)
    endpoint: Mapped[str] = mapped_column(String(255), nullable=False)
    units: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    client: Mapped["Client"] = relationship("Client", back_populates="usage_events")
    api_key: Mapped["ApiKey"] = relationship("ApiKey", back_populates="usage_events")
    service: Mapped["Service"] = relationship("Service", back_populates="usage_events")
