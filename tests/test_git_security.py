import shlex
import subprocess

import pytest


def test_git_never_runs_repository_filters(repo):
    obs, _, root, _, _ = repo
    marker = root / "filter-was-executed"
    command = "touch " + shlex.quote(str(marker)) + "; cat"
    subprocess.run(["git", "-C", str(root), "config", "filter.evil.clean", command], check=True)
    subprocess.run(["git", "-C", str(root), "config", "filter.evil.required", "true"], check=True)
    (root / ".gitattributes").write_text("train.py filter=evil\n")
    obs.call("get_git_diff", project_id="p")
    obs.call("get_git_status", project_id="p")
    assert not marker.exists()


def test_git_ignores_inherited_git_environment(repo, monkeypatch, tmp_path):
    obs, _, root, _, _ = repo
    monkeypatch.setenv("GIT_DIR", str(tmp_path / "unrelated"))
    monkeypatch.setenv("GIT_WORK_TREE", str(tmp_path))
    monkeypatch.setenv("GIT_EXTERNAL_DIFF", "false")
    assert obs.call("get_git_status", project_id="p")["branch"] == "main"
    assert "smaller batch" in obs.call("get_git_diff", project_id="p")["text"]


def test_git_diff_cursor_and_staged_selection(repo):
    obs, _, root, _, _ = repo
    full = obs.call("get_git_diff", project_id="p")["text"]
    assert obs.call("get_git_diff", project_id="p", char_offset=10)["text"] == full[10:]
    assert obs.call("get_git_diff", project_id="p", staged=True)["text"] == ""
    with pytest.raises(ValueError):
        obs.call("get_git_diff", project_id="p", path="escape/private.txt")
