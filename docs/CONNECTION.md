# MCP 与 ChatGPT 连接

## 本地 stdio

支持 MCP stdio 的客户端可使用以下配置（路径根据安装位置调整）：

```json
{
  "mcpServers": {
    "agent-observer": {
      "command": "/absolute/install-prefix/bin/run_stdio.sh",
      "args": []
    }
  }
}
```

项目 ID 来自部署机器的 TOML 注册；示例查询为 `get_project_overview({"project_id":"my_project"})`。`/absolute/install-prefix` 需替换为当地安装目录（默认 `~/.local/share/agent-observer` 的绝对路径）。注册和当地 `doctor` 成功后再查询。

## Streamable HTTP

部署默认使用 `http://127.0.0.1:8765/mcp`。端口变更在独立 `[http]` 配置中完成，不修改已有 Feishu MCP。stdio 与 HTTP 暴露相同的 12 个只读工具。

## 私有 Secure MCP Tunnel（推荐）

根据官方 [Secure MCP Tunnel 文档](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels)，此方式通过出站连接访问私有 MCP，不需要公网入站端口。在实际部署机器安装 `tunnel-client`，并以当地 `help quickstart` 与 `init --help` 核对参数。本文仅交付说明，开发机不配置或改动任何 Tunnel。

1. 在 Platform Tunnel 设置创建 **Observer 专用** Tunnel，并关联需要使用它的 ChatGPT 工作区。已有 Feishu Tunnel 的上游继续保留。
2. 在本地安全地设置 `CONTROL_PLANE_API_KEY` 环境变量，不把值粘贴到对话、脚本、命令参数或版本库。Tunnel ID 是下文的 `tunnel_...`。账号需具备文档要求的 Tunnel 权限。
3. 使用独立 profile，管理端口选择 `127.0.0.1:0` 避免冲突：

```sh
tunnel-client init \
  --sample sample_mcp_remote_no_auth \
  --profile agent-observer \
  --tunnel-id tunnel_REPLACE_WITH_REAL_ID \
  --mcp-server-url http://127.0.0.1:8765/mcp \
  --health-listen-addr 127.0.0.1:0
tunnel-client doctor --profile agent-observer --explain
tunnel-client run --profile agent-observer
```

不要使用 `--force` 覆盖其他 profile，不把现有 Feishu Tunnel 的 upstream 换成 Observer。一个现有单上游 Tunnel 无法同时直接代表两个 MCP Server；复用已有多路由网关时，要新增独立路由并保留鉴权与原 upstream，不应把两个工具集无配置地混在一起。

## ChatGPT Custom MCP

按当前官方 [Add custom MCP server](https://developers.openai.com/api/docs/guides/custom-mcp-server) 页面操作：在网页端 Plugins 中添加 Custom MCP Server，Connection 选择 Tunnel 并选择 Observer 的 Tunnel ID；为这个私有服务选择 No authentication，创建并安装插件。账号权限和界面可能不同，以实际网页为准。在对话中 `@` 选择该插件，调用 `get_project_overview` 验证，实际部署完成后再执行 [真实项目验收任务](ACCEPTANCE.md)。本轮合成验收不要求 ChatGPT 账户连接。

这里的无应用认证依赖私有 Tunnel 的账户与工作区访问控制。Observer 本身没有实现 OAuth。通过普通公网 HTTPS Tunnel 接入时，应使用具有适当认证的独立 MCP 网关，不要将本地无认证端点直接发布到互联网。

如果已有受保护的多路由反向代理，可以把新路由 `/agent-observer/mcp` 转发到 `http://127.0.0.1:8765/mcp`，保留 Streamable HTTP 所需头与请求响应流；保持现有 Feishu 路由不变。若代理保留公网 Host/Origin，只将该精确域名加入 `[http].allowed_hosts` / `allowed_origins`，不要使用通配 `*`。这只是配置方案，本次没有修改或发布任何网关。

## 验证与排障

- `agent-observer doctor --project-id ...`：本地路径与可读数据先通过。
- `scripts/test.sh`：源码测试；bundle 的 `scripts/verify_install.py` 验证干净安装与合成协议调用。
- launchd `status`：确认进程运行；端口占用时不停止别的服务，修改 Observer 端口。
- `tunnel-client doctor`：确认上游 URL、运行身份与 Tunnel 可用。
- ChatGPT 中工具列表应包含 12 个工具，均标注只读，且必填 `project_id`。
- `421`：Host 未在精确白名单；不要禁用 DNS rebinding 防护来绕过。
- Session 数为 0：检查是否有本机记录、实际 cwd 是否精确匹配、是否已压缩/删除；不要放宽成前缀匹配。
- 最终验收必须看到 ChatGPT 的实际工具成功调用；仅本地 MCP 测试通过不代表账户连接已完成。
