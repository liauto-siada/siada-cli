---
title: Remote Access
description: Reach the chrome-acp proxy from other devices on your network.
---

`chrome-acp` can be reached from other devices on your local network — mobile phones, tablets, or other computers. This is useful for the web client (PWA) on a phone, for the session-sharing links produced by the `/share` command in the Siada terminal, and for a Chrome extension on another machine.

By default the proxy binds to `127.0.0.1` (this machine only). Anything else needs an explicit non-loopback bind, which automatically turns on HTTPS with a self-signed certificate.

## Quick Start

Managed by Siada CLI — set the bind address once at install time:

```bash
siada-browser setup /path/to/siada-agenthub/chrome-acp --host 0.0.0.0
# or
siada-cli --browser-setup /path/to/siada-agenthub/chrome-acp --browser-host 0.0.0.0
```

The host is persisted in `~/.siada-cli/browser/state.json`, so later `siada-browser start | restart` calls keep using it. A non-loopback host adds `--https` to the proxy command line automatically.

Running the proxy directly (from a built checkout or the installed copy):

```bash
node ~/.siada-cli/browser/proxy/dist/cli/bin.js --https --host 0.0.0.0 claude-code-acp
```

Either way, the proxy:

1. Binds to all network interfaces (`0.0.0.0`)
2. Enables HTTPS with a self-signed certificate
3. Generates (or reuses) an authentication token
4. Prints URLs and a QR code for connection

---

## Server Output

When running with remote access enabled:

```
  🚀 ACP Proxy Server (HTTPS + loopback ws)

  Open in browser:
    ➜ Local:   http://localhost:9315/app?token=abc123...
    ➜ Network: https://192.168.1.100:9315/app?token=abc123...

  Manual connection:
    URL:   wss://192.168.1.100:9315/ws
    Token: abc123...

  📱 Scan QR to connect on mobile:
    ┌──────────────────────┐
    │ █▀▀▀▀▀█ ▄▄▄▄ █▀▀▀▀▀█ │
    │ █ ███ █ ▀▄▄▀ █ ███ █ │
    │ ...                   │
    └──────────────────────┘

  📦 Agent: siada-cli --acp
     CWD:   /Users/you/.siada-cli/workspace

  Press Ctrl+C to stop
```

The QR code encodes the full connection details, including the auth token.

The port speaks both protocols: TLS (https/wss) for remote peers, plaintext
(http/ws) for loopback clients. Local connections need no certificate setup;
plaintext connections from non-loopback peers are refused, so LAN traffic
stays encrypted.

---

## Connecting Another Browser

For a Chrome extension on a different machine (or a fresh profile), open the extension's settings and enter:

- **URL:** `wss://<LAN-IP>:9315/ws` — `wss` is required for non-loopback peers
- **Token:** the token printed by the proxy (or stored in `~/.siada-cli/browser/state.json`)

Trust the certificate **first**: the extension page has no certificate-warning entry point, and the `wss` handshake simply fails until the certificate is trusted. Open the following in a normal browser tab and accept the warning:

```
https://<LAN-IP>:9315/app?token=<token>
```

The local Chrome on the proxy machine is unaffected — it keeps using `ws://localhost:9315/ws` and needs no trusted certificate.

---

## Why HTTPS?

HTTPS is required for several browser features:

| Feature | Requires HTTPS |
|---------|----------------|
| Camera access (QR scanning in web client) | Yes |
| Service Worker / PWA install | Yes (on non-localhost) |
| Secure WebSocket (wss://) | Yes |
| Clipboard access | Yes (on some browsers) |

### Self-Signed Certificate

The proxy generates a self-signed certificate on startup:
- Valid for 365 days
- Stored in `~/.acp-proxy/` (persisted in `~/.acp-proxy/cert.pem` and reused) — note this directory is shared with any other instance of this proxy on the machine
- Automatically regenerated if expiring within 7 days or LAN IP changes
- Browser will show a security warning

**To accept the certificate:**
1. Navigate to the URL
2. Click "Advanced" or "Show Details"
3. Click "Proceed to site" or "Accept the Risk"

Alternatively, import `~/.acp-proxy/cert.pem` into the system trust store.

:::tip
On mobile, you may need to visit the URL directly before scanning the QR code to accept the certificate.
:::

---

## Authentication Flow

### How It Works

1. **Token Generation:** Server generates a random 64-character hex token at startup (Siada CLI generates and persists one in `state.json`, and passes it as `ACP_AUTH_TOKEN`)
2. **URL Embedding:** Token is appended as `?token=abc123...`
3. **Connection:** Client sends token in initial WebSocket handshake
4. **Validation:** Server validates token before accepting connection

### Custom Token

Set a fixed token instead of random generation:

```bash
export ACP_AUTH_TOKEN="my-secret-token"
node ~/.siada-cli/browser/proxy/dist/cli/bin.js --host 0.0.0.0 --https claude-code-acp
```

Useful for:
- Automation scripts
- Persistent URLs in bookmarks
- Sharing access with known parties

### Token in QR Code

The QR code encodes the connection URL including token:
```
wss://192.168.1.100:9315/ws
```
plus the token itself, so any ACP client that understands the payload can connect.

Scan with any QR reader or your phone's camera.

---

## Connecting from Mobile

### Method 1: QR Code (Recommended)

1. Start the proxy with `--https --host 0.0.0.0`
2. Open phone camera and point at QR code
3. Tap the URL notification
4. Accept the certificate warning
5. Start chatting!

### Method 2: Manual URL

1. Find your computer's IP address:
   ```bash
   # macOS/Linux
   ifconfig | grep "inet "

   # Windows
   ipconfig
   ```
2. Open browser on mobile
3. Navigate to `https://<your-ip>:9315/app?token=<token>`

---

## Session Share Links

Siada CLI's `/share` command builds a link against the prompt that goes through this proxy:

```
https://<your-ip>:9315/app?token=<token>&session=<session-id>&cwd=<workspace>
```

The recipient opens it in a browser and sees the conversation update as you keep working. The link embeds the proxy token, which grants full control over the agent — only send it to people you trust, and make sure the proxy is reachable from the recipient (that is, bound to `0.0.0.0` and reachable on your LAN).

---

## Termux (Android)

Run the proxy directly on your Android device.

### Installation

```bash
# Install Termux from F-Droid (not Play Store)
# https://f-droid.org/packages/com.termux/

# Open Termux and install Node.js
pkg update && pkg upgrade
pkg install nodejs

# Get the chrome-acp sources (this repository) and build the proxy
cd chrome-acp
bun install && bun run build:proxy
# ...or unpack the prebuilt proxy tarball (chrome-acp-proxy-<version>.tar.gz)
# next to its node_modules

# Install an agent
npm install -g @anthropic-ai/claude-code @zed-industries/claude-code-acp
```

### Running with Auto-Launch

```bash
node packages/proxy-server/dist/cli/bin.js --termux claude-code-acp
```

The `--termux` flag:
1. Starts the proxy server on localhost
2. Waits for server to be ready
3. Calls `termux-open-url` to launch the PWA

### Requirements

For auto-launch to work:
- Install **Termux:API** app from F-Droid
- Grant Termux API permissions
- Install termux-api package: `pkg install termux-api`

---

## Network Options

| Option | Default | Description |
|--------|---------|-------------|
| `--host` | `localhost` | Bind address (`siada-browser setup --host`). `0.0.0.0` opens it to the LAN and turns on HTTPS |
| `--port` | `9315` | Server port (`siada-browser setup --port`) |
| `--https` | `false` | Enable HTTPS with a self-signed certificate (added automatically for non-loopback hosts) |
| `--public-url` | - | Public WebSocket URL for QR code |
| `--no-auth` | `false` | Disable authentication (localhost only!) |

### Common Configurations

**Local only (default):**
```bash
siada-browser setup /path/to/chrome-acp        # 127.0.0.1:9315
# http://localhost:9315/app
```

**LAN access with auth:**
```bash
siada-browser setup /path/to/chrome-acp --host 0.0.0.0
# https://192.168.1.x:9315/app?token=...
```

**Custom port:**
```bash
siada-browser setup /path/to/chrome-acp --host 0.0.0.0 --port 8443
# https://192.168.1.x:8443/app?token=...
```

---

## Security Considerations

:::caution[Important]
Remote access exposes your AI agent to network connections. Be careful!
:::

### Do's

- Use `--https` for any non-localhost access (Siada CLI does this for you)
- Keep authentication enabled (don't use `--no-auth`)
- Use on trusted networks only (home, office)
- Stop the server when not in use (`siada-browser stop`)

### Don'ts

- Don't use `--no-auth` with `--host 0.0.0.0`
- Don't expose to the internet without additional security
- Don't share your auth token publicly
- Don't run on untrusted networks

### For Public Access

If you need public access:
1. Use a reverse proxy (nginx, Caddy)
2. Set up proper TLS certificates (Let's Encrypt)
3. Add additional authentication (basic auth, OAuth)
4. Consider VPN access instead

---

## Server Deployment

When deploying on a server with a domain name, the auto-detected LAN IP won't work for the QR code. Use `--public-url` to specify the actual WebSocket URL:

```bash
node ~/.siada-cli/browser/proxy/dist/cli/bin.js --host 0.0.0.0 --public-url wss://example.com/ws claude-code-acp
```

This makes the QR code contain `wss://example.com/ws` instead of the local network IP.

### Example: nginx Reverse Proxy

```nginx
server {
    listen 443 ssl;
    server_name example.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location /ws {
        proxy_pass http://localhost:9315/ws;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }

    location / {
        proxy_pass http://localhost:9315;
        proxy_set_header Host $host;
    }
}
```
