"""TrainingPeaks domain client — a thin wrapper over `tp_mcp.client`.

This module exposes `TPClient`, the only TrainingPeaks entry point the rest of
the app uses. It keeps the surface area small and stable: routers call
high-level methods (`get_workouts`, `get_fitness`, `create_workout`) without
knowing anything about TrainingPeaks' URL scheme, athlete-ID resolution, OAuth
token exchange, or rate limiting — all of which are handled by the vendored
`tp_mcp` library (`backend/vendor/trainingpeaks-mcp`).

Authentication: `tp_mcp` reads the `TP_AUTH_COOKIE` environment variable (the
`Production_tpAuth` cookie value) and exchanges it for a short-lived OAuth
token on first use. This module never touches credentials directly.

Errors: `tp_mcp`'s `APIError` is re-exported here as `TPClientError` so routers
keep a stable import even if the backing library changes.
"""

__docformat__ = "google"

from tp_mcp.client.http import APIError, APIResponse, TPClient as _TPClient

# Re-export as TPClientError so routers don't need to change their import
TPClientError = APIError


class TPClient:
    """Domain wrapper around tp_mcp's `TPClient`.

    Exposes high-level methods (`get_workouts`, `get_fitness`, `create_workout`)
    while delegating all HTTP, authentication, and token-caching to `tp_mcp`.
    Credentials are read from the `TP_AUTH_COOKIE` environment variable by
    `tp_mcp`.

    Use as an async context manager so the underlying HTTP session is opened
    and closed correctly:

    ```python
    async with TPClient() as tp:
        workouts = await tp.get_workouts("2026-01-01", "2026-01-31")
    ```

    Attributes:
        _inner: The wrapped `tp_mcp` client handling transport and auth.
    """

    def __init__(self, timeout: float = 30.0):
        """Initialize the client.

        Args:
            timeout: Per-request timeout in seconds passed to the underlying
                ``tp_mcp`` client.
        """
        self._inner = _TPClient(timeout=timeout)

    async def __aenter__(self) -> "TPClient":
        """Enter the async context, opening the underlying HTTP session.

        Returns:
            The client instance, ready for requests.
        """
        await self._inner.__aenter__()
        return self

    async def __aexit__(self, *args) -> None:
        """Exit the async context, closing the underlying HTTP session.

        Args:
            *args: Standard exception context (type, value, traceback),
                forwarded to the wrapped client.
        """
        await self._inner.__aexit__(*args)

    def _check(self, response: APIResponse, op: str) -> None:
        # Raise TPClientError if the response indicates failure; `op` names the
        # calling operation, used in the fallback message when the response
        # carries none of its own.
        if not response.success:
            raise TPClientError(response.message or f"TP API error: {op}")

    async def get_athlete_id(self) -> int:
        """Resolve the current athlete's numeric ID.

        Returns:
            The athlete ID as an integer.

        Raises:
            TPClientError: If the athlete ID cannot be resolved.
        """
        athlete_id = await self._inner.ensure_athlete_id()
        if athlete_id is None:
            raise TPClientError("Could not resolve athlete ID")
        return int(athlete_id)

    async def get_workouts(self, start_date: str, end_date: str) -> list[dict]:
        """Fetch workouts within an inclusive date range.

        Args:
            start_date: Range start as an ISO date string (``YYYY-MM-DD``).
            end_date: Range end as an ISO date string (``YYYY-MM-DD``).

        Returns:
            A list of workout dicts, or an empty list if none are found.

        Raises:
            TPClientError: If the API request fails.
        """
        athlete_id = await self.get_athlete_id()
        response = await self._inner.get(
            f"/fitness/v6/athletes/{athlete_id}/workouts/{start_date}/{end_date}"
        )
        self._check(response, "get_workouts")
        return response.data if isinstance(response.data, list) else []

    async def create_workout(self, workout: dict) -> dict:
        """Create a planned workout on the athlete's calendar.

        Args:
            workout: The workout payload to POST to TrainingPeaks.

        Returns:
            The created workout dict as returned by the API, or an empty dict
            if the response carries no object body.

        Raises:
            TPClientError: If the API request fails.
        """
        athlete_id = await self.get_athlete_id()
        response = await self._inner.post(
            f"/fitness/v6/athletes/{athlete_id}/workouts", json=workout
        )
        self._check(response, "create_workout")
        return response.data if isinstance(response.data, dict) else {}

    async def get_fitness(self, start_date: str, end_date: str) -> list[dict]:
        """Fetch the daily fitness time series (CTL/ATL/TSB) for a date range.

        Uses fixed performance-management constants (ATL 7 days, CTL 42 days)
        across all workout types.

        Args:
            start_date: Range start as an ISO date string (``YYYY-MM-DD``).
            end_date: Range end as an ISO date string (``YYYY-MM-DD``).

        Returns:
            A list of daily fitness dicts, or an empty list if none are found.

        Raises:
            TPClientError: If the API request fails.
        """
        athlete_id = await self.get_athlete_id()
        response = await self._inner.post(
            f"/fitness/v1/athletes/{athlete_id}/reporting/performancedata/{start_date}/{end_date}",
            json={"atlConstant": 7, "atlStart": 0, "ctlConstant": 42, "ctlStart": 0, "workoutTypes": []},
        )
        self._check(response, "get_fitness")
        return response.data if isinstance(response.data, list) else []
