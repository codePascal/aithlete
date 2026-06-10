"""FastAPI application entry point.

Creates the app, configures CORS, and mounts every router under the `/api`
prefix. `.env` is loaded before any other import so `tp_mcp`'s credential
lookup finds `TP_AUTH_COOKIE` (and the other secrets) in `os.environ`.
"""

__docformat__ = "google"

from dotenv import load_dotenv

load_dotenv()  # populate os.environ so tp_mcp's credential lookup finds TP_AUTH_COOKIE

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import chat, dashboard, debrief, strength, workouts

app = FastAPI(title="aithlete API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(dashboard.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(workouts.router, prefix="/api")
app.include_router(strength.router, prefix="/api")
app.include_router(debrief.router, prefix="/api")


@app.get("/health")
async def health():
    """Liveness probe.

    Returns:
        A static ``{"status": "ok"}`` payload.
    """
    return {"status": "ok"}
