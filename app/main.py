from fastapi import FastAPI

from app.core.logger import configure_logging
from app.db.database import init_db
from app.routes import admin, billing, health, stripe, transform

app = FastAPI(title="Dummy API SaaS")
configure_logging()


@app.on_event("startup")
def on_startup() -> None:
    init_db()


app.include_router(admin.router)
app.include_router(billing.router)
app.include_router(stripe.admin_router)
app.include_router(stripe.router)
app.include_router(health.router)
app.include_router(transform.router)
