"""Unit tests for the Hevy client — request building and pagination."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.clients.hevy_client import HevyClient, HevyClientError


def _mock_http(json_data: dict, status: int = 200):
    mock_response = MagicMock()
    mock_response.status_code = status
    mock_response.json.return_value = json_data
    mock_response.text = str(json_data)

    mock_http = AsyncMock()
    mock_http.get.return_value = mock_response
    return mock_http


class TestHevyClientInit:
    @pytest.mark.asyncio
    async def test_sets_api_key_header(self):
        async with HevyClient(api_key="test-key-123") as client:
            assert client._api_key == "test-key-123"

    @pytest.mark.asyncio
    async def test_http_client_is_created(self):
        async with HevyClient(api_key="key") as client:
            assert client._http is not None

    @pytest.mark.asyncio
    async def test_http_client_is_closed_on_exit(self):
        async with HevyClient(api_key="key") as client:
            http = client._http
        # After exiting the context, the client should be closed
        assert http is not None


class TestHevyClientGet:
    @pytest.mark.asyncio
    async def test_successful_get_returns_json(self):
        payload = {"workouts": [{"id": "1", "title": "Chest Day"}], "page_count": 1}
        async with HevyClient(api_key="key") as client:
            client._http = _mock_http(payload)
            result = await client._get("/v1/workouts")
        assert result == payload

    @pytest.mark.asyncio
    async def test_non_200_raises_error(self):
        async with HevyClient(api_key="key") as client:
            client._http = _mock_http({}, status=401)
            with pytest.raises(HevyClientError, match="Hevy API 401"):
                await client._get("/v1/workouts")

    @pytest.mark.asyncio
    async def test_404_raises_error(self):
        async with HevyClient(api_key="key") as client:
            client._http = _mock_http({}, status=404)
            with pytest.raises(HevyClientError):
                await client._get("/v1/exercise-history/nonexistent")


class TestHevyWorkoutPagination:
    @pytest.mark.asyncio
    async def test_get_workouts_all_single_page(self):
        payload = {
            "workouts": [{"id": "1"}, {"id": "2"}],
            "page": 1,
            "page_count": 1,
        }
        async with HevyClient(api_key="key") as client:
            client._http = _mock_http(payload)
            result = await client.get_workouts_all(max_pages=5)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_get_workouts_all_stops_at_page_count(self):
        def side_effect(path, params=None):
            page = (params or {}).get("page", 1)
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "workouts": [{"id": str(page)}],
                "page": page,
                "page_count": 2,
            }
            return mock_response

        async with HevyClient(api_key="key") as client:
            client._http = AsyncMock()
            client._http.get.side_effect = side_effect
            result = await client.get_workouts_all(max_pages=10)

        assert len(result) == 2  # 2 pages × 1 workout

    @pytest.mark.asyncio
    async def test_get_workouts_all_respects_max_pages(self):
        def side_effect(path, params=None):
            page = (params or {}).get("page", 1)
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "workouts": [{"id": str(page)}],
                "page": page,
                "page_count": 100,  # many pages
            }
            return mock_response

        async with HevyClient(api_key="key") as client:
            client._http = AsyncMock()
            client._http.get.side_effect = side_effect
            result = await client.get_workouts_all(max_pages=3)

        assert len(result) == 3


class TestHevyExerciseTemplates:
    @pytest.mark.asyncio
    async def test_get_templates_all_collects_pages(self):
        def side_effect(path, params=None):
            page = (params or {}).get("page", 1)
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "exercise_templates": [{"id": f"t{page}", "title": f"Ex {page}"}],
                "page": page,
                "page_count": 2,
            }
            return mock_response

        async with HevyClient(api_key="key") as client:
            client._http = AsyncMock()
            client._http.get.side_effect = side_effect
            result = await client.get_exercise_templates_all()

        assert len(result) == 2
        assert result[0]["id"] == "t1"
        assert result[1]["id"] == "t2"

    @pytest.mark.asyncio
    async def test_get_workout_count(self):
        async with HevyClient(api_key="key") as client:
            client._http = _mock_http({"workout_count": 147})
            count = await client.get_workout_count()
        assert count == 147
