---
name: siada-help
description: Answer user questions about siada (features, configuration, usage) and modify siada's configuration file. Use when the user asks how siada works, what settings are available, or wants to change siada's config.
metadata:
  short-description: Answer siada questions and manage siada configuration
---

# Siada Help

This skill handles three types of requests:

1. **Q&A** — answer questions about siada's features, components, and configuration
2. **Config changes** — read or modify `~/.siada-cli/conf.yaml`
3. **Config diagnostics** — check whether `conf.yaml` is syntactically valid and correctly typed

---

## Workflow: Answering Questions

1. Read `{skill_dir}/references/features.md` for feature and usage questions.
2. Read `{skill_dir}/references/configuration.md` for config schema questions.
3. Answer directly and concisely. If the user wants to change a setting, switch to the Config workflow.

**When explaining how to do something, always give the user-facing approach:**
- If a built-in slash command exists for the task (e.g. `/model` to switch models), tell the user to use that command.
- If no slash command applies, tell the user to edit `~/.siada-cli/conf.yaml` directly.
- **Never tell users to run `config_manager.py`** — that is an internal tool used by siada to make changes on the user's behalf, not a user-facing instruction.

### Siada Overview

**siada** is an AI coding assistant with:

- **CodeGenAgent** (`coder`) — main agent that writes code, edits files, runs commands
- **ProactiveAgent** (`proactive`) — background agent that monitors work, sends daily summaries, runs scheduled cron tasks
- **Daemon** — background process hosting both agents; auto-starts when siada launches
- **CLI** — `siada-cli` command for interactive sessions

**Key files:**
- `~/.siada-cli/conf.yaml` — main configuration (LLM, proactive agent, checkpoints)
- `~/.siada-cli/user_preference.yaml` — UI preferences (theme, pre_plan)
- `~/.siada-cli/mcp_config.json` — MCP server configuration
- `~/.siada-cli/workspace/cron_tasks.json` — scheduled cron tasks
- `~/.siada-cli/workspace/memory/` — agent memory files

**Daemon commands:**
```
siada-cli --stop-daemon     # stop daemon
siada-cli --daemon-status   # check if running
```
Note: there is no separate start command; the daemon auto-starts when siada is launched.

---

## Workflow: Modifying Configuration

**Before making any change, confirm the exact key:**
- If the user's request maps clearly and unambiguously to one of the valid keys in the table below, proceed directly.
- If there is **any doubt** about which key the user means (e.g., vague description, multiple matching keys, or unknown key), **ask the user to confirm the exact key and value before running any command**. Do not guess or pick the most likely option silently.

Use `{skill_dir}/scripts/config_manager.py` for all config operations. This script is for siada's internal use only — do not quote these commands in responses to the user.


### View current config

```bash
python {skill_dir}/scripts/config_manager.py view
```

### Get a specific value

```bash
python {skill_dir}/scripts/config_manager.py get --key llm_config.model
python {skill_dir}/scripts/config_manager.py get --key proactive.enabled
```

### Set a value

```bash
python {skill_dir}/scripts/config_manager.py set --key <dotted.key> --value <value>
```

**Common examples:**

```bash
# Change LLM model
python {skill_dir}/scripts/config_manager.py set --key llm_config.model --value claude-3-5-sonnet-20241022

# Disable proactive agent
python {skill_dir}/scripts/config_manager.py set --key proactive.enabled --value false

# Change work hours
python {skill_dir}/scripts/config_manager.py set --key proactive.work_hours --value "08:00-20:00"

# Change daily task time
python {skill_dir}/scripts/config_manager.py set --key proactive.daily_task_execution_time --value "09:00"

# Enable auto-execute (use with caution)
python {skill_dir}/scripts/config_manager.py set --key proactive.auto_execute_enabled --value true

# Set command timeout
python {skill_dir}/scripts/config_manager.py set --key command_timeout --value 300
```

### Validate config syntax

```bash
python {skill_dir}/scripts/config_manager.py validate
```

### Valid config keys

| Key | Type |
|-----|------|
| `llm_config.model` | string |
| `llm_config.provider` | string |
| `llm_config.base_url` | string |
| `llm_config.api_key` | string |
| `llm_config.thinking` | bool |
| `llm_config.parallel_tool_calls` | bool |
| `checkpoint_config.enable` | bool |
| `checkpoint_config.max_checkpoint_files` | int |
| `proactive.enabled` | bool |
| `proactive.work_hours` | string |
| `proactive.trigger_interval` | int |
| `proactive.daily_task_execution_time` | string |
| `proactive.auto_execute_enabled` | bool |
| `command_timeout` | int |

---

## Workflow: Diagnosing Configuration

**Trigger:** user asks whether their config is correct/healthy (e.g. "配置是否正常", "配置有没有问题", "is my config ok", "check my config").

### Steps

1. Run validate to check YAML syntax, unknown keys, and value types:

```bash
python {skill_dir}/scripts/config_manager.py validate
```

2. If the file is missing, tell the user: siada will use built-in defaults, no action needed.

3. Parse the output and report to the user in plain language:
   - Lines starting with `[OK]` — fine, no need to list all of them unless asked
   - Lines starting with `[WARN]` — explain each issue and how to fix it (edit `~/.siada-cli/conf.yaml` or use the relevant slash command)
   - Line starting with `[ERROR]` — YAML is broken; show the error and tell the user to check the file manually
   - "All checks passed" — tell the user the config looks correct

4. Optionally show the current config with `view` if the user wants to review the values:

```bash
python {skill_dir}/scripts/config_manager.py view
```

---

## After Config Changes

Always remind the user:

> Configuration saved. Restart the siada daemon for changes to take effect:
> ```
> siada --stop-daemon
> siada
> ```

A backup of the previous config is automatically saved to `~/.siada-cli/conf.yaml.bak`.

---

## Notes

- `{skill_dir}` is the absolute path to this skill directory.
- For cron task management, use the **manage-cron-task** skill instead.
- For complete config schema, see `{skill_dir}/references/configuration.md`.
