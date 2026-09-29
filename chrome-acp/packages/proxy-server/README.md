# Proxy Server (chrome-acp)

A WebSocket proxy server that bridges Chrome extensions (and the bundled web client) to ACP (Agent Client Protocol) agents.

Part of the `chrome-acp/` browser add-on for Siada CLI in this repository (`packages/proxy-server`). The npm package is **not published**, so it is installed either from a checkout of this repository or from an artifact host.

## Installation

### With Siada CLI (recommended)

```bash
# Build once, then install + start (also installs the extension)
cd chrome-acp && bun install && bun run build
siada-browser setup /path/to/siada-agenthub/chrome-acp
# or: siada-cli --browser-setup /path/to/siada-agenthub/chrome-acp
```

The proxy ends up in `~/.siada-cli/browser/proxy/`, is started detached, and is launched as:

```
node ~/.siada-cli/browser/proxy/dist/cli/bin.js --host 127.0.0.1 --port 9315 siada-cli -- --acp
```

Prebuilt artifacts can be installed instead with `siada-browser setup --base-url <artifact-host>/chrome-acp`.

### From source

```bash
# From monorepo root
bun install
bun run build:proxy
node packages/proxy-server/dist/cli/bin.js --help
```

## Usage

### Through Siada CLI

```bash
siada-browser start | stop | restart | status
```

### Directly

```bash
# Installed copy
node ~/.siada-cli/browser/proxy/dist/cli/bin.js /path/to/agent

# From a checkout
node packages/proxy-server/dist/cli/bin.js /path/to/agent
```

### Examples

```bash
# Basic usage (agent command is required)
node dist/cli/bin.js /path/to/agent

# Local, no auth
node dist/cli/bin.js --no-auth claude-code-acp

# With custom port
node dist/cli/bin.js --port 9000 /path/to/agent

# LAN access with HTTPS (self-signed certificate) and QR code
node dist/cli/bin.js --https --host 0.0.0.0 claude-code-acp

# With debug logging
node dist/cli/bin.js --debug /path/to/agent

# Pass arguments to the agent (use -- to separate)
node dist/cli/bin.js /path/to/agent -- --verbose --model gpt-4
```

## CLI Reference

```
USAGE
  acp-proxy [options] <command>... [-- <agent-args>...]
  acp-proxy --help
  acp-proxy --version

FLAGS
     [--port]        Port to listen on                       [default = 9315]
     [--host]        Host to bind to (0.0.0.0 = LAN)         [default = localhost]
     [--https]       Enable HTTPS with a self-signed certificate
     [--public-url]  Public WebSocket URL for the QR code (e.g. wss://example.com/ws)
     [--no-auth]     DANGEROUS: disable authentication
     [--termux]      Auto-launch the PWA via Termux
     [--debug]       Enable debug logging
  -h  --help         Print help information and exit
  -v  --version      Print version information and exit

ENVIRONMENT
  ACP_AUTH_TOKEN     Fixed auth token instead of a random one (Siada CLI sets this)

ARGUMENTS
  command...  Agent command followed by its arguments
```

## How It Works

The proxy server:
1. Listens for WebSocket connections from the Chrome extension and the web client
2. When a "connect" message is received, spawns the configured ACP agent as a subprocess
3. Bridges messages between the WebSocket (browser) and stdin/stdout (agent)
4. Exposes browser tools to agents via MCP (Model Context Protocol)

This allows Chrome extensions to communicate with ACP agents despite not being able to spawn subprocesses directly. With a Siada CLI installation the agent command is `siada-cli --acp`, so the side panel is a normal Siada session.

## Endpoints

| Endpoint | Description |
|----------|-------------|
| `/app` | Web client (PWA) — also accepts `?token=…&session=…&cwd=…` share links |
| `/ws` | WebSocket for browser clients (token-checked when auth is enabled) |
| `/ws/trajectory` | WebSocket for recorded step events pushed by the extension |
| `/mcp` | Streamable HTTP MCP endpoint |
| `/health`, `/status` | Probes used by `siada-browser status` / setup verification |

## Browser Tools (via MCP)

The proxy server exposes an MCP endpoint at `http://localhost:{port}/mcp` with these tools:

| Tool | Description |
|------|-------------|
| `browser_tabs` | List all open tabs (returns id, url, title, active status) |
| `browser_read` | Read content of a specific tab (requires tabId from browser_tabs) |
| `browser_execute` | Execute JavaScript in a specific tab (requires tabId from browser_tabs) |
| `browser_screenshot` | Capture the visible viewport of a tab as an image |
| `browser_replay` | Replay one recorded step in a tab |
| `browser_paragraphs` | Extract indexed readable paragraphs |
| `browser_annotate` | Render AI-generated content into the page |
| `browser_pdf_render` | Open a PDF in the extension's built-in pdf.js viewer |

## License

MIT — this package is derived from the MIT-licensed **Chrome ACP** project and has been modified for Siada CLI (see `../../LICENSE`).
