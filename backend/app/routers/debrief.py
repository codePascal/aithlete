"""Weekly debrief — AI-generated planned vs completed analysis.

Gathers a target week's TrainingPeaks workouts, Hevy strength sessions, and
CTL/ATL/TSB fitness delta, then streams a structured AI debrief (summary,
compliance, key sessions, fitness trend, next-week focus) over SSE.
"""

__docformat__ = "google"

import asyncio
import json
from datetime import date, timedelta

import anthropic
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.clients.hevy_client import HevyClient, HevyClientError
from app.clients.tp_client import TPClient, TPClientError
from app.config import Settings, get_settings

router = APIRouter()

MODEL = "claude-sonnet-4-6"


class DebriefRequest(BaseModel):
    """Request body for the weekly debrief endpoint.

    Attributes:
        week_offset: Which week to analyze, counting back from the current
            one (0 = this week, 1 = last week, ...).
    """

    week_offset: int = 0  # 0 = current week, 1 = last week, etc.


@router.post("/debrief")
async def generate_debrief(
    request: DebriefRequest,
    settings: Settings = Depends(get_settings),
):
    """Stream an AI weekly debrief as Server-Sent Events.

    Resolves the target week from ``week_offset``, fetches TP and Hevy data
    plus the fitness delta concurrently, then streams Claude's structured
    analysis.

    Args:
        request: Selects the week to analyze via ``week_offset``.
        settings: Injected application settings (API keys).

    Returns:
        A ``text/event-stream`` `StreamingResponse`. Each SSE ``data:`` line is
        a JSON object — a ``delta`` text chunk, a final ``done`` carrying the
        aggregated ``meta`` payload, or an ``error``.

    Raises:
        HTTPException: 502 if the TrainingPeaks or Hevy API fails.
    """
    today = date.today()
    week_start = today - timedelta(days=today.weekday()) - timedelta(weeks=request.week_offset)
    week_end = week_start + timedelta(days=6)

    tp_workouts: list[dict] = []
    fitness_data: list[dict] = []
    hevy_workouts: list[dict] = []

    async def fetch_tp():
        nonlocal tp_workouts, fitness_data
        try:
            async with TPClient() as tp:
                tp_workouts, fitness_data = await asyncio.gather(
                    tp.get_workouts(str(week_start), str(week_end)),
                    tp.get_fitness(str(week_start - timedelta(days=2)), str(week_end)),
                )
        except TPClientError as e:
            raise HTTPException(502, f"TrainingPeaks error: {e}")

    async def fetch_hevy():
        nonlocal hevy_workouts
        try:
            async with HevyClient(settings.hevy_api_key) as hevy:
                all_workouts = await hevy.get_workouts_all(max_pages=5)
                cutoff_start = week_start.isoformat()
                cutoff_end = week_end.isoformat()
                hevy_workouts = [
                    w for w in all_workouts
                    if cutoff_start <= (w.get("start_time") or "")[:10] <= cutoff_end
                ]
        except HevyClientError as e:
            raise HTTPException(502, f"Hevy error: {e}")

    await asyncio.gather(fetch_tp(), fetch_hevy())

    planned = [w for w in tp_workouts if w.get("tssPlanned")]
    completed = [w for w in tp_workouts if w.get("tssActual")]
    tss_planned = sum(w.get("tssPlanned") or 0 for w in planned)
    tss_actual = sum(w.get("tssActual") or 0 for w in completed)

    fitness_start = fitness_data[0] if fitness_data else {}
    fitness_end = fitness_data[-1] if fitness_data else {}

    debrief_data = {
        "week": f"{week_start} to {week_end}",
        "trainingpeaks": {
            "planned_workouts": len(planned),
            "completed_workouts": len(completed),
            "tss_planned": round(tss_planned, 1),
            "tss_actual": round(tss_actual, 1),
            "compliance_rate": round(len(completed) / len(planned), 2) if planned else None,
            "workouts": [
                {
                    "date": (w.get("workoutDay") or "")[:10],
                    "title": w.get("title") or w.get("workoutTypeValueId", "Workout"),
                    "type": w.get("workoutTypeValueId", "").lower(),
                    "tss_planned": w.get("tssPlanned"),
                    "tss_actual": w.get("tssActual"),
                    "completed": w.get("tssActual") is not None,
                    "description": (w.get("description") or "")[:200],
                    "coach_comments": (w.get("coachComments") or "")[:200],
                    "athlete_comments": (w.get("athleteComments") or "")[:200],
                }
                for w in tp_workouts
            ],
        },
        "strength": {
            "sessions": len(hevy_workouts),
            "workouts": [
                {
                    "date": (w.get("start_time") or "")[:10],
                    "title": w.get("title", "Strength"),
                    "exercises": [
                        {
                            "name": ex.get("title", ""),
                            "sets": len(ex.get("sets", [])),
                            "volume_kg": sum(
                                (s.get("weight_kg") or s.get("weight") or 0) * (s.get("reps") or 0)
                                for s in ex.get("sets", [])
                            ),
                        }
                        for ex in w.get("exercises", [])
                    ],
                }
                for w in hevy_workouts
            ],
        },
        "fitness_delta": {
            "ctl_start": round(fitness_start.get("ctl", 0), 1),
            "ctl_end": round(fitness_end.get("ctl", 0), 1),
            "atl_start": round(fitness_start.get("atl", 0), 1),
            "atl_end": round(fitness_end.get("atl", 0), 1),
            "tsb_start": round(fitness_start.get("tsb", 0), 1),
            "tsb_end": round(fitness_end.get("tsb", 0), 1),
        },
    }

    prompt = f"""Generate a comprehensive weekly training debrief for the following data.

<training_data>
{json.dumps(debrief_data, indent=2)}
</training_data>

Structure your analysis as:
1. **Week Summary** — one punchy sentence capturing the week's character
2. **Planned vs Completed** — specific comparison with TSS numbers, what was hit/missed and why it matters
3. **Key Sessions** — highlight 2-3 notable workouts (best performance, biggest miss, or most interesting)
4. **Strength Training** — brief analysis of gym work if present
5. **Fitness Trend** — CTL/ATL/TSB delta interpretation and what it means for next week
6. **Next Week Focus** — 2-3 specific, actionable recommendations based on this week's data

Be direct, data-driven, and specific. No filler text."""

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def stream():
        try:
            async with client.messages.stream(
                model=MODEL,
                max_tokens=1500,
                messages=[{"role": "user", "content": prompt}],
            ) as stream_ctx:
                async for text in stream_ctx.text_stream:
                    yield f"data: {json.dumps({'delta': text})}\n\n"
                yield f"data: {json.dumps({'done': True, 'meta': debrief_data})}\n\n"
        except anthropic.APIError as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
