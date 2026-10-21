# Browser installation and release

The browser distribution consists of one ZIP per platform. It contains
Node.js 24.13.0 with its license, the proxy server and locked production
dependencies, the web client, and the Chrome extension with redistribution
notices. The Python wheel contains the terminal UI bundle and installer,
but does not contain these browser binaries.

The current stable release is [1.7.37](https://github.com/liauto-siada/siada-cli/releases/tag/v1.7.37). Platform packages are published with the
CLI release on GitHub Releases. Builds check the bundled runtime and proxy;
reload the extension and check its connection after installation.

## Install a published version

```bash
uv tool install --force --python python3.12 --with pip --default-index https://pypi.org/simple "siada-cli==1.7.37"
uv tool update-shell
siada-browser setup
```

The installer reads `browser-manifest.json` from the GitHub Release
`v<installed-cli-version>`, selects the OS and architecture, and checks the
ZIP's SHA-256. It validates licenses, runs Node and proxy CLI checks, then
replaces the installation while preserving connection state. Downloads and
validation failures leave the previous installation intact.

Open `chrome://extensions`, enable Developer mode, and load
`~/.siada-cli/browser/extension`. The extension discovers the local token and
connects to `ws://localhost:9315/ws`. Remote connections require manual URL/token
configuration. Choose API Key or Free Trial in the Chrome login wizard.

For one-command installation, use Linux/macOS:

```bash
curl -fsSL https://liauto-siada.github.io/siada-cli/scripts/install-browser.sh | SIADA_VERSION=1.7.37 sh
```

Or Windows PowerShell:

```powershell
& ([scriptblock]::Create((Invoke-WebRequest -UseBasicParsing 'https://liauto-siada.github.io/siada-cli/scripts/install-browser.ps1').Content)) -Version '1.7.37'
```

```bash
siada-browser status
siada-browser stop
siada-browser start
```

The UI and proxy share the installed Node runtime. Terminal-only users can
install Node.js 24 LTS themselves. Startup does not download a runtime.

## Update

```bash
uv tool upgrade siada-cli
siada-browser setup
```

Reload the extension in Chrome after setup. The installed extension directory
remains fixed. The browser ZIP version matches the CLI version; component
versions are internal metadata.

## Source development

Install Poetry, Node.js 24 LTS with npm, and Bun. Install the Python checkout
with Poetry, then build and install the browser components:

```bash
cd chrome-acp
bun install --frozen-lockfile
bun run test
bun run build
cd ..
poetry run siada-browser setup chrome-acp
```

Source installation uses npm to install production dependencies from the
committed proxy lockfile and uses an existing Node runtime.

## Build and publish

After building browser components:

```bash
node scripts/package-browser.mjs pack
```

Or use `just pack` to build and package together. Output is written to
`chrome-acp/release/`. The packer supports macOS ARM64/x64, Linux ARM64/x64,
and Windows x64 on matching build hosts. Configured support does not imply
that every remote platform has passed acceptance.

The root `browser-release.yml` workflow accepts an existing tag and a
`publish` boolean, defaulting to false. It checks tag/version consistency,
tests and builds components, packages platforms, then merges manifests and
checks artifact hashes. Publishing requires explicitly setting `publish`
to true. It does not publish npm packages or push tags.

Candidate packages can be served from an HTTPS directory containing
`browser-manifest.json` and its referenced ZIP:

```bash
siada-browser setup --base-url https://example.com/candidate
```

Before publication, verify clean installation and Chrome connection on each
supported platform. Publish the manifest and platform ZIPs together to the
same GitHub Release as the corresponding CLI version.