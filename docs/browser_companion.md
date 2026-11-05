# Automatic local Chrome connection

After installing Siada CLI, install and start its browser components:

```bash
siada-browser setup
```

Load the extension directory printed by setup in `chrome://extensions`, then
open the Siada sidepanel. The extension obtains the running local proxy's token,
saves it in connection settings and connects automatically. The existing ACP
handshake starts the configured CLI and reports connection failures.

If the CLI is not logged in, the sidepanel displays the CLI's login options:
LiId, Device Code, and API Key. The proxy runs `siada-cli --browser-login` and
relays the wizard's messages over an authorized local connection. Complete the
wizard in Chrome; the CLI validates and saves the configuration. The sidepanel
connects automatically after login. API keys are masked and are not saved in
Chrome storage. Closing the wizard terminates its login subprocess.

To sign in again or change model services, expand connection settings and
choose **重新登录 / 切换模型服务**. Cancelling keeps the current configuration;
successful configuration reconnects the sidepanel automatically.

If the local proxy is unavailable, the sidepanel shows the Chrome ACP icon and
copyable installation commands. It retries discovery every five seconds.
Choose **Already installed / Siada CLI on another device** at the bottom to
open the connection settings and enter the server address and token.
The internal installation commands enable remote access with `0.0.0.0`;
the page explains that this opens the corresponding network ports.
For an existing installation, start its service:

```bash
siada-browser start
```

Discovery uses the local server address in settings (default port 9315).
Remote connections and older proxy versions retain manual token entry.
An existing proxy must be updated and restarted to provide automatic discovery.
After updating unpacked extension files, reload the extension in Chrome.

Token discovery is restricted to plaintext loopback requests from the extension
installed by setup. The CLI derives its allowed ID from the extension manifest
public key or unpacked installation path. To use a separately loaded extension,
provide its ID when starting the proxy:

```bash
SIADA_BROWSER_EXTENSION_IDS=<extension-id> siada-browser restart
```

Ordinary websites and remote devices cannot use the discovery endpoint.