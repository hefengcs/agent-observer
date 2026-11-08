#!/usr/bin/env python3
"""Run with the freshly installed Python, using synthetic data and real MCP clients."""

import argparse
import asyncio
import json
import socket
import subprocess
import sys
from pathlib import Path

import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client

import agent_observer


async def accept(bundle, prefix, sandbox):
    # Only fixture modules are loaded from the bundle, never the Observer source tree.
    sys.path.insert(0, str(bundle / "tests"))
    from protocol_checks import exercise
    from synthetic_project import create_fixture

    assert Path(agent_observer.__file__).resolve().is_relative_to(prefix.resolve())
    assert "site-packages" in Path(agent_observer.__file__).parts
    config = create_fixture(sandbox / "synthetic")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    with config.open("a") as stream:
        stream.write(f'\n[http]\nhost = "127.0.0.1"\nport = {port}\n')
    import os

    env = {**os.environ, "AGENT_OBSERVER_CONFIG": str(config), "AGENT_OBSERVER_PREFIX": str(prefix)}
    params = StdioServerParameters(command=str(prefix / "bin/run_stdio.sh"), env=env)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await exercise(session)
    process = subprocess.Popen(
        [str(prefix / "bin/run_http.sh")], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    url = f"http://127.0.0.1:{port}/mcp"
    try:
        async with httpx.AsyncClient(trust_env=False) as client:
            for _ in range(100):
                if process.poll() is not None:
                    raise RuntimeError("Installed HTTP server exited before startup")
                try:
                    await client.get(url, timeout=0.2)
                    break
                except httpx.ConnectError:
                    await asyncio.sleep(0.05)
            else:
                raise RuntimeError("Installed HTTP server startup timed out")
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
    return {
        "version": agent_observer.__version__,
        "imported_from_installed_site_packages": True,
        "stdio_all_12_tools": "passed",
        "http_all_12_tools": "passed",
        "codex_history": "passed",
        "claude_history": "passed",
        "cross_project_isolation": "passed",
        "fixture": "generated synthetic only",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--prefix", type=Path, required=True)
    parser.add_argument("--sandbox", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    result = asyncio.run(accept(args.bundle, args.prefix, args.sandbox))
    args.report.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
