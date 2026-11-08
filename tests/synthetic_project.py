"""Synthetic-only data generator; no dependency on an actual external project."""

import argparse
import json
import os
import subprocess
from pathlib import Path

from agent_observer.config import Config, History, Project


def jsonl(path: Path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records))
    return path


def codex(cwd, sid="c1", text="experiment failed: shape mismatch"):
    return [
        {
            "type": "session_meta",
            "timestamp": "2026-01-02T10:00:00Z",
            "payload": {"id": sid, "cwd": str(cwd), "cli_version": "synthetic"},
        },
        {"type": "turn_context", "payload": {"cwd": str(cwd)}},
        {"type": "event_msg", "payload": {"type": "user_message", "message": "Run experiment"}},
        {
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "Run experiment"}],
            },
        },
        {
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": text}],
            },
        },
        {
            "type": "response_item",
            "payload": {
                "type": "custom_tool_call",
                "name": "exec",
                "call_id": "call1",
                "input": "python train.py",
            },
        },
        {
            "type": "response_item",
            "payload": {
                "type": "custom_tool_call_output",
                "call_id": "call1",
                "output": "ValueError: shape mismatch",
            },
        },
        {
            "type": "response_item",
            "payload": {
                "type": "reasoning",
                "summary": [{"text": "Try padding"}],
                "encrypted_content": "DO_NOT_EXPORT_OPAQUE",
            },
        },
    ]


def claude(cwd, sid="a1"):
    base = {"cwd": str(cwd), "sessionId": sid, "timestamp": "2026-01-03T10:00:00Z", "version": "synthetic"}
    return [
        {"type": "permission-mode", "sessionId": sid, "permissionMode": "default"},
        {**base, "type": "user", "message": {"role": "user", "content": "Find failure"}},
        {
            **base,
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "Try a smaller batch"},
                    {"type": "tool_use", "name": "Read", "id": "t1", "input": {"file_path": "train.py"}},
                ],
            },
        },
        {
            **base,
            "type": "user",
            "message": {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "t1",
                        "content": [{"type": "text", "text": "CUDA OOM"}],
                    }
                ],
            },
        },
    ]


def create_environment(base: Path):
    root = base / "project"
    other = base / "other"
    root.mkdir()
    other.mkdir()
    (root / "train.py").write_text("# experiment\nraise ValueError('shape mismatch')\n")
    (root / "run.log").write_text("start\nexperiment failed: shape mismatch\n失败原因：形状不符\n")
    (root / "config.toml").write_text('batch_size = 16\napi_key = "sensitive-fixture-value"\n')
    (root / ".env").write_text("TOP_SECRET=fixture\n")
    (root / "node_modules").mkdir()
    (root / "node_modules/hidden.txt").write_text("dependency data")
    (root / "binary.bin").write_bytes(b"hello\x00world")
    (other / "private.txt").write_text("OTHER_PROJECT_UNIQUE")
    (root / "escape").symlink_to(other, target_is_directory=True)
    history = base / "history"
    croot, aroot = history / "codex", history / "claude"
    jsonl(croot / "one.jsonl", codex(root))
    jsonl(croot / "other.jsonl", codex(other, "other-id", "OTHER_PROJECT_UNIQUE"))
    jsonl(aroot / "one.jsonl", claude(root))
    jsonl(aroot / "other.jsonl", claude(other, "other-claude-id"))
    config = Config(
        projects=[
            Project(project_id="p", project_name="Test", absolute_path=root),
            Project(project_id="q", project_name="Other", absolute_path=other),
        ],
        history=History(codex_root=croot, claude_root=aroot),
    )
    return config, root, other


def initialize_git(root: Path):

    def git(*args):
        return (
            subprocess.check_output(
                [
                    "git",
                    "-c",
                    "commit.gpgsign=false",
                    "-c",
                    "core.hooksPath=/dev/null",
                    "-C",
                    str(root),
                    *args,
                ],
                stderr=subprocess.DEVNULL,
                env={**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"},
            )
            .decode()
            .strip()
        )

    git("init", "-b", "main")
    git("config", "user.name", "Synthetic Fixture")
    git("config", "user.email", "fixture@example.test")
    git("add", "train.py", "config.toml", ".env")
    git("commit", "-m", "Initial experiment")
    first = git("rev-parse", "HEAD")
    (root / "train.py").write_text("# experiment\nraise ValueError('shape mismatch')\n# try padding\n")
    git("add", "train.py")
    git("commit", "-m", "Try padding")
    commit = git("rev-parse", "HEAD")
    (root / "train.py").write_text("# experiment\n# now use smaller batch\n")
    (root / ".env").write_text("HIDDEN_DIFF=fixture-secret\n")
    return first, commit


def create_fixture(destination: Path):
    destination = destination.expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    if any(destination.iterdir()):
        raise ValueError("Refusing to overwrite a nonempty synthetic fixture directory")
    config, root, other = create_environment(destination)
    initialize_git(root)
    text = "\n".join(
        f'[[projects]]\nproject_id = "{p.project_id}"\nproject_name = "Synthetic"\nabsolute_path = {json.dumps(str(p.absolute_path))}\n'
        for p in config.projects
    )
    text += f"[history]\ncodex_root = {json.dumps(str(config.history.codex_root))}\nclaude_root = {json.dumps(str(config.history.claude_root))}\n"
    (destination / "observer.toml").write_text(text, encoding="utf-8")
    return destination / "observer.toml"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    print(create_fixture(parser.parse_args().output))
