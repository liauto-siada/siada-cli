# Remote Control Siada via Lark

Remotely control your local siada-cli through a Lark bot. The local siada-cli communicates directly with the Lark Open Platform via the Lark SDK's WebSocket long connection, without deploying a relay server. Messages sent to the bot in Lark are forwarded to the local Agent for execution, and results are streamed back in real-time.

> **Use cases**: Individual developers, small team internal use. Each bot instance can only be bound to one local siada-cli process.

---

## Table of Contents

1. [Create a Lark Bot](#1-create-a-lark-bot)
2. [Configure conf.yaml](#2-configure-confyaml)
3. [Restart Daemon Service](#3-restart-daemon-service)
4. [Pair with the Bot](#4-pair-with-the-bot)

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

| Permission ID | Permission Name | Purpose |
|--------------|-----------------|---------|
| `im:message` | Read and send messages in chats | Receive user messages |
| `im:message:send_as_bot` | Send messages as the app | Bot replies |
| `im:message.reactions:write_as_bot` | Add message reactions as the app | Typing indicator animation |
| `contact:user.base:readonly` | Get basic user info | Resolve sender names |
| `im:chat:readonly` | Get chat info | Read conversation info |
| `cardkit:card` | Create and update cards | Streaming Card output |

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
  # Connection mode: direct (Lark WS SDK) or relay (via IM Gateway)
  mode: direct

  # Working directory (optional, defaults to ~/.siada-cli/workspace/lark)
  # workspace: /path/to/your/project

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

  # Access control (optional)
  access:
    # DM policy: open (anyone) or allowlist (whitelist only)
    dm_policy: open

    # Allowlist (only effective when dm_policy is allowlist)
    # allow_from:
    #   - "ou_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    #   - "ou_yyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy"
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
```

### 2.4 Configuration Reference

| Config Item | Required | Default | Description |
|-------------|----------|---------|-------------|
| `lark.mode` | ✅ | - | Connection mode, use `direct` for direct mode |
| `lark.workspace` | ❌ | `~/.siada-cli/workspace/lark` | Agent working directory |
| `lark.direct.app_id` | ✅ | - | Lark App ID |
| `lark.direct.app_secret` | ✅ | - | Lark App Secret |
| `lark.direct.domain` | ❌ | `lark` | `feishu` (China Feishu) or `lark` (international Lark), or custom domain |
| `lark.direct.http_timeout_ms` | ❌ | `30000` | HTTP API request timeout (ms) |
| `lark.direct.resolve_sender_names` | ❌ | `true` | Whether to resolve sender names via API |
| `lark.access.dm_policy` | ❌ | `open` | DM access policy: `open` or `allowlist` |
| `lark.access.allow_from` | ❌ | `[]` | Allowlisted user IDs (open_id format) |

> **Notes**:
> - `domain` field: Use `feishu` for China Feishu users, `lark` (default) for international Lark users
> - Agent type is fixed to `coder` in IM mode, no configuration needed

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

### 4.3 Access Control Pairing

If you configured `dm_policy: allowlist` in `conf.yaml`, you need to add users' `open_id` to the `allow_from` list.

**How to get a user's open_id:**

1. Set `dm_policy` to `open` first
2. Have the user send any message to the bot
3. Check the log for `user_id` or `sender_open_id`:
   ```bash
   tail -f ~/.siada-cli/logs/siada_cli.log | grep "Received IM message"
   ```
   Log example:
   ```
   INFO  Received IM message: request_id=xxx, user_id=ou_xxxxx, chat_id=oc_xxxxx, ...
   ```
4. Alternatively, if a user not in the allowlist sends a message, the bot will reply with their pair key:
   ```
   ⚠️ Access denied. Please contact the admin to grant access.
   
   Your pair key: ou_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```
5. Add the `ou_xxx` format open_id to the `allow_from` list in `conf.yaml`:
   ```yaml
   lark:
     access:
       dm_policy: allowlist
       allow_from:
         - "ou_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
   ```
6. Restart Daemon to apply changes

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

> **Note**: Some CLI-only commands (e.g. `/editor`, `/undo`, `/restore`, `/resume`) are not available in IM mode.

---

## FAQ

### Q: Bot not responding to messages?

1. **Check if Daemon is running**: `siada-cli --daemon-status`
2. **Check logs for errors**: `tail -100 ~/.siada-cli/logs/siada_cli.log`
3. **Confirm app is published and approved**: Check application status on Lark Open Platform
4. **Confirm all permissions are granted**: Especially `im:message` and event subscriptions
5. **Confirm using long connection for events**: Not HTTP callback mode

### Q: Getting "Access denied"?

Check `lark.access.dm_policy` in `conf.yaml`. If set to `allowlist`, ensure the user's `open_id` is added to the `allow_from` list.

### Q: Connection frequently dropping?

The Lark SDK has built-in heartbeat and auto-reconnection. If connections drop frequently, check:
- Network stability
- `app_id` and `app_secret` correctness
- Application is still active (not disabled)

### Q: Group chat supported?

Currently only **direct messages (p2p)** are supported. Group messages are automatically ignored.