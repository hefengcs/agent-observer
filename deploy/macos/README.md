# macOS launchd

安装包提供 `bin/manage_http.py`。使用已安装 venv 的 Python 调用它，
程序路径来自部署机器的 Python 环境：

```sh
PREFIX="$HOME/.local/share/agent-observer"
"$PREFIX/venv/bin/python" "$PREFIX/bin/manage_http.py" start
"$PREFIX/venv/bin/python" "$PREFIX/bin/manage_http.py" status
"$PREFIX/venv/bin/python" "$PREFIX/bin/manage_http.py" stop
```

自定义配置在 action 后加 `--config /absolute/path/config.toml`。
服务标签为 `local.agent-observer.http`，不修改其他 MCP 或 Tunnel。
