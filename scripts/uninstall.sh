#!/bin/sh
# Keeps all configuration, project registrations, history and logs.
set -eu
HERE=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
if [ -f "$HERE/../.agent-observer-install" ]; then
    AGENT_OBSERVER_PREFIX=$(CDPATH='' cd -- "$HERE/.." && pwd)
    export AGENT_OBSERVER_PREFIX
fi
exec "${PYTHON:-python3}" "$HERE/installer.py" --uninstall "$@"
