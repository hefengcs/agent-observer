# GitHub 准备与 Tag 发布

正式 Remote 为 https://github.com/hefengcs/agent-observer.git。发布只使用这个已确认仓库。

## 初次连接

检查索引的公开源码和隐私审计，确认后再提交。使用自己正确的 Git 作者身份，不把 token 放进 Remote URL。

```sh
git status --short
git diff --cached --stat
python3 scripts/audit_repository.py
git commit -m "Prepare Agent Observer distribution"
git remote add origin https://github.com/hefengcs/agent-observer.git
git push -u origin main
```

首次接入只添加一次 origin；已有 Remote 时先核对 URL，不覆盖未知来源。仓库当前为 public，发布前继续审计索引，避免上传个人历史和配置。

## CI

每次 Push / Pull Request 运行 macOS + Ubuntu、Python 3.11/3.13 四组，依次执行源码隐私检查、Ruff、ShellCheck、pytest、本地协议、包构建、固定 Tag 克隆安装/升级/卸载和 Bundle 安装。运行产物作为 Actions artifacts 保留，不进入源码索引。

工作流仅默认 contents:read，外部 Actions 固定完整 commit SHA。Release 的 publish job 单独使用 contents:write。没有 pull_request_target，不给 PR 测试写入权限。

## 发布 v0.2.0

1. pyproject.toml 和 src/agent_observer/__init__.py 的版本一致，提交并等 CI 全绿。
2. 本地运行下列校验并创建固定 Tag：

```sh
python3 scripts/release_info.py --tag v0.2.0
git tag -a v0.2.0 -m "Agent Observer 0.2.0"
git push origin v0.2.0
```

3. Release 工作流核对 Tag/包版本，等待完整 CI 矩阵通过，再构建 wheel、sdist、Bundle、SHA256SUMS。
4. 先创建 draft 并附上四项资产，全部上传成功后发布。只使用仓库内置 GITHUB_TOKEN，不需要把个人 API Key 写进仓库。
5. 到 Releases 检查版本和资产，再验证目标服务器固定版本安装。

Tag 必须严格为稳定版本 vX.Y.Z，与源码版本相同。不要移动已发布 Tag 或覆盖资产；修复应发布新版本。如果工作流中途留下 draft，维护者先检查失败原因，处理该 draft 后重跑；工作流不会静默覆盖已有 Release。

版本验证与构建路径动态读取 pyproject，无需修改 CI 内版本常量。未来升级时同时更新两处版本及面向用户的示例。

## 远程尚不可用时

可以完成全部本地准备、生成四项资产和校验、验证安装流程，但不能报告 GitHub Actions 的远程结果，也不能宣称 Release 已发布。实际的 Ubuntu runner 与 ChatGPT 目标服务器结果以部署后的证据为准。

参考：[GitHub reusable workflows](https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows)、[GitHub CLI Release](https://cli.github.com/manual/gh_release_create)。
