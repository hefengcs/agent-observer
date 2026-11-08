"""Local registry administration, never exposed through MCP."""

import json
import os
import re
import tempfile
import tomllib
from pathlib import Path

from .config import Config, Project, load_config


def register(config_path: Path, project: Project):
    original = config_path.read_text() if config_path.exists() else ""
    config = load_config(config_path) if original else Config()
    if any(
        p.project_id == project.project_id or p.absolute_path == project.absolute_path
        for p in config.projects
    ):
        raise ValueError("Project id or path already registered; edit the existing registration explicitly")
    # All registration writes are local administrator actions; preserve existing TOML/comments.
    if not config.projects:
        original = re.sub(
            r'(?m)^[ \t]*(?:projects|"projects"|\'projects\')[ \t]*=[ \t]*\[[ \t\r\n]*\][ \t]*(?:#[^\n]*)?(?:\n|$)',
            "",
            original,
            count=1,
        )
    addition = (
        "\n[[projects]]\n"
        + "\n".join(
            f"{key} = {str(value).lower() if isinstance(value, bool) else json.dumps(str(value), ensure_ascii=False)}"
            for key, value in project.model_dump().items()
        )
        + "\n"
    )
    updated = original + addition
    Config.model_validate(tomllib.loads(updated))
    config_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".observer-", dir=config_path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(updated)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, config_path)
    finally:
        Path(name).unlink(missing_ok=True)
