"""Tests for kbase.web — FastAPI endpoints (unit tests with TestClient)."""
import pytest


@pytest.fixture
def client():
    """Create FastAPI test client.

    Note: This requires the server to be importable. Some endpoints need
    a real store, so we only test stateless/config endpoints here.
    """
    try:
        from fastapi.testclient import TestClient

        from kbase.web import create_app
        app = create_app()
        return TestClient(app)
    except Exception:
        pytest.skip("FastAPI app not importable (missing deps or store init)")


class TestVersionEndpoint:
    def test_version_returns_200(self, client):
        resp = client.get("/api/version")
        assert resp.status_code == 200
        data = resp.json()
        assert "version" in data


class TestStaticFiles:
    def test_index_html_served(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "KBase" in resp.text
