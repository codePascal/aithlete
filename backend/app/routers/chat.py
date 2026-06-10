"""AI Coach chat endpoint — SSE streaming with 14-day context + workout creation tool.

Streams Claude coaching responses over Server-Sent Events. Before each turn it
injects the athlete's last 14 days of TrainingPeaks and Hevy data as JSON
context, and it exposes a ``create_workout`` tool so Claude can write planned
workouts straight to the TrainingPeaks calendar.
"""

__docformat__ = "google"

import asyncio
import json
from datetime import date, timedelta
from typing import AsyncIterator

import anthropic
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.clients.hevy_client import HevyClient, HevyClientError
from app.clients.tp_client import TPClient, TPClientError
from app.config import Settings, get_settings

router = APIRouter()

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 2048
CONTEXT_DAYS = 14

# (familyId, typeValueId) from TP API — mirrors trainingpeaks-mcp SPORT_TYPE_MAP
_SPORT_TYPE_MAP: dict[str, tuple[int, int]] = {
    "Swim": (1, 1),
    "Bike": (2, 2),
    "Run": (3, 3),
    "Brick": (4, 4),
    "Crosstrain": (5, 5),
    "Strength": (9, 9),
    "Walk": (13, 13),
    "Rowing": (12, 12),
    "Other": (100, 100),
}

CREATE_WORKOUT_TOOL: dict = {
    "name": "create_workout",
    "description": (
        "Creates a planned workout in TrainingPeaks. "
        "Use this when the athlete asks you to create, schedule, or add a workout to their calendar. "
        "Always confirm the date and sport with the athlete before calling this tool."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Workout title (e.g. 'Threshold Intervals', 'Easy Recovery Run')",
            },
            "date": {
                "type": "string",
                "description": "Workout date in YYYY-MM-DD format",
            },
            "sport": {
                "type": "string",
                "enum": list(_SPORT_TYPE_MAP.keys()),
                "description": "Sport type",
            },
            "duration_minutes": {
                "type": "number",
                "description": "Planned duration in minutes",
            },
            "tss_planned": {
                "type": "number",
                "description": "Planned Training Stress Score",
            },
            "description": {
                "type": "string",
                "description": (
                    "Full workout description: warm-up, main set with targets "
                    "(pace, power, HR zones), cool-down, and any coach notes."
                ),
            },
            "distance_km": {
                "type": "number",
                "description": "Planned distance in kilometres (optional)",
            },
        },
        "required": ["title", "date", "sport", "description"],
    },
}


class Message(BaseModel):
    """A single chat turn in the conversation history.

    Attributes:
        role: Either ``"user"`` or ``"assistant"``.
        content: The message text.
    """

    role: str
    content: str


class ChatRequest(BaseModel):
    """Request body for the chat endpoint.

    Attributes:
        message: The athlete's new message.
        history: Prior turns, oldest first; defaults to empty.
    """

    message: str
    history: list[Message] = []


async def _build_context(settings: Settings) -> str:
    # Fetch the last CONTEXT_DAYS of TP + Hevy data concurrently and serialize
    # a trimmed snapshot (recent workouts, sets, current fitness) to JSON for
    # the system prompt. Fetch failures degrade gracefully to empty sections.
    end = date.today()
    start = end - timedelta(days=CONTEXT_DAYS)

    tp_workouts: list[dict] = []
    fitness_data: list[dict] = []
    hevy_workouts: list[dict] = []

    async def fetch_tp():
        nonlocal tp_workouts, fitness_data
        try:
            async with TPClient() as tp:
                tp_workouts, fitness_data = await asyncio.gather(
                    tp.get_workouts(str(start), str(end)),
                    tp.get_fitness(str(start), str(end)),
                )
        except TPClientError:
            pass

    async def fetch_hevy():
        nonlocal hevy_workouts
        try:
            async with HevyClient(settings.hevy_api_key) as hevy:
                hevy_workouts = await hevy.get_workouts_all(max_pages=3)
        except HevyClientError:
            pass

    await asyncio.gather(fetch_tp(), fetch_hevy())

    cutoff = start.isoformat()
    tp_recent = [
        {
            "date": (w.get("workoutDay") or "")[:10],
            "title": w.get("title") or w.get("workoutTypeValueId", "Workout"),
            "type": w.get("workoutTypeValueId", "").lower(),
            "tss_planned": w.get("tssPlanned"),
            "tss_actual": w.get("tssActual"),
            "duration_min": round((w.get("totalTime") or 0) / 60, 1),
            "completed": w.get("tssActual") is not None,
            "description": (w.get("description") or "")[:300],
            "coach_comments": (w.get("coachComments") or "")[:200],
        }
        for w in tp_workouts
        if (w.get("workoutDay") or "")[:10] >= cutoff
    ]

    hevy_recent = [
        {
            "date": (w.get("start_time") or "")[:10],
            "title": w.get("title", "Strength"),
            "exercises": [
                {
                    "name": ex.get("title", ""),
                    "sets": [
                        {"reps": s.get("reps"), "weight_kg": s.get("weight_kg") or s.get("weight")}
                        for s in ex.get("sets", [])[:5]
                    ],
                }
                for ex in w.get("exercises", [])[:8]
            ],
        }
        for w in hevy_workouts
        if (w.get("start_time") or "")[:10] >= cutoff
    ]

    current_fitness: dict = {}
    if fitness_data:
        latest = fitness_data[-1]
        current_fitness = {
            "ctl": round(latest.get("ctl", 0), 1),
            "atl": round(latest.get("atl", 0), 1),
            "tsb": round(latest.get("tsb", 0), 1),
        }

    return json.dumps(
        {
            "today": str(end),
            "context_window": f"{start} to {end}",
            "current_fitness": current_fitness,
            "training_peaks_workouts": tp_recent,
            "hevy_strength_workouts": hevy_recent,
        },
        indent=2,
    )


SYSTEM_PROMPT = """You are an elite AI training coach with deep expertise in endurance sports, strength training, and periodization. You have direct access to the athlete's recent training data from TrainingPeaks and Hevy.

Your coaching philosophy:
- Data-driven but athlete-centered
- Honest about fatigue, recovery, and realistic expectations
- Specific and actionable — no generic advice
- Understand TSS, CTL/ATL/TSB, progressive overload, and periodization

You can also CREATE workouts directly on the athlete's TrainingPeaks calendar using the create_workout tool. When an athlete asks you to schedule, add, or create a workout, use this tool. Always write a detailed, coach-quality description including warm-up, main set with specific targets (power zones, pace, HR), and cool-down.

The athlete's last {days} days of training data is provided below as JSON context. Use it to give personalized, specific coaching advice.

<athlete_data>
{context}
</athlete_data>

Today's date: {today}

Respond conversationally but with precision. Reference specific workouts, numbers, and trends when relevant."""


async def _execute_create_workout(tool_input: dict, settings: Settings) -> dict:
    # Translate the create_workout tool input into a TP workout payload, POST
    # it, and return a result dict ({success, workout_id, ...} or
    # {success: False, error}).
    sport = tool_input.get("sport", "Other")
    family_id, type_id = _SPORT_TYPE_MAP.get(sport, (100, 100))
    workout_date = tool_input["date"]

    payload: dict = {
        "workoutDay": f"{workout_date}T00:00:00",
        "title": tool_input["title"],
        "workoutTypeFamilyId": family_id,
        "workoutTypeValueId": type_id,
        "description": tool_input.get("description", ""),
    }
    if tool_input.get("tss_planned") is not None:
        payload["tssPlanned"] = float(tool_input["tss_planned"])
    if tool_input.get("duration_minutes") is not None:
        payload["totalTimePlanned"] = int(tool_input["duration_minutes"] * 60)
    if tool_input.get("distance_km") is not None:
        payload["distancePlanned"] = float(tool_input["distance_km"]) * 1000

    try:
        async with TPClient() as tp:
            result = await tp.create_workout(payload)
        return {
            "success": True,
            "workout_id": str(result.get("workoutId", "")),
            "title": tool_input["title"],
            "date": workout_date,
            "sport": sport,
            "tss_planned": tool_input.get("tss_planned"),
            "duration_minutes": tool_input.get("duration_minutes"),
        }
    except TPClientError as e:
        return {"success": False, "error": str(e)}


async def _stream_response(request: ChatRequest, settings: Settings) -> AsyncIterator[str]:
    # Build the system prompt + message list and yield SSE chunks, converting
    # any Anthropic API error into a terminal {error} event.
    context = await _build_context(settings)
    system = SYSTEM_PROMPT.format(days=CONTEXT_DAYS, context=context, today=str(date.today()))

    messages: list[dict] = [
        {"role": m.role, "content": m.content}
        for m in request.history
        if m.role in ("user", "assistant")
    ]
    messages.append({"role": "user", "content": request.message})

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    try:
        async for event in _run_with_tools(client, system, messages, settings):
            yield event
    except anthropic.APIError as e:
        yield f"data: {json.dumps({'error': str(e)})}\n\n"


async def _run_with_tools(
    client: anthropic.AsyncAnthropic,
    system: str,
    messages: list[dict],
    settings: Settings,
) -> AsyncIterator[str]:
    # Stream Claude's reply as SSE; if it stops for tool use, run each tool
    # (currently only create_workout), feed results back, and stream the
    # follow-up turn. Emits delta/tool_start/tool_done/done events.
    async with client.messages.stream(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=system,
        messages=messages,
        tools=[CREATE_WORKOUT_TOOL],
    ) as stream:
        async for text in stream.text_stream:
            yield f"data: {json.dumps({'delta': text})}\n\n"

        final = await stream.get_final_message()

    if final.stop_reason != "tool_use":
        yield f"data: {json.dumps({'done': True})}\n\n"
        return

    # Collect tool use blocks
    tool_blocks = [b for b in final.content if b.type == "tool_use"]

    # Build assistant message with full content (text + tool_use blocks)
    assistant_content = [b.model_dump() for b in final.content]
    messages = messages + [{"role": "assistant", "content": assistant_content}]

    tool_results = []
    for block in tool_blocks:
        yield f"data: {json.dumps({'tool_start': {'name': block.name, 'input': block.input}})}\n\n"

        if block.name == "create_workout":
            result = await _execute_create_workout(block.input, settings)
        else:
            result = {"error": f"Unknown tool: {block.name}"}

        yield f"data: {json.dumps({'tool_done': result})}\n\n"

        tool_results.append({
            "type": "tool_result",
            "tool_use_id": block.id,
            "content": json.dumps(result),
        })

    messages = messages + [{"role": "user", "content": tool_results}]

    # Second stream — Claude's response after seeing tool results
    async with client.messages.stream(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=system,
        messages=messages,
        tools=[CREATE_WORKOUT_TOOL],
    ) as stream2:
        async for text in stream2.text_stream:
            yield f"data: {json.dumps({'delta': text})}\n\n"

    yield f"data: {json.dumps({'done': True})}\n\n"


@router.post("/chat")
async def chat(request: ChatRequest, settings: Settings = Depends(get_settings)):
    """Stream an AI coaching reply as Server-Sent Events.

    Args:
        request: The athlete's message plus prior conversation history.
        settings: Injected application settings (API keys).

    Returns:
        A ``text/event-stream`` `StreamingResponse`. Each SSE ``data:`` line is
        a JSON object — a ``delta`` text chunk, a ``tool_start`` / ``tool_done``
        pair when a workout is created, a final ``done``, or an ``error``.
    """
    return StreamingResponse(
        _stream_response(request, settings),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
