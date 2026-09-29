# Siada Browser Extension (chrome-acp)

Chrome extension for chatting with [ACP](https://agentclientprotocol.com) agents via sidepanel.

Part of the `chrome-acp/` browser add-on for Siada CLI in this repository (`packages/chrome-extension`). Siada CLI installs the built extension into `~/.siada-cli/browser/extension` with `siada-browser setup <chrome-acp-dir>` (or `siada-cli --browser-setup <chrome-acp-dir>`); the build and development instructions below are for working on the package itself.

## Features

- Sidepanel chat interface for ACP agents
- Real-time streaming responses
- Tool call visualization
- Browser tools for agents (tabs, read, execute, plus screenshot / replay / paragraphs / annotate / pdf_render)

## Development

### Prerequisites

- [Bun](https://bun.sh) installed
- Chrome browser

### Build

```bash
# From monorepo root
bun install
bun run build:extension

# Or from this directory
bun run build
```

### Load in Chrome

1. Open `chrome://extensions`
2. Enable "Developer mode"
3. Click "Load unpacked"
4. Select this directory (`packages/chrome-extension`)

For a Siada CLI installation, select `~/.siada-cli/browser/extension` instead — that is the copy `siada-browser setup` installs and keeps up to date.

### Development Mode

```bash
# From monorepo root
bun run dev

# Or from this directory
bun --hot src/index.ts
```

## Usage

1. Start the [proxy server](../proxy-server) with your ACP agent (`siada-browser start` starts the one Siada CLI installed, which runs `siada-cli --acp`)
2. Click the extension icon to open the sidepanel
3. Open Settings and enter the proxy URL and the auth token (`~/.siada-cli/browser/state.json` holds the token used by Siada CLI)
4. Start chatting!

## Browser Tools

The extension provides browser capabilities to connected agents:

| Tool | Description |
|------|-------------|
| `browser_tabs` | List all open tabs (returns id, url, title, active status) |
| `browser_read` | Read content of a specific tab (requires tabId from browser_tabs) |
| `browser_execute` | Execute JavaScript in a specific tab (requires tabId from browser_tabs) |
| `browser_screenshot` | Capture the visible viewport of a tab as an image |
| `browser_replay` | Replay one recorded step (click / input / select / keydown / scroll / navigate) |
| `browser_paragraphs` | Extract indexed readable paragraphs (used for on-page translation/explanation) |
| `browser_annotate` | Render AI-generated content into the page |
| `browser_pdf_render` | Open a PDF in the built-in pdf.js viewer |

## Configuration

Default proxy server URL: `ws://localhost:9315/ws`

Use `wss://<host>:<port>/ws` (with the same token) when the proxy is bound to a non-loopback host, e.g. for LAN access.

## Tech Stack

- React 19
- Tailwind CSS 4
- Radix UI components
- Bun bundler

## License

MIT — this package is derived from the MIT-licensed **Chrome ACP** project and has been modified for Siada CLI (see `../../LICENSE`).
