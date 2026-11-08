"""User-local paths, with XDG support and existing defaults preserved."""

import os
from pathlib import Path


def xdg(variable: str, fallback: str) -> Path:
    value = os.environ.get(variable)
    return Path(value) if value and Path(value).is_absolute() else Path.home() / fallback


def config_path() -> Path:
    return Path(
        os.environ.get("AGENT_OBSERVER_CONFIG")
        or xdg("XDG_CONFIG_HOME", ".config") / "agent_observer/config.toml"
    ).expanduser()


def state_dir() -> Path:
    return xdg("XDG_STATE_HOME", ".local/state") / "agent_observer"
