import importlib.util
from pathlib import Path

import pytest
from conftest import codex, jsonl

from agent_observer.config import Config, load_config
from agent_observer.security import read_bytes


def test_registration_preserves_existing_config_and_refuses_duplicates(tmp_path):
    script = Path(__file__).resolve().parents[1] / "scripts/register_project.py"
    spec = importlib.util.spec_from_file_location("registry_admin", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    from agent_observer.config import Project

    config_path = tmp_path / "config.toml"
    config_path.write_text("# Preserve this comment\n[http]\nport=8767\n")
    root = tmp_path / "project"
    root.mkdir()
    project = Project(project_id="p", project_name="Synthetic", absolute_path=root)
    module.register(config_path, project)
    assert load_config(config_path).project("p").absolute_path == root.resolve()
    assert config_path.read_text().startswith("# Preserve this comment")
    assert config_path.stat().st_mode & 0o777 == 0o600
    with pytest.raises(ValueError):
        module.register(config_path, project)


def test_binary_size_and_directory_scan_limit(env):
    obs, cfg, root, _ = env
    cfg.limits.max_files = 1
    result = obs.call("list_project_files", project_id="p")
    assert result["warnings"]
    with pytest.raises(ValueError):
        read_bytes(root, "run.log", 1)


def test_oversized_jsonl_record_is_rejected(env):
    obs, cfg, root, _ = env
    cfg.limits.max_jsonl_line_bytes = 1024
    jsonl(cfg.history.codex_root / "large.jsonl", codex(root, "large", "x" * 2000))
    result = obs.call("list_agent_sessions", project_id="p", provider="codex")
    assert "large" not in [s["session_id"] for s in result["items"]]
    assert result["warnings"]


def test_removed_source_does_not_survive_in_stale_index(env):
    obs, cfg, root, _ = env
    assert obs.call("search_agent_history", project_id="p", query="mismatch")["items"]
    (cfg.history.codex_root / "one.jsonl").unlink()
    assert not obs.call("search_agent_history", project_id="p", query="mismatch")["items"]
    assert obs.call("search_project_content", project_id="p", query="mismatch")["items"]
    (root / "run.log").unlink()
    (root / "train.py").unlink()
    assert not obs.call("search_project_content", project_id="p", query="mismatch")["items"]


def test_git_metadata_cannot_redirect_to_other_repository(repo, tmp_path):
    obs, _, root, _, _ = repo
    gitdir = root / ".git"
    target = tmp_path / "external-git"
    gitdir.rename(target)
    gitdir.symlink_to(target, target_is_directory=True)
    with pytest.raises(ValueError, match="external Git metadata"):
        obs.call("get_git_status", project_id="p")


def test_no_global_projects_authorized_by_default():
    from agent_observer.service import Observer

    obs = Observer(Config())
    with pytest.raises(ValueError):
        obs.call("list_projects", project_id="unregistered_project")


def test_conflicting_cwd_aliases_fail_closed(env):
    obs, cfg, root, other = env
    records = codex(other, "alias")
    records[0]["cwd"] = str(root)
    jsonl(cfg.history.codex_root / "alias.jsonl", records)
    assert "alias" not in [s.session_id for s in obs.sessions("p")[0]]


def test_git_status_supports_repository_without_commits(env):
    import subprocess

    obs, _, root, _ = env
    subprocess.run(["git", "-C", str(root), "init", "-b", "main"], check=True, capture_output=True)
    assert obs.call("get_git_status", project_id="p")["branch"] == "main"
