"""Protocol acceptance checks shared by pytest and installed-package validation."""

import json

from agent_observer.server import TOOLS


async def exercise(session):
    await session.initialize()
    tools = (await session.list_tools()).tools
    assert {t.name for t in tools} == set(TOOLS)
    args = {
        "search_project_files": {"keyword": "train"},
        "search_project_content": {"query": "experiment"},
        "read_project_file": {"path": "train.py"},
        "search_agent_history": {"query": "failed"},
        "get_agent_session": {"session_id": "c1", "provider": "codex"},
    }
    for name in TOOLS:
        result = await session.call_tool(name, {"project_id": "p", **args.get(name, {})})
        assert not result.isError, (name, result)
        assert "OTHER_PROJECT_UNIQUE" not in json.dumps(result.model_dump(mode="json"))
    rejected = await session.call_tool(
        "get_agent_session", {"project_id": "p", "session_id": "other-id", "provider": "codex"}
    )
    assert rejected.isError
    missing = await session.call_tool("list_projects", {})
    assert missing.isError
    traversal = await session.call_tool(
        "read_project_file", {"project_id": "p", "path": "../other/private.txt"}
    )
    assert traversal.isError
    for provider, sid, expected in (("codex", "c1", "shape mismatch"), ("claude", "a1", "smaller batch")):
        result = await session.call_tool(
            "get_agent_session", {"project_id": "p", "provider": provider, "session_id": sid}
        )
        assert not result.isError
        assert expected in json.dumps(result.model_dump(mode="json"))
    search = await session.call_tool(
        "search_agent_history", {"project_id": "p", "query": "OTHER_PROJECT_UNIQUE"}
    )
    payload = search.structuredContent or json.loads(next(c.text for c in search.content if c.type == "text"))
    assert not search.isError and not payload["items"]
    other_claude = await session.call_tool(
        "get_agent_session", {"project_id": "q", "provider": "claude", "session_id": "other-claude-id"}
    )
    assert not other_claude.isError
    forbidden_claude = await session.call_tool(
        "get_agent_session", {"project_id": "p", "provider": "claude", "session_id": "other-claude-id"}
    )
    assert forbidden_claude.isError
    file_search = await session.call_tool(
        "search_project_content", {"project_id": "p", "query": "OTHER_PROJECT_UNIQUE"}
    )
    payload = file_search.structuredContent or json.loads(
        next(c.text for c in file_search.content if c.type == "text")
    )
    assert not file_search.isError and not payload["items"]
