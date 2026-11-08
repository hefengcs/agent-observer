import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from agent_observer import __version__
from agent_observer.paths import config_path, state_dir


def script(name):
    path = Path(__file__).resolve().parents[1] / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_canonical_cli_and_legacy_aliases(tmp_path):
    config = tmp_path / "config.toml"

    def run(*args):
        return subprocess.run(
            [sys.executable, "-m", "agent_observer.cli", "--config", str(config), *args],
            check=True,
            text=True,
            capture_output=True,
        ).stdout

    assert run("version").strip() == __version__
    run("init")
    assert json.loads(run("doctor"))["sqlite_fts5"]
    assert json.loads(run("check"))["config_valid"]
    root = tmp_path / "arbitrary-project"
    root.mkdir()
    run("register", "--id", "arbitrary", "--name", "Test", "--path", str(root))
    assert run("list-projects") == run("projects")


def test_xdg_and_override_paths(monkeypatch, tmp_path):
    monkeypatch.delenv("AGENT_OBSERVER_CONFIG", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    assert config_path() == tmp_path / "config/agent_observer/config.toml"
    assert state_dir() == tmp_path / "state/agent_observer"
    monkeypatch.setenv("AGENT_OBSERVER_CONFIG", str(tmp_path / "explicit.toml"))
    assert config_path() == tmp_path / "explicit.toml"


def test_tag_version_validation(tmp_path):
    module = script("release_info")
    assert module.version() == __version__
    result = subprocess.run(
        [sys.executable, str(Path(module.__file__)), "--tag", "v99.0.0"], capture_output=True
    )
    assert result.returncode


def test_unstable_install_requires_explicit_opt_in(tmp_path):
    module = script("installer")
    (tmp_path / "pyproject.toml").write_text('[project]\nversion="0.2.0"\n')
    assert module.source_version(tmp_path, allow_unreleased=True) == "0.2.0"
    with pytest.raises(ValueError, match="release tag"):
        module.source_version(tmp_path)


def test_uninstall_refuses_unowned_prefix_and_preserves_external_data(tmp_path, monkeypatch):
    module = script("installer")
    prefix = tmp_path / "installed"
    prefix.mkdir()
    with pytest.raises(ValueError, match="marker"):
        module.uninstall(prefix)
    config = tmp_path / "config.toml"
    config.write_text("projects=[]")
    cli = tmp_path / "cli"
    cli.symlink_to(prefix / "venv/bin/agent-observer")
    (prefix / ".agent-observer-install").write_text(json.dumps({"prefix": str(prefix), "launcher": str(cli)}))
    monkeypatch.setattr(module, "active_service", lambda: False)
    module.uninstall(prefix)
    assert config.read_text() == "projects=[]" and not cli.is_symlink() and not prefix.exists()
