# GitHub 分发准备报告

## 本地仓库

当前目录已初始化独立 Git 仓库，分支 main。源码、文档、测试、工作流和安装辅助脚本已准备进入索引；维护者已确认正式仓库 https://github.com/hefengcs/agent-observer；远程为空且当前身份具有写入权限。首次源码上传已完成；本地 main 与正式仓库一致。

公开源码隐私审计通过；默认项目白名单为空。虚拟环境、生成的 synthetic 项目、个人 Session/JSONL、本地配置、数据库、日志和包含机器路径的测试输出被忽略。发行构建仅从经审计的 Git 索引文件复制源文件，不把工作区其他文件夹直接打包。测试中只有明确的假凭据，没有个人历史或真实项目数据。

## 验证结果

- 原有 51 项继续通过；新增 5 项后 **56 项通过、0 失败**（本地 54、真实协议 2）。
- Ruff、ShellCheck、Python compileall、pip check 通过。
- actionlint 1.7.12 对两份工作流校验通过（工具下载经官方 release 校验和核对）。
- 临时 Git 仓库创建合成提交和 v0.2.0 Tag，再从 Tag 克隆：安装成功。
- 未带发布 Tag 的 main 默认安装被拒绝，显式开发 opt-in 仍可用。
- XDG 目录、统一 CLI、升级保留项目注册、卸载保留配置和项目均通过。
- Bundle 干净安装和 stdio/HTTP 全 12 工具验收由 scripts/verify_install.py 复现，结果见本地生成的 clean-install.json。

## 工作流与发布

CI 对每次 Push / Pull Request 运行 macOS / Ubuntu × Python 3.11 / 3.13，包含测试、构建、脚本检查和安装生命周期验收。Actions 固定 commit SHA，默认 token 只读。

vX.Y.Z Tag 发布先验证版本一致，再等待完整矩阵，通过后生成 wheel、sdist、独立 Bundle 与 SHA256SUMS。Release 先 draft 上传完整资产，再公开发布。只有 publish job 使用 contents:write。默认安装不跟随 main。

## 远程验证

首轮远程 CI 四组全部成功：https://github.com/hefengcs/agent-observer/actions/runs/42443664619 。Ubuntu/macOS 的 Python 3.11/3.13 均执行测试、构建、固定 Tag 安装、升级卸载和 Bundle 安装。Release 另有完整矩阵验证，状态在 Actions 与 Releases 页面查看。

本轮没有变更 Personal Feishu MCP、现有 Tunnel 或 Observer 核心只读权限。OversightHarness 仍不是硬编码依赖；实际项目的端到端验收等待目标机器部署。
