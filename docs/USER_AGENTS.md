# Custom Agents (`.agents/agents/`)

**[简体中文](./zh-CN/USER_AGENTS_zh.md) | English**

Custom agents let you define your own specialized sub-agents in Markdown files.
The main agent sees them in its system prompt and can hand them a self-contained
task through the `run_subtask` tool — each named agent brings its own system
prompt, tool set, skills, MCP servers, background preference, reasoning effort,
and model.

## Table of Contents

- [Overview](#overview)
- [Quick Start](#quick-start)
- [Where Agent Definitions Live](#where-agent-definitions-live)
- [Agent Definition File Format](#agent-definition-file-format)
- [Field Reference](#field-reference)
  - [`name` and `description`](#name-and-description)
  - [`tools`](#tools)
  - [`skills`](#skills)
  - [`mcpServers`](#mcpservers)
  - [`background`](#background)
  - [`effort`](#effort)
  - [`model`](#model)
- [What Happens at Run Time](#what-happens-at-run-time)
- [Priority and Deduplication](#priority-and-deduplication)
- [Examples](#examples)
- [Compatibility with Claude Code Agent Files](#compatibility-with-claude-code-agent-files)
- [Troubleshooting](#troubleshooting)
- [Related Documentation](#related-documentation)

## Overview

Custom agents are the sub-agent counterpart of skills:

| | Skills (`SKILL.md`) | Custom agents (`agents/*.md`) |
|---|---|---|
| Purpose | Reusable instructions the agent reads | A named sub-agent with its own prompt and configuration |
| Consumed by | The main agent (catalog in the system prompt) | `run_subtask(agent="<name>")` |
| Extra configuration | — | `tools`, `skills`, `mcpServers`, `background`, `effort`, `model` |

Definitions are read from disk every time the prompt is built and every time an
agent is spawned, so adding or editing a definition takes effect on the next
turn — no restart needed.

## Quick Start

1. Create the directory and a definition file in your project:

   ```bash
   mkdir -p .agents/agents
   ```

   ```markdown
   <!-- .agents/agents/code-reviewer.md -->
   ---
   name: code-reviewer
   description: Reviews diffs for bugs, style and security issues. Use after implementing a change.
   tools: [read_file, regex_search_files, run_cmd]
   skills: [wiki]
   effort: high
   ---

   You are a meticulous code reviewer. For every finding, report the file, the
   line, why it is a problem, and a concrete fix. Do not rewrite the code
   yourself — report findings only.
   ```

2. Start (or keep using) `siada-cli`. The main agent now advertises the agent:

   ```
   AGENT TYPES
   ...
   Available agents (name — description):
   - `code-reviewer` — Reviews diffs for bugs, style and security issues. Use after implementing a change.
   ```

3. Ask for work that matches the description, e.g. *"implement X, then have the
   code-reviewer agent review the diff"*. The main agent calls
   `run_subtask` with `agent: "code-reviewer"` and reports back its summary.

## Where Agent Definitions Live

Each root is an `agents/` directory. Definitions are `.md` files and may live in
subdirectories (they are discovered recursively).

| Scope | Directories (in increasing priority) |
|-------|--------------------------------------|
| Repository | `<project>/.claude/agents/` → `<project>/.siada/agents/` → `<project>/.agents/agents/` → `<project>/.siada-cli/agents/` |
| User | `~/.claude/agents/` → `~/.agents/agents/` → `~/.siada-cli/agents/` |

The repository scope is resolved from the working directory the agent runs in.
`.agents/agents/` is the recommended location; `.siada-cli/agents/` is the
canonical Siada location and `.claude/agents/` exists for Claude Code
compatibility.

## Agent Definition File Format

A definition is a Markdown file with a YAML frontmatter block:

```markdown
---
name: researcher
description: Researches a topic on the web and returns a sourced summary.
tools: [web_search, web_fetch, read_file]
mcpServers:
  - lark
background: true
effort: medium
---

Your system prompt goes here. Write it the way you would brief a colleague:
what the agent is responsible for, how it should work, and what its final
answer must contain.
```

- The **frontmatter** configures the agent.
- The **body** is appended to the sub-agent's standard instructions (the
  unattended-execution rules always come first; the body follows them).

Minor frontmatter quirks are tolerated: if a value such as `description`
contains `": "` without being quoted (common in third-party agent packs), the
file is still loaded instead of being rejected.

## Field Reference

### `name` and `description`

Both are **required**; a file missing either one fails to load and is reported
as a load error (other definitions in the same directory still load).

- `name` (max 64 characters) — how the agent is identified. It is matched
  case-insensitively when `run_subtask` resolves `agent="<name>"`.
- `description` (max 1024 characters) — when to use the agent. This is the text
  the main agent sees in the `AGENT TYPES` section, so write it as a trigger
  ("Use when …"), not as marketing copy.

### `tools`

Restricts the sub-agent's tool set. Accepted forms:

```yaml
tools: [read_file, regex_search_files, run_cmd]   # YAML list
tools: read_file, regex_search_files, run_cmd     # comma-separated string
tools: ['*']                                      # every default tool
```

Semantics:

- **Omitted** → the default sub-agent tool set is used unchanged.
- **`['*']`** → same as omitted.
- **A list** → only the named tools are kept.
- Unknown names are dropped with a warning in the log.
- If nothing matches at all, the default tool set is used instead, so a
  definition can never produce a tool-less agent.

Default sub-agent tool set (depends on the model family):

| Tool | Notes |
|------|-------|
| `read_file` + `apply_patch` | Native-patch models (GPT-5-and-newer, Astra) |
| `edit_file` | All other models |
| `regex_search_files`, `run_cmd`, `list_code_definition_names` | Always |
| `web_search`, `web_fetch` | When web tools are enabled |
| `run_powershell` | When available |
| `run_subtask` | Only when `sub_agent.allow_recursive_subagents` is enabled |

`read_file`, `edit_file` and `apply_patch` are treated as one group: naming any
of them keeps whichever file tools the current model actually exposes, so the
same definition works across models.

Claude Code tool names are accepted too and mapped automatically
(`Read`→`read_file`, `Bash`→`run_cmd`, `Grep`/`Glob`→`regex_search_files`,
`Task`→`run_subtask`, `TodoWrite`→`todo_write`, `WebSearch`/`WebFetch`→
`web_search`/`web_fetch`, `Write`/`Edit`→`edit_file`).

### `skills`

A list of skill names to **preload**. Each named skill's `SKILL.md` body is read
at spawn time and inlined into the sub-agent's prompt under `## Preloaded
Skills`, so the agent does not have to discover and read the skill itself.

```yaml
skills: [wiki, open-source-release]
```

- Names resolve through the same skill loader as the main agent, so
  `.agents/skills/`, `.siada-cli/skills/`, and plugin skills are all reachable.
- Unknown skill names are logged and skipped; a skill that cannot be read is
  skipped as well — neither blocks the spawn.
- The sub-agent still receives the skill-root hints, so it can read other
  skills on demand.

### `mcpServers`

MCP servers that are attached to the sub-agent **for its run only**.

```yaml
mcpServers:
  - lark                                            # a configured server, by name
  - browser: {url: "https://example.test/mcp"}      # an inline definition
  - notes: {command: "npx", args: ["-y", "notes-mcp"]}
```

- A **name** refers to a server from your MCP configuration
  (`~/.siada-cli/mcp_config.json`, project `.mcp.json`, …). If the server is
  already connected for the session, that connection is reused; if it is only
  configured, it is connected for this run.
- An **inline definition** is created and connected just for this run, and
  cleaned up when the run finishes. Environment variables in the definition
  (`${VAR}`) are resolved.
- Servers disabled in the configuration (`enabled: false`) are skipped.
- Names that are neither configured nor inline are logged and skipped.
- MCP tools that would shadow Siada's own tool names are renamed, exactly as
  for the main agent.

### `background`

```yaml
background: true
```

`true` means **every** spawn of this agent runs as a background task: the main
agent gets a `task_id` immediately and the summary arrives later as a
notification. Use it for long-running, independent work (audits, large
searches, batch refactors).

- The setting wins over the caller: even if the model passes `async: false`, a
  `background: true` agent still runs in the background.
- `false` or omitted (the default) leaves the choice to the caller.

### `effort`

Requests a reasoning-effort level for the agent's runs:

```yaml
effort: high
```

- Valid values: `low`, `medium`, `high`, `xhigh`, `max`.
- The level is mapped onto the levels the **effective sub-agent model** accepts
  (nearest strength wins, ties go stronger). For example GLM-5.3 accepts
  `low`/`high`/`max`, so `medium` becomes `high`.
- It applies to the sub-agent run only: your own session's `/effort` setting is
  never modified.
- An invalid value is ignored with a warning (the model's own default applies).
- `effort` is most useful together with a sub-agent model configured under
  `sub_agent.llm_config` in `conf.yaml` — or a per-agent [`model`](#model).

### `model`

Runs this agent on a specific model:

```yaml
model: gpt-6-luna
```

- The value must be a model name from the model catalog (the models `/model`
  offers).
- It takes precedence over the sub-agent model configured in `conf.yaml`
  (`sub_agent.llm_config.model`). Omitted, that configuration applies — or,
  when it is not set either, the parent session's own model.
- The provider stays the one the spawn would have used anyway (the
  `sub_agent.llm_config.provider` from `conf.yaml` when set, the parent's
  provider otherwise), so switching the model never switches the gateway.
- `inherit` (Claude Code's "same model as the main agent") means "not
  configured": the default resolution above applies.
- An unknown model name (typo, or a model renamed since) is ignored with a
  warning in the log; the run keeps the configured sub-agent model.
- [`effort`](#effort) is mapped against this model's accepted levels.

## What Happens at Run Time

1. The main agent's system prompt gains an `AGENT TYPES` section listing every
   available agent as `name — description` (the section is omitted entirely
   when you have no definitions, and also when the sub-agent feature is off via
   `sub_agent.enabled: false`, so nothing changes by default).
2. When a task matches a description, the main agent calls
   `run_subtask` with `agent: "<name>"`.
3. Siada loads the definition and applies it: the body is appended to the
   sub-agent's standard instructions, `tools` → filtered tool set, `skills` →
   preloaded instructions, `mcpServers` → servers connected for the run,
   `model` → the run's model, `effort` → the run's model settings,
   `background` → background execution.
4. The sub-agent still runs unattended: it cannot ask you questions, and it
   must finish with a summary.
5. An unknown agent name is not an error — the tool returns the list of
   available agent names so the model can correct itself.

Notes:

- `fork: true` is ignored when an agent is named, because a named agent always
  brings its own prompt and tools (forking exists to reuse the parent's cached
  prompt prefix, which a definition would change).
- Custom agents configure **sub-agent** runs only. The main agent's own prompt,
  tools and model are unaffected.
- Like any other sub-agent, the run is displayed in the sub-agent detail view,
  not inline in the conversation.

## Priority and Deduplication

When two definitions share a name:

- **Within a scope**, the later directory in the table above wins (so
  `.siada-cli/agents/` beats `.agents/agents/`, which beats `.claude/agents/`).
- **Across scopes**, user-level definitions (`~/.siada-cli/agents/` etc.) win
  over repository-level ones.

This lets you keep a personal version of an agent while a project ships its own.

## Examples

**A read-only reviewer that never touches code:**

```markdown
---
name: code-reviewer
description: Reviews a diff for bugs, style and security issues. Use after implementing a change.
tools: [read_file, regex_search_files, run_cmd]
effort: high
---

You are a meticulous code reviewer. Report every finding as
`path:line — problem — suggested fix`. Never modify files.
```

**A background researcher with web access and MCP tools:**

```markdown
---
name: researcher
description: Researches a topic on the web and returns a sourced summary. Use for external comparisons and best-practice surveys.
tools: ['*']
mcpServers: [lark]
background: true
---

You research topics using web search and the available MCP tools. Every claim
in your summary must cite a URL or a tool result.
```

**An agent that always applies a project skill:**

```markdown
---
name: release-notes
description: Turns a commit range into user-facing release notes. Use when preparing a release.
skills: [lark-workflow-release-announcement]
---

You write release notes for end users. Group changes by theme, drop internal
refactors, and keep the wording non-technical.
```

## Compatibility with Claude Code Agent Files

Files written for Claude Code's `.claude/agents/` layout generally work as-is:

- The same directories are searched (`.claude/agents/` in the repository and
  home directory).
- `name`, `description`, `tools`, `skills`, `mcpServers`, `background`,
  `effort` and `model` have the same names and meanings (for `model`, Siada
  expects a model name from its catalog; `inherit` is also understood).
- Common Claude Code tool names are mapped to their Siada equivalents (see
  [`tools`](#tools)).
- Unsupported Claude Code fields (`permissionMode`, `hooks`, `maxTurns`,
  `memory`, `isolation`, …) are ignored — they do not break the definition.
  For model aliases that only exist in Claude Code (`sonnet`, `opus`,
  `haiku`), use the Siada model name instead — see [`model`](#model).

## Troubleshooting

| Symptom | Likely cause / fix |
|---------|--------------------|
| The agent never appears in `AGENT TYPES` | `name` or `description` missing/not a string; check the `siada_cli.log` warning for the parse error. |
| `Unknown agent 'x'. Available agents: …` | Typo, or the definition lives outside the searched directories. |
| The agent runs but has fewer tools than expected | Some names in `tools` were unknown (logged as a warning). Use the names from the table in [`tools`](#tools) or `['*']`. |
| A named skill is ignored | The skill name does not resolve; check the warning and the skill's own `name` field in its `SKILL.md`. |
| MCP tools are missing in the agent | The `mcpServers` entry is neither configured nor inline (logged), or the server failed to connect (logged) — a failed server never blocks the run. |
| The effort level looks different from what you wrote | Expected: levels are mapped to the effective model's accepted set. |
| The agent runs on the default sub-agent model despite `model:` | The name is not in the model catalog (typo, or renamed since) — the log has an "not a known model; ignoring the override" warning. Use a name from `/model`. |
| A definition edit has no effect | Definitions are reloaded per turn — make sure you edited the file that wins the [priority rules](#priority-and-deduplication). |

## Related Documentation

- [User Manual](./USERMANUAL.md)
- [Skills System](./SKILLS.md)
- [MCP configuration](./USERMANUAL.md#mcp-configuration)
- [External Model Configuration](./external_model_configuration.md)
