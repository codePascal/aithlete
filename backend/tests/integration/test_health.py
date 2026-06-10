"""Integration tests that always run — no credentials needed."""


def test_health_endpoint(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_openapi_schema_available(client):
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    schema = resp.json()
    assert "paths" in schema
    # All five routes must be registered
    paths = schema["paths"]
    assert "/api/dashboard" in paths
    assert "/api/workouts" in paths
    assert "/api/strength" in paths
    assert "/api/chat" in paths
    assert "/api/debrief" in paths
