---
title: Quick Start
description: Install the chrome-acp browser add-on for Siada CLI in a few minutes.
---

`chrome-acp` has two halves: the **proxy server** (installed into `~/.siada-cli/browser/proxy/`) and the **Chrome extension** (installed into `~/.siada-cli/browser/extension/`). Siada CLI builds, installs, starts and stops both for you.

## Prerequisites

- **Siada CLI** installed, with `siada-cli` on `PATH` — the proxy launches `siada-cli --acp` as its agent
- **Node.js 18+** — Siada CLI bundles one inside its virtualenv; otherwise `node` must be on `PATH`
- **Bun** and a checkout of this repository, to build the packages from source
- **Chrome** (or any Chromium browser) for the extension

## Step 1: Build the Add-on

From the repository root:

```bash
cd chrome-acp
bun install
bun run build
```

`bun run build` builds all four packages (extension, proxy server, web client, shared). Individual targets: `bun run build:extension`, `bun run build:proxy`, `bun run build:web`.

`just pack` in the same directory packages those outputs as distributable artifacts (`chrome-acp-proxy-<version>[-<platform>].tar.gz` and `chrome-acp-extension-<version>.zip`) for an artifact host — see [Installation](/getting-started/installation/).

## Step 2: Install and Start

```bash
# Point setup at the chrome-acp/ directory of this repository
siada-browser setup /path/to/siada-agenthub/chrome-acp
```

The equivalent `siada-cli` flag:

```bash
siada-cli --browser-setup /path/to/siada-agenthub/chrome-acp
```

`setup`:

1. copies the proxy and the extension into `~/.siada-cli/browser/`
2. writes `state.json` (port + auth token)
3. starts the proxy on `http://localhost:9315`
4. prints the extension directory and the token

Using prebuilt artifacts instead of a checkout — this build ships no default artifact host, so name one explicitly:

```bash
siada-browser setup --base-url https://<artifact-host>/chrome-acp
# or
siada-cli --browser-setup --browser-base-url https://<artifact-host>/chrome-acp
```

## Step 3: Load the Extension in Chrome (Once)

`setup` opens `chrome://extensions` for you and copies the extension path to the clipboard:

1. Enable **Developer mode** (top right)
2. Click **Load unpacked** and select the directory printed by `setup` — normally `~/.siada-cli/browser/extension` (the path is already in your clipboard)
3. Open the **Siada** side panel → **Settings** and paste the proxy URL and the token printed by `setup`

That token is the credential which lets the browser reach your local `siada-cli` — keep it to yourself. It lives in `~/.siada-cli/browser/state.json` and is reused on every start.

## Step 4: Start Chatting

- **Side panel** — click the Siada icon in the Chrome toolbar
- **Web client (PWA)** — open the URL the proxy printed, e.g. `http://localhost:9315/app?token=...`
- **Terminal** — `siada-cli` keeps working as before; browser tools simply become available to it

## Managing the Add-on

```bash
siada-browser status     # JSON from the proxy's /status endpoint
siada-browser restart
siada-browser stop
```

`siada-cli --browser-status`, `--browser-restart` and `--browser-stop` do the same. `status` reports whether the proxy is `running`, whether the extension is connected (`extensionConnected`) and which host/port it listens on.

## What's Next?

- Learn about [Browser Tools](/guides/browser-tools/) the extension provides
- See all [Supported Agents](/guides/supported-agents/)
- Configure [Remote Access](/guides/remote-access/) for mobile devices
- Read the full [CLI Reference](/reference/cli-reference/)
