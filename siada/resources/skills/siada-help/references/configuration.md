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
| `llm_config.enable_thinking` | bool | (model default) | Hard on/off switch for thinking/reasoning, persisted by `/thinking`. `false` wins over any effort level or thinking-token budget |
| `llm_config.reasoning_effort` | string | (model default) | Default reasoning effort level, persisted by `/effort`. Accepted levels depend on the model |
| `llm_config.vision_model` | string | (none) | Image-capable model used as a "vision bridge" when the main model cannot read images: attachments are transcribed into text evidence by this model before the main model sees them |
| `llm_config.vision_provider` | string | (`llm_config.provider`) | Provider for `llm_config.vision_model` |
| `llm_config.parallel_tool_calls` | bool | `true` | Allow parallel tool calls |

**Example:**
```yaml
llm_config:
  model: claude-3-5-sonnet-20241022
  provider: anthropic
  api_key: sk-ant-...
```

---

## goal

Controls the automatic retry budget for the session's `/goal` verifier.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `goal.max_turns` | int | `6` | Maximum number of consecutive failed verifier turns before a goal is blocked and automatic continuation stops. Values below 1 are treated as 1. |

**Example:**
```yaml
goal:
  max_turns: 8
```

Two consecutive verifier system errors still block a goal independently of this
limit. A failed verdict with an empty `nextAction` also stops automatic
continuation immediately.

---

## proactive

Controls the ProactiveAgent — the background agent that monitors work and runs scheduled tasks.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `proactive.enabled` | bool | `true` | Enable or disable the proactive agent entirely |
| `proactive.work_hours` | string | `"09:00-18:00"` | Active window (format: `HH:MM-HH:MM`) |
| `proactive.trigger_interval` | int | `60` | Minutes between proactive checks |
| `proactive.daily_task_execution_time` | string | `"06:00"` | Time daily task *generation* starts (format: `HH:MM`), staggered over a 2h window |
| `proactive.daily_im_send_time` | string | `"08:30"` | Earliest time the generated daily summary is sent to IM (staggered over 30min after this) |
| `proactive.auto_execute_enabled` | bool | `false` | Auto-execute tasks without user confirmation; default is `false` for safety |
| `proactive.send_daily_summary_to_im` | bool | `false` | Also push the daily summary to configured IM controllers (e.g. Lark) after generation |
| `proactive.llm_config` | object | (none) | Override the default model specifically for cron/proactive tasks (same shape as top-level `llm_config`) |

**Notes:**
- `auto_execute_enabled: false` means all tasks require explicit user approval before running.
- Setting `auto_execute_enabled: true` allows tasks with `needs_confirmation=false` to run autonomously.
- Work hours are checked when the daemon decides whether to send proactive messages.
- `daily_task_execution_time` was renamed in meaning from "notification time" to "task generation start time"; the actual notification time is now controlled separately by `daily_im_send_time`.

**Example:**
```yaml
proactive:
  enabled: true
  work_hours: "09:00-18:00"
  trigger_interval: 60
  daily_task_execution_time: "06:00"
  daily_im_send_time: "08:30"
  auto_execute_enabled: false
  send_daily_summary_to_im: false
```

---

## checkpoint_config

Controls session checkpointing (save/restore conversation state).

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `checkpoint_config.enable` | bool | `true` | Enable session checkpoints |
| `checkpoint_config.max_checkpoint_files` | int | `10` | Maximum checkpoint files to retain |

---

## auto_update

Controls the background auto-update mechanism run by the proactive daemon (silently checks for and installs new siada-cli versions).

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `auto_update.enabled` | bool | `true` | Enable silent background update checks and installation |
| `auto_update.check_interval_minutes` | int | `30` | How often to check for a new version, in minutes |
| `auto_update.channel` | string | `"prod"` | Release channel: `prod`, `beta`, or `test` |

**Example:**
```yaml
auto_update:
  enabled: true
  check_interval_minutes: 30
  channel: "prod"
```

Related CLI flag: `siada-cli --just-check-update` checks the version once without installing.

---

## code_agent

Controls behavior of the code generation agent.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `code_agent.max_turns` | int | `1000` | Maximum number of turns (LLM round-trips) for a single code agent run |

**Example:**
```yaml
code_agent:
  max_turns: 1000
```

---

## sub_agent

Controls the sub-agent feature — the parallel task-dispatch mechanism (`run_subtask`) that lets the main agent hand self-contained work to a helper agent running in a clean context window.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `sub_agent.enabled` | bool | `true` | Master switch for the whole feature. `false` removes `run_subtask` from the agent's tool list and drops its prompt guidance, so every task is worked inline in the main agent's own context. |
| `sub_agent.allow_recursive_subagents` | bool | `false` | Allow a sub-agent to launch its own sub-sub-agent (nesting hard-capped at 2 levels; at most 12 live agents per agent tree). Only effective while `sub_agent.enabled: true`. |
| `sub_agent.llm_config` | object | (none) | Override the default model specifically for sub-agents (same shape as top-level `llm_config`) |

**Notes:**
- Disabling `sub_agent.enabled` also disables recursive nesting, since it is an extension of the same feature.
- Some bundled skills (e.g. `design-doc-writer`) are built around `run_subtask`; with the feature disabled the agent simply does that work inline instead of delegating it.
- Changes take effect after a daemon restart (see the top of this page).

**Example:**
```yaml
sub_agent:
  enabled: true
  allow_recursive_subagents: false
  llm_config:
    model: claude-sonnet-4.6
```

---

## memory

Master switch and tuning for the cross-session memory subsystem (inline `MEMORY.md`/`USER.md` plus the holographic structured-fact layer).

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `memory.enabled` | bool | `true` | Master switch for the entire memory subsystem (tools, prompt sections, background update pipeline, holographic memory). Set `false` to silence memory entirely. |
| `memory.user_profile_enabled` | bool | `true` | Enable the personal work-style/preferences profile (`USER.md`) |
| `memory.memory_facts_enabled` | bool | `true` | Enable general fact/experience memory (`MEMORY.md`) |
| `memory.memory_char_limit` | int | `2200` | Character budget injected from `MEMORY.md` per turn |
| `memory.user_char_limit` | int | `1375` | Character budget injected from `USER.md` per turn |

### memory.holographic

Sub-section of `memory`: structured fact memory with entity binding and trust scoring (SQLite + FTS5). See `design_docs/siada-holographic-memory-introduction.md` for background.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `memory.holographic.enabled` | bool | `true` | Enable holographic structured fact memory (only effective when `memory.enabled: true`) |
| `memory.holographic.hrr_enabled` | bool | `true` | Enable HRR (Holographic Reduced Representation) vectors even when `numpy` is available |
| `memory.holographic.hrr_dim` | int | `1024` | Phase vector length; raise (e.g. to `4096`) for more per-bank capacity |
| `memory.holographic.default_trust` | float | `0.5` | Initial trust score assigned to newly stored facts |
| `memory.holographic.min_trust_threshold` | float | `0.3` | Facts below this trust score are excluded from default search/prefetch |
| `memory.holographic.temporal_decay_half_life` | int | `0` | `0` disables time decay; e.g. `90` halves a fact's relevance every 90 days |
| `memory.holographic.prefetch_limit` | int | `5` | Max number of facts injected into context per turn |
| `memory.holographic.db_path` | string | `~/.siada-cli/workspace/memory/holographic/facts.db` | Override the SQLite DB path |
| `memory.holographic.custom_dict` | list[string] | `[]` | Extra jieba segmentation terms (e.g. project/product names) to improve Chinese fact search |

**Example:**
```yaml
memory:
  enabled: true
  user_profile_enabled: true
  memory_facts_enabled: true
  memory_char_limit: 2200
  user_char_limit: 1375
  holographic:
    enabled: true
    hrr_enabled: true
    hrr_dim: 1024
    default_trust: 0.5
    min_trust_threshold: 0.3
    temporal_decay_half_life: 0
    prefetch_limit: 5
    custom_dict:
      - your-project-name
```

---

## web

Tri-state master switch for the web tools (`web_search` / `web_fetch`) exposed to the agent.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `web.enabled` | bool or null | `null` (on) | `null`/unset = on (default); `true` = always on; `false` = always off |

**Example:**
```yaml
web:
  enabled: true
```

---

## lark

Configures the Lark/Feishu bot integration that lets you remotely control your local siada-cli from a Lark chat (DM or @mention in a group). This is a **separate feature** from the generic MCP integration — it turns Lark into another *client/entry point* for siada, not just a tool the agent can call. See `docs/remote_control_lark.md` for the full setup guide.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `lark.mode` | string | `"relay"` | `"relay"` (via IM Gateway, no bot credentials needed) or `"direct"` (talk to Lark's WebSocket SDK directly) |
| `lark.workspace` | string | `~/.siada-cli/workspace/lark` | Workspace directory for Lark session state |
| `lark.direct.app_id` | string | (none) | Lark app ID (only for `mode: direct`) |
| `lark.direct.app_secret` | string | (none) | Lark app secret (only for `mode: direct`) |
| `lark.direct.access.dm_policy` | string | `"open"` | `"open"` or `"allowlist"` — who can DM the bot (only for `mode: direct`) |
| `lark.direct.access.allow_from` | list[string] | `[]` | Allowed Lark open IDs when `dm_policy: allowlist` |
| `lark.relay.server_url` | string | (hardcoded default) | IM Gateway relay WebSocket URL (only needed to override the default) |
| `lark.relay.heartbeat_interval` | int | `10` | Relay heartbeat interval in seconds |
| `lark.relay.reconnect_backoff` | list[int] | `[3, 5, 10, 30, 60]` | Reconnect backoff schedule in seconds |

**Example (relay mode, minimal):**
```yaml
lark:
  mode: relay
```

**Example (direct mode):**
```yaml
lark:
  mode: direct
  direct:
    app_id: "your_app_id"
    app_secret: "your_app_secret"
    access:
      dm_policy: allowlist
      allow_from:
        - "ou_xxx"
```

---

## compaction_strategy

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `compaction_strategy` | string or null | `null` (auto-detect) | Context compression strategy. Auto-detected by session mode when unset: CLI/TUI → `"header_summary"`, IM → `"turn_prune_summary"`. Valid values: `"header_summary"` (conservative, keeps the first user/assistant pair as a header) or `"turn_prune_summary"` (multi-layer: turn limit + tool truncation + LLM summary) |

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

## enable_notification

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enable_notification` | bool | `true` | Whether to send a task-completion notification when an agent turn finishes |

---

## ui

Terminal UI preferences (terminal and front-end themes). Written by slash commands, so you normally don't need to edit this section by hand.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `ui.theme` | string | `"auto"` | UI color theme: `"auto"` (follows the system/terminal background), `"dark"`, or `"light"`. Persisted by `/theme` |

**Example:**
```yaml
ui:
  theme: dark
```

---

## im

Settings for the Lark/Feishu IM client (see the `lark` section for enabling remote control).

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `im.verbose.p2p` | bool | `true` | Stream detail level in direct (1:1) chats: `true` shows thinking + tool calls + answer, `false` shows only the answer |
| `im.verbose.group` | bool | `false` | Same switch for group chats |

**Example:**
```yaml
im:
  verbose:
    p2p: true
    group: false
```

---

## headroom

Optional integration with a local `headroom` proxy that routes LLM traffic and tracks a spend budget. Only effective when enabled; upstream endpoints are not configurable.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `headroom.enabled` | bool | `false` | Start the local headroom proxy and route LLM traffic through it |
| `headroom.host` | string | `"127.0.0.1"` | Proxy bind host |
| `headroom.port` | int | `8787` | Proxy port |
| `headroom.budget` | float or null | `null` | Spend limit in USD (no limit when unset) |
| `headroom.budget_period` | string | `"daily"` | Budget window: `hourly`, `daily`, or `monthly` |
| `headroom.telemetry` | bool | `false` | Send proxy telemetry |
| `headroom.startup_timeout` | float | `30.0` | Seconds to wait for the proxy to become healthy at startup |

Related CLI flags: `--headroom` (one-click enable), `--no-headroom` (force off, overrides `conf.yaml`), `--headroom-port <port>`, `--headroom-budget <usd>`.

---

## user_id and credentials

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `user_id` | string | (set at login) | Identifier written automatically when you sign in |
| `siada_api_key` | string | (set at login) | Access token for the configured provider |
| `refresh_token` | string | (set at login) | Token used to silently renew `siada_api_key` |
| `user_email` | string | (set at login) | Email of the signed-in account |
| `email_refresh_token` | string | (set at login) | Refresh token for the email identity |

These keys are written by the login flow (`/configure`) and removed by `/logout`. There is normally no reason to edit them by hand.

---

## Full example conf.yaml

```yaml
llm_config:
  model: claude-sonnet-4.6

proactive:
  enabled: true
  work_hours: "09:00-18:00"
  trigger_interval: 60
  daily_task_execution_time: "06:00"
  daily_im_send_time: "08:30"
  auto_execute_enabled: false
  send_daily_summary_to_im: false

checkpoint_config:
  enable: true
  max_checkpoint_files: 10

auto_update:
  enabled: true
  check_interval_minutes: 30
  channel: "prod"

code_agent:
  max_turns: 1000

memory:
  enabled: true
  user_profile_enabled: true
  memory_facts_enabled: true
  memory_char_limit: 2200
  user_char_limit: 1375
  holographic:
    enabled: true
    hrr_dim: 1024

web:
  enabled: null

sub_agent:
  enabled: true
  allow_recursive_subagents: false

ui:
  theme: auto

im:
  verbose:
    p2p: true
    group: false

# lark:
#   mode: relay

compaction_strategy: null
command_timeout: 300
pre_plan: false
preferred_language: null
enable_notification: true
```

---

## Not covered by `conf.yaml` (separate config files)

These are configured in their own files, not `~/.siada-cli/conf.yaml`:

| What | File |
|------|------|
| Per-model overrides (context window, pricing, thinking budget, etc.) | `~/.siada-cli/model_config.json` — see `docs/external_model_configuration.md` |
| MCP servers | `~/.siada-cli/mcp_config.json` |
| Cron tasks | `~/.siada-cli/workspace/cron_tasks.json` (managed via the **manage-cron-task** skill) |
| Custom slash commands | `~/.siada-cli/commands/**/*.toml` |
