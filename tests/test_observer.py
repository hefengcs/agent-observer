import json
from pathlib import Path

import pytest
from conftest import claude, codex, jsonl
from pydantic import ValidationError

from agent_observer.config import HTTP, Config, Project
from agent_observer.history import ClaudeCodeAdapter, CodexAdapter
from agent_observer.security import redact
from agent_observer.server import TOOLS, create_server


def test_codex_actual_shapes(env):
    obs, cfg, root, _ = env
    session = CodexAdapter(cfg.history.codex_root).parse(
        cfg.history.codex_root / "one.jsonl", cfg.project("p"), cfg.limits
    )
    assert session.session_id == "c1" and session.cwd == str(root)
    assert [e.kind for e in session.events] == [
        "user",
        "assistant",
        "tool_call",
        "tool_output",
        "analysis_summary",
    ]
    assert session.events[2].call_id == "call1"
    assert session.events[3].source_line == 7
    assert "DO_NOT_EXPORT_OPAQUE" not in json.dumps(
        obs.call("get_agent_session", project_id="p", session_id="c1", provider="codex")
    )


def test_codex_function_and_legacy_variants(env):
    obs, cfg, root, _ = env
    records = codex(root, "variant")[:2] + [
        {
            "type": "response_item",
            "payload": {"type": "function_call", "name": "shell", "arguments": "pwd", "call_id": "x"},
        },
        {
            "type": "response_item",
            "payload": {"type": "function_call_output", "output": "synthetic", "call_id": "x"},
        },
        {"type": "assistant", "content": "legacy text"},
        {"type": "compacted", "payload": {"message": "history was compacted"}},
    ]
    p = jsonl(cfg.history.codex_root / "variant.jsonl", records)
    s = CodexAdapter(cfg.history.codex_root).parse(p, cfg.project("p"), cfg.limits)
    assert [e.kind for e in s.events] == ["tool_call", "tool_output", "assistant", "compaction"]


def test_claude_actual_shapes(env):
    obs, cfg, _, _ = env
    s = ClaudeCodeAdapter(cfg.history.claude_root).parse(
        cfg.history.claude_root / "one.jsonl", cfg.project("p"), cfg.limits
    )
    assert s.session_id == "a1"
    assert [e.kind for e in s.events] == ["user", "assistant", "tool_call", "tool_output"]
    assert s.events[-1].call_id == "t1" and s.events[-1].text == "CUDA OOM"


@pytest.mark.parametrize("variant", ["subdir", "prefix", "missing", "changed", "relative", "conflicting_id"])
def test_cwd_must_match_exactly(env, variant):
    obs, cfg, root, other = env
    records = codex(root, "bad")
    if variant == "subdir":
        records = codex(root / "child", "bad")
    elif variant == "prefix":
        records = codex(Path(str(root) + "-other"), "bad")
    elif variant == "missing":
        del records[0]["payload"]["cwd"]
        records.pop(1)
    elif variant == "changed":
        records.append({"type": "turn_context", "payload": {"cwd": str(other)}})
    elif variant == "relative":
        records = codex(Path("relative"), "bad")
    else:
        records.append({"type": "session_meta", "payload": {"id": "conflict", "cwd": str(root)}})
    jsonl(cfg.history.codex_root / "bad.jsonl", records)
    assert "bad" not in [s.session_id for s in obs.sessions("p")[0]]


def test_claude_encoded_directory_never_authorizes(env):
    obs, cfg, root, other = env
    jsonl(cfg.history.claude_root / str(root).replace("/", "-") / "spoof.jsonl", claude(other, "spoof"))
    assert "spoof" not in [s.session_id for s in obs.sessions("p")[0]]


def test_history_and_registry_isolation(env):
    obs, *_ = env
    assert obs.call("search_agent_history", project_id="p", query="OTHER_PROJECT_UNIQUE")["items"] == []
    assert "other-id" not in json.dumps(obs.call("list_agent_sessions", project_id="p"))
    assert obs.call("search_agent_history", project_id="q", query="OTHER_PROJECT_UNIQUE")["items"]
    with pytest.raises(ValueError, match="not found"):
        obs.call("get_agent_session", project_id="p", session_id="other-id", provider="codex")
    assert [p["project_id"] for p in obs.call("list_projects", project_id="p")["items"]] == ["p", "q"]
    with pytest.raises(ValueError):
        obs.call("list_projects", project_id="unknown")


@pytest.mark.parametrize(
    "path",
    [
        "../other/private.txt",
        "/etc/passwd",
        "escape/private.txt",
        ".env",
        "node_modules/hidden.txt",
        ".git/config",
        "binary.bin",
    ],
)
def test_file_access_defenses(env, path):
    obs, *_ = env
    with pytest.raises((ValueError, OSError)):
        obs.call("read_project_file", project_id="p", path=path)


def test_file_listing_ranges_and_search(env):
    obs, *_ = env
    names = [i["path"] for i in obs.call("list_project_files", project_id="p")["items"]]
    assert "run.log" in names and ".env" not in names and "binary.bin" not in names
    assert not any("escape" in p or "node_modules" in p for p in names)
    assert (
        obs.call("search_project_files", project_id="p", keyword=".toml")["items"][0]["path"] == "config.toml"
    )
    assert obs.call("read_project_file", project_id="p", path="run.log", start_line=2, end_line=2)[
        "text"
    ].startswith("experiment failed")
    matches = obs.call("search_project_content", project_id="p", query="shape mismatch")["items"]
    assert {(m["source"], m["line"]) for m in matches} == {("run.log", 2), ("train.py", 2)}
    assert obs.call("search_project_content", project_id="p", query="失败")["items"][0]["line"] == 3
    assert not obs.call("search_project_content", project_id="p", query="sensitive-fixture-value")["items"]


def test_history_search_filters(env):
    obs, *_ = env
    assert obs.call(
        "search_agent_history", project_id="p", query="mismatch", provider="codex", session_id="c1"
    )["items"]
    assert not obs.call("search_agent_history", project_id="p", query="mismatch", provider="claude")["items"]
    assert not obs.call("search_agent_history", project_id="p", query='" OR secret --')["items"]


def test_large_session_lossless_pagination(env):
    obs, cfg, root, _ = env
    long = "page-marker " * 2000
    records = codex(root, "long", long)
    records += [
        {
            "type": "response_item",
            "payload": {"type": "message", "role": "assistant", "content": [{"text": f"entry {i}"}]},
        }
        for i in range(120)
    ]
    jsonl(cfg.history.codex_root / "long.jsonl", records)
    args = dict(project_id="p", session_id="long", provider="codex", limit=17)
    parts, seen, calls = [], set(), 0
    while True:
        page = obs.call("get_agent_session", **args)
        calls += 1
        assert len(json.dumps(page, ensure_ascii=False)) <= cfg.limits.max_output_chars
        for event in page["items"]:
            seen.add(event["event_index"])
            if event["event_index"] == 1:
                parts.append(event["text"])
        if page["next_offset"] is None:
            break
        assert (page["next_offset"], page["next_char_offset"]) != (
            args.get("offset", 0),
            args.get("char_offset", 0),
        )
        args.update(
            offset=page["next_offset"], char_offset=page["next_char_offset"], snapshot=page["snapshot"]
        )
        assert calls < 100
    assert "".join(parts) == long and len(seen) == 125


def test_session_snapshot_and_tool_filter(env):
    obs, cfg, root, _ = env
    p = obs.call("get_agent_session", project_id="p", session_id="c1", provider="codex", include_tools=False)
    assert all(e["kind"] not in ("tool_call", "tool_output") for e in p["items"])
    jsonl(cfg.history.codex_root / "one.jsonl", codex(root, text="changed"))
    with pytest.raises(ValueError, match="changed"):
        obs.call(
            "get_agent_session",
            project_id="p",
            session_id="c1",
            provider="codex",
            snapshot=p["snapshot"],
            include_tools=False,
        )


def test_malformed_oversize_and_duplicate_sessions_fail_closed(env):
    obs, cfg, root, _ = env
    jsonl(cfg.history.codex_root / "duplicate.jsonl", codex(root))
    assert not obs.call("list_agent_sessions", project_id="p", provider="codex")["items"]
    path = jsonl(cfg.history.codex_root / "bad.jsonl", codex(root, "bad"))
    with path.open("a") as f:
        f.write('{"cwd":')
    assert "bad" not in [s.session_id for s in obs.sessions("p")[0]]
    cfg.limits.max_session_bytes = 1024
    assert "c1" not in [s.session_id for s in obs.sessions("p")[0]]


def test_size_limit_and_large_file_cursor(env):
    obs, cfg, root, _ = env
    (root / "too_big.txt").write_bytes(b"x" * (cfg.limits.max_file_bytes + 1))
    with pytest.raises(ValueError):
        obs.call("read_project_file", project_id="p", path="too_big.txt")
    (root / "line.txt").write_text("a" * 30000)
    first = obs.call("read_project_file", project_id="p", path="line.txt")
    assert first["truncated"]
    second = obs.call(
        "read_project_file", project_id="p", path="line.txt", char_offset=first["next_char_offset"]
    )
    assert first["text"] + second["text"] == "a" * 24000


@pytest.mark.parametrize(
    "secret",
    [
        'api_key="abc123"',
        "password: super-secret",
        "Authorization: Bearer abcdef123456",
        "https://user:password@example.test",
        "sk-proj-abcdefghijklmnop",
        "-----BEGIN PRIVATE KEY-----\nABCDEF\n-----END PRIVATE KEY-----",
    ],
)
def test_redaction(secret):
    clean = redact(secret)
    assert "[REDACTED" in clean
    for value in (
        "abc123",
        "super-secret",
        "abcdef123456",
        "user:password",
        "sk-proj-abcdefghijklmnop",
        "ABCDEF",
    ):
        assert value not in clean
    assert clean.count("\n") == secret.count("\n")


def test_history_redacted_before_search_and_egress(env):
    obs, cfg, root, _ = env
    jsonl(cfg.history.codex_root / "secret.jsonl", codex(root, "secret", "token=raw-fixture-value"))
    p = obs.call("get_agent_session", project_id="p", session_id="secret", provider="codex")
    assert "raw-fixture-value" not in json.dumps(p)
    assert not obs.call("search_agent_history", project_id="p", query="raw-fixture-value")["items"]


def test_git_read_only_diff_log_status(repo):
    obs, cfg, root, first, commit = repo
    before = (root / ".git/index").read_bytes()
    assert obs.call("get_git_status", project_id="p")["branch"] == "main"
    assert commit in obs.call("get_git_log", project_id="p")["text"]
    assert first in obs.call("get_git_log", project_id="p", path="train.py")["text"]
    assert "smaller batch" in obs.call("get_git_diff", project_id="p")["text"]
    assert "try padding" in obs.call("get_git_diff", project_id="p", commit=commit)["text"]
    assert "HIDDEN_DIFF" not in obs.call("get_git_diff", project_id="p")["text"]
    assert "fixture-secret" not in json.dumps(obs.call("get_git_status", project_id="p"))
    assert (root / ".git/index").read_bytes() == before
    with pytest.raises(ValueError):
        obs.call("get_git_diff", project_id="p", commit="--output=/tmp/should-not-exist")
    with pytest.raises(ValueError):
        obs.call("get_git_log", project_id="p", path="../other")


def test_config_and_disabled_project(env):
    obs, cfg, root, _ = env
    with pytest.raises(ValidationError):
        HTTP(host="0.0.0.0")
    with pytest.raises(ValidationError):
        Project(project_id="bad", project_name="bad", absolute_path=Path.home())
    with pytest.raises(ValidationError):
        Config(projects=[cfg.project("p"), cfg.project("p")])
    cfg.project("p").enabled = False
    with pytest.raises(ValueError):
        obs.call("get_project_overview", project_id="p")


@pytest.mark.asyncio
async def test_all_mcp_tool_schemas_and_invocations(repo):
    obs, cfg, root, first, commit = repo
    server = create_server(cfg)
    tools = await server.list_tools()
    assert {t.name for t in tools} == set(TOOLS)
    for t in tools:
        assert "project_id" in t.inputSchema["required"]
        assert t.annotations.readOnlyHint and not t.annotations.destructiveHint
    args = {
        "search_project_files": {"keyword": "train"},
        "search_project_content": {"query": "experiment"},
        "read_project_file": {"path": "train.py"},
        "search_agent_history": {"query": "failed"},
        "get_agent_session": {"session_id": "c1", "provider": "codex"},
    }
    for tool in tools:
        result = await server.call_tool(tool.name, {"project_id": "p", **args.get(tool.name, {})})
        assert result
