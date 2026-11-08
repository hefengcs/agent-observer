# 0.2.0 开发验收报告

本次验收仅针对开发机器与合成数据。Mac mini 不是 OversightHarness 的部署机器，默认 `projects = []`。不要求该项目在开发机器存在，也不注册任何真实项目。

## 结果

**原有 47 项全部通过；新增 4 项后共 51 项通过、0 失败。** 本地阶段 49 项，协议阶段 2 项。全部使用合成项目、临时 Git 仓库与合成 Session，没有真实个人历史 Fixture。

| 验收项 | 结果 | 证据 |
| --- | --- | --- |
| 本地读取、安全和配置 | 49 passed | [pytest-local.xml](pytest-local.xml) |
| stdio / Streamable HTTP 协议 | 2 passed，全部 12 个工具调用 | [pytest-transport.xml](pytest-transport.xml) |
| 合成 Codex / Claude 读取 | 通过，两种 Provider 均有直接读取检查 | tests/protocol_checks.py |
| 不同项目隔离 | 通过，历史、内容搜索、路径与两种 Provider 的跨项目读取被拒绝 | 同上与单元测试 |
| 空默认配置和管理员 CLI | 通过，init/register-project，支持显式空数组注册 | tests/test_installation.py |
| 安装包干净安装运行 | 通过，源码外新 venv、非 editable 安装、两种传输调用全部工具 | [clean-install.json](clean-install.json) |
| 重复安装 | 通过，不覆盖已有配置 | 同上 |
| 源码目录独立性 | 导入来自新 venv 的 site-packages，启动脚本使用当地安装路径 | 同上 |
| 格式/静态检查 | Ruff 通过 | scripts/test.sh |
| 依赖/脚本语法 | pip check、compileall、sh -n 通过 | 当地验证 |

## 覆盖范围

包含 Codex/Claude 格式兼容、cwd 精确匹配和冲突拒绝、项目间隔离、路径穿越与 Symlink、文件/Session/JSONL 行大小上限、Git status/log/diff、Git filter 执行防护、FTS5 英文/中文搜索、工具正常调用、长 Session 无损分页与 snapshot 检查、敏感信息脱敏、损坏与重复 Session、来源删除后的索引失效、HTTP Host 防护。

可重复生成的独立 fixture 位于 `tests/synthetic_project.py`，实际示例生成于开发工作区 `tests/.generated/synthetic`；其中有项目目录、Git、实验日志、配置、两种 Agent 的历史及第二个隔离对照项目。生成数据不进入发行包，发行包携带生成器。

## 平台与限制

实际执行环境为 macOS arm64 / Python 3.13.12 / MCP 1.30.0。Observer wheel 为 py3-none-any；依赖在部署机器选择对应的平台 wheel。Linux 的前台启动和 systemd 模板已提供，CI 配置覆盖 Ubuntu/macOS 与 Python 3.11/3.13，但本次没有 Linux VM/container，也没有运行远程 CI，因此**没有宣称 Linux 实机运行验收通过**。

第一次安装默认需要包索引网络；bundle 不捆绑所有平台依赖，支持部署机器自备 wheelhouse 离线安装。秘密过滤不能识别所有任意编码形式。第一阶段 Git 不支持外部 gitdir / linked worktree。

## 后续真实项目验收

OversightHarness 的真实实验分析与 ChatGPT 端到端测试，等待用户把安装包部署到真正的项目机器之后进行。本轮不把它视为未满足的开发机前置条件，也不声称已验收。

Personal Feishu MCP 与现有 Tunnel 的配置、代码、进程均未修改。临时协议测试进程会退出；不为开发机器配置新的 Tunnel。

复现本地测试：`./scripts/test.sh`。复现构建和干净安装：依次运行 `scripts/build_release.py` 与 `scripts/verify_install.py --bundle dist/0.2.0/agent-observer-0.2.0-bundle.tar.gz`。
