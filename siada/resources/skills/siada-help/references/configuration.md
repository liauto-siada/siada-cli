# Siada Configuration Reference

Configuration file location: `~/.siada-cli/conf.yaml`

**Important**: After modifying `conf.yaml`, restart the daemon for changes to take effect:
```
siada-cli --stop-daemon
siada-cli
```

---

## llm_config

Controls which LLM model siada uses.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `llm_config.model` | string | `claude-sonnet-4.6` | Model name, e.g. `claude-3-5-sonnet-20241022`, `gpt-4o` |
| `llm_config.provider` | string | (auto-detected) | Provider: `anthropic`, `openai`, etc. |
| `llm_config.base_url` | string | (provider default) | API endpoint base URL |
| `llm_config.api_key` | string | (env var) | API key for authentication |
| `llm_config.thinking` | bool | `true` | Enable extended thinking for models that support it |
| `llm_config.parallel_tool_calls` | bool | `true` | Allow parallel tool calls |

**Example:**
```yaml
llm_config:
  model: claude-3-5-sonnet-20241022
  provider: anthropic
  api_key: sk-ant-...
```

---

## proactive

Controls the ProactiveAgent — the background agent that monitors work and runs scheduled tasks.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `proactive.enabled` | bool | `true` | Enable or disable the proactive agent entirely |
| `proactive.work_hours` | string | `"09:00-18:00"` | Active window (format: `HH:MM-HH:MM`) |
| `proactive.trigger_interval` | int | `60` | Minutes between proactive checks |
| `proactive.daily_task_execution_time` | string | `"08:30"` | Time daily cron tasks fire (format: `HH:MM`) |
| `proactive.auto_execute_enabled` | bool | `false` | Auto-execute tasks without user confirmation; default is `false` for safety |

**Notes:**
- `auto_execute_enabled: false` means all tasks require explicit user approval before running.
- Setting `auto_execute_enabled: true` allows tasks with `needs_confirmation=false` to run autonomously.
- Work hours are checked when the daemon decides whether to send proactive messages.

**Example:**
```yaml
proactive:
  enabled: true
  work_hours: "09:00-18:00"
  trigger_interval: 60
  daily_task_execution_time: "08:30"
  auto_execute_enabled: false
```

---

## checkpoint_config

Controls session checkpointing (save/restore conversation state).

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `checkpoint_config.enable` | bool | `true` | Enable session checkpoints |
| `checkpoint_config.max_checkpoint_files` | int | `10` | Maximum checkpoint files to retain |

---

## command_timeout

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `command_timeout` | int | (none) | Timeout in seconds for shell command execution |

---

## pre_plan

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `pre_plan` | bool | `false` | Agent shows a plan and waits for approval before executing |

---

## preferred_language

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `preferred_language` | string | `null` | Preferred language for AI responses: `"en"` (English) or `"zh-CN"` (Chinese) |

---

## Full example conf.yaml

```yaml
llm_config:
  model: claude-sonnet-4.6

proactive:
  enabled: true
  work_hours: "09:00-18:00"
  trigger_interval: 60
  daily_task_execution_time: 08:30
  auto_execute_enabled: false

checkpoint_config:
  enable: true
  max_checkpoint_files: 10

command_timeout: 300
pre_plan: false
preferred_language: null
```
