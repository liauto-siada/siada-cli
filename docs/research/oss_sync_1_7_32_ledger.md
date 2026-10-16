# 1.7.32 open-source sync ledger

This ledger records the commit-by-commit port of the 1.7.32 mainline
changes into the open-source release branch (`open_source_1_7_32`).
Every entry lists the source commit, its destination on this branch, the
porting approach, and the offline validation evidence collected at the
time of porting. Private bundles, internal installers, and internal
hosts/aliases were never copied; public adaptations on this branch were
preserved throughout.

Porting conventions:

- `cherry-pick -x` — the change was entirely public-compatible.
- `focused port` — the change mixed public and private content; the
  public part was adapted manually and committed separately with the
  source hash referenced in the commit body.
- `skipped` — the change had no public equivalent or was bundle-only;
  the reason is recorded below.

## Batch 1 (previous sync stage)

| Source | Destination | Approach | Notes |
| --- | --- | --- | --- |
| ff5ed450 | 6baf1200 | port | baseline effective-context sync |
| 27093e04 | a962c2ad | already adapted | public launcher/provider adaptations and isolated SDK/main-session regressions; not repeated in this sync |
| 153c415d | fd914ffd | cherry-pick | |
| 5336ac43 | — | skipped | internal auth-only change |
| 64c0537f | a4b2ac6c | cherry-pick | lockfile hash corrected for public registry |
| b4fdc641 | 2c448a3e | cherry-pick | |
| 4f96b27c | 96e32fd0 | cherry-pick | |
| e5b3bb40 | 1b284d5d | cherry-pick | |
| b3e80d9b | 825e60b3 | cherry-pick | |

## Batch 2 (this sync stage)

| Source | Destination | Approach | Notes and evidence |
| --- | --- | --- | --- |
| ebfaa086 | 4277b3a1 | focused port | internal installers and BOS hostname changes excluded; public GitHub installer gained HTTP error surfacing and version pinning. browser_addon tests 60 passed |
| 5f67f459 | 3703b720 | cherry-pick | login/reconfigure/pending injection 24 passed; UI login-submission 3 passed |
| 0cec15af | 5912800b | focused port | logging-correlation source only; the generated private UI bundle/map was excluded. log context tests 31 passed, proxy logger 2, UI adapter/logger 12 |
| d5951200 | 47299fbc (deferred) | skipped then rebuilt | bundle-only commit; deferred to the final public source rebuild (bundle regenerated from public sources, executable bit retained, no map tracked) |
| cdab2ac8 | 47299fbc (deferred) | skipped then rebuilt | bundle-only commit; same final rebuild |
| 615c043c | d8d648e3 | cherry-pick | model wrapper retries 77 passed |
| c093399a | 6e82e233 | cherry-pick | disconnect + wrapper retry 90 passed |
| b3dd7331 | aaadaf7f | cherry-pick | runtime 11 passed |
| fef607f5 | 2d900799 | cherry-pick | theme/controller/help 79 passed |
| 520c718d | 26dada27 | focused port | chrome file-error isolation merged with the OSS turn-lifecycle and frame listeners; 42 passed |
| 5893afbe | 909f52f6 | cherry-pick | browser logging/environment 63 passed 2 skipped (offline env-gated); proxy logger 7; UI logger 16 |
| beb6b20c | e5215bcb | focused port | compaction threshold `max(0, context_window - 60_000)` kept the focused public tests instead of the source's large matrices; 259 passed, 2 pre-existing failures (see Gaps) |
| 566400e8 | 3547bb1c | focused port | public DeepSeek presets added, LiId/device login never introduced; 20 passed |
| 3f1336a0 | f3c85b25 | focused port | disconnect/blank-panel fix merged with OSS lifecycle; extension DOM 1, client 35 passed |
| baedf4cd | f34b651c | cherry-pick | 40 passed; UI detail 5 |
| 18814a58 | 1aaedeec | cherry-pick | 27 passed |
| ee8e7987 | — | skipped | internal build-script Bun discovery only; the public browser CI uses `oven-sh/setup-bun@v2`, no equivalent public shell build path exists |
| d5c83741 | a9342b69 | focused port | public CNY snapshot pricing; internal model-name alias import removed; sub-agent usage tests fixed for the public SDK (required `cache_write_tokens`) — 193 passed |
| 55be9971 | f4c7d35d | focused port | detailed token usage; public pricing expectations; 14 passed |
| f9748a43 | a0f1d095 | focused port | prompt queue + steering + image previews; README conflict resolved to keep the public install narrative (upstream quick-start block not carried); ACPClient kept the public turn-lifecycle `emitTurn` alongside the new requestId/steering API. shared 44 passed, proxy 6, extension DOM 2, python steering/context 58 |
| 1c6c97b8 | 26ba1802 | focused port | history replay hides generated page context and internal reminders; README feature bullet adapted (upstream bullets not carried) |
| — | b718abcd | follow-up fix | entrypoint test expects the new steering capability `_meta`; browser-prompt fixture attaches a minimal `RunningSession` stub (session-less contexts were already unsupported by the authoritative filter landed in ff5ed450). tests/acp_server 59 passed |
| 2f21d82e | 61ab35ea | focused port | login replies isolated per request; the public EOFError semantics for unmonitored stdin preserved. 36 passed; UI 20 passed |
| de960a8f | 25870092 | cherry-pick | bounded browser-skill learning retries; 12 passed |
| 42d87f07 | b6ffb944 | cherry-pick | Responses-stream EOF/exhaustion coverage; 82 passed |
| — | 47299fbc | rebuild | public UI bundle regenerated from synced sources (covers deferred d5951200/cdab2ac8 and the bundle half of 0cec15af). tsc clean, 302 vitest passed |
| 86f53689 | 98120166 | focused port | installer restart after addon install: the internal tarball/local/PowerShell installers have no public counterpart (public `scripts/install.sh` installs the wheel only, no `.ps1`/tarball/venv installer exists), and the public native setup path (`siada-browser setup` / `siada-cli --browser-setup`) already restarts the CLI-managed proxy after install through the same `manager.restart()` behind `--browser-restart`, mapping restart errors to exit 1 — no runtime change required, no substitute step fabricated; added `tests/services/browser_addon/test_browser_setup_restart.py` pinning install→restart ordering, restart-failure and failed-install semantics, and the shared `--browser-restart` dispatch. 5 passed; browser_addon dir 67 passed, 2 env-gated skips |

## Latest mainline audit (2026-10-16)

The mainline was rewritten after the previous sync. Its fetched tip at the
start of this audit is `bb2176f7789e37b6f5f88863c400c82d082b59e1`.
The common ancestor with the previously audited source is `27093e04`.
The initial 40 commits in `27093e04..bb2176f7` were audited by their changes,
rather than treating every new hash as a new feature. A final source check
also found `10a5eb7ef27ca7c32bc91f666aa4c7ccda0e4751`, extending the audited
range to 41 commits.

The main workspace subsequently added local commit
`1fd40f1abd30cbc025879c50b1ece89a231f86b4` while the fetched remote remained
at `10a5eb7e`. This extends the audited source range to 42 commits; the local
main workspace, rather than the remote alone, determines the requested tip.

Two further commits, `841f435b12828d622e7a493a6c55f4d58d69d22e` and
`e6659b9460983ef45f8d5f118a184197bf99f842`, subsequently arrived in both the
main workspace and fetched remote. The latest audited range contains all
44 commits in `27093e04..e6659b94`.

The table below records every rewritten source hash alongside its previous
source and destination. Existing ports were retained; new public changes were
committed individually in source order.

| Current source | Previous source | Destination | Disposition |
| --- | --- | --- | --- |
| e9c54573 | — | 5a7cf8a5 | focused port: runtime provider ownership and ordered shutdown; public routing and cancellation cleanup retained |
| 48fae88e | — | a7ce3276 | cherry-pick with public compatibility fixes: standalone SDK helpers, isolated endpoint overrides and durable learning retry budgets |
| 5d627f62 | — | 5a769791 | focused port: trustworthy legacy snapshot boundary recovery; resume and model switches preserve durable storage |
| 57aa8095 | — | — | excluded: private provider authentication retry |
| 202178fc | — | 62418a61 | focused port: explicit workspace selection, launch-directory default and absolute ACP backend forwarding |
| 1e383906 | 153c415d | fd914ffd | previously ported editor preservation |
| 921e5ca0 | 5336ac43 | — | previously excluded private authentication change |
| 2fd46dd5 | 64c0537f | a4b2ac6c | previously ported DOCX dependency compatibility |
| 11e6e111 | b4fdc641 | 2c448a3e | previously ported conversation forks |
| 5bc21cfc | 4f96b27c | 96e32fd0 | previously ported transport retry |
| 374918cb | e5b3bb40 | 1b284d5d | previously ported missing-final-response detection |
| fccd463d | b3e80d9b | 825e60b3 | previously ported pane state preservation |
| db0a66de | ebfaa086 | 4277b3a1 | previously adapted public installer |
| b0d69c4d | 5f67f459 | 3703b720 | previously ported API configuration deadlock fix |
| fd15e932 | 0cec15af | 5912800b / 47299fbc | previously ported logging and public bundle rebuild |
| 68f490af | d5951200 | 47299fbc | previously rebuilt public executable bundle |
| d23184d4 | cdab2ac8 | 47299fbc | previously rebuilt public logging bundle |
| 0d3c9f18 | 615c043c | d8d648e3 | previously ported transient stream retry |
| ccffb75b | c093399a | 6e82e233 | previously ported empty-start-event retry |
| 85a59f09 | b3dd7331 | aaadaf7f | previously ported model persistence |
| 9d12c661 | fef607f5 | 2d900799 | previously ported dark theme default |
| 606012d3 | 520c718d | 26dada27 | previously adapted browser file-error isolation |
| 26b9518d | 5893afbe | 909f52f6 | previously ported consolidated logging |
| a05b5b47 | beb6b20c | e5215bcb | previously adapted compaction threshold |
| 6a0a9fb7 | 566400e8 | 3547bb1c | previously adapted public DeepSeek presets |
| 8d53dbff | 3f1336a0 | f3c85b25 | previously adapted browser disconnect handling |
| 83b1e5cd | baedf4cd | f34b651c | previously ported sub-agent reasoning display |
| 4e2c2d82 | 18814a58 | 1aaedeec | previously ported sub-agent provider inheritance |
| 9c6d2634 | ee8e7987 | — | previously excluded private build script |
| 43c946c9 | d5c83741 | a9342b69 | previously adapted request usage logging |
| 9b21d638 | 55be9971 | f4c7d35d | previously adapted detailed token logging |
| 30a2484d | f9748a43 | a0f1d095 | previously adapted browser queue and steering |
| 08142a89 | 1c6c97b8 | 26ba1802 | previously adapted history context filtering |
| f8990ab9 | 2f21d82e | 61ab35ea | previously adapted login reply isolation |
| 35970711 | de960a8f | 25870092 | previously ported bounded browser learning retries |
| 7964c6da | 42d87f07 | b6ffb944 | previously ported stream EOF regressions |
| d8d52241 | 86f53689 | 98120166 | previously adapted restart after addon installation |
| a94f47dc | — | fe090a7f | focused port: CLI version 1.7.33; public dependency graph unchanged |
| fc95facc | — | — | excluded: private GitLab release trigger configuration |
| bb2176f7 | — | f2ab58b2 | focused port: browser versions 1.0.46; public proxy lock metadata aligned |
| 10a5eb7e | — | 7f418be8 | focused port: platform-appropriate file flush handles; existing Windows directory guard and POSIX error handling retained; Windows CRT emulation and POSIX read-only regression coverage |
| 1fd40f1a | — | c4ee6c0c | cherry-pick with public pricing fixture retained: resume sub-agent sessions after transient stream errors, preserve completed tools and independent retry budgets, and record incomplete request durations |
| 841f435b | — | 6893f886 | focused port: bounded HTTP 403 retries; public wiki remains sanitized and correctly records disabled native SDK retries; HTTP 401 and answer/tool replay boundaries retained |
| e6659b94 | — | fac02439 | cherry-pick preserving public task-local retry limits: reasoning streams remain live and retryable, failed completed reasoning items stay out of history, and restarted thinking displays close before new response IDs |

### Rewritten history reconciliation

The 32 rewritten entries were compared with their previous source patches on
tracked public paths, excluding generated bundles/maps, private trees and
installer scripts. The retained audit (`oss-latest-history-audit.log`) records
24 matching nonempty patches, five matching empty public scopes and three
reviewed differences. Empty scopes do not imply that private changes were
ported: their exclusions or public bundle rebuilds remain recorded above.

The three differences preserve existing public behavior:

- `374918cb` / `e5b3bb40`: final-response detection and iterator cleanup moved
  earlier in the rewritten history. The public Responses adapter retains
  typed terminal errors and request iterator cleanup; the SDK helper and
  transport suites exercise failed, incomplete, empty and cancelled streams.
- `4e2c2d82` / `18814a58`: strict unsupported-provider handling moved earlier.
  The public factory still rejects unsupported providers, and sub-agent
  inheritance retains its public fallback and isolated session fixtures.
- `35970711` / `de960a8f`: browser learning documentation/comments differ;
  the functional retry budget is unchanged. The helper port additionally
  prevents SDK retries from multiplying the durable learning queue budget.

### Latest validation and completion audit

The concrete deliverables are a complete source-to-destination mapping,
individual commits for new public changes, preserved pre-existing work, and
verification of the resulting working tree. The checks below refer to retained
test output, Git ancestry/content checks and built artifacts, not ledger status
alone.

| Requirement | Evidence |
| --- | --- |
| Audit the latest mainline | All 44 commits in `27093e04..e6659b94` appear once in the table; ten new public ports and two new private-only exclusions; all 32 rewritten entries reconciled |
| Port individually | Each of the ten destination commits contains its full source hash; all destinations are ancestors of this branch and follow source order |
| Retain public adaptations | Strict provider rejection, pinned endpoint overrides, cancellation cleanup and startup fix `0814f145` retained; public UI bundle subsequently rebuilt in the separately requested UI follow-up `d2a9111d` |
| Preserve existing diagnostics | After the final retry ports, nine tracked files and two untracked files match stash bytes; every diagnostic addition remains in two merged files; all 13 files remain uncommitted and backups `3fb57119`, `ca60af11` and `6df327c2` are retained |
| Verify provider/runtime/CLI compatibility | Earlier mainline contract selection: 929 passed, 147 skipped, one existing forkpty warning; includes all provider tests, workspace/launcher/SDK bootstrap, ACP runtime, cron, sub-agents, helper consumers, browser setup, diagnostics and Git/storage. Recovery follow-up: 360 passed for reviewed sub-agent/model-wrapper/diagnostic/business-verifier contracts |
| Verify session and storage behavior | Earlier strict network-blocked session baseline plus Git and platform flushing tests: 901 passed, three existing xfails (G01, G12, G14); includes simulated Windows writable-handle requirements and POSIX read-only files. Recovery follow-up session baseline and Windows storage: 335 passed, the same three expected failures |
| Verify UI and browser | UI follow-up: 30 files / 308 tests passed, TypeScript `--noEmit` and `build:all` passed; Chrome ACP unchanged: 118 extension + 165 shared/proxy + five web tests passed; all three browser packages built successfully |
| Verify release artifacts | CLI wheel 1.7.33 built with current storage code and CLI/ACP entrypoints; public UI bundle executable without a source map; browser manifests and proxy lock metadata 1.0.46; Node packaging two passed; `poetry check --lock` passed with existing manifest deprecation warnings |
| Verify scope and cleanliness | No unresolved/staged files, introduced conflict markers or private-provider imports; only the restored diagnostics and this ledger remain modified before the documentation commit; working and committed diffs pass whitespace checks |

The SDK migration's broader verification also required focused fixture follow-up
`b23e92e1`: assert native Responses `max_retries=0` and prevent repeated vendor
body captures after deliberately synthetic response parsing failures.

#### Sub-agent recovery follow-up

`c4ee6c0c` ports the full public scope of `1fd40f1a` as one commit. The accounting
fixture conflict preserves the existing public price expectation of CNY 0.0227;
SDK detail fields are checked as parsed JSON, including cached reads and explicit
zero cache writes, rather than relying on key order. No pricing or dependency
change was introduced.

The clean port passed 52 recovery/reasoning/accounting tests before restoring
diagnostics. After restoration, the reviewed sub-agent, model-wrapper, diagnostic
and business-verifier selection passed 360 tests with one existing forkpty
warning. The session baseline and Windows storage selection passed 335 tests
with three existing expected failures. These are focused follow-up selections,
not a claim that the previously failing full suite is green.

The new real-SDK matrix covers foreground and background runs, completed tools
executed once, timeout and missing-final-response recovery, preserved session
inputs, iterator cleanup and request accounting. Separate cases cover temporary
HTTP failures, cancellation during backoff, non-retryable errors, exhausted
continuations and reasoning-only budgets that do not reset during recovery.
Retained logs are `oss-subtask-recovery-clean.log`,
`oss-subtask-recovery-contracts.log` and `oss-subtask-recovery-baseline.log`.

The 1.7.33 wheel was rebuilt after this port. Its 514 Python files match the
verified working tree byte for byte, including restored diagnostic files, and
its UI bundle matches the committed bundle in `d2a9111d`. This artifact check
does not turn the uncommitted diagnostics into part of the port commit.

The separately requested UI commit `d2a9111d` removes Provider from compact,
expanded and exported banner lines while retaining Agent, Model and mode hints.
It includes six display regressions and the rebuilt public bundle.

#### HTTP 403 and reasoning-stream follow-up

`6893f886` ports `841f435b` independently, retaining the public provider wiki
without private-provider sections. HTTP 403 shares the model wrapper's existing
budget; HTTP 401 remains non-retryable, and the wrapper does not refresh
credentials. Its clean offline SDK, wrapper and sub-agent selection passed
119 tests (`oss-http403-clean.log`).

`fac02439` then ports `e6659b94`, retaining the public `_retry_limit()` and
`model_retry_scope()` interfaces. Reasoning events can remain visible during
retry while answer, tool and unknown events close the replay window. Failed
completed reasoning items are withheld from Runner history. The clean focused
selection passed 200 tests (`oss-reasoning-clean.log`), including real SDK
streaming and conversation thinking-display boundaries.

After restoring diagnostics, all provider tests plus the reviewed sub-agent,
model-stream, model-wrapper, diagnostic, thinking-display and business-verifier
tests passed: 896 passed, 145 skipped, one existing forkpty warning
(`oss-retry-latest-contracts.log`). The network-blocked session baseline,
sub-agent compaction simulation and Windows storage selection passed 349 tests
with three existing expected failures (`oss-retry-latest-baseline.log`).
These selections cover zero retry overrides, bounded mixed-status failures,
nested-wrapper budgets, cancellation and preservation of completed tool results.
The public retry wiki was also updated for the new reasoning boundary and the
64-event buffer's revised flush behavior.

The initial combined run put localhost integration tests under the session
baseline's strict network guard and failed. Its output is retained in
`oss-latest-final-offline.log`; it is not a passing result. The final checks run
the network-blocked session baseline separately from synthetic localhost
HTTP/child-process contracts. Retained final logs include
`oss-latest-final-contracts.log`, `oss-latest-windows-storage.log`,
`oss-latest-ui-tests-lts.log`, `oss-latest-ui-types-lts.log`,
`oss-latest-chrome-tests.log`, `oss-latest-chrome-build.log`,
`oss-latest-browser-packaging-lts.log`, `oss-latest-wheel-build.log`,
`oss-latest-poetry-check.log` and `oss-latest-artifact-audit.log`.

Repository checks can be rerun with the commands below, the repository
dependencies and a compatible Node 24 LTS runtime on `PATH`. The final contract
total above also includes restored, uncommitted diagnostic cases; it describes
the tested working tree rather than a clean checkout's case count.

```bash
poetry run python tests/run_session_baseline.py -- tests/services/test_session_storage_windows.py tests/services/test_git_service.py
env -u API_KEY -u BASE_URL -u SIADA_TEST_PROXY_ENTRY SIADA_CLI_LOG_DIR=/tmp/oss-final-contract-logs SIADA_REMOTE_MODEL_CONFIG=0 LITELLM_LOCAL_MODEL_COST_MAP=True poetry run python -m pytest tests/provider tests/entrypoint/test_workspace.py tests/entrypoint/test_env_assignments.py tests/entrypoint/test_public_startup.py tests/entrypoint/test_public_launcher_setup.py tests/entrypoint/test_sdk_bootstrap_gate.py tests/entrypoint/test_provider_runtime_lifecycle.py tests/acp_server/test_runtime.py tests/services/test_sub_agent_run_config.py tests/tools/agent/test_user_agent_end_to_end.py tests/agent_hub/proactive/test_cron_provider_lifecycle.py tests/services/test_one_shot_consumers.py tests/services/browser_skill/test_learning_retry_policy.py tests/services/browser_addon tests/services/test_model_wrapper_transport_retry.py tests/tools/agent/test_sub_agent_usage.py tests/tools/agent/test_subagent_async.py tests/services/test_session_storage_windows.py tests/services/test_git_service.py -q -m 'not integration'
npm --prefix siada_cli_ui test -- --run
npm --prefix siada_cli_ui run build -- --noEmit
(cd chrome-acp && bun run test && bun run build)
node --test chrome-acp/scripts/package-browser.test.mjs
poetry check --lock
poetry build -f wheel
git diff bfd6d60e..HEAD --check
git diff --check
```

Windows-specific behavior was validated through CRT emulation on Darwin; no
native Windows run is claimed. The three baseline xfails and the historical
full-suite limitations below remain visible; the full repository suite is not
claimed green.

## Previous validation evidence

- Offline session baseline (`tests/run_session_baseline.py`):
  837 passed, 3 xfailed (the three documented legacy gaps).
- Terminal UI: `tsc` build clean, esbuild bundle regenerated, 302 vitest
  tests passed. The final follow-up reran all 29 Vitest files (302 passed)
  and TypeScript with `--noEmit`, retaining both command outputs.
- Chrome ACP test manifest (extension cwd, shared+proxy, web-client):
  288 tests passed, 0 failed.
- Chrome ACP package builds (web-client, extension, proxy-server)
  completed successfully.
- Node packaging validation (`chrome-acp/scripts/package-browser.test.mjs`):
  2 passed, confirmed by a final Node LTS rerun.
- Public startup, launcher isolation, SDK bootstrap and provider contracts:
  119 passed with an ambient `SIADA_BROWSER_NODE` override. The launcher
  fixture now isolates the dedicated browser home as well as `Path.home()`.
  Provider routing documentation was checked against the shipped `default`
  implementation; unsupported provider rows and missing source links were removed.
- Full `tests/` sweep at `47299fbc`: 4073 passed, 62 failed, 151 skipped,
  3 xfailed. The pre-sync sweep reported 3813 passed, 74 failed, 149 skipped,
  3 xfailed. Comparing failure IDs gives 15 baseline-only failures and
  3 sync-only test-expectation mismatches. The latter were two provider-factory
  contract tests and one login-reply monitor fixture, corrected by `bc4815e1`;
  rerunning their two files gives 62 passed. The 15 resolved baseline failures
  comprise 14 sub-agent provider/model-override tests and one browser-prompt
  history test.
- After excluding those three corrected mismatches, the raw sweep has
  59 remaining pre-existing failure IDs. This is a reconciliation of the
  earlier sweep, not a new full-suite result. The additional launcher fixture
  correction in `c1e039d2` addresses five of those IDs and is covered by the
  119-pass startup/SDK/provider selection above. No full sweep has been rerun
  after these fixture corrections; the full suite is not claimed green.

Previous follow-up commands (run without model calls):

```bash
poetry run python -m pytest tests/entrypoint/test_public_startup.py tests/entrypoint/test_public_launcher_setup.py tests/entrypoint/test_sdk_bootstrap_gate.py tests/provider/test_chat_completions_providers.py -q
poetry run python -m pytest tests/provider/test_provider_factory.py tests/entrypoint/test_public_login_prompt.py -q
npm --prefix siada_cli_ui test -- --run
npm --prefix siada_cli_ui run build -- --noEmit
node --test chrome-acp/scripts/package-browser.test.mjs
poetry check --lock
git diff --check
```

The first selection also passed with an ambient `SIADA_BROWSER_NODE` override.
Validation used a compatible Node 24 LTS runtime and isolated test log directories.

## Gaps and known pre-existing issues

1. `tests/agent_hub/context_filter/test_litellm_token_counter.py` — two
   tests fail only when run after other files in the same process
   (test-order pollution). Each passes in isolation, before and after the
   sync. The same pattern also affects a handful of launcher/provider
   files that pass in isolation. Not introduced by this sync.
2. `tests/agent_hub/proactive/` (16), `tests/services/memory/` (13),
   `tests/tools/test_read_many_files_tool.py` (6),
   `tests/tools/memory/` (6), `tests/entrypoint/interaction/test_controller_background_subtask_await.py`
   (2), `tests/agent_hub/coder/test_code_gen_agent_at_command.py` (4),
   `tests/services/test_input_processor.py` (2) and a few single-file
   stragglers — all verified present at the pre-sync branch point; the
   visible causes are environment-specific test assumptions (macOS
   `/private/var` tmp-path resolution and similar), unrelated to the
   ported changes.
3. Offline browser logging E2E: the two `test_logging_e2e.py` tests skip
   without `SIADA_TEST_PROXY_ENTRY`; both were verified passing against
   the freshly built proxy entry (`packages/proxy-server/dist/cli/bin.js`)
   with the offline fake-agent fixture — 2 passed.
4. The internal `readline`-style raw key logging from the private tree
   was intentionally not ported; the public keyboard logging keeps its
   stronger sanitization (no raw keys, characters, previews, or
   per-keystroke content).
