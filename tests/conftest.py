import pytest

from fastapi.testclient import TestClient

from app.db.database import engine, init_db
from app.db.models import Base
from app.main import app


@pytest.fixture(scope="session", autouse=True)
def reset_db():
    Base.metadata.drop_all(bind=engine)
    init_db()
    yield


@pytest.fixture
def client():
    return TestClient(app)
