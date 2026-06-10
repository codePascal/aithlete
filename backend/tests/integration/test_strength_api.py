"""Integration tests for GET /api/strength — requires real credentials."""

import pytest

from tests.conftest import requires_credentials


@requires_credentials
def test_strength_returns_200(client):
    resp = client.get("/api/strength")
    assert resp.status_code == 200


@requires_credentials
def test_strength_shape(client):
    resp = client.get("/api/strength")
    data = resp.json()
    assert "exercises" in data
    assert "total_sessions" in data
    assert "date_range" in data
    assert isinstance(data["exercises"], list)
    assert isinstance(data["total_sessions"], int)


@requires_credentials
def test_strength_days_param(client):
    resp = client.get("/api/strength?days=30")
    assert resp.status_code == 200


@requires_credentials
def test_strength_invalid_days_rejected(client):
    resp = client.get("/api/strength?days=6")   # min is 7
    assert resp.status_code == 422

    resp = client.get("/api/strength?days=366")  # max is 365
    assert resp.status_code == 422


@requires_credentials
def test_exercise_entries_have_required_fields(client):
    resp = client.get("/api/strength?days=180")
    exercises = resp.json()["exercises"]
    for ex in exercises:
        assert "id" in ex
        assert "name" in ex
        assert "session_count" in ex
        assert "latest_max_weight_kg" in ex
        assert "latest_1rm" in ex
        assert "pr_1rm" in ex
        assert ex["trend"] in ("up", "down", "neutral")
        assert isinstance(ex["history"], list)


@requires_credentials
def test_exercise_history_entries_are_sorted_by_date(client):
    resp = client.get("/api/strength?days=180")
    exercises = resp.json()["exercises"]
    for ex in exercises:
        dates = [h["date"] for h in ex["history"]]
        assert dates == sorted(dates), f"{ex['name']} history not sorted by date"


@requires_credentials
def test_pr_1rm_is_max_of_history(client):
    resp = client.get("/api/strength?days=180")
    for ex in resp.json()["exercises"]:
        history_max = max((h["estimated_1rm"] for h in ex["history"]), default=0)
        assert ex["pr_1rm"] == pytest.approx(history_max, abs=0.01)
