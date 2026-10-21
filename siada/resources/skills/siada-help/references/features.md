# Siada Feature Reference

## Conversation & Coding

- **Write and edit code**: describe what you need — siada writes code, makes edits, and fixes bugs
- **Read and explain code**: ask siada to explain the logic or meaning of any code snippet
- **Run terminal commands**: siada can execute shell commands and return the output
- **File operations**: create, edit, view, and search files
- **Side questions**: use `/btw <question>` to ask a quick question without polluting the main conversation history

Siada works within the requested task scope and the tool's permission checks.
The coding agent sends progress, results, and blockers through ordinary assistant
messages. You can add instructions while it works, including a request to review
a plan before execution. There is no separate question tool or planning-mode
panel. Normal, forked, background, and recursive `run_subtask` calls run unattended
and report blockers to their calling agent.

## Tool Call Summaries (terminal)

Tool calls in the terminal UI are rendered as concise structured summaries: a heading plus a few labeled fields (for example a file read with its path, a directory view, a command, or a patch with its change counts), with a compact one-line form while collapsed. Expand a call to inspect the full details and output.

This is a display layer only: it parses the tool call that actually ran and shows it. It does not call a model to summarize, does not learn from your sessions, and does not change what the agent does. Semantic tools (analyze-definitions, memory search/write, fact store, sub-agent delegation, undo) render the same way.

## Sign-in and Authentication

siada signs in with **your own model-provider API key** — there is no hosted/account login in this build:

- On first launch (or with `/configure`) choose a provider API key or Free Trial. Free Trial selects curated anonymous Kilo models. Settings persist into `llm_config` in `~/.siada-cli/conf.yaml` (`provider: default`). The active provider catalogue appears before `models.json`, with duplicate names retaining user metadata; Custom adds only the entered model.
- Credentials can also come from the `BASE_URL` / `API_KEY` environment variables (e.g. `siada-cli --set-env API_KEY=... --set-env BASE_URL=...`)
- `/logout` or `siada-cli --logout` removes the stored provider API key
- The legacy account options `--user-id` / `--access-token` are deprecated and rejected: they exit with an error that points at configuring a provider API key (LiId/domain-account credentials are not supported here)
- Old `user_id` / `siada_api_key` / `refresh_token` / `user_email` / `email_refresh_token` keys may remain in a migrated `conf.yaml`; they are compatibility leftovers, not a sign-in method

## Models and Cost Estimates

- `/model` opens the model selector (or switches to a named model); `/effort` and `/thinking` tune reasoning for the current model; `siada-cli --list-models` prints the catalog
- Built-in catalog entries use the vendor's own published model IDs (e.g. `claude-sonnet-5`, `gpt-6-astra`, `kimi-k3`, `glm-5.3`)
- Cost numbers shown in the status bar and exports are **estimates** in CNY per million tokens. Vendors that publish USD prices are converted at a fixed snapshot rate (7.0 CNY per USD) — not a live exchange rate. Off-list models have no known price and report 0 instead of a guessed number
- `~/.siada-cli/models.json` is authoritative for your own setup: user-defined models replace the built-in catalog, and any `input_price` / `output_price` / `cache_*_price` you set wins over the built-in estimate (see `docs/external_model_configuration.md`)

The default provider uses OpenAI-compatible Chat Completions except for its
Claude/Gemini routes and GPT-5-and-later Responses routes. A provider prefix is
not enough to make an endpoint compatible. Custom models declare reasoning
capabilities through `supports_extra_params` and `default_reasoning_effort`;
Siada does not infer these settings from a custom GLM model's name.

Kimi K3 and later use a Kimi Code-based prompt; Kimi K2 and older keep the generic
prompt. GPT-6 prompts are composed from packaged Markdown templates. GLM-5.2
and later receive a dedicated prompt profile and hidden reminders after three
identical tool calls. GLM models of any generation can also receive a reminder
after ten assistant turns without `todo_write` while the list is empty; set
`SIADA_TODO_EMPTY_LIST_REMINDER=0` to disable that empty-list reminder.

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
  (if the hidden reminder cannot be saved to session history, the goal is still
  removed and a warning is shown)
- Automatic continuation stops if the verifier has no actionable `nextAction` or
  the configured maximum number of consecutive failed verifier turns is
  reached. Configure the limit with `goal.max_turns` in `~/.siada-cli/conf.yaml`
  (default: `6`); two consecutive verifier system errors remain a separate,
  faster safety breaker.
- There is no `/goal complete`, pause, resume, or status subcommand by design: completion is
  judged only by the verifier, never self-declared. A completed goal is dropped automatically,
  and a blocked goal (auto-tripped after repeated verifier failures) is automatically
  reactivated as soon as you send your next conversational message, not by
  internal retry or background-task feedback turns.
- Every time a goal is set or cleared, whatever goal it replaces is archived to
  `<session_dir>/goal_history.jsonl` first, so nothing is silently lost.

## Built-in Slash Commands

Type `/` in the input box to trigger — no configuration required:

| Command | Description |
|---------|-------------|
| `/model` | Open model selector (UI picker in UI mode, text list in terminal mode) |
| `/model <name>` | Switch to the specified model and persist to `conf.yaml` |
| `/effort [level]` | Show or set the reasoning effort level for the current model, persisted to `conf.yaml`. Valid levels depend on the model: `low`/`medium`/`high` for most, Claude also supports `xhigh`/`max`, GPT-5/GPT-6 (`gpt-5.6-*`, `gpt-6-astra`) also support `max`, Kimi K3/GLM/DeepSeek use `low`/`high`/`max` (GLM-5.2 has no `low`) |
| `/thinking [on\|off]` | Show, enable, or disable thinking/reasoning for the current model, persisted to `conf.yaml` (`llm_config.enable_thinking`). `off` is an absolute switch: it wins over any effort level or thinking-token budget |
| `/theme [dark\|light]` | Show or switch the UI color theme, persisted to `conf.yaml` (`ui.theme`). Defaults to `dark`; legacy `auto` uses `dark` without detection |
| `/status` | Show current status (model, agent, session ID, workspace) |
| `/clear` | Clear conversation history and start a new task |
| `/compact` | Manually compact conversation history; show message counts and the number removed beneath the compaction status |
| `/btw <question>` | Ask a quick side question without polluting the main conversation |
| `/export [<filename>]` | Export the conversation to a `.txt` file (UI mode) |
| `/share` | Share the current session as a web link served by the browser-addon proxy (see Browser Add-on & Session Sharing) |
| `/editor` | Open an external editor to compose a prompt |
| `/memory [enable\|disable]` | Show or toggle the memory subsystem for the current workspace |
| `/web [enable\|disable]` | Show or toggle the web search tools (`web_search`/`web_fetch`) |
| `/lang en` / `/lang zh-CN` | Switch language preference |
| `/goal <objective>` | Set a standing goal; the agent starts working immediately and a verifier checks completion after each turn |
| `/goal clear` | Remove the current standing goal |
| `/init` | Analyze the project and generate a tailored `SIADA.md` context file |
| `/rule-list` | List all loaded hierarchical context rule files |
| `/rule-init` | Create an empty `siada_rule.md` file |
| `/rule-show` | Display the combined hierarchical context content |
| `/rule-refresh` | Refresh hierarchical context content |
| `/rule-status` | Show hierarchical-context status (config, discovered rule files, content size) |
| `/rule-global-add` | Append a memory entry to the global rule file |
| `/context-file-refresh` | Refresh `SIADA.md`/`AGENTS.md` context files and show a content overview |
| `/task-list` | View pending tasks discovered by the proactive agent |
| `/todo-task` | Re-display the most recent todo list in the UI |
| `/skill-list` | List all available skills |
| `/skill-reload` | Reload skills (clear cache and rediscover) |
| `/plugin` | Manage skills/plugins: discover, install, disable, remove, browse marketplace, validate |
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
| `/configure` | Re-run API Key / Free Trial sign-in in the Siada UI without restarting; cancelling leaves the session and config untouched. Requires the UI |
| `/logout` | Sign out: remove the stored provider API key from `conf.yaml` (the process then exits) |
| `/exit` | Exit siada |
| `/help` | Show help for all commands |

Note: `/shell` (persistent shell mode via slash command) is currently disabled in this build; use the `!<command>` prefix to run a one-off shell command directly from the prompt instead.

Note: on Lark/Feishu (IM) clients a subset of commands is intentionally unavailable — `/goal`, `/init`, `/task-list`, `/resume`, `/undo`, `/restore`, `/compare`, `/migrate-detect`, `/migrate-import`, `/lark-auth`, `/configure`, `/logout`, `/editor`, and `/exit`.

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
- When the workspace contains `AGENTS.md`, neither root `CLAUDE.md` nor
  `.claude/CLAUDE.md` is added to workspace memory. `SIADA.md` remains eligible.
- The main coding agent attaches a bounded, hidden Git snapshot to the first user
  request in a Git workspace and refreshes it after compaction. It is context
  data, not additional authorization. Set `SIADA_GIT_SNAPSHOT=0` to disable it.

## Remote Control via Lark/Feishu

Beyond the local CLI, siada can be controlled remotely through a **Lark (Feishu) bot** — this is a separate feature from the generic MCP tool integration below: it turns Lark into another *entry point* for siada, not just a tool the agent calls.

- Message the bot directly (DM) or `@mention` it in a group chat; the message is forwarded to your local siada-cli and results stream back in real time
- This build serves **direct mode only**: siada connects to the Lark Open Platform through the Lark SDK's WebSocket long connection using your own app credentials (`lark.direct.app_id` / `app_secret`). `mode: relay` (a hosted IM Gateway) is a legacy value — the relay client is not bundled and the daemon fails with a clear error if you request it
- Access control lives under `lark.access` (`dm_policy`, `allow_from`, `group_policy`, `group_allow_from`); `lark.enabled: false` disables the bot without deleting the config
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
- **Safe by default**: `proactive.auto_execute_enabled` is `false`, so tasks wait for explicit user approval before they run

## Cron Tasks

Create periodically auto-executed tasks, such as:

- Generate a daily work plan every morning
- Generate a weekly report every Friday afternoon
- Regularly check code quality

Managed via the **manage-cron-task** skill; tasks are stored in `~/.siada-cli/workspace/cron_tasks.json`.

## Parallel Sub-agent Dispatch

For tasks that decompose into independent pieces of work, siada can dispatch multiple **sub-agents** to work on them in parallel (rather than doing everything sequentially in a single agent). Sub-agents can use their own model override via `sub_agent.llm_config` in `conf.yaml`.

A sub-agent can also be launched in the **background**: the main agent hands off a self-contained job, keeps working, and the sub-agent's result is injected into the conversation once it finishes. Sub-agent activity (tool calls, files touched, progress) is shown in the sub-agent view rather than the main message flow.

Set `sub_agent.enabled: false` in `conf.yaml` to turn the feature off entirely: `run_subtask` is removed from the agent's tools and every task is worked inline in the main agent's own context (recursive nesting is disabled as well).

## Custom Agents

You can define your own named sub-agents as Markdown files under `.agents/agents/` (repository) or `~/.siada-cli/agents/` (user level); `.claude/agents/` files are picked up too. The main agent sees each agent's name and description in its prompt and delegates to it through `run_subtask`.

A definition is a Markdown file with YAML frontmatter (`name` and `description` are required) whose body becomes the agent's system prompt. Optional fields:

| Field | Meaning |
|-------|---------|
| `tools` | Restrict the sub-agent's tools (`['*']` = all default tools) |
| `skills` | Skill names whose `SKILL.md` content is preloaded into the agent's prompt |
| `mcpServers` | MCP servers (by name, or inline `{name: {command/url: ...}}`) attached for the agent's run |
| `background` | `true` = every run of this agent goes to the background |
| `effort` | Reasoning effort (`low`/`medium`/`high`/`xhigh`/`max`), mapped to what the model accepts |
| `model` | Run this agent on a specific model (e.g. `gpt-6-luna`); wins over the `sub_agent.llm_config` model in `conf.yaml`, `inherit` keeps the default resolution |

Definitions are reloaded per turn, so edits apply without restarting. Full guide: `docs/USER_AGENTS.md`.

## Plugins & Marketplace

siada supports installable plugins that can bundle skills, MCP servers, and lifecycle hooks. Manage them with `/plugin`:

- Discover and browse the plugin marketplace
- Install / disable / remove plugins
- Validate a plugin's manifest

## Skills

siada has built-in specialized capabilities that activate automatically for matching tasks:

| Skill | Capability |
|-------|------------|
| `design-doc-writer` | Write detailed, unambiguous design documents that an AI can implement directly |
| `long-horizon` | Force a research → plan → execute pipeline for complex, long-horizon tasks |
| `skill-creator` | Create new skills (SKILL.md scaffolding and frontmatter) |
| `manage-cron-task` | Manage scheduled cron tasks |
| `siada-help` | Answer siada usage questions, modify siada configuration |

Beyond this curated list, siada also ships a number of workflow/process skills that activate for more specialized development work — e.g. `brainstorming`, `writing-plans`, `executing-plans`, `systematic-debugging`, `test-driven-development`, `requesting-code-review`, `dispatching-parallel-agents`, `using-git-worktrees`, and `verification-before-completion`. Use `/skill-list` to see everything currently available (any skill can also be invoked directly as `/<skill-name>`), and `/plugin` to browse/install additional skills from the marketplace.

## Memory

siada remembers across sessions:

- Personal work style and preferences (`USER.md`)
- Past work events and experience (`MEMORY.md`)
- Project-specific context
- Optionally, structured "holographic" fact memory with per-fact trust scoring, for more precise long-term recall

Memory files are stored in `~/.siada-cli/workspace/memory/`. Use `/memory` to check or toggle the whole subsystem on/off for the current workspace; see the `memory` section in `conf.yaml` for fine-grained tuning.

## Web Tools

siada can search the web and fetch page content (`web_search` / `web_fetch`) when useful for a task. Web tools are on by default; use `/web` to check the current status or force them on/off, or set `web.enabled: false` in `conf.yaml` to turn them off.

## Browser Add-on & Session Sharing

The `chrome-acp` browser add-on connects siada to your own Chrome through a local proxy, so the agent can see and drive pages using your real browser session. It is managed from the CLI:
The Chrome side panel supports installation guidance for Linux/macOS and Windows,
automatic local token discovery, API Key / Free Trial login, and signing in again
or switching providers from connection settings. Remote URL/token settings remain manual.

- `siada-cli --browser-setup` — install the proxy + Chrome extension and start the proxy (optional value: path to an already-built `chrome-acp` repo; omit it to download prebuilt artifacts)
- `siada-cli --browser-start` / `--browser-stop` / `--browser-restart` / `--browser-status` — manage or inspect the running proxy
- `siada-cli --browser-port <port>`, `--browser-host <host>`, `--browser-base-url <url>` — tune the setup; `--browser-host 0.0.0.0` allows connections from other devices on your LAN (wss/https with a self-signed certificate)

### Browser activity trace

The Chrome side panel and the web client share a **Trace** tab: a timeline of what the agent did in the browser, next to real pictures of the controlled tab.

- steps, durations, targets and values come from the ACP session stream, so they describe tool calls that really ran
- the picture is a real capture: a before/after pair around each mutating call, plus an optional live view ("Go live") that streams the tab through the Chrome debugger while it is enabled (needs the `debugger` permission, off by default)
- the change-region overlay is a pixel diff of that before/after pair

The trace only observes and displays. It does not learn from runs, keeps no trained or persisted model, and never replays anything on its own — replaying a recorded step is what the separate `browser_replay` tool does. Read a trace as a record of the agent's real actions in your signed-in browser, not as a background learning feature.

Use `/share` to expose the current session as a web link served by that proxy — the recipient opens it in a browser and sees the conversation update as you keep working. The link embeds a token that grants full control over the agent, so only send it to people you trust; sharing requires the proxy to be reachable from the recipient (e.g. bound to `0.0.0.0`).

## MCP Tool Integration

Connect external tools (e.g. databases, browsers, or the Lark MCP server) via the MCP protocol. Config file: `~/.siada-cli/mcp_config.json`. Use `/mcp-server` to check connection status and `/mcp-list` to see available tools per server.

The JSON loader reads configuration files only. Plugin-provided MCP servers
are attached separately by the plugin runtime.

## Session Checkpoints

siada can save session state so you can resume from where you left off, or manually roll back to a previous state. Checkpoints are opt-in: set `checkpoint_config.enable: true` in `conf.yaml`, or start with `siada-cli --checkpointing` (non-interactive runs never checkpoint). Up to `checkpoint_config.max_checkpoint_files` files are kept per session (default `50`). Related commands: `/resume`, `/undo`, `/restore`, `/compare`.

## Background Auto-Update

siada can silently check for and install new versions in the background via the proactive daemon. Controlled by the `auto_update` section in `conf.yaml` (`enabled`, `check_interval_minutes`, `channel`).

Manual version handling from the CLI:

- `siada-cli --version` — print the installed version
- `siada-cli --just-check-update` — check once without installing (the exit code reports whether an update is available)
- `siada-cli --upgrade` (alias `--update`) — install the latest release
- For a `uv`-managed install, update with `uv tool upgrade siada-cli` (or reinstall with `uv tool install --force --python python3.12 siada-cli` if the environment is broken)

## ACP Mode (editor / third-party clients)

siada ships a standalone Agent Client Protocol server, so any ACP-compatible client (Zed, Kiro, vscode-acp, ...) can use it as a first-class agent:

- `siada-acp` — run the standalone ACP stdio server
- `siada-cli --acp` — launch the bundled UI over the same ACP core

The ACP session advertises the installed siada version (the same value `siada-cli --version` prints), and a failed prompt is reported to the client with its underlying cause — including the provider's error text — instead of a generic failure.

## Theme

Switch the UI color theme with `/theme` — `dark` (the default) or `light`. The choice is persisted to `conf.yaml` as `ui.theme`. Legacy `auto` configuration values use `dark` without system or terminal detection; `/theme auto` saves `dark`.
