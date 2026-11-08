#!/usr/bin/env python3
"""Start/stop only this Observer's macOS launchd service."""

import argparse
import os
import plistlib
import socket
import subprocess
import sys
import time
from pathlib import Path

from agent_observer.config import DEFAULT_CONFIG, load_config
from agent_observer.paths import state_dir

LABEL = "local.agent-observer.http"


def main():
    if sys.platform != "darwin":
        raise SystemExit("This helper is macOS-only; use deploy/linux/agent-observer.service on Linux")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["start", "stop", "status"])
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()
    target = f"gui/{os.getuid()}/{LABEL}"
    plist_path = Path.home() / "Library/LaunchAgents" / f"{LABEL}.plist"
    if args.action == "status":
        raise SystemExit(subprocess.call(["launchctl", "print", target]))
    if args.action == "stop":
        result = subprocess.call(["launchctl", "bootout", target])
        if result:
            raise SystemExit(result)
        # launchd bootout can return before the label is fully removed.
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            state = subprocess.run(["launchctl", "print", target], capture_output=True)
            if state.returncode:
                return
            time.sleep(0.1)
        raise SystemExit("Observer is still stopping; retry status before start")
    config = load_config(args.config)
    with socket.socket() as sock:
        sock.bind((config.http.host, config.http.port))
    state = state_dir()
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    state.chmod(0o700)
    for filename in ("http.stdout.log", "http.stderr.log"):
        path = state / filename
        path.touch(mode=0o600, exist_ok=True)
        path.chmod(0o600)
    plist = {
        "Label": LABEL,
        "ProgramArguments": [
            str(Path(sys.executable).parent / "agent-observer"),
            "--config",
            str(args.config.resolve()),
            "serve",
            "--transport",
            "streamable-http",
        ],
        "WorkingDirectory": str(args.config.expanduser().resolve().parent),
        "RunAtLoad": True,
        "KeepAlive": True,
        "StandardOutPath": str(state / "http.stdout.log"),
        "StandardErrorPath": str(state / "http.stderr.log"),
        "Umask": 0o077,
        "EnvironmentVariables": {"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"},
    }
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    if plist_path.exists():
        existing = plistlib.loads(plist_path.read_bytes())
        if (
            existing.get("Label") != LABEL
            or existing.get("ProgramArguments", [None])[0] != plist["ProgramArguments"][0]
        ):
            raise ValueError("Existing launch agent does not belong to this installation")
    plist_path.write_bytes(plistlib.dumps(plist))
    plist_path.chmod(0o600)
    subprocess.run(["launchctl", "bootstrap", f"gui/{os.getuid()}", str(plist_path)], check=True)
    print(f"Started {LABEL} at http://{config.http.host}:{config.http.port}/mcp")


if __name__ == "__main__":
    main()
