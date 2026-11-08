#!/bin/sh
set -eu
ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"
.venv/bin/ruff check src tests scripts
.venv/bin/ruff format --check src tests scripts
.venv/bin/shellcheck scripts/*.sh
.venv/bin/python -m pytest -q -m 'not transport' --junitxml=reports/pytest-local.xml
# Only start protocol test servers after local reads and checks succeed.
.venv/bin/python -m pytest -q -m transport --junitxml=reports/pytest-transport.xml
