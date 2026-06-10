"""Shared helpers for the 1Password tooling scripts.

Reads the service-account token and Environment ID from .env.1password.local and
fetches a 1Password Environment's variables via the 1Password Python SDK.
"""

from __future__ import annotations

import sys
from pathlib import Path

LOCAL_FILE = Path(__file__).resolve().parent.parent / ".env.1password.local"

INTEGRATION_NAME = "aithlete-backend"
INTEGRATION_VERSION = "v1.0.0"


def load_credentials() -> tuple[str, str]:
    """Return ``(service_account_token, environment_id)`` from .env.1password.local.

    Exits the process with a helpful message if the file or either value is
    missing. Secret values are returned to the caller but never printed here.
    """
    if not LOCAL_FILE.exists():
        sys.exit(
            f"Credentials file not found: {LOCAL_FILE}\n"
            "Run ./scripts/setup-auth.sh first, then fill in your keys."
        )

    values: dict[str, str] = {}
    for raw in LOCAL_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        values[key.strip()] = val.strip()

    token = values.get("OP_SERVICE_ACCOUNT_TOKEN", "")
    environment_id = values.get("OP_ENVIRONMENT_ID", "")
    if not token:
        sys.exit(
            "OP_SERVICE_ACCOUNT_TOKEN is empty in .env.1password.local\n"
            "Run ./scripts/setup-auth.sh and paste your service-account token."
        )
    if not environment_id:
        sys.exit(
            "OP_ENVIRONMENT_ID is empty in .env.1password.local\n"
            "Copy it from 1Password: Developer > Environments > Manage environment > Copy environment ID."
        )
    return token, environment_id


async def fetch_environment_variables(token: str, environment_id: str) -> dict[str, str]:
    """Authenticate with the service account and return the Environment's variables.

    Returns a ``{name: value}`` mapping of every variable defined in the given
    1Password Environment.
    """
    from onepassword.client import Client

    client = await Client.authenticate(
        auth=token,
        integration_name=INTEGRATION_NAME,
        integration_version=INTEGRATION_VERSION,
    )
    response = await client.environments.get_variables(environment_id)
    return {var.name: var.value for var in response.variables}
