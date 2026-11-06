# Interactive webpages in Chrome ACP

Chrome ACP can display interactive HTML in the browser side panel and web chat.
Ask the agent, for example: “Build an interactive sales dashboard with a date
filter and a budget slider.” Controls can update the page immediately. An
explicit assistant action sends the page identity and current state into the
same conversation.

Use **Share** next to the page title, or ask “Share this interface as a
webpage on my local network.” Share publishes the current page and state and
returns a LAN URL, with **Copy link** and **Open webpage** controls. Recipients
can interact independently; their changes stay in their own browsers. To
continue with the assistant, return to the Siada conversation.

Shared pages are persisted under `~/.chrome-acp/pages/shared/`. Links work while
Chrome ACP is running and are restored on restart with the same directory and
LAN address. Sharing starts a read-only HTTP listener on all interfaces,
normally port 9316 (the proxy port plus one). Set `SIADA_UI_SHARE_PORT` before
starting the proxy to choose a different port. This listener serves only
published webpages; the proxy retains its existing connection configuration.
Anyone on the network with the unguessable share URL can read the snapshot.
Subsequent edits in chat do not change previously published snapshots.

The agent discovers `browser_present_ui`, `browser_share_ui` and
`browser_list_ui` through the browser MCP server. Pages use self-contained
HTML, inline CSS/JavaScript and `window.siadaUI.state`, `setState(patch)` and
`submit(prompt)` for state and assistant actions. External resources and network
requests are blocked inside the generated page. The maximum source size is
2 MiB and the maximum state size is 64 KiB. Browser-side changes in chat are
saved to the local proxy; a save failure is shown with a retry message.

For a custom storage location, set `SIADA_UI_DIR` before starting the proxy.

For a mechanism, ask “Show how a four-stroke engine works, with controls to
isolate a cylinder and open a cutaway.” The model chooses whether to use ordinary
HTML or the built-in [teardown toolkit](https://github.com/elvarofficial/teardown).
The interface has one entry point and the same Share action.

Source-based pages use `browser_ui_project`, `browser_ui_build` and
`browser_ui_inspect`. Projects survive restart under the page directory's
`projects/` folder. Build updates the same card and preserves committed user
state; a failed build keeps the last working page. The UI appears in the current
chat as soon as it is created or built. Inspection is optional when the model
needs evidence about a specific issue; it does not delay presentation or require
opening a separate page. The model decides what to refine and reuses existing
findings instead of repeating unchanged checks.

The interactive teardown kit, guide and three machine source families ship with
Chrome ACP, including their original MIT license. A separate skill installation
is unnecessary. To deliberately use a custom upstream checkout, set
`SIADA_TEARDOWN_DIR` before starting the proxy; otherwise the bundled sources are used.
The `teardown-v8` starter supplies responsive controls for camera, cutaway,
isolation, RPM, crank angle and layered disassembly. The `teardown` workspace
supplies the kit, guide and example source modules for custom mechanisms.
Inspection needs an installed Chromium browser; set `SIADA_UI_CHROMIUM` if it
cannot be discovered.

For live simulations, `siadaUI.registerState({capture, restore})` captures the
latest small JSON state when sharing or sending an assistant action.
`siadaUI.onVisibility(callback)` allows rendering to pause offscreen. Save user
actions and checkpoints rather than sending each animation frame to the proxy.

Use **Display** (`显示`) in the top bar to adjust interface scale from 80% to
120% and the input box from one to six lines. Scale changes text, spacing and
embedded interactive pages together. The defaults are 90% and one line; long
messages scroll inside the input box. **Restore defaults** resets both choices.
Preferences survive closing and reopening the side panel. The web client also
supports these controls and stores its preferences separately.