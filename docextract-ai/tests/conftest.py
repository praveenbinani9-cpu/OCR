"""Pytest fixtures: in-memory SQLite engine + FastAPI TestClient with overridden DB."""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure project root is importable
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Provide test env BEFORE importing app
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("S3_ENDPOINT", "http://localhost:9000")
os.environ.setdefault("S3_BUCKET", "test")
os.environ.setdefault("S3_ACCESS_KEY", "test")
os.environ.setdefault("S3_SECRET_KEY", "test")
os.environ.setdefault("JWT_SECRET", "test-secret-please-change")
os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.setdefault("OCR_ENGINE", "tesseract")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402


@pytest.fixture(scope="session")
def engine():
    # SQLite for unit/integration; UUID columns use char(32) representation.
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    from app.models import Base

    Base.metadata.create_all(engine)
    return engine


@pytest.fixture()
def db_session_local(engine):
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = TestingSession()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture()
def client(engine, monkeypatch):
    from app import main as app_main
    from app.api import deps as api_deps
    from app.core import database as core_db

    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app_main.app.dependency_overrides[core_db.get_db] = override_get_db
    monkeypatch.setattr(core_db, "SessionLocal", TestingSession)

    with TestClient(app_main.app) as c:
        yield c

    app_main.app.dependency_overrides.clear()
