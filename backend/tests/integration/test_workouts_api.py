"""Integration tests for GET /api/workouts — requires real credentials."""

import pytest

from tests.conftest import requires_credentials


@requires_credentials
def test_workouts_returns_200(client):
    resp = client.get("/api/workouts")
    assert resp.status_code == 200


@requires_credentials
def test_workouts_default_shape(client):
    resp = client.get("/api/workouts")
    data = resp.json()
    assert "workouts" in data
    assert "fitness_series" in data
    assert "date_range" in data


@requires_credentials
def test_workouts_date_range_param(client):
    resp = client.get("/api/workouts?days=14")
    assert resp.status_code == 200
    data = resp.json()
    assert data["date_range"]["start"] is not None
    assert data["date_range"]["end"] is not None


@requires_credentials
def test_workouts_invalid_days_rejected(client):
    resp = client.get("/api/workouts?days=0")
    assert resp.status_code == 422

    resp = client.get("/api/workouts?days=366")
    assert resp.status_code == 422


@requires_credentials
def test_workout_entries_have_required_fields(client):
    resp = client.get("/api/workouts?days=30")
    workouts = resp.json()["workouts"]
    assert isinstance(workouts, list)
    for w in workouts:
        assert "id" in w
        assert "title" in w
        assert "date" in w
        assert "type" in w
        assert "completed" in w


@requires_credentials
def test_fitness_series_entries_have_required_fields(client):
    resp = client.get("/api/workouts?days=30")
    series = resp.json()["fitness_series"]
    assert isinstance(series, list)
    for entry in series:
        assert "date" in entry
        assert "ctl" in entry
        assert "atl" in entry
        assert "tsb" in entry
