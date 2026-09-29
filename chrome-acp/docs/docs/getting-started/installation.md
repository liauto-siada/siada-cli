---
title: Installation
description: Detailed installation instructions for the chrome-acp browser add-on.
---

This guide covers the installation options for `chrome-acp`, the browser add-on for Siada CLI.

| Option | When to use it | Command |
|--------|----------------|---------|
| **From this repository** | You have a checkout of this monorepo | `siada-browser setup <chrome-acp-dir>` |
| **From an artifact host** | Prebuilt artifacts were published somewhere reachable | `siada-browser setup --base-url <url>` |
| **By hand (development)** | You want to build, run and debug the pieces yourself | Build in `chrome-acp/`, run the proxy CLI directly |

The npm packages of this monorepo are **not published**, so there is nothing to `npm install -g` for the proxy or the extension.

## Prerequisites

- **Siada CLI** installed and on `PATH` (the proxy launches `siada-cli --acp` as its agent)
- **Node.js 18+** (Siada CLI bundles one in its virtualenv; otherwise put `node` on `PATH`)
- **Bun** and a checkout of this repository when building from source
- **Chrome** (or any Chromium browser) for the extension

## Option 1: Install from This Repository

### Build the packages

```bash
cd chrome-acp

# Install dependencies
bun install

# Build all packages (extension, proxy server, web client, shared)
bun run build

# ...or build one at a time
bun run build:proxy
bun run build:extension
bun run build:web
```

### Install and start

```bash
siada-browser setup /path/to/siada-agenthub/chrome-acp
# or, without the standalone entry point
siada-cli --browser-setup /path/to/siada-agenthub/chrome-acp
```

`setup` copies the built proxy and extension into `~/.siada-cli/browser/`, persists `{host, port, token}` in `state.json`, starts the proxy (idempotently) and walks you through loading the extension in Chrome.

| `siada-browser setup` flag | `siada-cli` equivalent | Default | Description |
|----------------------------|------------------------|---------|-------------|
| `--port PORT` | `--browser-port PORT` | `9315` | Proxy port |
| `--host HOST` | `--browser-host HOST` | `127.0.0.1` | Bind address. `0.0.0.0` also lets other devices on the LAN connect; non-loopback hosts automatically get `--https` (self-signed certificate) |
| `--base-url URL` | `--browser-base-url URL` | *(none)* | Artifact host to download the prebuilt proxy/extension from; only used when no repo path is given |

The repo path must point at the `chrome-acp/` directory of this repository, and the proxy must already be built (`packages/proxy-server/dist/cli/bin.js`) — `setup` refuses to install an unbuilt checkout.

## Option 2: Install from an Artifact Host

`just pack` in `chrome-acp/` (and the release CI) produces the artifacts the installer expects:

| Artifact | Contents |
|----------|----------|
| `chrome-acp-proxy-<version>-<platform>.tar.gz` | Per-platform proxy build (e.g. `macos-arm64`, `linux-x64`, `windows-x64`); bundles that platform's native `@parcel/watcher` binary |
| `chrome-acp-proxy-<version>.tar.gz` | Platform-independent fallback (pure JS; the watcher degrades to `fs.watch`) |
| `chrome-acp-extension-<version>.zip` | Built unpacked extension (`manifest.json`, `icons/`, `rules/`, `dist/`) |
| `latest_version` + `<artifact>.sha256` | Version pointer and checksums the installer verifies |

```bash
# The artifact host has to be named explicitly in this build
siada-browser setup --base-url https://<artifact-host>/chrome-acp

# Same thing through siada-cli
siada-cli --browser-setup --browser-base-url https://<artifact-host>/chrome-acp
```

The installer reads `<base-url>/latest_version`, prefers the platform tarball for your OS/arch and falls back to the neutral one, verifies the SHA-256 checksum before unpacking, and finishes with the same steps as Option 1 (start the proxy, guide the extension load).

## Option 3: Run It by Hand (Development)

Without the Siada CLI you can drive the proxy yourself:

```bash
cd chrome-acp
bun install
bun run build

# <agent-command> is any ACP agent; siada-cli --acp is the one Siada CLI uses
node packages/proxy-server/dist/cli/bin.js --port 9315 claude-code-acp
```

Then build and load the extension from the checkout:

```bash
bun run build:extension
```

1. Open `chrome://extensions`
2. Enable **Developer mode**
3. Click **Load unpacked** and select `packages/chrome-extension`
4. In the extension settings, point the proxy URL at `ws://localhost:9315/ws` and paste the token printed by the proxy (or start the proxy with `--no-auth` on localhost only)

See the [CLI Reference](/reference/cli-reference/) for every proxy flag, and [Architecture](/reference/architecture/) for how the pieces fit together.

## What the Installer Puts Where

| Path (under `~/.siada-cli/browser/`) | Contents |
|--------------------------------------|----------|
| `proxy/` | Proxy server (`dist/`, `public/`, production `node_modules/`) |
| `extension/` | Unpacked MV3 extension — the fixed path Chrome pins for *Load unpacked* |
| `state.json` | `{host, port, token}`; the token is exported to the proxy as `ACP_AUTH_TOKEN` |
| `acp-proxy.log` | Proxy stdout/stderr (check this first when something fails) |
| `proxy.pid` | PID of the proxy spawned by Siada CLI (used by `stop`) |

## Installing an ACP Agent

The proxy is agent-agnostic, but the proxy that Siada CLI manages always runs `siada-cli --acp`, so with a normal Siada CLI installation there is nothing else to install. To use another agent, install that agent (plus its ACP adapter where one is needed) and either point the proxy at it manually or run your own proxy process:

### Claude Code

```bash
npm install -g @anthropic-ai/claude-code @zed-industries/claude-code-acp

# Run the proxy with it instead of siada-cli
node ~/.siada-cli/browser/proxy/dist/cli/bin.js --no-auth claude-code-acp
```

**Requirements:** `ANTHROPIC_API_KEY` environment variable

### Codex CLI (OpenAI)

```bash
npm install -g @openai/codex @zed-industries/codex-acp
```

**Requirements:** `OPENAI_API_KEY` environment variable

### OpenCode

```bash
curl -fsSL https://opencode.ai/install | bash
```

### Gemini CLI

```bash
npm install -g @google/gemini-cli
```

### Qwen Code

```bash
npm install -g @qwen-code/qwen-code@latest
```

### Augment Code

```bash
npm install -g @augmentcode/auggie
```

See [Supported Agents](/guides/supported-agents/) for the exact commands to pass to the proxy.

## Verifying the Installation

```bash
# Managed install: proxy state as JSON (running, port, host, extensionConnected, ...)
siada-browser status        # or: siada-cli --browser-status

# The same data over HTTP
curl http://localhost:9315/status

# Proxy CLI options
node ~/.siada-cli/browser/proxy/dist/cli/bin.js --help
```

If the proxy is not running, check `~/.siada-cli/browser/acp-proxy.log`, then `siada-browser start`.

## Updating

Re-run the install with the same source you used the first time; both the proxy and the extension directories are replaced in place, which keeps the unpacked extension ID (and therefore your Chrome settings) stable:

```bash
cd chrome-acp
bun install
bun run build
siada-browser setup /path/to/siada-agenthub/chrome-acp     # reinstall + restart
```

## Next Steps

- Follow the [Quick Start](/getting-started/quick-start/) guide
- Learn about [CLI Options](/reference/cli-reference/)
