# Remote Control Siada via Lark

Remotely control your local siada-cli through a Lark bot. The local siada-cli communicates directly with the Lark Open Platform via the Lark SDK's WebSocket long connection, without deploying a relay server. Messages sent to the bot in Lark (via DM or @mention in group chat) are forwarded to the local Agent for execution, and results are streamed back in real-time.

> **Use cases**: Individual developers, small team internal use. Each bot instance can only be bound to one local siada-cli process.

---

## Table of Contents

1. [Create a Lark Bot](#1-create-a-lark-bot)
2. [Configure conf.yaml](#2-configure-confyaml)
3. [Restart Daemon Service](#3-restart-daemon-service)
4. [Pair with the Bot](#4-pair-with-the-bot)
5. [Group Chat Usage](#5-group-chat-usage)

---

## 1. Create a Lark Bot

### 1.1 Create Application

1. Open [Lark Open Platform](https://open.larksuite.com/app) (or [Feishu Open Platform](https://open.feishu.cn/app) for China), log in with your account
2. Click **Create Custom App**
3. Fill in the application name (e.g. `Siada Bot`) and description, upload an icon
4. After creation, go to the application details page

### 1.2 Get Credentials

In the **Credentials & Basic Info** section, obtain the following (needed for configuration):

| Field | Description |
|-------|-------------|
| **App ID** | Unique application identifier |
| **App Secret** | Application secret key (keep it safe, do not expose) |

### 1.3 Enable Bot Capability

1. Go to **App Capabilities** → **Add Capability**
2. Enable **Bot** capability

### 1.4 Configure Permissions

Go to the **Permissions** page, search and enable the following permissions:

| Permission ID | Purpose |
|--------------|---------|
| `im:message` | Read and send messages in chats |
| `im:message:send_as_bot` | Send messages as the app |
| `im:message:readonly` | Read message content |
| `im:message.p2p_msg:readonly` | Read DM messages |
| `im:message.group_msg` | Read and send group messages |
| `im:message.group_at_msg:readonly` | Read @bot messages in group chat |
| `im:chat:readonly` | Get chat info |
| `contact:user.base:readonly` | Get basic user info (resolve sender names) |
| `contact:contact.base:readonly` | Get basic contact info (`resolve_sender_names` requires this to resolve sender_name) |
| `contact:user.id:readonly` | Get user ID (email → open_id resolution) |
| `contact:user.employee_id:readonly` | Get user employee_id (user_id field in events) |
| `cardkit:card:read` | Read cards |
| `cardkit:card:write` | Create and update cards (streaming output) |

**Bulk import permissions**: On the Lark Open Platform **Permissions** page, click **Batch Enable** and paste the following JSON:

```json
{
  "scopes": {
    "tenant": [
      "cardkit:card:read",
      "cardkit:card:write",
      "contact:contact.base:readonly",
      "contact:user.base:readonly",
      "contact:user.employee_id:readonly",
      "contact:user.id:readonly",
      "im:chat:readonly",
      "im:message",
      "im:message.group_at_msg:readonly",
      "im:message.group_msg",
      "im:message.p2p_msg:readonly",
      "im:message:readonly",
      "im:message:send_as_bot"
    ],
    "user": []
  }
}
```

> **Note**: All permissions require admin approval. Contact your organization's admin to approve in the Admin Console.

### 1.5 Configure Event Subscription

1. Go to the **Events & Callbacks** page
2. In **Event Configuration Method**, select **Use Long Connection to Receive Events** (this is key for direct mode — no public IP needed)
3. Add event: search and subscribe to `im.message.receive_v1` (receive messages)

### 1.6 Publish Application

1. Go to **Version Management & Publishing**
2. Create a version and submit for review
3. Once approved by admin, the application is ready to use

> ⚠️ **Note**: The application must be published and approved before the bot can receive messages. During development, you can set the availability scope to yourself only for testing.

---

## 2. Configure conf.yaml

### 2.1 Edit Configuration File

`conf.yaml` is the unified configuration file for siada-cli, automatically created on first launch. If it doesn't exist, create it manually:

```bash
mkdir -p ~/.siada-cli
vim ~/.siada-cli/conf.yaml
```

### 2.2 Configuration Content

Add the `lark` section to `conf.yaml`:

```yaml
# ... other siada config (llm_config, checkpoint_config, etc.) ...

# Lark IM configuration (direct mode)
lark:
  # Set to false to disable the Lark bot entirely without removing the config.
  # When false, the daemon starts without establishing a Lark WebSocket connection.
  # Default: true
  # enabled: true

  # Connection mode: direct (Lark WS SDK) or relay (via IM Gateway)
  mode: direct

  # Working directory (optional, defaults to ~/.siada-cli/workspace/lark)
  # workspace: /path/to/your/project

  # Notification email (optional, used to auto-resolve open_id for routing bootstrap)
  # notify_email: "you@example.com"

  # Direct mode settings
  direct:
    # Lark app credentials (required)
    app_id: "cli_xxxxxxxxxxxx"
    app_secret: "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

    # Lark domain: feishu (China) or lark (international)
    domain: "lark"

    # HTTP request timeout (ms), default 30000
    # http_timeout_ms: 30000

    # Whether to resolve sender names via API, default true
    # resolve_sender_names: true

  # Context injection (optional)
  context:
    # Whether to inject conversation metadata (sender_name, sender_user_id, etc.) into user messages
    # When enabled, Agent can identify senders — useful for multi-user shared bot scenarios
    # sender_name requires contact:contact.base:readonly
    # user_id requires contact:user.employee_id:readonly
    # include_conversation_info: true

  # Access control (optional)
  access:
    # DM policy: open (anyone) or allowlist (whitelist only, default)
    dm_policy: open

    # DM allowlist (only effective when dm_policy is allowlist)
    # allow_from:
    #   - "ou_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    #   - "ou_yyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy"

    # Group chat policy: open (all groups) | allowlist (whitelist only, default) | disabled
    # group_policy: allowlist

    # Group chat allowlist (only effective when group_policy is allowlist)
    # group_allow_from:
    #   - "oc_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

    # Pending history buffer limit for group chat (optional, default 50)
    # history_limit: 50

    # Idle window (seconds) after which a new session is auto-started.
    # Applies to both DM and group chats: when a chat is silent longer than
    # this, the next message starts a fresh session and tells you how to
    # /resume the previous one. Idle timers are persisted and restored across
    # daemon restarts. Default 86400 (24 hours); set to 0 to disable.
    # idle_session_timeout: 86400
```

### 2.3 Full conf.yaml Example

A complete `conf.yaml` example with both LLM and Lark direct mode config:

```yaml
# LLM configuration
llm_config:
  model: "claude-sonnet-4-20250514"
  provider: "anthropic"
  api_key: "sk-ant-xxxxx"
  thinking: true

# Lark IM direct mode
lark:
  mode: direct
  direct:
    app_id: "cli_xxxxxxxxxxxx"
    app_secret: "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    domain: "lark"

  access:
    dm_policy: open
    group_policy: allowlist
    group_allow_from:
      - "oc_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
```

### 2.4 Configuration Reference

| Config Item | Required | Default | Description |
|-------------|----------|---------|-------------|
| `lark.enabled` | ❌ | `true` | Set to `false` to disable the Lark bot without removing the config; daemon starts without a Lark WebSocket connection |
| `lark.mode` | ✅ | - | Connection mode, use `direct` for direct mode |
| `lark.workspace` | ❌ | `~/.siada-cli/workspace/lark` | Agent working directory |
| `lark.notify_email` | ❌ | - | Notification email for auto open_id resolution and routing bootstrap |
| `lark.direct.app_id` | ✅ | - | Lark App ID |
| `lark.direct.app_secret` | ✅ | - | Lark App Secret |
| `lark.direct.domain` | ❌ | `lark` | `feishu` (China Feishu) or `lark` (international Lark), or custom domain |
| `lark.direct.http_timeout_ms` | ❌ | `30000` | HTTP API request timeout (ms) |
| `lark.direct.resolve_sender_names` | ❌ | `true` | Whether to resolve sender names via API |
| `lark.context.include_conversation_info` | ❌ | `false` | Inject conversation metadata (sender_name, sender_user_id, etc.) into user messages for multi-user bot scenarios |
| `lark.access.dm_policy` | ❌ | `allowlist` | DM access policy: `open` or `allowlist` |
| `lark.access.allow_from` | ❌ | `[]` | DM allowlisted user IDs (open_id format) |
| `lark.access.group_policy` | ❌ | `allowlist` | Group chat access policy: `open`, `allowlist`, or `disabled` |
| `lark.access.group_allow_from` | ❌ | `[]` | Group chat allowlisted group IDs (chat_id format, e.g. `oc_xxx`) |
| `lark.access.history_limit` | ❌ | `50` | Pending history buffer size for non-triggered group messages |
| `lark.access.idle_session_timeout` | ❌ | `86400` | Idle window (seconds) before a DM or group chat auto-starts a new session (persisted across restarts); `0` disables it |

> **Notes**:
> - `domain` field: Use `feishu` for China Feishu users, `lark` (default) for international Lark users
> - Agent type is fixed to `coder` in IM mode, no configuration needed
> - Both `dm_policy` and `group_policy` default to `allowlist` — you need to add entries to the allowlist or change to `open`

---

## 3. Restart Daemon Service

The Lark connection is managed by the background Daemon process. After configuring `conf.yaml`, restart the Daemon to apply changes.

### 3.1 Check Daemon Status

```bash
siada-cli --daemon-status
```

### 3.2 Stop Existing Daemon

```bash
siada-cli --stop-daemon
```

### 3.3 Restart Daemon

```bash
siada-cli
```

Starting siada-cli will automatically launch the Daemon process.

---

## 4. Pair with the Bot

### 4.1 Find Your Bot

After configuration and Daemon startup, search for your bot name (e.g. `Siada Bot`) in Lark and open a direct message conversation.

### 4.2 Send a Test Message

Send any message to the bot to start using it:

```
Hello, write me a quicksort algorithm
```

After receiving a message, the bot will:
1. Add a ⏳ typing reaction to your message (indicating processing)
2. Local Agent starts executing the task
3. Stream results via Streaming Card in real-time
4. Remove the typing reaction when complete

### 4.3 DM (Private Chat) Access Control

DM access is controlled via `dm_policy`, independent of group chat's `group_policy`:

| Policy | Description |
|--------|-------------|
| `open` | Anyone can DM the bot |
| `allowlist` (default) | Only allowlisted users can DM the bot |

If you configured `dm_policy: allowlist` (default) in `conf.yaml`, you need to add users' `open_id` to the `allow_from` list.

**How to get a user's open_id:**

**Method 1:** If a user not in the allowlist sends a message, the bot will automatically reply with their pair key:

```
⚠️ Access denied. Please contact the admin to grant access.

Your pair key: ou_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

Add the `ou_xxx` format open_id to the `allow_from` list in `conf.yaml`:

```yaml
lark:
  access:
    dm_policy: allowlist
    allow_from:
      - "ou_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
```

Restart Daemon to apply changes:

```bash
siada-cli --stop-daemon && siada-cli
```

**Method 2:** Set `dm_policy` to `open` first, have the user send any message to the bot, then check the log for `sender_open_id`:

```bash
tail -f ~/.siada-cli/logs/im.log | grep "Received IM message"
```

Log example:

```
INFO  Received IM message: request_id=xxx, chat_id=oc_xxxxx, chat_type=p2p, sender_open_id=ou_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx, content=...
```

Restart Daemon to apply changes:

```bash
siada-cli --stop-daemon && siada-cli
```

### 4.4 Slash Commands

After pairing, you can use the following slash commands in Lark conversations (IM mode supported subset):

| Command | Description |
|---------|-------------|
| `/help` | Show help information |
| `/status` | Show current status |
| `/model` | Switch model |
| `/clear` | Clear conversation history, start new session |
| `/lang` | Switch language (en / zh-CN) |
| `/pre-plan-mode` | Toggle pre-plan mode |
| `/verbose` | Control output verbosity (see below) |
| `/resume` | Switch to a specific session (DM only) |
| `/mcp-list` | List MCP services and tools |
| `/mcp-server` | Show MCP server connection status |
| `/skill-list` | List available skills |
| `/skill-reload` | Reload skills |
| `/lark-status` | Show Lark MCP auth status |
| `/lark-refresh` | Manually refresh Lark access token |
| `/rule-init` | Create an empty siada_rule.md file |
| `/rule-show` | Display hierarchical context content |
| `/rule-list` | List loaded context files |
| `/rule-refresh` | Refresh hierarchical context |
| `/rule-status` | Display context status |
| `/rule-global-add` | Add global context memory entry |
| `/context-file-refresh` | Refresh SIADA.md and other context files |

> **Note**: Some CLI-only commands (e.g. `/editor`, `/undo`, `/restore`, `/plugin`) are not available in IM mode.

#### Verbose Mode

The `/verbose` command controls IM output verbosity. This is an IM-only command:

| Command | Description |
|---------|-------------|
| `/verbose` | Show current verbose status |
| `/verbose on` | Enable verbose: show 💭 Thinking + 🔧 Tool Calls + 💬 Answer |
| `/verbose off` | Disable verbose: show 💬 Answer only |

**Defaults:**
- **DM (P2P)**: verbose **ON** (show full process)
- **Group chat**: verbose **OFF** (show final answer only, less noise)

Each chat's verbose setting is persisted and survives restarts.

#### Resume Command

`/resume <session_id>` switches to a specific historical session in DM mode, continuing the previous context.

```
/resume feishu_direct_ou_xxx_oc_xxx_20260416
```

> **Note**: `/resume` is only available in DM (P2P) mode.

---

## 5. Group Chat Usage

### 5.1 Group Chat Support

Siada now supports Lark group chats. In group chat, the bot is triggered via **@mention**:

- **@bot + message**: Triggers the Agent to execute a task
- **Non-@bot messages**: Does not trigger the Agent, but gets buffered as pending history context
- **@all**: Also triggers the bot

When the bot is @mentioned, it automatically injects recent chat history before the trigger as context, helping the Agent understand the group conversation background.

### 5.2 Group Chat Access Control

Group chat access is controlled via `group_policy`, independent of DM's `dm_policy`:

| Policy | Description |
|--------|-------------|
| `open` | All groups can use the bot |
| `allowlist` (default) | Only allowlisted groups can use the bot |
| `disabled` | Disable all group chat functionality |

**How to get a group's chat_id:**

1. Set `group_policy` to `open` first
2. @mention the bot in the group
3. Check logs for `chat_id`:
   ```bash
   tail -f ~/.siada-cli/logs/im.log | grep "gate_group_message"
   ```
4. Alternatively, if the group is not in the allowlist, the bot will reply with the group key:
   ```
   ⚠️ Access denied. This group is not in the allowlist.
   Please contact the admin to configure access.
   
   Group key: oc_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```
5. Add the `oc_xxx` format chat_id to `group_allow_from`:
   ```yaml
   lark:
     access:
       group_policy: allowlist
       group_allow_from:
         - "oc_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
   ```
6. Restart Daemon to apply changes

### 5.3 Group Chat Pause Command

In group chat, if the Agent is running a task, you can @mention the bot with a pause keyword to interrupt:

```
@Siada Bot pause
```

or

```
@Siada Bot 暂停
```

After pausing, you can @mention the bot again with a new instruction.

### 5.4 Group Chat Concurrency Limit

Each group can only run one Agent task at a time. If a task is already running, new @triggers will be intercepted with a message:

```
⏳ Task is currently running, please wait for completion.
💡 @me and send `pause`/`暂停` to pause the current task.
```

---

## FAQ

### Q: Bot not responding to messages?

1. **Check if Daemon is running**: `siada-cli --daemon-status`
2. **Check logs for errors**: `tail -100 ~/.siada-cli/logs/siada_cli.log`
3. **Confirm app is published and approved**: Check application status on Lark Open Platform
4. **Confirm all permissions are granted**: Especially `im:message` and event subscriptions
5. **Confirm using long connection for events**: Not HTTP callback mode

### Q: Getting "Access denied"?

- **DM**: Check `lark.access.dm_policy` in `conf.yaml`. Default is `allowlist` — ensure the user's `open_id` is in the `allow_from` list, or change to `open`.
- **Group chat**: Check `lark.access.group_policy`. Default is `allowlist` — ensure the group's `chat_id` is in `group_allow_from`, or change to `open`.

### Q: Connection frequently dropping?

The Lark SDK has built-in heartbeat and auto-reconnection. If connections drop frequently, check:
- Network stability
- `app_id` and `app_secret` correctness
- Application is still active (not disabled)

### Q: Bot not responding in group chat?

1. **Confirm @mention**: Bot must be @mentioned in group chat to trigger
2. **Check group policy**: Ensure `group_policy` is not `disabled`
3. **Check group allowlist**: If `group_policy` is `allowlist`, ensure the group's `chat_id` is in `group_allow_from`
4. **Check for running tasks**: Only one task can run per group at a time — use `@bot pause` to stop then retry

### Q: How to reduce output noise in group chat?

Use `/verbose off` to disable verbose mode. The bot will only show the final answer without thinking process or tool call details. Group chat has verbose off by default.
