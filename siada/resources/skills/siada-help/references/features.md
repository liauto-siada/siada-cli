# Siada Feature Reference

## Conversation & Coding

- **Write and edit code**: describe what you need — siada writes code, makes edits, and fixes bugs
- **Read and explain code**: ask siada to explain the logic or meaning of any code snippet
- **Run terminal commands**: siada can execute shell commands and return the output
- **File operations**: create, edit, view, and search files

## @ File References

Use `@filename` in conversation to bring file content into context:

```
@main.py what's wrong with this function?
@src/ give me an overview of this directory
```

Supports single files, directories, and fuzzy matching (e.g. `@main` matches `main.py`).

## Built-in Slash Commands

Type `/` in the input box to trigger — no configuration required:

| Command | Description |
|---------|-------------|
| `/model` | Open model selector (UI picker in UI mode, text list in terminal mode) |
| `/model <name>` | Switch to the specified model and persist to `conf.yaml` |
| `/status` | Show current status (model, agent, session ID, workspace) |
| `/clear` | Clear conversation history and start a new task |
| `/lang en` / `/lang zh-CN` | Switch language preference |
| `/pre-plan-mode` | Toggle plan mode (show a plan before executing) |
| `/task-list` | View pending tasks discovered by the proactive agent |
| `/skill-list` | List all available skills |
| `/skill-reload` | Reload skills (clear cache and rediscover) |
| `/memory-status` | Show current memory status |
| `/memory-refresh` | Reload memory from siada.md |
| `/rule-list` | List all loaded context rule files |
| `/mcp-server` | List MCP servers and their connection status |
| `/resume` | Resume a previous session |
| `/undo` | Roll back to a checkpoint |
| `/shell` | Switch to shell mode |
| `/help` | Show help for all commands |

## Custom Commands (/command)

Create reusable prompt shortcuts using TOML files, triggered with `/command-name` in conversation.

**Locations:**
- Global commands: `~/.siada-cli/commands/`
- Project commands: `<project>/.siada-cli/commands/`

**TOML example (`~/.siada-cli/commands/git/commit.toml`):**
```toml
description = "Generate a commit message from staged changes"
prompt = """
Generate a commit message for the following git diff:
!{git diff --staged}
"""
```

Trigger: `/git:commit`

Commands support: `{{args}}` argument injection, `@{filepath}` file embedding, `!{shell command}` output injection.

## Proactive Features

siada monitors your work in the background and can:

- **Daily task summary**: report task progress at a scheduled time (default 08:30)
- **Proactive suggestions**: periodically analyze work status during work hours and offer suggestions
- **Toggle**: set `proactive.enabled: false` in `conf.yaml` to disable all proactive features

## Cron Tasks

Create periodically auto-executed tasks, such as:

- Generate a daily work plan every morning
- Generate a weekly report every Friday afternoon
- Regularly check code quality

Managed via the **manage-cron-task** skill; tasks are stored in `~/.siada-cli/workspace/cron_tasks.json`.

## Skills

siada has built-in specialized capabilities that activate automatically for matching tasks:

| Skill | Capability |
|-------|------------|
| `docx` | Create and edit Word documents, with comments and tracked changes |
| `pptx` | Create and edit presentations |
| `xlsx` | Create and edit spreadsheets, with formulas and data analysis |
| `pdf` | Extract PDF text, fill PDF forms |
| `frontend-design` | Generate high-quality frontend pages and components |
| `manage-cron-task` | Manage scheduled cron tasks |
| `siada-help` | Answer siada usage questions, modify siada configuration |

## Memory

siada remembers across sessions:

- Personal work style and preferences
- Past work events and experience
- Project-specific context

Memory files are stored in `~/.siada-cli/workspace/memory/`.

## MCP Tool Integration

Connect external tools (e.g. Lark/Feishu, databases, browsers) via the MCP protocol. Config file: `~/.siada-cli/mcp_config.json`.

## Session Checkpoints

siada automatically saves session state so you can resume from where you left off, or manually roll back to a previous state. Config key: `checkpoint_config.enable`.

## Theme

Supports `dark`, `light`, and `auto` (follows system) themes. Set `theme` in `user_preference.yaml`.
