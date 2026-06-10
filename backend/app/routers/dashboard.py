"""Dashboard endpoint — unified stats from TP + Hevy.

Aggregates TrainingPeaks and Hevy data into a single overview: an 8-week TSS
chart, current CTL/ATL/TSB fitness, planned-vs-completed compliance, and the
most recent workouts from both sources.
"""

__docformat__ = "google"

import asyncio
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException

from app.clients.hevy_client import HevyClient, HevyClientError
from app.clients.tp_client import TPClient, TPClientError
from app.config import Settings, get_settings

router = APIRouter()


def _tp_workout_to_summary(w: dict) -> dict:
    # Flatten a raw TrainingPeaks workout into the dashboard summary shape.
    return {
        "source": "trainingpeaks",
        "id": str(w.get("workoutId", "")),
        "title": w.get("title") or w.get("workoutTypeValueId", "Workout"),
        "date": (w.get("workoutDay") or "")[:10],
        "type": w.get("workoutTypeValueId", "").lower(),
        "tss_planned": w.get("tssPlanned"),
        "tss_actual": w.get("tssActual"),
        "duration_minutes": round((w.get("totalTimePlanned") or w.get("totalTime") or 0) / 60, 1),
        "completed": w.get("completedWorkout") is not None or w.get("tssActual") is not None,
    }


def _hevy_workout_to_summary(w: dict) -> dict:
    # Flatten a raw Hevy workout into the dashboard summary shape (always
    # treated as completed strength work).
    start = w.get("start_time", "")
    exercises = w.get("exercises", [])
    return {
        "source": "hevy",
        "id": w.get("id", ""),
        "title": w.get("title", "Strength"),
        "date": start[:10],
        "type": "strength",
        "tss_planned": None,
        "tss_actual": None,
        "duration_minutes": _hevy_duration(w),
        "completed": True,
        "exercise_count": len(exercises),
    }


def _hevy_duration(w: dict) -> float:
    # Compute a Hevy session's duration in minutes from its start/end
    # timestamps; returns 0.0 if either is missing or unparseable.
    try:
        from datetime import datetime
        s = datetime.fromisoformat(w["start_time"].replace("Z", "+00:00"))
        e = datetime.fromisoformat(w["end_time"].replace("Z", "+00:00"))
        return round((e - s).total_seconds() / 60, 1)
    except Exception:
        return 0.0


@router.get("/dashboard")
async def get_dashboard(settings: Settings = Depends(get_settings)):
    """Return a unified training overview from TrainingPeaks and Hevy.

    Fetches the last 8 weeks of TP workouts/fitness and recent Hevy workouts
    concurrently, then derives the dashboard panels.

    Args:
        settings: Injected application settings (provides the Hevy API key).

    Returns:
        A dict with ``weekly_tss`` (8-week planned/actual series), ``fitness``
        (current CTL/ATL/TSB plus status), ``compliance_rate`` (completed ÷
        planned over the window, or ``None``), and ``recent_workouts`` (the 20
        most recent workouts across both sources).

    Raises:
        HTTPException: 502 if either the TrainingPeaks or Hevy API fails.
    """
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    eight_weeks_ago = today - timedelta(weeks=8)
    seven_days_ago = today - timedelta(days=7)

    tp_workouts_raw: list[dict] = []
    fitness_data: list[dict] = []
    hevy_workouts_raw: list[dict] = []

    async def fetch_tp():
        nonlocal tp_workouts_raw, fitness_data
        try:
            async with TPClient() as tp:
                tp_workouts_raw, fitness_data = await asyncio.gather(
                    tp.get_workouts(str(eight_weeks_ago), str(today)),
                    tp.get_fitness(str(eight_weeks_ago), str(today)),
                )
        except TPClientError as e:
            raise HTTPException(502, f"TrainingPeaks error: {e}")

    async def fetch_hevy():
        nonlocal hevy_workouts_raw
        try:
            async with HevyClient(settings.hevy_api_key) as hevy:
                hevy_workouts_raw = await hevy.get_workouts_all(max_pages=8)
        except HevyClientError as e:
            raise HTTPException(502, f"Hevy error: {e}")

    await asyncio.gather(fetch_tp(), fetch_hevy())

    # --- Weekly TSS chart (8 weeks) ---
    weekly_tss: list[dict] = []
    for i in range(7, -1, -1):
        ws = today - timedelta(weeks=i + 1) - \
            timedelta(days=(today - timedelta(weeks=i + 1)).weekday())
        we = ws + timedelta(days=6)
        label = ws.strftime("W%W")
        planned = sum(
            w.get("tssPlanned") or 0
            for w in tp_workouts_raw
            if ws.isoformat() <= (w.get("workoutDay") or "")[:10] <= we.isoformat()
        )
        actual = sum(
            w.get("tssActual") or 0
            for w in tp_workouts_raw
            if ws.isoformat() <= (w.get("workoutDay") or "")[:10] <= we.isoformat()
        )
        weekly_tss.append({"week": label, "planned": round(
            planned, 1), "actual": round(actual, 1)})

    # --- Current fitness (CTL/ATL/TSB) ---
    current_fitness = {"ctl": 0.0, "atl": 0.0, "tsb": 0.0, "status": "No data"}
    if fitness_data:
        latest = fitness_data[-1]
        tsb = round(latest.get("tsb", 0), 1)
        current_fitness = {
            "ctl": round(latest.get("ctl", 0), 1),
            "atl": round(latest.get("atl", 0), 1),
            "tsb": tsb,
            "status": _tsb_status(tsb),
        }

    # --- Compliance rate (last 8 weeks) ---
    tp_planned = [w for w in tp_workouts_raw if w.get("tssPlanned")]
    tp_completed = [w for w in tp_planned if w.get("tssActual")]
    compliance = round(len(tp_completed) / len(tp_planned),
                       2) if tp_planned else None

    # --- Recent workouts (last 7 days) ---
    cutoff = seven_days_ago.isoformat()
    recent_tp = [
        _tp_workout_to_summary(w)
        for w in tp_workouts_raw
        if (w.get("workoutDay") or "")[:10] >= cutoff
    ]
    recent_hevy = [
        _hevy_workout_to_summary(w)
        for w in hevy_workouts_raw
        if (w.get("start_time") or "")[:10] >= cutoff
    ]
    recent = sorted(recent_tp + recent_hevy,
                    key=lambda x: x["date"], reverse=True)[:20]

    return {
        "weekly_tss": weekly_tss,
        "fitness": current_fitness,
        "compliance_rate": compliance,
        "recent_workouts": recent,
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
