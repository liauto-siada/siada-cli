# Siada Feature Reference

## Conversation & Coding

- **Write and edit code**: describe what you need — siada writes code, makes edits, and fixes bugs
- **Read and explain code**: ask siada to explain the logic or meaning of any code snippet
- **Run terminal commands**: siada can execute shell commands and return the output
- **File operations**: create, edit, view, and search files
- **Side questions**: use `/btw <question>` to ask a quick question without polluting the main conversation history

## @ File References

Use `@filename` in conversation to bring file content into context:

```
@main.py what's wrong with this function?
@src/ give me an overview of this directory
```

Supports single files, directories, and fuzzy matching (e.g. `@main` matches `main.py`).

## Todo List Tracking

While working on multi-step tasks, siada can maintain a visible todo list showing what it's planning to do, what's in progress, and what's done. This is model-driven (siada decides when to create/update it) and is displayed live in the UI as work progresses.

- `/todo-task` — re-display the most recent todo list (useful if the todo panel was closed and you want to bring it back)

## Standing Goal (/goal)

`/goal <objective>` sets a standing goal for the session and immediately hands the objective
to the agent as the first real turn — it's not a silent background flag flip, it actually
starts work. Once set, an independent verifier checks after every turn whether the goal has
been met; on failure it automatically forces another turn with feedback.

- `/goal <objective>` — set a new goal, overwriting the current one regardless of its status
  (no need to `/goal clear` first)
- `/goal clear` — remove the current goal entirely
- There is no `/goal complete`, pause, resume, or status subcommand by design: completion is
  judged only by the verifier, never self-declared. A completed goal is dropped automatically,
  and a blocked goal (auto-tripped after repeated verifier failures) is automatically
  reactivated as soon as you send your next conversational message.
- Every time a goal is set or cleared, whatever goal it replaces is archived to
  `<session_dir>/goal_history.jsonl` first, so nothing is silently lost.

## Built-in Slash Commands

Type `/` in the input box to trigger — no configuration required:

| Command | Description |
|---------|-------------|
| `/model` | Open model selector (UI picker in UI mode, text list in terminal mode) |
| `/model <name>` | Switch to the specified model and persist to `conf.yaml` |
| `/status` | Show current status (model, agent, session ID, workspace) |
| `/clear` | Clear conversation history and start a new task |
| `/compact` | Manually compact conversation history to reduce context window usage |
| `/btw <question>` | Ask a quick side question without polluting the main conversation |
| `/memory [enable\|disable]` | Show or toggle the memory subsystem for the current workspace |
| `/web [enable\|disable]` | Show or toggle the web search tools (`web_search`/`web_fetch`) |
| `/lang en` / `/lang zh-CN` | Switch language preference |
| `/pre-plan-mode` | Toggle plan mode (show a plan before executing) |
| `/goal <objective>` | Set a standing goal; the agent starts working immediately and a verifier checks completion after each turn |
| `/goal clear` | Remove the current standing goal |
| `/init` | Analyze the project and generate a tailored `SIADA.md` context file |
| `/rule-list` | List all loaded hierarchical context rule files |
| `/rule-init` | Create an empty `siada_rule.md` file |
| `/rule-show` | Display the combined hierarchical context content |
| `/rule-refresh` | Refresh hierarchical context content |
| `/context-file-refresh` | Refresh `SIADA.md`/`AGENTS.md` context files and show a content overview |
| `/task-list` | View pending tasks discovered by the proactive agent |
| `/skill-list` | List all available skills |
| `/skill-reload` | Reload skills (clear cache and rediscover) |
| `/plugin` | Manage skills/plugins: discover, install, disable, remove, browse marketplace, validate |
| `/memory-status` | Show current memory status |
| `/memory-refresh` | Reload memory from siada.md |
| `/mcp-server` | List MCP servers and their connection status |
| `/mcp-list` | List all MCP servers and the tools they expose |
| `/lark-auth` | Authenticate with the Lark MCP server via OAuth 2.0 |
| `/lark-status` | Show Lark MCP authentication status |
| `/lark-refresh` | Manually refresh the Lark MCP access token |
| `/migrate-detect` | Detect migratable config/skills/context from Claude Code or Codex |
| `/migrate-import` | Import config/skills/context from Claude Code or Codex into siada |
| `/resume` | Resume a previous session |
| `/undo` | Roll back to a checkpoint |
| `/restore` | Restore files from a checkpoint |
| `/compare` | Compare files between the working directory and a checkpoint |
| `/statusbar` | Toggle status bar item visibility (UI mode) |
| `/configure` | Reconfigure the provider API key or switch login method without restarting |
| `/logout` | Sign out and clear all stored credentials |
| `/help` | Show help for all commands |

Note: `/shell` (persistent shell mode via slash command) is currently disabled in this build; use the `!<command>` prefix to run a one-off shell command directly from the prompt instead.

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

## Hierarchical Project Context

siada can build and maintain a layered understanding of a project:

- `/init` analyzes the project and writes a tailored `SIADA.md` (and honors an existing `AGENTS.md`)
- `siada_rule.md` files (global and per-directory) let you pin persistent instructions/conventions that get combined into the agent's context
- `/rule-list`, `/rule-show`, `/rule-refresh`, `/rule-init`, `/context-file-refresh` manage and inspect this layered context

## Remote Control via Lark/Feishu

Beyond the local CLI, siada can be controlled remotely through a **Lark (Feishu) bot** — this is a separate feature from the generic MCP tool integration below: it turns Lark into another *entry point* for siada, not just a tool the agent calls.

- Message the bot directly (DM) or `@mention` it in a group chat; the message is forwarded to your local siada-cli and results stream back in real time
- Two connection modes: `relay` (via a hosted IM Gateway, no bot credentials needed) or `direct` (talk to Lark's WebSocket SDK directly with your own app credentials)
- Configured under the `lark:` section of `conf.yaml`; see `docs/remote_control_lark.md` for the full setup guide
- `/lark-auth`, `/lark-status`, `/lark-refresh` manage the Lark **MCP** OAuth connection (a related but distinct piece — see MCP Tool Integration below)

## Migrating from Claude Code / Codex

If you're switching from Claude Code or Codex, siada can detect and import your existing setup:

- `/migrate-detect` scans for migratable configuration, skills, and context files
- `/migrate-import` imports the detected items into siada's own config/skills/context locations

## Proactive Features

siada monitors your work in the background and can:

- **Daily task summary**: generate a task-progress report starting at a scheduled time (default `06:00`, staggered), optionally pushed to configured IM controllers (e.g. Lark) starting at `daily_im_send_time` (default `08:30`)
- **Proactive suggestions**: periodically analyze work status during work hours and offer suggestions
- **Toggle**: set `proactive.enabled: false` in `conf.yaml` to disable all proactive features
- **Dedicated model**: `proactive.llm_config` can override the model used specifically for proactive/cron tasks

## Cron Tasks

Create periodically auto-executed tasks, such as:

- Generate a daily work plan every morning
- Generate a weekly report every Friday afternoon
- Regularly check code quality

Managed via the **manage-cron-task** skill; tasks are stored in `~/.siada-cli/workspace/cron_tasks.json`.

## Parallel Sub-agent Dispatch

For tasks that decompose into independent pieces of work, siada can dispatch multiple **sub-agents** to work on them in parallel (rather than doing everything sequentially in a single agent). Sub-agents can use their own model override via `sub_agent.llm_config` in `conf.yaml`.

## Plugins & Marketplace

siada supports installable plugins that can bundle skills, MCP servers, and lifecycle hooks. Manage them with `/plugin`:

- Discover and browse the plugin marketplace
- Install / disable / remove plugins
- Validate a plugin's manifest

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

Beyond this curated list, siada also ships a number of workflow/process skills (e.g. for planning, debugging, code review) that activate for more specialized development tasks. Use `/skill-list` to see everything currently available, and `/plugin` to browse/install additional skills from the marketplace.

## Memory

siada remembers across sessions:

- Personal work style and preferences (`USER.md`)
- Past work events and experience (`MEMORY.md`)
- Project-specific context
- Optionally, structured "holographic" fact memory with per-fact trust scoring, for more precise long-term recall

Memory files are stored in `~/.siada-cli/workspace/memory/`. Use `/memory` to check or toggle the whole subsystem on/off for the current workspace; see the `memory` section in `conf.yaml` for fine-grained tuning.

## Web Tools

siada can search the web and fetch page content (`web_search` / `web_fetch`) when useful for a task. Availability follows the active LLM provider by default; use `/web` to check the current status or force it on/off, or set `web.enabled` in `conf.yaml`.

## MCP Tool Integration

Connect external tools (e.g. databases, browsers, or the Lark MCP server) via the MCP protocol. Config file: `~/.siada-cli/mcp_config.json`. Use `/mcp-server` to check connection status and `/mcp-list` to see available tools per server.

## Session Checkpoints

siada automatically saves session state so you can resume from where you left off, or manually roll back to a previous state. Config key: `checkpoint_config.enable`. Related commands: `/resume`, `/undo`, `/restore`, `/compare`.

## Background Auto-Update

siada can silently check for and install new versions in the background via the proactive daemon. Controlled by the `auto_update` section in `conf.yaml` (`enabled`, `check_interval_minutes`, `channel`). Use `siada-cli --just-check-update` to check the version once without installing.

## Theme

Supports `dark`, `light`, and `auto` (follows system) themes. Set `theme` in `user_preference.yaml`.
