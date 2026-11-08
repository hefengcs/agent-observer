# Linux / macOS 部署指南

## 1. 固定版本获取与一键安装

需要 Python 3.11+（venv/pip）、Git 2.28+、Python SQLite FTS5。程序不需要 sudo，不修改系统 Python。正式仓库为 https://github.com/hefengcs/agent-observer。

```sh
git clone --branch v0.2.0 --depth 1 https://github.com/hefengcs/agent-observer.git agent-observer && cd agent-observer && PYTHON=python3 ./scripts/install.sh
export PATH="$HOME/.local/bin:$PATH"
agent-observer version
agent-observer doctor
```

安装脚本可从 Git Repository 根目录运行，要求 HEAD 有与 pyproject 版本相同的稳定 Tag，且工作区干净。默认不安装 main 最新代码；没有合适 Tag 时会给出明确错误。`--allow-unreleased` 仅供主动选择的开发/CI 使用。

也可从 GitHub Release 下载同一版本的 Bundle 和 SHA256SUMS，Linux `sha256sum -c SHA256SUMS` 或 macOS `shasum -a 256` 核对已下载资产后解压，在 bundle 根运行 `./scripts/install.sh`。发布共四项资产：wheel、sdist、Bundle、SHA256SUMS。若只下载 Bundle，只校验 SHA256SUMS 中对应的那一行。

Linux Python 缺少 venv/pip 时，先由服务器管理员按该发行版策略安装对应系统软件包；安装器不自动执行 sudo。macOS 可使用自己已装的 Python 3.11+，通过 PYTHON 指定。

## 2. 目录与配置

| 项目 | 默认值 / 配置 |
| --- | --- |
| 程序与独立 venv | `${XDG_DATA_HOME:-~/.local/share}/agent-observer/` |
| 配置 | `${XDG_CONFIG_HOME:-~/.config}/agent_observer/config.toml` |
| CLI 符号链接 | `~/.local/bin/agent-observer` |
| macOS 日志 | `${XDG_STATE_HOME:-~/.local/state}/agent_observer/` |
| Linux 服务日志 | systemd 用户 journal |

可用 `AGENT_OBSERVER_PREFIX`、`AGENT_OBSERVER_CONFIG`、`AGENT_OBSERVER_BIN_DIR` 指定绝对路径。配置必须在安装目录之外，以便卸载保留它。相对 XDG 变量按规范忽略并使用默认值。安装器不会覆盖已有配置，也不会自动配置服务。

默认白名单为 `projects = []`。在实际项目所在机器注册：

```sh
agent-observer register --id my_project --name 'My Project' --path /absolute/path/to/project
agent-observer list-projects
```

在配置中编辑 `[history].codex_root`、`claude_root`，指向获准读取的当地历史目录。也可以在一个尚不存在的配置文件上执行：

```sh
agent-observer --config /absolute/path/new-config.toml init \
  --codex-root /absolute/path/allowed-codex/sessions \
  --claude-root /absolute/path/allowed-claude/projects --port 8765
```

init 不修改已有文件；配置默认 0600。历史目录和项目必须由部署机器配置，核心代码没有特定项目路径。旧 cwd 不会自动映射到新机器，子目录/前缀也不自动授权。

```sh
agent-observer doctor
agent-observer doctor --project-id my_project
agent-observer serve --transport stdio
# 或 HTTP，仅本地监听：
agent-observer serve --transport streamable-http
```

## 3. Linux systemd 用户服务

默认目录下安装模板：

```sh
PREFIX="${XDG_DATA_HOME:-$HOME/.local/share}/agent-observer"
mkdir -p "$HOME/.config/systemd/user"
cp "$PREFIX/deploy/linux/agent-observer.service" "$HOME/.config/systemd/user/agent-observer.service"
systemctl --user daemon-reload
systemctl --user enable --now agent-observer.service
systemctl --user status agent-observer.service
journalctl --user -u agent-observer.service
```

模板使用默认安装路径。使用自定义 prefix 或 XDG_CONFIG_HOME 时，按当地绝对路径修改用户 service 的 ExecStart、Environment；无需修改 Observer 源码。systemd 不会自动继承交互式 shell 的全部环境变量，所以必须显式设置配置路径或 XDG 变量。需要退出登录后继续运行时，由服务器管理员按当地策略设置 linger。没有 systemd 的 Linux 可将前台命令交给自己的进程管理器。

服务配置 host 只能是 `127.0.0.1`，默认端口 8765。端口冲突时仅修改 Observer 的配置，不停止其他 MCP。远程 ChatGPT 通过 [独立安全 Tunnel](CONNECTION.md)，无需开放公网入站端口。

## 4. macOS 后台服务

```sh
PREFIX="${XDG_DATA_HOME:-$HOME/.local/share}/agent-observer"
"$PREFIX/venv/bin/python" "$PREFIX/bin/manage_http.py" start
"$PREFIX/venv/bin/python" "$PREFIX/bin/manage_http.py" status
"$PREFIX/venv/bin/python" "$PREFIX/bin/manage_http.py" stop
```

自定义配置在 action 后加 `--config /absolute/path/config.toml`。服务标签仅为 local.agent-observer.http。

## 5. 升级与回退

先停止 Observer 自己的后台服务（Linux：`systemctl --user stop agent-observer.service`；macOS：上述 stop）。在 checkout 中选择明确的新版本，然后重跑安装器：

```sh
git fetch origin --tags
git checkout --detach v0.2.0  # 替换成明确要安装的已发布版本
./scripts/install.sh --upgrade
agent-observer version
agent-observer doctor
systemctl --user restart agent-observer.service  # Linux，已配置服务时
```

升级保留配置与项目注册。选择旧 Tag 重装同样可用作程序回退；配置格式若未来有变化，需要遵循该版本的迁移说明。安装器不自动停止服务；检测到自己的服务仍运行时会拒绝升级，避免运行中替换依赖。升级失败时保留配置，先重跑安装或选择原 Tag，不将 pip 安装视为原子事务。

## 6. 卸载（保留数据）

Linux 先停止并取消用户服务：

```sh
systemctl --user disable --now agent-observer.service
rm "$HOME/.config/systemd/user/agent-observer.service"
systemctl --user daemon-reload
```

macOS 先 stop，再删除 Observer 自己的 `~/Library/LaunchAgents/local.agent-observer.http.plist`。随后执行安装器提供的卸载脚本：

```sh
PREFIX="${XDG_DATA_HOME:-$HOME/.local/share}/agent-observer"
"$PREFIX/bin/uninstall.sh"
```

只删除带 Observer 所有权标记的安装目录及其 CLI 链接。配置、注册、项目文件、Agent 历史和日志均保留；不会停止或修改 Personal Feishu MCP 或其他 Tunnel。旧安装目录如果还是空标记，先用新安装器重装一次以记录卸载所有权。

## 7. 离线与目标服务器验收

联网环境应与目标平台/架构/Python 相同，准备 wheelhouse：

```sh
python3 -m pip download --only-binary=:all: --dest wheelhouse ./wheels/agent_observer-0.2.0-py3-none-any.whl
AGENT_OBSERVER_WHEELHOUSE=/absolute/path/wheelhouse ./scripts/install.sh
```

离线推荐 Bundle 模式；源码安装还需要预备 setuptools 等构建依赖。Bundle 不捆绑所有平台二进制依赖。

目标服务器按顺序验收：

1. `version` 对应所选 Tag，`doctor` 确认 Git/FTS5 与配置可用。
2. 默认项目列表为空，登记当地实际项目与历史路径，再运行 `doctor --project-id ...`。
3. 本地协议测试或合成验收确认全部工具、两种历史与隔离；源码环境可执行 `scripts/test.sh`（开发依赖）和 `scripts/verify_repository_install.py`。
4. systemd 仅监听 loopback，通过 `ss -ltn` 核对当地端口。
5. 用独立 Tunnel 连接 ChatGPT，调用 overview 并检查 Provider Session 数量。
6. 在实际项目机器执行 [真实失败实验验收](ACCEPTANCE.md)，保留文件行号、Commit 和 Session 证据；缺失信息明确注明。

本地 macOS 检查不能代替 Ubuntu CI 或目标服务器验收。尚未配置 Remote 时，不声称 GitHub Actions 或 Release 已在远程成功运行。
