---
title: CLI Reference
description: The siada-browser commands and the acp-proxy server options.
---

There are two command-line surfaces:

1. **`siada-browser`** (or the `--browser-*` flags on `siada-cli`) — the Siada CLI manager that installs, starts, stops and inspects the add-on. This is what you normally use.
2. **`acp-proxy`** — the proxy server itself. Siada CLI launches it for you, but it can also be run directly (development, alternative agents, Termux).

---

# 1. Siada CLI Browser Commands

## Usage

```bash
siada-browser setup [<chrome-acp-dir>] [--port N] [--host H] [--base-url URL]
siada-browser start | stop | restart | status
```

The same operations through `siada-cli`:

| `siada-browser` | `siada-cli` |
|-----------------|-------------|
| `setup <dir>` | `--browser-setup <dir>` |
| `setup` (artifacts) | `--browser-setup` |
| `start` | `--browser-start` |
| `stop` | `--browser-stop` |
| `restart` | `--browser-restart` |
| `status` | `--browser-status` |

## `setup`

Installs the proxy and the extension into `~/.siada-cli/browser/`, then starts the proxy.

**Arguments:**

- `<chrome-acp-dir>` (optional) — path to the `chrome-acp/` directory of this repository, already built (`bun run build`). When given, the proxy and extension are copied from that checkout.

**Options:**

| Option | `siada-cli` equivalent | Default | Description |
|--------|------------------------|---------|-------------|
| `--port` | `--browser-port` | `9315` | Proxy port |
| `--host` | `--browser-host` | `127.0.0.1` | Bind address. Non-loopback (e.g. `0.0.0.0`) also enables `--https` with a self-signed certificate |
| `--base-url` | `--browser-base-url` | *(none)* | Artifact host serving `chrome-acp-proxy-<version>[-<platform>].tar.gz`, `chrome-acp-extension-<version>.zip`, `latest_version` and `.sha256` files. Only used when no directory is given; this build has no default host |

Without a directory, `setup` downloads from the artifact host instead of a checkout. Without a directory **and** without `--base-url`, there is nothing to install — pass one of the two.

After installing, `setup` prints the extension directory and the auth token (both copied to the clipboard where supported) and opens `chrome://extensions`, where the unpacked extension is loaded once by hand.

## `start` / `stop` / `restart`

```bash
siada-browser start     # idempotent: prints "running" or "started"
siada-browser stop      # kills the proxy started by Siada CLI (pidfile, else by port)
siada-browser restart   # stop + start
```

`start` refuses to run when the proxy is not installed yet, and reports `error: ...` (exit code `1`) if the proxy does not become healthy within 30 seconds — the log file path is included in the message.

## `status`

Prints the proxy's `/status` payload as JSON:

```json
{
  "status": "ok",
  "version": "1.0.45",
  "port": 9315,
  "host": "127.0.0.1",
  "authEnabled": true,
  "extensionConnected": true,
  "executor": { "dedicated": true, "fallback": false, "connected": true },
  "agentSessions": 1,
  "clients": 1,
  "running": true
}
```

When the proxy is not reachable, it prints `{ "running": false }`.

## Installed Layout

| Path | Contents |
|------|----------|
| `~/.siada-cli/browser/proxy/` | Proxy server (`dist/`, `public/`, production `node_modules/`) |
| `~/.siada-cli/browser/extension/` | Unpacked extension (load this path in Chrome) |
| `~/.siada-cli/browser/state.json` | `{host, port, token}`, mode `0600` |
| `~/.siada-cli/browser/acp-proxy.log` | Proxy stdout/stderr |
| `~/.siada-cli/browser/proxy.pid` | PID of the proxy process |
| `~/.siada-cli/workspace/` | Working directory of the proxy, i.e. the side panel's default workspace |

Environment overrides used mainly by tests: `SIADA_BROWSER_HOME` (root of the layout), `SIADA_BROWSER_NODE` (Node.js binary), `SIADA_BROWSER_PROXY_CMD` (full proxy command).

---

# 2. Proxy CLI (`acp-proxy`)

## Usage

```bash
acp-proxy [options] <agent-command> [-- <agent-args>]
```

`acp-proxy` is the bin name of the proxy; it is not installed globally (there is no npm release), so in a Siada CLI installation you invoke it through Node, using the copy the installer put in place:

```bash
node ~/.siada-cli/browser/proxy/dist/cli/bin.js [options] <agent-command> [-- <agent-args>]
```

**Arguments:**
- `<agent-command>` - The ACP agent executable to run (`siada-cli` in the managed setup)
- `[agent-args]` - Arguments passed to the agent (after `--`)

## Options

| Option | Default | Description |
|--------|---------|-------------|
| `--port` | `9315` | Server port |
| `--host` | `localhost` | Host to bind (`0.0.0.0` for LAN access) |
| `--https` | `false` | Enable HTTPS with self-signed certificate |
| `--public-url` | - | Public WebSocket URL for QR code (e.g., `wss://example.com/ws`) |
| `--no-auth` | `false` | Disable authentication |
| `--termux` | `false` | Auto-launch PWA via Termux API |
| `--debug` | `false` | Enable debug logging to file |

---

## Environment Variables

### `ACP_AUTH_TOKEN`

Set a custom authentication token instead of auto-generating one:

```bash
export ACP_AUTH_TOKEN="my-secret-token"
node ~/.siada-cli/browser/proxy/dist/cli/bin.js --host 0.0.0.0 claude-code-acp
```

When not set, a random token is generated and printed to the console. Siada CLI always sets it, using the token persisted in `state.json`, so the extension stays connected across restarts.

### Agent Environment

The proxy inherits and passes through all environment variables to the agent. Set API keys before starting:

```bash
# For Claude Code
export ANTHROPIC_API_KEY="sk-ant-..."

# For OpenAI Codex
export OPENAI_API_KEY="sk-..."

# For Gemini CLI
export GOOGLE_API_KEY="..."

node ~/.siada-cli/browser/proxy/dist/cli/bin.js --no-auth claude-code-acp
```

---

## Examples

### Basic Local Usage

```bash
node ~/.siada-cli/browser/proxy/dist/cli/bin.js --no-auth claude-code-acp
```

Output (abridged):

```
  🚀 ACP Proxy Server

  Open in browser:
    ➜ Local:   http://localhost:9315/app

  Manual connection:
    URL:   ws://localhost:9315/ws

  ⚠️  Authentication disabled (--no-auth)

  📦 Agent: claude-code-acp
     CWD:   /home/user/project

  Press Ctrl+C to stop
```

### Custom Port

```bash
node ~/.siada-cli/browser/proxy/dist/cli/bin.js --port 8080 --no-auth claude-code-acp
```

### Network Access with HTTPS

```bash
node ~/.siada-cli/browser/proxy/dist/cli/bin.js --https --host 0.0.0.0 claude-code-acp
```

Output includes:
- URLs with embedded auth token
- The WebSocket URL and token for manual entry
- A QR code for mobile connection

### Server Deployment with Public URL

When deploying behind a reverse proxy with a domain name:

```bash
node ~/.siada-cli/browser/proxy/dist/cli/bin.js --host 0.0.0.0 --public-url wss://example.com/ws claude-code-acp
```

The `--public-url` overrides the QR code URL, so mobile devices can connect via your domain instead of the local IP.

### Agent with Arguments

Use `--` to separate proxy options from agent arguments:

```bash
# siada-cli's ACP entry point (what the managed proxy runs)
node ~/.siada-cli/browser/proxy/dist/cli/bin.js --no-auth siada-cli -- --acp

# Gemini CLI with experimental ACP flag
node ~/.siada-cli/browser/proxy/dist/cli/bin.js --no-auth gemini -- --experimental-acp

# Qwen Code with ACP mode
node ~/.siada-cli/browser/proxy/dist/cli/bin.js --no-auth qwen -- --acp
```

### Debug Mode

```bash
node ~/.siada-cli/browser/proxy/dist/cli/bin.js --debug --no-auth claude-code-acp
```

Debug logs are written to `.acp-proxy/` in the current working directory:
- **Format:** `.acp-proxy/acp-proxy-YYYY-MM-DD_HH-MM-SS.log`
- **Example:** `.acp-proxy/acp-proxy-2026-02-16_14-30-45.log`

---

## HTTP Endpoints

| Endpoint | Description |
|----------|-------------|
| `/` | Redirects to `/app/` |
| `/app` | Web client (PWA), also accepts `?token=…&session=…&cwd=…` share links |
| `/ws` | WebSocket endpoint for browser clients (token-checked when auth is enabled) |
| `/ws/trajectory` | WebSocket endpoint for recorded step events pushed by the extension |
| `/mcp` | MCP Streamable HTTP endpoint exposing the browser tools |
| `/health` | Liveness probe, `{ "status": "ok" }` |
| `/status` | Readiness/details probe used by `siada-browser status` |

---

## HTTPS Configuration

When `--https` is enabled:

1. **Self-signed certificate** is generated automatically
2. Certificate is stored in `~/.acp-proxy/cert.pem` (persisted and reused)
3. Browser will show a security warning - this is expected
4. The port serves TLS to remote peers and plaintext `http`/`ws` to loopback clients, so local setups need no certificate trust

:::tip[LAN Only]
Self-signed certificates are only suitable for local network use. For public access, use a reverse proxy with proper TLS termination.
:::

### Why HTTPS?

Required for:
- **Camera access** on mobile (for QR scanning)
- **Service Worker** registration on non-localhost origins
- **Secure WebSocket** (wss://) connections

---

## Termux Mode

The `--termux` flag is designed for running on Android:

```bash
node packages/proxy-server/dist/cli/bin.js --termux claude-code-acp
```

Behavior:
1. Starts the proxy server
2. Waits for server to be ready
3. Launches the PWA URL using Termux's `termux-open-url` command

### Termux Setup

```bash
# Install Node.js
pkg install nodejs

# Build the proxy from this repository (Bun is not available for Termux builds)
cd chrome-acp && bun install && bun run build:proxy
# ...or unpack the prebuilt tarball chrome-acp-proxy-<version>.tar.gz

# Install your agent
npm install -g @anthropic-ai/claude-code @zed-industries/claude-code-acp

# Run
node packages/proxy-server/dist/cli/bin.js --termux claude-code-acp
```

---

## Working Directory

The agent runs in the **current working directory** of the proxy. This determines:

- Which files the agent can access
- The project context for coding agents
- The base path for file operations
- The workspace root shown in the side panel

Siada CLI starts the proxy with `~/.siada-cli/workspace` as its working directory:

```bash
cd /path/to/your/project
node ~/.siada-cli/browser/proxy/dist/cli/bin.js --no-auth claude-code-acp
```

---

## Authentication

### With Authentication (default)

When authentication is enabled (no `--no-auth` flag):

1. Server generates random token (or uses `ACP_AUTH_TOKEN`)
2. Token is embedded in printed URLs and in the QR code
3. Clients must provide token to connect

Token format in URL:
```
http://192.168.1.100:9315/app?token=abc123...
```

### Without Authentication

```bash
node ~/.siada-cli/browser/proxy/dist/cli/bin.js --no-auth claude-code-acp
```

:::caution
Only use `--no-auth` when:
- Binding to `localhost` only
- On a trusted private network
- For development/testing

Never use `--no-auth` with `--host 0.0.0.0` on public networks!
:::

---

## Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Clean shutdown (Ctrl+C) |
| `1` | Agent process failed to start |
| `1` | Invalid command-line arguments |
