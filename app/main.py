from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.core.logger import configure_logging
from app.db.database import init_db
from app.routes import admin, billing, clients, health, stripe, transform

app = FastAPI(title="Dummy API SaaS")
configure_logging()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_origin_regex=settings.cors_allow_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    init_db()


app.include_router(admin.router)
app.include_router(billing.router)
app.include_router(stripe.admin_router)
app.include_router(stripe.router)
app.include_router(clients.router)
app.include_router(health.router)
app.include_router(transform.router)
