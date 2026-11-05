# Browser installation

The browser installer downloads the platform ZIP matching the installed CLI
version from GitHub Releases. Each ZIP contains Node.js 24.13.0, the proxy,
locked production dependencies, the web client, the Chrome extension and
redistribution notices. The Python wheel contains the terminal UI and installer.

After installing a published version of Siada CLI, run:

```bash
siada-browser setup
```

The installer validates the manifest, SHA-256, licenses and runtime before
replacing the existing installation. Failed downloads and validation leave the
previous installation intact. Connection state is preserved.

Open `chrome://extensions`, enable Developer mode and load
`~/.siada-cli/browser/extension`. Local connections discover the token
automatically. Remote connections require a configured URL and token.

```bash
siada-browser status
siada-browser stop
siada-browser start
```

To update a published installation:

```bash
uv tool upgrade siada-cli
siada-browser setup
```

Reload the extension in Chrome after updating. Terminal-only users can install
Node.js 24 LTS themselves; CLI startup does not download or install toolchains.

For source development:

```bash
cd chrome-acp
bun install --frozen-lockfile
bun run test
bun run build
cd ..
poetry run siada-browser setup chrome-acp
```

Source installation uses the proxy's npm lockfile for production dependencies.
The public browser workflow builds ZIPs for macOS, Linux and Windows.