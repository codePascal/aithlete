#!/usr/bin/env bash
#
# setup-auth.sh — create the local 1Password credentials file from the template.
#
#   1. If .env.1password.local does not exist, copies .env.1password.example to it.
#   2. If it already exists, asks whether to overwrite it:
#        - yes -> deletes the existing file and copies the template afresh.
#        - no  -> leaves it untouched and exits.
#   3. Prints instructions telling you to open the file and paste your own keys.
#
# This script never reads, prompts for, or writes secret values — you fill them
# in yourself by editing .env.1password.local (which is gitignored). Editing the
# file directly avoids terminal paste corruption of long tokens.
#
# Usage (from the backend/ directory):
#   ./scripts/setup-auth.sh
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
EXAMPLE_FILE="$BACKEND_DIR/.env.1password.example"
LOCAL_FILE="$BACKEND_DIR/.env.1password.local"

if [[ ! -f "$EXAMPLE_FILE" ]]; then
  echo "Template not found: $EXAMPLE_FILE" >&2
  exit 1
fi

if [[ -f "$LOCAL_FILE" ]]; then
  read -rp ".env.1password.local already exists. Overwrite it? [y/N]: " answer < /dev/tty || true
  case "$answer" in
    [yY] | [yY][eE][sS])
      rm -f "$LOCAL_FILE"
      cp "$EXAMPLE_FILE" "$LOCAL_FILE"
      echo "Overwrote .env.1password.local from .env.1password.example."
      ;;
    *)
      echo "Left .env.1password.local untouched. Nothing to do."
      exit 0
      ;;
  esac
else
  cp "$EXAMPLE_FILE" "$LOCAL_FILE"
  echo "Created .env.1password.local from .env.1password.example."
fi

cat <<EOF

Next steps:
  1. Open the file in your editor:
       $LOCAL_FILE
  2. Paste your 1Password values after the '=' for each key, e.g.:
       OP_SERVICE_ACCOUNT_TOKEN=ops_...
       OP_ENVIRONMENT_ID=...
  3. Save the file, then verify the connection:
       ./scripts/test-connection.sh

The file is gitignored and is never committed.
EOF
