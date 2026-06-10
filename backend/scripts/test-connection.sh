#!/usr/bin/env bash
#
# test-connection.sh — verify the stored 1Password service-account credentials.
#
#   1. Loads the keys from .env.1password.local (written by setup-auth.sh).
#   2. Checks the 1password CLI is installed and on PATH.
#   3. Calls `op whoami` to confirm the service-account token authenticates,
#      then `op vault list` to confirm it can actually read.
#
# Behavior notes:
#   - Secret values are loaded into the environment but never printed.
#   - `op whoami` / `op vault list` only echo the account URL and vault names,
#     never the token itself.
#
# Usage (from the backend/ directory):
#   ./scripts/test-connection.sh
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
LOCAL_FILE="$BACKEND_DIR/.env.1password.local"

if [[ ! -f "$LOCAL_FILE" ]]; then
  echo "Credentials file not found: $LOCAL_FILE" >&2
  echo "Run ./scripts/setup-auth.sh first." >&2
  exit 1
fi

# Load KEY=value pairs into the environment without echoing any values.
set -a
# shellcheck disable=SC1090
source "$LOCAL_FILE"
set +a

if [[ -z "${OP_SERVICE_ACCOUNT_TOKEN:-}" ]]; then
  echo "OP_SERVICE_ACCOUNT_TOKEN is empty in .env.1password.local" >&2
  echo "Run ./scripts/setup-auth.sh to set it." >&2
  exit 1
fi

if ! command -v op >/dev/null 2>&1; then
  echo "1Password CLI ('op') is not on PATH." >&2
  echo "Install it: https://developer.1password.com/docs/cli/get-started/" >&2
  exit 1
fi

echo "Testing 1Password connection..."

if ! op whoami; then
  echo "Connection failed — the service-account token was rejected." >&2
  echo "Re-run ./scripts/setup-auth.sh with a valid OP_SERVICE_ACCOUNT_TOKEN." >&2
  exit 1
fi

echo
echo "Vaults the service account can read:"
if ! op vault list; then
  echo "Authenticated, but listing vaults failed — check the service account's grants." >&2
  exit 1
fi

echo
echo "Connection OK."
