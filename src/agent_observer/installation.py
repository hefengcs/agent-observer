"""Configuration initialization for both wheel and source installations."""

import json
import os
import platform
import shutil
import sqlite3
import tomllib
from importlib.resources import files
from pathlib import Path

from .config import Config, load_config


def initialize(
    path: Path, *, port: int = 8765, codex_root: Path | None = None, claude_root: Path | None = None
) -> bool:
    path = path.expanduser()
    if path.exists():
        load_config(path)
        return False
    text = files("agent_observer").joinpath("templates/config.toml").read_text(encoding="utf-8")
    text = text.replace("port = 8765", f"port = {port}")
    defaults = {"codex_root": "~/.codex/sessions", "claude_root": "~/.claude/projects"}
    for key, value in (("codex_root", codex_root), ("claude_root", claude_root)):
        if value is not None:
            text = text.replace(
                f'{key} = "{defaults[key]}"',
                f"{key} = {json.dumps(str(value), ensure_ascii=False)}",
            )
    Config.model_validate(tomllib.loads(text))
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(text)
    return True


def runtime_check() -> dict:
    if not shutil.which("git"):
        raise ValueError("Git is required")
    with sqlite3.connect(":memory:") as db:
        db.execute("CREATE VIRTUAL TABLE fts_check USING fts5(text)")
    return {
        "platform": platform.system(),
        "python": platform.python_version(),
        "sqlite_fts5": True,
        "git_available": True,
    }
