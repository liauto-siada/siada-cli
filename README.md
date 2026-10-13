# Siada CLI

**[简体中文](./docs/zh-CN/README_zh.md) | English**

[![PyPI version](https://img.shields.io/pypi/v/siada-cli)](https://pypi.org/project/siada-cli/)
[![Python versions](https://img.shields.io/badge/python-3.12%20%E2%80%93%203.13-blue)](https://www.python.org/downloads/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)

**Siada CLI is an AI assistant for coding, debugging, and automation.** It works with your project, tools, and persistent memory to carry tasks from investigation through implementation and verification. It can also control your browser and perceive your intent from your current reading and recent actions.

[News](#news) · [Capabilities](#what-siada-can-do) · [Quick start](#quick-start) · [Browser preview](#browser-collaboration-preview) · [Documentation](#documentation)

[![Preview: from terminal conversation to browser action in Siada CLI](./docs/assets/demos/siada-chrome-home-desktop-v2-preview.gif)](./docs/assets/demos/siada-chrome-home-desktop-v2.mp4?raw=1)

[Explore the browser collaboration showcase and user guide](https://liauto-siada.github.io/siada-cli/). The showcase links back to this GitHub repository.

## News

### Siada: Human in browser use

> AI's value is not in replacing people, but in making room for creativity.

**Development preview:** the browser addon and Chrome extension are not yet included in public `main` or the published PyPI package. The workflows below come from the browser collaboration demos. Feishu outputs require the relevant skills and authorization.

The browser collaboration preview brings Siada into the page you are reading. Your current reading, browsing history, and recent actions provide context for understanding, organizing, and creating.

**Understand your intent.** Find previously visited papers, GitHub projects, and articles, then compare them with the current page. Read recorded clicks, scrolling, and navigation to answer questions about what you just did.

**Make room to create.** Place translations, explanations, and comparisons beside the relevant paragraphs. Turn information from the web into reports, presentations, pages, or tools using the skills and integrations you have configured.

**Browse efficiently.** Search, navigate, and extract information across pages. Trace lets you inspect action snapshots, tool execution time, and intervals between calls to review the process.

| Workflow | Demonstrated result | Full video |
| --- | --- | --- |
| Reading → Feishu sharing | Organize a daily article selection, retain source links, and share it with a study group. | [▶ 30 s](./docs/assets/demos/siada-reading-to-feishu.mp4?raw=1) |
| Browsing history → Paper comparison | Recover relevant research and compare it with five key insights in a survey, with explanations and comparisons placed in the original page. | [▶ 28 s](./docs/assets/demos/siada-history-to-paper.mp4?raw=1) |
| Recent actions → Browsing path | Summarize recorded clicks, scrolling, searches, and page navigation in a readable reply. | [▶ 28 s](./docs/assets/demos/siada-human-action-perception.mp4?raw=1) |
| Current page → Inline explanation | Put translations, annotations, and comparisons beside the corresponding paragraphs. | [▶ 28 s](./docs/assets/demos/siada-history-to-paper.mp4?raw=1) |
| Financial reports → Feishu report | Compare quarterly and annual revenue, gross margin, and cash flow, then organize analysis, charts, and sources in a document. | [▶ 32 s](./docs/assets/demos/siada-financial-report.mp4?raw=1) |
| Product research → Presentation | Collect product images and specifications, compare prices and features, and produce buying recommendations as Feishu slides. | [▶ 34 s](./docs/assets/demos/siada-ecommerce-to-ppt.mp4?raw=1) |
| Browser search → Trace review | Find agent dependencies, versions, and sources in a GitHub project's `pyproject.toml`, then inspect the actions and their timing. | [▶ 36 s](./docs/assets/demos/siada-browser-control-trace.mp4?raw=1) |

Click an animated preview to open the full MP4. The six demos are silent, with Chinese on-screen captions; the paper comparison demo also shows inline explanations.

| Reading → Feishu · 30 s | Browsing history → Paper · 28 s |
| --- | --- |
| [![Preview: reading, organizing, and sharing to Feishu](./docs/assets/demos/siada-reading-to-feishu-preview.gif)](./docs/assets/demos/siada-reading-to-feishu.mp4?raw=1) | [![Preview: browsing history, paper comparison, and inline explanation](./docs/assets/demos/siada-history-to-paper-preview.gif)](./docs/assets/demos/siada-history-to-paper.mp4?raw=1) |

| Recent actions → Context · 28 s | Financial reports → Feishu · 32 s |
| --- | --- |
| [![Preview: recent clicks, scrolling, and browsing paths](./docs/assets/demos/siada-human-action-perception-preview.gif)](./docs/assets/demos/siada-human-action-perception.mp4?raw=1) | [![Preview: financial analysis and a Feishu report](./docs/assets/demos/siada-financial-report-preview.gif)](./docs/assets/demos/siada-financial-report.mp4?raw=1) |

| Product research → Slides · 34 s | Browser search → Trace · 36 s |
| --- | --- |
| [![Preview: product research and Feishu slides](./docs/assets/demos/siada-ecommerce-to-ppt-preview.gif)](./docs/assets/demos/siada-ecommerce-to-ppt.mp4?raw=1) | [![Preview: browser search and Trace review](./docs/assets/demos/siada-browser-control-trace-preview.gif)](./docs/assets/demos/siada-browser-control-trace.mp4?raw=1) |

See [Browser collaboration preview](#browser-collaboration-preview) for the integration overview. Follow [Releases](https://github.com/liauto-siada/siada-cli/releases) and [PyPI](https://pypi.org/project/siada-cli/) for published versions.

## What Siada Can Do

| Capability | How it helps |
| --- | --- |
| Code development and debugging | Explore a repository, implement features, fix defects, and run relevant checks across languages and frameworks. |
| Long tasks and sub-agents | Plan complex work, delegate bounded tasks to specialized agents, and track progress toward a goal. |
| Model choice | Use different model families and configure custom API endpoints through the provider layer. |
| Persistent memory | Retain preferences, project context, and decisions across sessions, with a structured fact store for retrieval and feedback. |
| Skills, agents, and MCP | Add reusable workflows, specialized sub-agents, and tools from external MCP servers. |
| Session control | Resume conversations, compact context, and opt into checkpoints for recovery. |
| Multiple entry points | Work in the terminal, connect an ACP client, or send tasks through a configured Feishu/Lark bot. |
| Scheduled automation | Use the background daemon for recurring tasks and proactive workflows. |

## Quick Start

### Requirements

| Requirement | Details |
| --- | --- |
| Operating system | macOS, Linux, or Windows |
| Python | 3.12–3.13; the installation command selects Python 3.12 |
| GCC | 11+ on macOS / Linux |
| Package manager | [uv](https://docs.astral.sh/uv/) |
| Model access | A configured provider account or your own API key |

The terminal UI uses Node.js 24 LTS. Install Node.js yourself for terminal-only use, or use the runtime installed by `siada-browser setup` with a published browser platform package. The launcher does not download Node.js on startup. Source development and browser builds also need npm and Bun.

### Install

Install uv on **macOS / Linux**:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Or on **Windows (PowerShell)**:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Install the published Siada CLI package with the same command on all platforms:

```bash
uv tool install --force --python python3.12 --compile --with pip siada-cli@latest
uv tool update-shell
```

Open a new terminal if `siada-cli` is not yet on `PATH`.

### Start a Task

Launch Siada in the project you want to work on:

```bash
cd path/to/your/project
siada-cli
```

Complete the provider, model, and API key setup when prompted, then describe a task:

```text
Find the cause of the failing tests, fix it, and run the relevant test suite.
```

Use `/model` to select an available model. Configuration lives in `~/.siada-cli/conf.yaml`; custom model definitions live in `~/.siada-cli/models.json`. See the [User Manual](./docs/USERMANUAL.md) and [External Model Configuration](./docs/external_model_configuration.md) for details.

### Update or Uninstall

```bash
uv tool upgrade siada-cli
```

```bash
uv tool uninstall siada-cli
```

## Usage Modes

Sub-agents retry up to twice when a response ends with reasoning and an empty
final answer. Retries continue the existing session with completed tool results.
If all three attempts return this result, the task is marked failed. This check
detects a potentially incomplete response; it does not establish a network fault.

| Entry point | Usage |
| --- | --- |
| Interactive terminal | Run `siada-cli` for a continuous conversation in the terminal UI. |
| Script or CI task | Run `siada-cli --prompt "Find and fix the failing tests"` for a single task. |
| ACP client | Configure the client to launch `siada-acp` as its agent process. |
| Feishu / Lark | Configure a bot, then send tasks from chat; see the [Remote Control Guide](./docs/remote_control_lark.md). |
| Browser preview | A development preview requiring the browser addon and Chrome extension; see the [integration overview](#browser-collaboration-preview). |

### Common Commands

Enter these commands inside an interactive session:

| Command | Purpose |
| --- | --- |
| `/help` | List available commands. |
| `/model` | Select or change the model. |
| `/resume` | Browse and resume saved sessions. |
| `/clear` | Start a fresh conversation context. |
| `/compact` | Compact the current conversation. |
| `/skill-list` | List available skills. |
| `/skill-reload` | Reload skills after adding or editing them. |
| `/goal <objective>` | Set a goal for the session; use `/goal clear` to clear it. |

Enable checkpoints when starting an interactive session:

```bash
siada-cli --checkpointing
```

Checkpoints are opt-in and are unavailable in non-interactive mode. See the [User Manual](./docs/USERMANUAL.md) for restore, undo, and comparison commands.

## Browser Collaboration Preview

The preview connects a Chrome extension to a local proxy and the Siada ACP agent. ACP handles the agent conversation; MCP exposes browser tools for reading pages, navigating, capturing snapshots, and adding inline annotations. Browser actions and page snapshots can be reviewed in Trace.

This checkout adds a browser platform package containing Node.js, the proxy, its production dependencies, the web client, and the Chrome extension. The packages have not yet been published or verified through the release workflow. Once the matching release is available, install with:

```bash
siada-browser setup
```

Load `~/.siada-cli/browser/extension` manually through `chrome://extensions` and enter the setup token in the extension settings. After `uv tool upgrade siada-cli`, run `siada-browser setup` again and reload the extension in Chrome. See [Browser installation](./docs/browser-installation.md) for source installation, candidate artifact testing, and release details.

## Development

Install Python 3.12 or 3.13, [Poetry](https://python-poetry.org/docs/#installation), and a maintained Node.js LTS release with npm. Node.js 24 LTS satisfies the current UI dependencies.

```bash
git clone https://github.com/liauto-siada/siada-cli.git
cd siada-cli
poetry install --with dev
npm --prefix siada_cli_ui ci
npm --prefix siada_cli_ui run build:all
poetry run siada-cli
```

Rebuild the UI after changing its source; the launcher uses the bundled UI. To run the standalone ACP agent from the checkout, use `poetry run siada-acp`.

| Directory | Responsibility |
| --- | --- |
| `siada/entrypoint/` | CLI arguments and startup |
| `siada/acp_server/` | ACP agent server |
| `siada/agent_hub/` | Agents and orchestration |
| `siada/tools/`, `siada/services/` | Tools and application services |
| `siada/provider/` | Model provider integrations |
| `siada_cli_ui/` | Terminal UI |
| `tests/`, `docs/` | Tests and documentation |

## Documentation

| Document | Contents |
| --- | --- |
| [User Manual](./docs/USERMANUAL.md) | Configuration, usage modes, commands, checkpoints, and troubleshooting |
| [Skills](./docs/SKILLS.md) | Create and manage reusable workflows |
| [Custom Agents](./docs/USER_AGENTS.md) | Define specialized sub-agents and their tools, models, and skills |
| [External Model Configuration](./docs/external_model_configuration.md) | Connect custom models and API endpoints |
| [Feishu / Lark Remote Control](./docs/remote_control_lark.md) | Configure the bot transport and chat access |
| [Compaction Configuration](./docs/compaction_configuration.md) | Configure conversation compression |
| [Contributing](./docs/CONTRIBUTING.md) | Development conventions and contribution workflow |

## Contributing

Bug fixes, features, documentation improvements, and reusable skills are welcome. Read the [Contributing Guide](./docs/CONTRIBUTING.md) for the contribution agreement and pull request requirements, and use [GitHub Issues](https://github.com/liauto-siada/siada-cli/issues) to report a problem or propose a change.

## Acknowledgements

Thanks to the open source projects and contributors that make Siada possible, including:

- [OpenAI Agents SDK](https://github.com/openai/openai-agents-python) — agent framework.
- [LiteLLM](https://github.com/BerriAI/litellm) — model provider integration.
- [OpenHands ACI](https://github.com/OpenHands/OpenHands) — agent tools.
- [Gemini CLI](https://github.com/google-gemini/gemini-cli) — inspiration for terminal agent design.
- [Agent Client Protocol](https://agentclientprotocol.com/) — integration with agent clients.

See [CREDITS.md](./docs/CREDITS.md) for the full acknowledgements and license information.

## License

Distributed under the [Apache License 2.0](LICENSE).

## Disclaimers

See [disclaimers.md](./docs/disclaimers.md).

---

<div align="center">
Built with care by Li Auto Code Intelligence Team and the open source community
</div>
