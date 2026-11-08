import subprocess
import sys

import pytest
from pydantic import ValidationError

from agent_observer.config import History, Project, load_config
from agent_observer.installation import initialize
from agent_observer.registry import register


def test_init_is_empty_and_non_overwriting(tmp_path):
    path = tmp_path / "config.toml"
    assert initialize(path)
    assert load_config(path).projects == []
    before = path.read_bytes()
    assert not initialize(path, port=9999)
    assert path.read_bytes() == before
    assert path.stat().st_mode & 0o777 == 0o600


def test_register_explicit_empty_projects_array(tmp_path):
    path = tmp_path / "config.toml"
    initialize(path)
    root = tmp_path / "deployment-project"
    root.mkdir()
    register(path, Project(project_id="sample", project_name="Sample", absolute_path=root))
    assert load_config(path).project("sample").absolute_path == root.resolve()


def test_init_accepts_deployment_history_paths_and_port(tmp_path):
    path = tmp_path / "config.toml"
    initialize(path, port=9999, codex_root=tmp_path / "codex", claude_root=tmp_path / "claude")
    config = load_config(path)
    assert config.http.port == 9999
    assert config.history.codex_root == tmp_path / "codex"
    assert config.history.claude_root == tmp_path / "claude"
    with pytest.raises(ValidationError):
        History(codex_root="relative/path")


def test_installed_cli_registration_flow(tmp_path):
    path = tmp_path / "config.toml"
    root = tmp_path / "project"
    root.mkdir()

    def run(*args):
        return subprocess.run(
            [sys.executable, "-m", "agent_observer.cli", "--config", str(path), *args],
            check=True,
            capture_output=True,
            text=True,
        )

    run("init")
    run("register-project", "--id", "sample", "--name", "Sample", "--path", str(root))
    assert '"project_id": "sample"' in run("projects").stdout
