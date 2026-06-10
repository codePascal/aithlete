"""Hevy API client — async access to the Hevy REST API.

This module exposes `HevyClient`, used by the dashboard and strength routers to
pull workout and exercise data from Hevy (https://api.hevyapp.com). Unlike
TrainingPeaks, Hevy uses stateless per-request auth: every call carries an
`api-key` header and there is no token exchange. The key comes from the
`HEVY_API_KEY` environment variable and requires a Hevy PRO subscription.

The client is a small `httpx`-based wrapper and is intended to be used as an
async context manager so the HTTP session is opened and closed cleanly. Most
endpoints are paginated; the `*_all` helpers walk pages until the reported
`page_count` is reached and return a single flat list. Any non-200 response
raises `HevyClientError`.
"""

__docformat__ = "google"

from typing import Any

import httpx

HEVY_BASE = "https://api.hevyapp.com"


class HevyClientError(Exception):
    """Raised when a Hevy API request returns a non-200 response."""


class HevyClient:
    """Async client for the Hevy REST API.

    Authenticates with a per-request `api-key` header (no token exchange).
    Use as an async context manager so the underlying HTTP session is opened
    and closed correctly:

    ```python
    async with HevyClient(api_key) as hevy:
        workouts = await hevy.get_workouts_all(max_pages=8)
    ```
    """

    def __init__(self, api_key: str, timeout: float = 30.0):
        """Initialize the client.

        Args:
            api_key: Hevy API key (requires a Hevy PRO subscription).
            timeout: Per-request timeout in seconds.
        """
        self._api_key = api_key
        self._timeout = timeout
        self._http: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "HevyClient":
        """Enter the async context, opening the HTTP session.

        Returns:
            The client instance, ready for requests.
        """
        self._http = httpx.AsyncClient(
            base_url=HEVY_BASE,
            headers={"api-key": self._api_key, "Accept": "application/json"},
            timeout=self._timeout,
        )
        return self

    async def __aexit__(self, *_: Any) -> None:
        """Exit the async context, closing the HTTP session.

        Args:
            *_: Standard exception context (type, value, traceback); ignored.
        """
        if self._http:
            await self._http.aclose()

    async def _get(self, path: str, params: dict | None = None) -> Any:
        # GET `path` (relative to the Hevy base URL) with optional query params
        # and return the decoded JSON body; raises HevyClientError on any
        # non-200 response.
        assert self._http is not None
        resp = await self._http.get(path, params=params)
        if resp.status_code == 200:
            return resp.json()
        raise HevyClientError(
            f"Hevy API {resp.status_code}: {resp.text[:200]}")

    async def get_workouts(self, page: int = 1, page_size: int = 10) -> dict:
        """Fetch a single page of workouts.

        Args:
            page: 1-based page number.
            page_size: Number of workouts per page.

        Returns:
            The raw paginated response dict (includes ``workouts`` and
            ``page_count``).

        Raises:
            HevyClientError: If the API request fails.
        """
        return await self._get("/v1/workouts", {"page": page, "pageSize": page_size})

    async def get_workouts_all(self, max_pages: int = 5) -> list[dict]:
        """Fetch workouts across pages, newest first.

        Stops early once the reported page count is reached.

        Args:
            max_pages: Maximum number of pages to fetch.

        Returns:
            A flat list of workout dicts.

        Raises:
            HevyClientError: If any underlying API request fails.
        """
        workouts: list[dict] = []
        for page in range(1, max_pages + 1):
            data = await self.get_workouts(page=page, page_size=10)
            batch = data.get("workouts", [])
            workouts.extend(batch)
            if page >= data.get("page_count", 1):
                break
        return workouts

    async def get_workout_count(self) -> int:
        """Fetch the total number of recorded workouts.

        Returns:
            The workout count, or ``0`` if absent from the response.

        Raises:
            HevyClientError: If the API request fails.
        """
        data = await self._get("/v1/workouts/count")
        return data.get("workout_count", 0)

    async def get_exercise_templates(self, page: int = 1, page_size: int = 100) -> dict:
        """Fetch a single page of exercise templates.

        Args:
            page: 1-based page number.
            page_size: Number of templates per page.

        Returns:
            The raw paginated response dict (includes ``exercise_templates``
            and ``page_count``).

        Raises:
            HevyClientError: If the API request fails.
        """
        return await self._get("/v1/exercise-templates", {"page": page, "pageSize": page_size})

    async def get_exercise_templates_all(self) -> list[dict]:
        """Fetch all exercise templates across every page.

        Returns:
            A flat list of exercise template dicts.

        Raises:
            HevyClientError: If any underlying API request fails.
        """
        templates: list[dict] = []
        page = 1
        while True:
            data = await self.get_exercise_templates(page=page, page_size=100)
            batch = data.get("exercise_templates", [])
            templates.extend(batch)
            if page >= data.get("page_count", 1):
                break
            page += 1
        return templates

    async def get_exercise_history(self, exercise_template_id: str, page: int = 1, page_size: int = 20) -> dict:
        """Fetch a single page of history for one exercise.

        Args:
            exercise_template_id: ID of the exercise template to query.
            page: 1-based page number.
            page_size: Number of history events per page.

        Returns:
            The raw paginated response dict (includes ``events`` and
            ``page_count``).

        Raises:
            HevyClientError: If the API request fails.
        """
        return await self._get(
            f"/v1/exercise-history/{exercise_template_id}",
            {"page": page, "pageSize": page_size},
        )

    async def get_exercise_history_all(self, exercise_template_id: str, max_pages: int = 10) -> list[dict]:
        """Fetch history for one exercise across pages.

        Stops early once the reported page count is reached.

        Args:
            exercise_template_id: ID of the exercise template to query.
            max_pages: Maximum number of pages to fetch.

        Returns:
            A flat list of history event dicts.

        Raises:
            HevyClientError: If any underlying API request fails.
        """
        events: list[dict] = []
        for page in range(1, max_pages + 1):
            data = await self.get_exercise_history(exercise_template_id, page=page, page_size=20)
            batch = data.get("events", [])
            events.extend(batch)
            if page >= data.get("page_count", 1):
                break
        return events
