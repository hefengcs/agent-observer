#!/bin/sh
# Run from a version-tagged checkout or an extracted deployment bundle.
set -eu
ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
exec "${PYTHON:-python3}" "$ROOT/scripts/installer.py" "$@"
