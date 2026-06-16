from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from backend.app.db import Base, configure_database, init_db
from backend.app.main import app
from backend.app.seed import seed_database


@pytest.fixture()
def client(tmp_path) -> Generator[TestClient, None, None]:
    db_path = tmp_path / "contract-tests.sqlite"
    configure_database(f"sqlite:///{db_path}")
    init_db()
    from backend.app.db import SessionLocal

    db = SessionLocal()
    try:
        seed_database(db)
        db.commit()
    finally:
        db.close()
    with TestClient(app) as test_client:
        yield test_client
    from backend.app.db import engine

    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def admin_headers() -> dict[str, str]:
    return {"X-API-Key": "admin-key"}


@pytest.fixture()
def analyst_headers() -> dict[str, str]:
    return {"X-API-Key": "analyst-key"}


@pytest.fixture()
def integration_headers() -> dict[str, str]:
    return {"X-API-Key": "integration-key"}
