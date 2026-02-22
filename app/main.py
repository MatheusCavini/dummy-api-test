from fastapi import FastAPI
from app.routes import health, transform
from app.core.logger import configure_logging

app = FastAPI(title="Dummy API SaaS")
configure_logging()

app.include_router(health.router)
app.include_router(transform.router)
