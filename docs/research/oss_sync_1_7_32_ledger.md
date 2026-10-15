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

## Final validation evidence

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

Final follow-up commands (run without model calls):

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
