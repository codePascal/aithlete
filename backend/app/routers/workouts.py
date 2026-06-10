"""Workouts endpoint — TrainingPeaks workouts + fitness metrics.

Returns the athlete's TrainingPeaks workouts for the last N days alongside a
daily CTL/ATL/TSB fitness time series and the current fitness snapshot.
"""

__docformat__ = "google"

import asyncio
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query

from app.clients.tp_client import TPClient, TPClientError
from app.config import Settings, get_settings

router = APIRouter()


@router.get("/workouts")
async def get_workouts(
    days: int = Query(default=30, ge=1, le=365),
    settings: Settings = Depends(get_settings),
):
    """Return TrainingPeaks workouts and a fitness series for the last N days.

    Args:
        days: Size of the look-back window in days (1–365, default 30).
        settings: Injected application settings.

    Returns:
        A dict with ``workouts`` (parsed workout list), ``fitness_series``
        (daily TSS/CTL/ATL/TSB), ``current_fitness`` (latest entry plus a TSB
        status, or ``None``), and ``date_range``.

    Raises:
        HTTPException: 502 if the TrainingPeaks API fails.
    """
    end = date.today()
    start = end - timedelta(days=days)

    try:
        async with TPClient() as tp:
            workouts_raw, fitness_raw = await asyncio.gather(
                tp.get_workouts(str(start), str(end)),
                tp.get_fitness(str(start), str(end)),
            )
    except TPClientError as e:
        raise HTTPException(502, f"TrainingPeaks error: {e}")

    workouts = [_parse_workout(w) for w in workouts_raw]

    fitness_series = [
        {
            "date": entry.get("workoutDay", "")[:10],
            "tss": entry.get("tssActual", 0),
            "ctl": round(entry.get("ctl", 0), 1),
            "atl": round(entry.get("atl", 0), 1),
            "tsb": round(entry.get("tsb", 0), 1),
        }
        for entry in fitness_raw
    ]

    current_fitness = None
    if fitness_series:
        latest = fitness_series[-1]
        current_fitness = {**latest, "status": _tsb_status(latest["tsb"])}

    return {
        "workouts": workouts,
        "fitness_series": fitness_series,
        "current_fitness": current_fitness,
        "date_range": {"start": str(start), "end": str(end)},
    }


def _parse_workout(w: dict) -> dict:
    # Flatten a raw TrainingPeaks workout into the API response shape.
    return {
        "id": str(w.get("workoutId", "")),
        "title": w.get("title") or w.get("workoutTypeValueId", "Workout"),
        "date": (w.get("workoutDay") or "")[:10],
        "type": w.get("workoutTypeValueId", "").lower(),
        "tss_planned": w.get("tssPlanned"),
        "tss_actual": w.get("tssActual"),
        "distance_planned_m": w.get("distancePlanned"),
        "distance_actual_m": w.get("distanceActual"),
        "duration_planned_s": w.get("totalTimePlanned"),
        "duration_actual_s": w.get("totalTime"),
        "completed": w.get("tssActual") is not None,
        "description": w.get("description"),
        "coach_comments": w.get("coachComments"),
        "athlete_comments": w.get("athleteComments"),
    }


def _tsb_status(tsb: float) -> str:
    # Map a Training Stress Balance value to a human-readable freshness label.
    if tsb > 25:
        return "Very Fresh"
    if tsb > 10:
        return "Fresh"
    if tsb > 0:
        return "Neutral"
    if tsb > -10:
        return "Tired"
    if tsb > -25:
        return "Very Tired"
    return "Exhausted"
