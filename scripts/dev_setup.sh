#!/bin/sh
set -eu
ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
PYTHON=${PYTHON:-python3}
"$PYTHON" -c 'import sys; assert sys.version_info >= (3,11)'
if [ ! -d "$ROOT/.venv" ]; then "$PYTHON" -m venv "$ROOT/.venv"; fi
"$ROOT/.venv/bin/python" -m pip install -e "${ROOT}[dev,build]"
