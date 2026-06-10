"""Shared fixtures for all tests."""

import os

import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient

# Load .env so integration tests can use real credentials
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))


@pytest.fixture(scope="session")
def client():
    """FastAPI test client (session-scoped — one backend startup per run)."""
    from app.main import app
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


def has_credentials() -> bool:
    return bool(
        os.environ.get("TP_AUTH_COOKIE")
        and os.environ.get("HEVY_API_KEY")
        and os.environ.get("ANTHROPIC_API_KEY")
    )


requires_credentials = pytest.mark.skipif(
    not has_credentials(),
    reason="Real API credentials not found in .env — skipping integration test",
)
