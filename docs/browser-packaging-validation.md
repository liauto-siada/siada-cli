# Browser packaging validation

This report covers the current local working tree. No tag, push, GitHub Release,
or PyPI publication was performed. Existing unrelated working-tree changes are
also present in the locally built Python distributions; these are validation
artifacts, not a frozen public release candidate.

## Completed checks

- Python browser installer and launcher selection: 95 passed.
  Command: `poetry run python -m pytest tests/services/browser_addon tests/entrypoint/test_public_launcher_setup.py -q`.
  User state was isolated with a temporary HOME and synthetic API configuration.
- Browser component tests: 251 passed (115 extension, 131 shared/proxy, 5 web).
  Command: `bun run test` from `chrome-acp`.
- Browser component build: `bun run build` passed.
- Manifest validation: 1 passed.
  Command: `node --test chrome-acp/scripts/package-browser.test.mjs`.
- macOS ARM64 package: built with Node 24.13.0 downloaded from nodejs.org and
  verified against official SHASUMS256; production npm dependencies installed
  from the committed lock; staged proxy `--help` passed.
- Latest Python wheel installed non-editably in an isolated venv. Loaded
  installer path was verified to be inside that venv's site-packages. The real
  browser ZIP installed successfully and passed Node version and proxy CLI
  checks; extension files were present.
- Workflow YAML parsed locally; `git diff --check` passed.

The real-package installation check replaced transport with local artifact
reads and mocked service lifecycle operations. It did not start the service or
open Chrome. The Poetry environment metadata reported 1.7.29, so the real
installation check used the freshly built 1.7.32 wheel instead.

## Local validation artifacts

| Artifact | SHA-256 |
| --- | --- |
| Browser macOS ARM64 ZIP | `162b20e29726b803b369ad50abcd517f710a81e0f615825958d5e177c58370fd` |
| Python wheel | `175c3d25c7bea1806560a877db5414aa3f672e482c189bc860107d5fb737ab58` |
| Python sdist | `cf47273c6adfbe2bdca5824a07139d9822b7c06674ac369b2648404def0f320e` |

## Remaining verification

- Run the root browser workflow on the frozen release tag with publish=false.
- Confirm all configured runners and platform packages pass.
- Verify download from the intended HTTPS release directory.
- Verify proxy startup and manual Chrome extension loading/connection.
- Review the frozen release tree and rebuild Python distributions before public
  publication; the local tree currently includes unrelated user changes.
- Publish browser assets and manifest only after platform acceptance.

Configured platforms are macOS ARM64/x64, Linux ARM64/x64 and Windows x64.
Only the macOS ARM64 package has been built and checked locally in this session.

## Local end-to-end acceptance

A subsequent local acceptance completed 11 checks using the wheel and browser
ZIP hashes listed above:

1. Real HTTPS artifact download with a temporary trusted local certificate.
2. Manifest selection and ZIP SHA-256 verification.
3. Non-editable wheel installer in a fresh venv.
4. Real packaged proxy startup with the packaged Node runtime.
5. Actual extension background executor connection in isolated headless Chromium.
6. ACP initialize, session creation, prompt, streamed reply and completion.
7. MCP browser_tabs executed by the actual extension.
8. MCP browser_read returned content from a synthetic browser page.
9. Proxy restart.
10. Reinstallation while running preserved the connection token and restored service.
11. Proxy stop.

The reusable manual harness is
`tests/services/browser_addon/manual_release_e2e.py`. It accepts `--wheel`,
`--artifacts`, `--output`, and `--chromium`. It runs a local HTTPS artifact
server and an isolated browser; all processes are cleaned up on completion.
The ACP agent is a synthetic offline peer. This verifies the packaging,
transport and browser tools without a model API call.

This supersedes the previous limitation on local service startup and automated
extension connection. Public GitHub hosting, other platforms, the real model
turn, and manual installation in the user's regular Chrome profile remain
unverified. Automated extension loading used the existing test Chromium binary,
explicitly selected because the installed Playwright version's default browser
cache was unavailable.