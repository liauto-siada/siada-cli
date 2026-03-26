# 通过飞书远程控制 Siada

通过飞书机器人远程控制本地运行的 siada-cli。本地 siada-cli 通过飞书 SDK 的 WebSocket 长连接直接与飞书开放平台通信，无需部署中转服务器。你在飞书中私聊机器人发送消息，机器人会将消息转发到本地 Agent 执行，并将结果流式回传到飞书。

> **适用场景**：个人开发者自用、小团队内部使用。每个机器人实例只能绑定一个本地 siada-cli 进程。

---

## 目录

1. [申请飞书机器人](#1-申请飞书机器人)
2. [配置 conf.yaml](#2-配置-confyaml)
3. [重启 Daemon 服务](#3-重启-daemon-服务)
4. [配对机器人](#4-配对机器人)

---

## 1. 申请飞书机器人

### 1.1 创建应用

1. 打开 [飞书开放平台](https://open.feishu.cn/app)，登录你的飞书账号
2. 点击 **创建企业自建应用**
3. 填写应用名称（如 `Siada Bot`）和描述，上传应用图标
4. 创建完成后，进入应用详情页

### 1.2 获取凭证

在应用详情页的 **凭证与基础信息** 中获取以下信息（后续配置需要用到）：

| 字段 | 说明 |
|------|------|
| **App ID** | 应用唯一标识 |
| **App Secret** | 应用密钥（请妥善保管，不要泄露） |

### 1.3 启用机器人能力

1. 进入 **应用能力** → **添加应用能力**
2. 启用 **机器人** 能力

### 1.4 配置权限

进入 **权限管理** 页面，搜索并开通以下权限：

| 权限标识 | 权限名称 | 用途 |
|---------|---------|------|
| `im:message` | 获取与发送单聊、群组消息 | 接收用户消息 |
| `im:message:send_as_bot` | 以应用的身份发送消息 | 机器人回复消息 |
| `im:message.reactions:write_as_bot` | 以应用的身份添加消息表情回复 | Typing 状态指示器（打字中动效） |
| `contact:user.base:readonly` | 获取用户基本信息 | 解析发送者姓名 |
| `im:chat:readonly` | 获取群组信息 | 读取会话信息 |
| `cardkit:card` | 创建和更新卡片 | 流式输出卡片（Streaming Card） |

> **说明**：上述权限均需要管理员审批通过后才会生效。请联系企业管理员在「管理后台」中审批。

### 1.5 配置事件订阅

1. 进入 **事件与回调** 页面
2. 在 **事件配置方式** 中选择 **使用长连接接收事件**（这是直连模式的关键，无需公网 IP）
3. 添加事件：搜索并订阅 `im.message.receive_v1`（接收消息）

### 1.6 发布应用

1. 进入 **版本管理与发布**
2. 创建版本并提交审核
3. 管理员审批通过后，应用即可使用

> ⚠️ **注意**：应用必须发布并通过审核后，机器人才能正常接收消息。开发阶段可以在「应用发布」中设置可用范围为自己，方便测试。

---

## 2. 配置 conf.yaml

### 2.1 编辑配置文件

`conf.yaml` 是 siada-cli 的统一配置文件，首次启动 siada-cli 时会自动创建。如果文件不存在，手动创建：

```bash
mkdir -p ~/.siada-cli
vim ~/.siada-cli/conf.yaml
```

### 2.2 配置内容

在 `conf.yaml` 中添加 `lark` 配置段：

```yaml
# ... 其他 siada 配置（llm_config、checkpoint_config 等）...

# Lark IM 配置（飞书机器人直连模式）
lark:
  # 连接模式：direct（直连）或 relay（中转）
  mode: direct

  # 工作目录（可选，默认为 ~/.siada-cli/workspace/lark）
  # workspace: /path/to/your/project

  # 直连模式配置
  direct:
    # 飞书应用凭证（必填）
    app_id: "cli_xxxxxxxxxxxx"
    app_secret: "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

    # 飞书域名：feishu（国内）或 lark（海外）
    domain: "feishu"

    # HTTP 请求超时（毫秒），默认 30000
    # http_timeout_ms: 30000

    # 是否解析发送者姓名，默认 true
    # resolve_sender_names: true

  # 访问控制（可选）
  access:
    # DM 策略：open（所有人可用）或 allowlist（白名单模式）
    dm_policy: open

    # 白名单（仅 dm_policy 为 allowlist 时生效）
    # allow_from:
    #   - "ou_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    #   - "ou_yyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy"
```

### 2.3 完整 conf.yaml 示例

以下是一个同时包含 LLM 配置和飞书直连配置的完整 `conf.yaml` 示例：

```yaml
# LLM 配置
llm_config:
  model: "claude-sonnet-4-20250514"
  provider: "anthropic"
  api_key: "sk-ant-xxxxx"
  thinking: true

# Lark IM 直连模式
lark:
  mode: direct
  direct:
    app_id: "cli_xxxxxxxxxxxx"
    app_secret: "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    domain: "feishu"

  access:
    dm_policy: open
```

### 2.4 配置说明

| 配置项 | 必填 | 默认值 | 说明 |
|--------|------|--------|------|
| `lark.mode` | ✅ | - | 连接模式，直连模式填 `direct` |
| `lark.workspace` | ❌ | `~/.siada-cli/workspace/lark` | Agent 工作目录 |
| `lark.direct.app_id` | ✅ | - | 飞书应用 App ID |
| `lark.direct.app_secret` | ✅ | - | 飞书应用 App Secret |
| `lark.direct.domain` | ❌ | `lark` | `feishu`（国内飞书）或 `lark`（海外 Lark），也可填自定义域名 |
| `lark.direct.http_timeout_ms` | ❌ | `30000` | HTTP API 请求超时（毫秒） |
| `lark.direct.resolve_sender_names` | ❌ | `true` | 是否通过 API 解析发送者姓名 |
| `lark.access.dm_policy` | ❌ | `open` | DM 访问策略：`open` 或 `allowlist` |
| `lark.access.allow_from` | ❌ | `[]` | 白名单用户 ID 列表（open_id 格式） |

> **说明**：
> - `domain` 字段：国内飞书用户请填 `feishu`，海外 Lark 用户填 `lark`（默认值）
> - IM 模式下 Agent 类型固定为 `coder`，无需配置

---

## 3. 重启 Daemon 服务

Siada 的飞书连接由后台 Daemon 守护进程管理。配置完 `conf.yaml` 后，需要重启 Daemon 使配置生效。

### 3.1 检查 Daemon 状态

```bash
siada-cli --daemon-status
```

输出示例：

```
✓ Proactive daemon is running (PID: 12345)
  Started: 2026-03-19 10:00:00
  Log: ~/.siada-cli/logs/siada_cli.log
```

### 3.2 停止现有 Daemon

```bash
siada-cli --stop-daemon
```

输出：

```
✓ Proactive daemon stopped
```

### 3.3 重新启动 Daemon

```bash
siada-cli
```

启动 siada-cli 即可自动拉起 Daemon 进程。

---

## 4. 配对机器人

### 4.1 找到你的机器人

配置完成并启动 Daemon 后，在飞书中搜索你创建的机器人名称（如 `Siada Bot`），打开私聊对话。

### 4.2 发送测试消息

直接向机器人发送任意消息即可开始使用：

```
你好，帮我写一个快速排序算法
```

机器人收到消息后会：
1. 在你发送的消息上添加 ⏳ Typing 表情回复（表示正在处理）
2. 本地 Agent 开始执行任务
3. 通过流式卡片（Streaming Card）实时展示 Agent 的输出
4. 完成后移除 Typing 表情

### 4.3 访问控制配对

如果你在 `conf.yaml` 中配置了 `dm_policy: allowlist`（白名单模式），则需要将用户的 `open_id` 添加到 `allow_from` 列表中。

**获取用户 open_id 的方法：**

1. 先将 `dm_policy` 设置为 `open`
2. 让用户向机器人发送任意消息
3. 查看日志中的 `user_id` 或 `sender_open_id` 字段：
   ```bash
   tail -f ~/.siada-cli/logs/siada_cli.log | grep "Received IM message"
   ```
   日志示例：
   ```
   INFO  Received IM message: request_id=xxx, user_id=ou_xxxxx, chat_id=oc_xxxxx, ...
   ```
4. 或者，如果用户不在白名单中发送消息，机器人会自动回复其 pair key：
   ```
   ⚠️ Access denied. Please contact the admin to grant access.
   
   Your pair key: ou_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```
5. 将获取到的 `ou_xxx` 格式的 open_id 添加到 `conf.yaml` 的 `allow_from` 列表中：
   ```yaml
   lark:
     access:
       dm_policy: allowlist
       allow_from:
         - "ou_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
   ```
6. 重启 Daemon 使配置生效

### 4.4 常用斜杠命令

配对成功后，可以在飞书对话中使用以下斜杠命令（IM 模式支持的命令子集）：

| 命令 | 说明 |
|------|------|
| `/help` | 显示帮助信息 |
| `/status` | 查看当前状态 |
| `/model` | 切换模型 |
| `/clear` | 清除对话历史，开启新会话 |
| `/lang` | 切换语言（en / zh-CN） |
| `/pre-plan-mode` | 切换预规划模式 |
| `/mcp-list` | 查看 MCP 服务及工具列表 |
| `/mcp-server` | 查看 MCP 服务连接状态 |
| `/skill-list` | 查看可用技能列表 |
| `/skill-reload` | 重新加载技能 |
| `/lark-status` | 查看 Lark MCP 认证状态 |
| `/lark-refresh` | 手动刷新 Lark 访问令牌 |
| `/rule-init` | 创建空的 siada_rule.md 文件 |
| `/rule-show` | 显示层级上下文内容 |
| `/rule-list` | 列出已加载的上下文文件 |
| `/rule-refresh` | 刷新层级上下文 |
| `/rule-status` | 显示上下文状态 |
| `/rule-global-add` | 添加全局上下文记忆 |
| `/context-file-refresh` | 刷新 SIADA.md 等上下文文件 |

> **说明**：部分 CLI 专用命令（如 `/editor`、`/undo`、`/restore`、`/resume` 等）在 IM 模式下不可用。

---

## 常见问题

### Q: 机器人没有响应消息？

1. **检查 Daemon 是否在运行**：`siada-cli --daemon-status`
2. **检查日志是否有错误**：`tail -100 ~/.siada-cli/logs/siada_cli.log`
3. **确认应用已发布审批通过**：在飞书开放平台检查应用状态
4. **确认权限已全部开通**：特别是 `im:message` 和事件订阅
5. **确认使用长连接接收事件**：而不是 HTTP 回调方式

### Q: 提示 "Access denied"？

检查 `conf.yaml` 中的 `lark.access.dm_policy` 配置，如果是 `allowlist` 模式，确认用户的 `open_id` 已添加到 `allow_from` 列表中。

### Q: 连接频繁断开？

飞书 SDK 内置了心跳保活和自动重连机制。如果频繁断开，请检查：
- 网络环境是否稳定
- `app_id` 和 `app_secret` 是否正确
- 应用是否仍然有效（未被停用）

### Q: 支持群聊吗？

当前版本仅支持 **私聊（p2p）** 模式，群聊消息会被自动忽略。
