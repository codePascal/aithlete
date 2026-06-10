"""Integration tests for GET /api/dashboard — requires real credentials."""

import pytest

from tests.conftest import requires_credentials


@requires_credentials
def test_dashboard_returns_200(client):
    resp = client.get("/api/dashboard")
    assert resp.status_code == 200


@requires_credentials
def test_dashboard_shape(client):
    resp = client.get("/api/dashboard")
    data = resp.json()

    assert "weekly_tss" in data
    assert "fitness" in data
    assert "recent_workouts" in data
    assert "compliance_rate" in data


@requires_credentials
def test_weekly_tss_is_list_of_8(client):
    resp = client.get("/api/dashboard")
    tss = resp.json()["weekly_tss"]
    assert isinstance(tss, list)
    assert len(tss) == 8
    for entry in tss:
        assert "week" in entry
        assert "planned" in entry
        assert "actual" in entry
        assert isinstance(entry["planned"], (int, float))
        assert isinstance(entry["actual"], (int, float))


@requires_credentials
def test_fitness_has_ctl_atl_tsb(client):
    resp = client.get("/api/dashboard")
    fit = resp.json()["fitness"]
    assert "ctl" in fit
    assert "atl" in fit
    assert "tsb" in fit
    assert "status" in fit
    assert isinstance(fit["ctl"], (int, float))
    assert isinstance(fit["atl"], (int, float))
    assert isinstance(fit["tsb"], (int, float))


@requires_credentials
def test_recent_workouts_have_required_fields(client):
    resp = client.get("/api/dashboard")
    workouts = resp.json()["recent_workouts"]
    assert isinstance(workouts, list)
    for w in workouts:
        assert w["source"] in ("trainingpeaks", "hevy")
        assert "id" in w
        assert "title" in w
        assert "date" in w
        assert "type" in w
        assert "completed" in w
