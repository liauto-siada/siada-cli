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
| `llm_config.model` | string | `claude-sonnet-5` | Model name, e.g. `claude-sonnet-5`, `gpt-6-astra`, `kimi-k3`. Built-in catalog names are the vendor's own model IDs |
| `llm_config.provider` | string | (auto-detected) | Provider: `anthropic`, `openai`, etc. Signing in with your own API key writes `default` |
| `llm_config.base_url` | string | (provider default) | API endpoint base URL |
| `llm_config.api_key` | string | (env var) | API key for authentication |
| `llm_config.thinking` | bool | `true` | Enable extended thinking for models that support it |
| `llm_config.enable_thinking` | bool | (model default) | Hard on/off switch for thinking/reasoning, persisted by `/thinking`. `false` wins over any effort level or thinking-token budget |
| `llm_config.reasoning_effort` | string | (model default) | Default reasoning effort level, persisted by `/effort`. Accepted levels depend on the model |
| `llm_config.vision_model` | string | (none) | Image-capable model used as a "vision bridge" when the main model cannot read images: attachments are transcribed into text evidence by this model before the main model sees them |
| `llm_config.vision_provider` | string | (`llm_config.provider`) | Provider for `llm_config.vision_model` |
| `llm_config.parallel_tool_calls` | bool | `true` | Allow parallel tool calls |

**Sign-in:** this build authenticates with your own provider API key. Signing in writes `provider: default`, `provider_id`, `base_url`, `api_key` (and `model`) into `llm_config`; `/logout` (or `siada-cli --logout`) removes those four provider/credential keys and leaves the rest of the section intact. `siada-cli --set-env API_KEY=... --set-env BASE_URL=...` supplies credentials for that invocation through the environment — it does not rewrite `conf.yaml`.

**Example:**
```yaml
llm_config:
  model: claude-sonnet-5
  provider: default
  provider_id: anthropic
  base_url: https://api.anthropic.com
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

Controls session checkpointing (save/restore conversation state). Disabled unless you turn it on.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `checkpoint_config.enable` | bool | `false` | Enable session checkpoints. Non-interactive runs always disable checkpointing |
| `checkpoint_config.max_checkpoint_files` | int | `50` | Maximum checkpoint files to retain per session. `0` or a negative value disables automatic cleanup |

Checkpoints are stored under `~/.siada-cli/data/tmp/{project_hash}/checkpoints/{session_id}/`; cleanup removes the oldest files in batches once the count exceeds the limit. Use `/resume`, `/undo`, `/restore` and `/compare` to work with them.

---

## auto_update

Controls the background auto-update mechanism run by the proactive daemon (silently checks for and installs new siada-cli versions).

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `auto_update.enabled` | bool | `true` | Enable silent background update checks and installation |
| `auto_update.check_interval_minutes` | int | `30` | How often to check for a new version, in minutes |
| `auto_update.channel` | string | `"prod"` | Which release line the updater reports against: `prod`, `beta`, or `test`. Releases are always read from the published `siada-cli` metadata; the channel is carried through for reporting |

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
    model: claude-sonnet-4-6
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

Sub-section of `memory`: structured fact memory with entity binding and trust scoring (local SQLite database with FTS5 tables). Each fact carries a trust score that decays over time; facts below the threshold are kept out of default search/prefetch.

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

Configures the Lark/Feishu bot integration that lets you remotely control your local siada-cli from a Lark chat (DM or @mention in a group). This is a **separate feature** from the generic MCP integration — it turns Lark into another *client/entry point* for siada, not just a tool the agent can call. See `docs/remote_control_lark.md` for the full setup guide (creating the app, permissions, pairing).

This build serves **direct mode only**: siada talks to the Lark Open Platform over the Lark SDK's WebSocket long connection, using your own app credentials. `mode: relay` (via a hosted IM Gateway) is a legacy value from older builds — the relay client is not bundled, and the daemon refuses to start that connection with a clear error. Set `mode: direct`.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `lark.enabled` | bool | `true` | Set `false` to disable the Lark bot without removing the config (the daemon then starts without a Lark connection) |
| `lark.mode` | string | `"direct"` | Connection mode. Only `"direct"` is supported in this build; `"relay"` is legacy and fails with a clear error |
| `lark.workspace` | string | `~/.siada-cli/workspace/lark` | Workspace directory for Lark session state |
| `lark.notify_email` | string | (none) | Optional email used to auto-resolve the `open_id` for routing bootstrap |
| `lark.direct.app_id` | string | (none) | Lark app ID (required for direct mode) |
| `lark.direct.app_secret` | string | (none) | Lark app secret (required for direct mode) |
| `lark.direct.domain` | string | `"lark"` | Lark domain: `"lark"` (international), `"feishu"` (China), or a custom base URL |
| `lark.direct.http_timeout_ms` | int | `30000` | HTTP request timeout in milliseconds |
| `lark.direct.resolve_sender_names` | bool | `true` | Resolve sender display names through the contact API |
| `lark.context.include_conversation_info` | bool | `true` | Inject conversation metadata (sender name, user ID, ...) into user messages |
| `lark.access.group_policy` | string | `"allowlist"` | Group chats: `"open"`, `"allowlist"` or `"disabled"` |
| `lark.access.group_allow_from` | list[string] | `[]` | Allowed group chat IDs when `group_policy: allowlist` |
| `lark.access.history_limit` | int | `30` | Pending-history buffer per group chat |
| `lark.access.idle_session_timeout` | int | `86400` | Seconds of DM silence after which the next message starts a new session (`<= 0` disables) |
| `lark.access.dm_policy` | string | `"allowlist"` | `"open"` or `"allowlist"` — who may DM the bot |
| `lark.access.allow_from` | list[string] | `[]` | Allowed Lark open IDs when `dm_policy: allowlist` |

The whole `lark` section is a nested object, so it has no `config_manager.py set` target — edit it in `conf.yaml` by hand.

The old `lark.relay.*` keys (`server_url`, `heartbeat_interval`, `reconnect_backoff`) have no effect in this build and can be deleted.

**Example (direct mode, minimal):**
```yaml
lark:
  mode: direct
  direct:
    app_id: "cli_xxxxxxxxxxxx"
    app_secret: "xxxxxxxxxxxxxxxx"
```

**Example (direct mode with access control):**
```yaml
lark:
  enabled: true
  mode: direct
  direct:
    app_id: "cli_xxxxxxxxxxxx"
    app_secret: "xxxxxxxxxxxxxxxx"
    domain: feishu
  access:
    dm_policy: allowlist
    allow_from:
      - "ou_xxxxxxxxxxxxxxxx"
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
| `ui.theme` | string | `"dark"` | UI color theme: `"dark"` or `"light"`. Legacy `"auto"` uses `"dark"` without detection. Persisted by `/theme` |

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

## headroom (legacy, not supported)

Older builds (and older `conf.yaml` files) may contain a `headroom:` section — a proxy that used to route LLM traffic and track a spend budget. **The proxy integration is not part of this distribution:** nothing is bundled or started, and the `--headroom*` CLI flags (`--headroom`, `--no-headroom`, `--headroom-port`, `--headroom-budget`) were removed.

The keys below are still *read* from an existing file so that a config migrated from an older build keeps parsing — they have no effect, and `enabled: true` does **not** start any proxy or route traffic:

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `headroom.enabled` | bool | `false` | Ignored — retained only for compatibility with older config files |
| `headroom.host` | string | `"127.0.0.1"` | Ignored |
| `headroom.port` | int | `8787` | Ignored |
| `headroom.budget` | float or null | `null` | Ignored |
| `headroom.budget_period` | string | `"daily"` | Ignored |
| `headroom.telemetry` | bool | `false` | Ignored |
| `headroom.startup_timeout` | float | `30.0` | Ignored |

The whole section can be deleted from `conf.yaml` without changing behavior.

---

## Sign-in state (API key) and legacy credential keys

This build signs in with your own **provider API key**. Everything it stores lives inside `llm_config`:

| Key | Description |
|-----|-------------|
| `llm_config.provider` | `"default"` after an API-key sign-in |
| `llm_config.provider_id` | Provider the key belongs to (e.g. `openai`, `kimi`, `custom`) |
| `llm_config.base_url` | API endpoint the key is used with |
| `llm_config.api_key` | The API key itself |
| `llm_config.model` | Model selected during sign-in |

`/configure` re-runs the sign-in selector (cancel leaves the session untouched); `/logout` (or `siada-cli --logout`) removes the stored key. `siada-cli --user-id` and `siada-cli --access-token` are deprecated and rejected: they exit with an error explaining that this build authenticates with a provider API key, plus how to configure one (`--set-env API_KEY=... --set-env BASE_URL=...`, or the login prompt).

Older builds signed in with LiId/domain-account credentials and wrote extra top-level keys. Those may still be present in a migrated `conf.yaml`; the current sign-in flow never writes them, so treat them as compatibility-only and leave them alone:

| Key | Status |
|-----|--------|
| `user_id` | Legacy account identifier. Not written by the API-key sign-in; a few older code paths still consult it, so do not hand-edit it |
| `siada_api_key` | Legacy access token — no longer read |
| `refresh_token` | Legacy token — no longer read |
| `user_email` | Legacy account email — no longer read |
| `email_refresh_token` | Legacy token — no longer read |

These legacy keys reach the validator's known-key list, so `config_manager.py validate` will not flag them as unknown.

---

## Full example conf.yaml

```yaml
llm_config:
  model: claude-sonnet-5

proactive:
  enabled: true
  work_hours: "09:00-18:00"
  trigger_interval: 60
  daily_task_execution_time: "06:00"
  daily_im_send_time: "08:30"
  auto_execute_enabled: false
  send_daily_summary_to_im: false

checkpoint_config:
  enable: false
  max_checkpoint_files: 50

auto_update:
  enabled: true
  check_interval_minutes: 30
  channel: "prod"

code_agent:
  max_turns: 1000

goal:
  max_turns: 6

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
  theme: dark

im:
  verbose:
    p2p: true
    group: false

# lark:
#   mode: direct
#   direct:
#     app_id: "cli_xxxxxxxxxxxx"
#     app_secret: "xxxxxxxxxxxxxxxx"

compaction_strategy: null
command_timeout: 300
preferred_language: null
enable_notification: true
```

---

## Not covered by `conf.yaml` (separate config files)

These are configured in their own files, not `~/.siada-cli/conf.yaml`:

| What | File |
|------|------|
| User-defined models (context window, thinking defaults, pricing, vision bridge) | `~/.siada-cli/models.json` — see `docs/external_model_configuration.md`. When present, user models replace the built-in catalog and user prices win over the built-in estimates |
| MCP servers | `~/.siada-cli/mcp_config.json` (a project-level `siada_mcp_config.json` is also read) |
| Cron tasks | `~/.siada-cli/workspace/cron_tasks.json` (managed via the **manage-cron-task** skill) |
| Custom slash commands | `~/.siada-cli/commands/**/*.toml` |
