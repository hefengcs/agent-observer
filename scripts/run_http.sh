#!/bin/sh
set -eu
ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
PREFIX=${AGENT_OBSERVER_PREFIX:-$ROOT}
EXECUTABLE="$PREFIX/venv/bin/agent-observer"
if [ ! -x "$EXECUTABLE" ]; then EXECUTABLE="$ROOT/.venv/bin/agent-observer"; fi
exec "$EXECUTABLE" serve --transport streamable-http
