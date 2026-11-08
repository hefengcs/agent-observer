"""Run only after the local suite passes: pytest -m transport."""

import asyncio
import json
import socket
import subprocess
import sys

import httpx
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client
from protocol_checks import exercise

pytestmark = [pytest.mark.transport, pytest.mark.asyncio]


def write_config(tmp_path, config, port):
    path = tmp_path / "observer.toml"
    path.write_text(
        f"[http]\nport = {port}\n[history]\ncodex_root = {json.dumps(str(config.history.codex_root))}\n"
        f"claude_root = {json.dumps(str(config.history.claude_root))}\n"
        + "".join(
            f'[[projects]]\nproject_id = "{p.project_id}"\nproject_name = "Synthetic"\n'
            f"absolute_path = {json.dumps(str(p.absolute_path))}\n"
            for p in config.projects
        )
    )
    return path


async def test_stdio_real_protocol(repo, tmp_path):
    _, cfg, *_ = repo
    path = write_config(tmp_path, cfg, 8765)
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "agent_observer.cli", "--config", str(path), "serve"]
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await exercise(session)


async def test_http_real_protocol_and_dns_rebinding(repo, tmp_path):
    _, cfg, *_ = repo
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    path = write_config(tmp_path, cfg, port)
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "agent_observer.cli",
            "--config",
            str(path),
            "serve",
            "--transport",
            "streamable-http",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}/mcp"
    try:
        async with httpx.AsyncClient(trust_env=False) as client:
            for _ in range(100):
                if process.poll() is not None:
                    pytest.fail("HTTP server exited before startup")
                try:
                    await client.get(url, timeout=0.2)
                    break
                except httpx.ConnectError:
                    await asyncio.sleep(0.05)
            else:
                pytest.fail("HTTP server startup timed out")
            rejected = await client.post(url, headers={"Host": "attacker.test"}, json={})
            assert rejected.status_code == 421
        async with streamable_http_client(url) as (read, write, _):
            async with ClientSession(read, write) as session:
                await exercise(session)
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
