import os
import tempfile

# Settings are read at import time, so configure the environment first.
_tmp = tempfile.mkdtemp()
os.environ["STW_DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["STW_SECRET_KEY"] = "test-only-secret-key-not-for-production-use"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.api import auth  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.seed import seed  # noqa: E402

PASSWORD = "test-pass-123"


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    auth._failures.clear()
    with SessionLocal() as db:
        seed(db, PASSWORD)
    yield


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def login(client):
    def _login(email: str) -> dict:
        r = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
        assert r.status_code == 200, r.text
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    return _login
