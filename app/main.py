from fastapi import FastAPI
from app.routes import health, transform

app = FastAPI(title="Dummy API SaaS")

app.include_router(health.router)
app.include_router(transform.router)
