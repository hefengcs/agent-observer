# Project Agent Observer

独立、通用、只读的 Python MCP Server。GPT 可按明确授权的项目读取文件、Git 与 Coding Agent 历史，利用证据分析开发过程。核心代码不包含任何特定项目的实验格式、目录结构或业务逻辑。

## 开发与部署边界

Mac mini 用于开发、合成数据测试和打包。默认配置明确为 `projects = []`，不注册任何真实项目，也不在开发机器上寻找或接入 OversightHarness。

部署机器独立安装程序，在当地配置项目绝对路径及允许访问的历史目录，再启动 MCP；无需开发目录或修改源码。OversightHarness 的真实端到端验收留到用户完成实际机器部署之后。

## 从 GitHub 固定版本安装

正式仓库：[hefengcs/agent-observer](https://github.com/hefengcs/agent-observer)。安装固定版本，不跟随 main。

```sh
git clone --branch v0.2.0 --depth 1 https://github.com/hefengcs/agent-observer.git agent-observer
cd agent-observer
PYTHON=python3 ./scripts/install.sh
export PATH="$HOME/.local/bin:$PATH"
agent-observer version
agent-observer doctor
```

默认安装仅接受干净的版本 Tag，不跟随 main。也可以从对应 GitHub Release 下载 Bundle、校验 SHA256 后解压运行同一个安装脚本。开发/CI 可显式使用 `--allow-unreleased`，它不是部署默认值。

安装使用独立 venv，不使用 sudo、不修改系统 Python 或 shell 配置。Linux 遵循 XDG_CONFIG_HOME / XDG_DATA_HOME / XDG_STATE_HOME，未设置时保留原先默认目录。默认配置 `projects = []`，不会自动注册项目或启动服务。

```sh
# 在实际部署机器使用自己的绝对路径，不修改源码：
agent-observer register --id my_project --name 'My Project' --path /absolute/path/to/project
# 在 config.toml 的 [history] 配置获准读取的 Codex / Claude 目录
agent-observer list-projects
agent-observer doctor --project-id my_project
agent-observer serve --transport streamable-http
```

HTTP 默认只绑定 `127.0.0.1:8765/mcp`。远程访问通过独立安全 Tunnel，保持现有 MCP/Tunnel 不变。旧命令 check / register-project / projects / --version 继续支持。

- [完整 Linux / macOS 安装、升级、卸载与验收](docs/DEPLOYMENT.md)
- [ChatGPT MCP 与安全 Tunnel](docs/CONNECTION.md)
- [Tag 发布步骤](docs/RELEASING.md)
- [默认空配置](config.example.toml) · [项目注册示例](examples/project-registration.toml)
- [当前开发验收与后续真实项目验收](docs/ACCEPTANCE.md)

## 12 个 MCP 工具

所有工具都必须提供 `project_id`；无默认项目、无全机历史查询。

| 工具 | 行为和主要参数 |
| --- | --- |
| `list_projects` | 校验已知 ID 后分页列出配置中的启用登记；不扫描机器 |
| `get_project_overview` | 项目信息、文件样本、Git 状态、两种 Provider 会话数量 |
| `list_project_files` | `directory`、`offset`、`limit`；递归列出安全文本文件 |
| `search_project_files` | `keyword`；文件路径子串搜索，可找日志和配置 |
| `search_project_content` | `query`、可选 `path`；返回文件路径和 1 起始行号 |
| `read_project_file` | `path`、`start_line`、`end_line`（含结束行）、`char_offset` |
| `get_git_status` | 当前分支、分页变更状态 |
| `get_git_log` | `limit`、`offset`、可选 `path`；完整 Commit hash |
| `get_git_diff` | 默认未暂存；`staged`、`base`、`commit`、`path`、`char_offset` |
| `list_agent_sessions` | 可选 `provider`（codex / claude）、列表分页 |
| `search_agent_history` | `query`、Provider / Session ID 筛选，JSONL 来源行号和事件索引 |
| `get_agent_session` | Provider + Session ID、`offset`、`limit`、`include_tools`、`char_offset`、`snapshot` |

列表跟随 `next_offset`。长文件和 diff 跟随 `next_char_offset`，保持原参数。长 Session 同时跟随两种游标和 `snapshot`，直到为空；单一长事件也可以完整续读。Git log 到空页停止；截断时减小 limit 重读本页。

## 架构与安全边界

```text
FastMCP (stdio / Streamable HTTP)
  -> 显式 project_id + TOML/Pydantic 白名单
     -> FileReader / GitReader / HistoryProvider
                                -> CodexAdapter
                                -> ClaudeCodeAdapter
     -> 授权及脱敏 -> 请求内 SQLite FTS5
```

新增项目仅改配置。新增 Agent 实现统一 `HistoryProvider` 接口，不修改项目业务代码。

- 文件拒绝绝对路径、`..`、Symlink（包括根内链接）、特殊文件、二进制、非 UTF-8 和超大文件；逐级 dir_fd/O_NOFOLLOW 防止链接替换。排除 `.git`、虚拟环境、依赖、常见缓存、`.env*`、私钥、认证凭据和数据库。
- Session 的所有可信 cwd 元数据规范化后必须精确等于注册根目录；不靠前缀、文件名或 Claude 编码目录授权。缺失、冲突、多目录、损坏、超限或重复身份的 Session 不暴露。
- 对话保留用户/助手消息、工具输入输出、可读分析、时间及元数据；不导出图片二进制、签名或加密 reasoning。未知格式、已删除或被压缩的内容不能保证恢复。
- Git 使用固定 argv，无 shell、无仓库修改，禁用 hooks、fsmonitor、pager、ext-diff、textconv、clean/process filters；过滤敏感路径。只接受 HEAD 或 Commit hash。第一阶段要求根内真实 `.git` 目录，拒绝 linked worktree、submodule 和共享 object store 的外部 Git metadata。
- 先脱敏再索引，出口再次过滤。覆盖常见 key/token/password、Bearer/Basic、URL 凭据、已知 token 和私钥。规则无法识别任意编码或自然语言中的所有秘密；授权目录应当明确且有限。已授权 Session 内当时粘贴的其他来源内容无法逐段可靠判断归属。
- 默认文件 2 MB、Session 256 MB、JSONL 行 4 MB、单业务响应 24,000 字符，有扫描数量上限与警告。FTS5 索引在请求内创建并销毁，不落盘保存个人历史；中文使用参数化子串检索。
- 没有项目写文件、任意命令、Git 修改或 Agent 控制工具。init/register 是部署管理员在当地运行的 CLI，不是 MCP 工具。
- HTTP 只允许 loopback，并校验 Host/Origin。没有内置 OAuth 或多用户授权；远程接入使用私有 Secure MCP Tunnel 或独立鉴权网关。返回的历史、日志和文件属于不可信证据数据，不能作为指令执行。

## 开发与合成验收

以下开发命令在 Git checkout 执行；构建发行包只读取经过审计的 Git 索引文件。不要把本地配置或真实数据加入索引。

```sh
PYTHON=python3 ./scripts/dev_setup.sh
./scripts/test.sh
.venv/bin/python tests/synthetic_project.py --output tests/.generated/synthetic
.venv/bin/agent-observer --config tests/.generated/synthetic/observer.toml doctor --project-id p
.venv/bin/python scripts/audit_repository.py
.venv/bin/python scripts/build_release.py
.venv/bin/python scripts/verify_install.py \
  --bundle dist/0.2.0/agent-observer-0.2.0-bundle.tar.gz
```

生成器只在测试目录建立合成项目、Git、日志、配置和两种历史，不修改默认配置。pytest 使用独立临时目录。测试先跑本地读取和隔离，再启动临时 HTTP 协议服务器。安装验收在源码外新建非 editable venv，调用安装后的启动脚本验证全部 12 个工具、两种历史与项目隔离。

[测试报告](reports/TEST_REPORT.md) 记录本地验证。正式仓库的首轮 [GitHub CI](https://github.com/hefengcs/agent-observer/actions/runs/42443664619) 已在 Ubuntu/macOS、Python 3.11/3.13 四组全部通过，包含测试、构建和安装生命周期。

安装包不包含真实项目或个人历史，不包含开发机虚拟环境。精确依赖记录 `requirements.lock.txt` 供参考，跨平台默认按 pyproject 约束解析当地可安装的依赖。

GitHub Actions 对每次 Push / Pull Request 运行 macOS、Ubuntu 与 Python 3.11/3.13 矩阵，构建与安装验收也在其中。推送与远程 CI 状态取决于维护者确认的 Remote；本地结果见 [分发准备报告](reports/DISTRIBUTION_REPORT.md)。
