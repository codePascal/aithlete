"""Strength endpoint — Hevy workouts + progressive overload stats.

Pulls Hevy workout history and per-exercise templates, then aggregates each
exercise's sessions into progressive-overload stats: estimated 1RM, max
weight, volume, a recent trend, and the full per-session history.
"""

__docformat__ = "google"

import asyncio
import math
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query

from app.clients.hevy_client import HevyClient, HevyClientError
from app.config import Settings, get_settings

router = APIRouter()


def _epley_1rm(weight: float, reps: int) -> float:
    # Estimate one-rep max via the Epley formula; an exact 1-rep set is its
    # own 1RM.
    if reps == 1:
        return weight
    return round(weight * (1 + reps / 30), 1)


def _parse_set(s: dict) -> dict | None:
    # Normalize a raw Hevy set, returning None when weight or reps are missing
    # or non-numeric so it can be filtered out.
    weight = s.get("weight_kg") or s.get("weight")
    reps = s.get("reps")
    if weight is None or reps is None:
        return None
    try:
        w = float(weight)
        r = int(reps)
    except (ValueError, TypeError):
        return None
    return {
        "reps": r,
        "weight_kg": round(w, 2),
        "type": s.get("type", "normal"),
        "rpe": s.get("rpe"),
    }


@router.get("/strength")
async def get_strength(
    days: int = Query(default=90, ge=7, le=365),
    settings: Settings = Depends(get_settings),
):
    """Return Hevy exercise history with progressive-overload stats.

    Args:
        days: Size of the look-back window in days (7–365, default 90).
        settings: Injected application settings (provides the Hevy API key).

    Returns:
        A dict with ``exercises`` (per-exercise stats sorted by session count,
        each including ``estimated_1rm``, ``pr_1rm``, ``trend``, and full
        ``history``), ``total_sessions``, and ``date_range``.

    Raises:
        HTTPException: 502 if the Hevy API fails.
    """
    cutoff = (date.today() - timedelta(days=days)).isoformat()

    try:
        async with HevyClient(settings.hevy_api_key) as hevy:
            workouts = await hevy.get_workouts_all(max_pages=10)
            templates = await hevy.get_exercise_templates_all()
    except HevyClientError as e:
        raise HTTPException(502, f"Hevy error: {e}")

    template_map = {t["id"]: t["title"] for t in templates}

    # Aggregate per-exercise history from workouts
    exercise_history: dict[str, list[dict]] = {}

    for workout in workouts:
        workout_date = (workout.get("start_time") or "")[:10]
        if workout_date < cutoff:
            continue
        for ex in workout.get("exercises", []):
            tid = ex.get("exercise_template_id") or ex.get("exerciseTemplateId", "")
            if not tid:
                continue
            sets_raw = ex.get("sets", [])
            parsed_sets = [s for s in (_parse_set(s) for s in sets_raw) if s]
            if not parsed_sets:
                continue

            volume = sum(s["weight_kg"] * s["reps"] for s in parsed_sets)
            max_weight = max(s["weight_kg"] for s in parsed_sets)
            best_set = max(parsed_sets, key=lambda s: s["weight_kg"])
            e1rm = _epley_1rm(best_set["weight_kg"], best_set["reps"])

            entry = {
                "date": workout_date,
                "sets": parsed_sets,
                "set_count": len(parsed_sets),
                "volume_kg": round(volume, 1),
                "max_weight_kg": max_weight,
                "estimated_1rm": e1rm,
            }
            exercise_history.setdefault(tid, []).append(entry)

    # Sort history by date and compute trends
    exercises = []
    for tid, history in exercise_history.items():
        history.sort(key=lambda x: x["date"])
        last = history[-1]
        first = history[0]
        trend = "neutral"
        if len(history) >= 2:
            if last["estimated_1rm"] > first["estimated_1rm"] * 1.02:
                trend = "up"
            elif last["estimated_1rm"] < first["estimated_1rm"] * 0.98:
                trend = "down"
        exercises.append({
            "id": tid,
            "name": template_map.get(tid, tid),
            "session_count": len(history),
            "latest_max_weight_kg": last["max_weight_kg"],
            "latest_1rm": last["estimated_1rm"],
            "pr_1rm": max(h["estimated_1rm"] for h in history),
            "trend": trend,
            "history": history,
        })

    exercises.sort(key=lambda x: x["session_count"], reverse=True)

    return {
        "exercises": exercises,
        "total_sessions": len(workouts),
        "date_range": {"start": cutoff, "end": date.today().isoformat()},
    }
