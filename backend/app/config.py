"""Application configuration.

Centralizes the three credentials the backend needs, loaded from environment
variables (or a `.env` file) via pydantic-settings. Environment variables take
precedence over the `.env` file, which is what lets the `op run` workflow
inject real secrets over the `op://` references stored on disk.
"""

__docformat__ = "google"

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed application settings sourced from the environment.

    Field names map case-insensitively to environment variables (e.g.
    `anthropic_api_key` reads `ANTHROPIC_API_KEY`).

    Attributes:
        anthropic_api_key: Anthropic API key used for Claude requests.
        hevy_api_key: Hevy API key sent on every Hevy request.
        tp_auth_cookie: TrainingPeaks `Production_tpAuth` cookie value.
    """

    anthropic_api_key: str
    hevy_api_key: str
    tp_auth_cookie: str

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide `Settings` instance.

    Cached so settings are read from the environment only once and reused as a
    FastAPI dependency.

    Returns:
        The singleton `Settings` instance.
    """
    return Settings()  # type: ignore[call-arg]
