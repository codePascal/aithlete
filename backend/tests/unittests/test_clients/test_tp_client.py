"""Unit tests for the TPClient domain wrapper (delegates HTTP/auth to tp_mcp)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.clients.tp_client import TPClient, TPClientError
from tp_mcp.client.http import APIResponse


def _ok(data):
    return APIResponse(success=True, data=data)


def _fail(msg="oops"):
    return APIResponse(success=False, message=msg)


@pytest.fixture()
def inner():
    """Mocked tp_mcp TPClient instance injected into our wrapper."""
    mock = AsyncMock()
    mock.__aenter__ = AsyncMock(return_value=mock)
    mock.__aexit__ = AsyncMock(return_value=False)
    return mock


@pytest.fixture()
def client(inner):
    c = TPClient()
    c._inner = inner
    return c


class TestGetAthleteId:
    async def test_returns_id(self, client, inner):
        inner.ensure_athlete_id.return_value = 42
        assert await client.get_athlete_id() == 42

    async def test_raises_when_none(self, client, inner):
        inner.ensure_athlete_id.return_value = None
        with pytest.raises(TPClientError, match="athlete ID"):
            await client.get_athlete_id()


class TestGetWorkouts:
    async def test_returns_list(self, client, inner):
        inner.ensure_athlete_id.return_value = 1
        inner.get.return_value = _ok([{"workoutId": 1}])
        result = await client.get_workouts("2025-01-01", "2025-01-31")
        assert result == [{"workoutId": 1}]

    async def test_empty_on_non_list_data(self, client, inner):
        inner.ensure_athlete_id.return_value = 1
        inner.get.return_value = _ok(None)
        assert await client.get_workouts("2025-01-01", "2025-01-31") == []

    async def test_raises_on_api_error(self, client, inner):
        inner.ensure_athlete_id.return_value = 1
        inner.get.return_value = _fail("not found")
        with pytest.raises(TPClientError, match="not found"):
            await client.get_workouts("2025-01-01", "2025-01-31")


class TestCreateWorkout:
    async def test_returns_dict(self, client, inner):
        inner.ensure_athlete_id.return_value = 1
        inner.post.return_value = _ok({"workoutId": 99})
        result = await client.create_workout({"title": "Test"})
        assert result == {"workoutId": 99}

    async def test_empty_dict_on_non_dict_data(self, client, inner):
        inner.ensure_athlete_id.return_value = 1
        inner.post.return_value = _ok(None)
        assert await client.create_workout({}) == {}

    async def test_raises_on_api_error(self, client, inner):
        inner.ensure_athlete_id.return_value = 1
        inner.post.return_value = _fail("forbidden")
        with pytest.raises(TPClientError, match="forbidden"):
            await client.create_workout({"title": "X"})


class TestGetFitness:
    async def test_returns_list(self, client, inner):
        inner.ensure_athlete_id.return_value = 1
        inner.post.return_value = _ok([{"ctl": 50, "atl": 55, "tsb": -5}])
        result = await client.get_fitness("2025-01-01", "2025-01-31")
        assert result[0]["ctl"] == 50

    async def test_raises_on_api_error(self, client, inner):
        inner.ensure_athlete_id.return_value = 1
        inner.post.return_value = _fail("timeout")
        with pytest.raises(TPClientError, match="timeout"):
            await client.get_fitness("2025-01-01", "2025-01-31")
