#!/usr/bin/env python
"""test_connection.py — verify 1Password auth and Environment key availability.

Authenticates with the stored service-account token, reads the configured
1Password Environment via the SDK, and reports which of the backend's expected
keys are present. Only key names and presence (available / missing) are printed —
never the secret values.

Usage (from the backend/ directory):
    python scripts/test_connection.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from auth import fetch_environment_variables, load_credentials

# Keys the backend reads from the environment (see app/config.py).
EXPECTED_KEYS = ["ANTHROPIC_API_KEY", "HEVY_API_KEY", "TP_AUTH_COOKIE"]


def main() -> None:
    token, environment_id = load_credentials()

    print("Testing 1Password connection...")
    try:
        secrets = asyncio.run(
            fetch_environment_variables(token, environment_id))
    except Exception as exc:  # noqa: BLE001 - surface any SDK/auth/network failure
        sys.exit(
            f"Connection failed: {exc}\n"
            "Check OP_SERVICE_ACCOUNT_TOKEN / OP_ENVIRONMENT_ID in .env.1password.local."
        )

    print(f"\nKeys available in Environment {environment_id}:")
    missing = False
    for key in EXPECTED_KEYS:
        if secrets.get(key):
            print(f"  available: {key}")
        else:
            print(f"  missing:   {key}")
            missing = True

    if missing:
        sys.exit(
            "\nOne or more expected keys are missing from the Environment.\n"
            "Add them in 1Password: Developer > Environments > (your Environment)."
        )

    print("\nConnection OK — all expected keys are available.")


if __name__ == "__main__":
    main()
