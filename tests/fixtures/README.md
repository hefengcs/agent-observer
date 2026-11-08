# Synthetic project fixture

生成器为 `tests/synthetic_project.py`，供原有 pytest fixture、真实 MCP 协议测试和安装包验收共同使用。
不复制任何真实项目、个人 Session 或机器路径。所有路径在执行时生成。

```sh
python tests/synthetic_project.py --output tests/.generated/synthetic
agent-observer --config tests/.generated/synthetic/observer.toml check --project-id p
```

生成内容：

```text
synthetic/
  observer.toml          # 仅供此 fixture，不修改默认配置
  project/              # p：两个 Git commits + 未提交 diff
    .git/
    train.py
    run.log
    config.toml
    .env                # 合成敏感数据，用来测试排除
    escape -> ../other  # 越权 Symlink 测试
  other/                # q：隔离对照
    private.txt
  history/
    codex/              # p 与 q 的合成 Session
    claude/             # p 的合成 Session
```

重复生成时拒绝覆盖非空目录。pytest 每次在隔离临时目录生成，不读取生成目录或用户真实历史。
