#!/usr/bin/env python
"""op_run.py — run a command with API keys injected from a 1Password Environment.

Reads OP_SERVICE_ACCOUNT_TOKEN and OP_ENVIRONMENT_ID from .env.1password.local,
fetches every variable in that 1Password Environment via the 1Password Python
SDK, injects them into the environment, then runs the wrapped command. The
secrets exist only in the child process's environment and are never printed.

Usage (from the backend/ directory):
    python scripts/op_run.py poetry run uvicorn app.main:app --reload --port 8000
    python scripts/op_run.py poetry run pytest tests/integration/ -v
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
from pathlib import Path

from auth import fetch_environment_variables, load_credentials


def main() -> None:
    argv = sys.argv[1:]
    if not argv:
        sys.exit("Usage: python scripts/op_run.py <command> [args...]")

    token, environment_id = load_credentials()

    try:
        secrets = asyncio.run(fetch_environment_variables(token, environment_id))
    except Exception as exc:  # noqa: BLE001 - surface any SDK/auth/network failure
        sys.exit(f"Failed to read 1Password Environment: {exc}")

    # Inject the Environment's variables, letting any value already set in the
    # surrounding environment win (explicit overrides take precedence).
    env = os.environ.copy()
    for name, value in secrets.items():
        env.setdefault(name, value)

    # Resolve the command against PATH (handles poetry.exe/.cmd, docker, etc.)
    # so it runs the same way as it would from an interactive shell.
    exe = shutil.which(argv[0])
    if exe is None:
        sys.exit(f"Command not found on PATH: {argv[0]}")

    result = subprocess.run([exe, *argv[1:]], env=env)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
