# 实施与环境边界

## 独立产品

Agent Observer 是独立 Python 项目。开发机器为 Mac mini；目标项目部署在其他机器。默认注册为空，开发流程仅使用合成数据。OversightHarness 不是依赖或当前测试前置条件。

## 历史格式与通用能力

最初仅核对了本机 Codex/Claude JSONL 的字段结构，未把真实消息正文复制到 Fixture。Codex 支持 session_meta / turn_context / response_item 与工具调用变体；Claude 支持消息块、tool_use / tool_result 和实际 cwd。所有历史暴露都经过精确 cwd 匹配与脱敏。

文件读取、FTS5、Git、Provider 和 MCP 工具不依赖特定业务目录。统一的安全、预算、分页和证据位置规则适用于每个登记项目。

## 0.2.0 部署交付

- 标准 wheel 与 sdist、带安装脚本的跨机器 bundle、SHA256 校验文件。
- wheel 内包含空配置模板、init 和 register-project 管理 CLI。
- 安装到当地独立 venv，启动脚本按当地安装路径定位程序。
- macOS launchd 辅助脚本与 Linux systemd 用户服务模板。
- 合成项目生成器、全工具协议检查、源码外干净安装验证。
- Ubuntu/macOS 与 Python 3.11/3.13 CI 矩阵，尚未在远程执行。

没有修改 Personal Feishu MCP 或现有 Tunnel。没有开发 Dashboard、调度器、多 Agent 框架或远程 Agent 控制。真实项目的端到端验收留待用户完成目标机器部署。
