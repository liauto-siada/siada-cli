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
| a962c2ad | 27093e04 | adapted | public pricing/SDK adaptations |
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
  tests passed.
- Chrome ACP test manifest (extension cwd, shared+proxy, web-client):
  288 tests passed, 0 failed.
- Chrome ACP package builds (web-client, extension, proxy-server)
  completed successfully.
- Node packaging validation (`chrome-acp/scripts/package-browser.test.mjs`):
  2 passed.
- Full `tests/` sweep: 4073 passed / 59 failing at the synced HEAD versus
  3813 passed / 74 failing at the pre-sync branch point. Every failing
  test id at the synced HEAD also fails at the pre-sync point, and twelve
  pre-sync failures now pass (the sub-agent provider-resolution group and
  the browser-prompt fixture). No failure was introduced by the sync.

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
