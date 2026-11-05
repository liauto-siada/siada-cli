# Session test baseline

[简体中文](./zh-CN/SESSION_TEST_BASELINE_zh.md)

This is a pre-refactor **behavioral** baseline for the current session/context
pipeline. It combines real SDK Runner characterization with an explicit,
reviewed selection of existing offline regressions. It does not change
production code by itself, require model credentials, or claim full repository coverage.
The original snapshots below are historical; the latest implementation status is
recorded in **Default execution cutover acceptance**.

## Running the baseline

Use Python `>=3.12,<3.14` and the Poetry development environment:

```bash
export REPO_ROOT="$(git rev-parse --show-toplevel)"
poetry -C "$REPO_ROOT" install --with dev

# New characterization tests plus the reviewed regression selection.
poetry -C "$REPO_ROOT" run python "$REPO_ROOT/tests/run_session_baseline.py"

# New tests only; list the full selection without executing it.
poetry -C "$REPO_ROOT" run python "$REPO_ROOT/tests/run_session_baseline.py" --scope new
poetry -C "$REPO_ROOT" run python "$REPO_ROOT/tests/run_session_baseline.py" --list

# Forward additional options to pytest; keep reports outside the checkout.
poetry -C "$REPO_ROOT" run python "$REPO_ROOT/tests/run_session_baseline.py" \
  --junitxml=/tmp/siada-session-baseline.xml --durations=10

# Audit the exact failing assertions. A nonzero exit is EXPECTED while gaps remain.
poetry -C "$REPO_ROOT" run python "$REPO_ROOT/tests/run_session_baseline.py" --scope new --runxfail
```

The launcher derives absolute test paths from its own location, so it works from
any working directory. `--scope full` is the default; it means the complete
**session baseline selection**, not every repository test. The checked-in
selection lives in `tests/run_session_baseline.py`; unrelated tests are not
silently added as the repository grows.

Additional options are passed through to pytest. No `--` separator is required:
Poetry versions can interpret or remove that separator before launching Python.

Before importing project modules, the launcher creates a disposable `HOME` and
log/cache directories, disables remote model-config fetching, and uses LiteLLM's
bundled model-cost map (`LITELLM_LOCAL_MODEL_COST_MAP=True`). A pytest plugin
blocks socket connections during collection and execution and fails the run even
if application error handling swallows a blocked attempt. New fixtures also use
temporary session/checkpoint/offload files, synthetic model settings, fake model
responses, disabled tracing, and mocked Git/UI/memory boundaries. The guard is
Python-process enforcement, not an OS sandbox for arbitrary subprocesses.

### Simulating sub-agent compaction

The full selection includes `test_run_subtask_compaction_simulation.py`. It runs
the real subtask entrypoint, `SubTaskAgent`, streamed SDK Runner, tokenizer, and
header-summary strategy with synthetic tool outputs and scripted model-service
responses. Besides the two single-compaction cases, a 48-scenario matrix runs
24 serial or 12 parallel tool rounds across clean/fork histories, three payload
sizes, and successful/empty/unexpected-error/`CompactionError` first summaries. Every model request checks
the session baseline, complete latest tool groups, and no resurrection of
summarized input or tools. Additional probes cover exact token thresholds,
identical inputs in twelve new runs, cancellation during summary/model calls,
late model failure and retry after multiple compactions, max-turn exhaustion,
and keep-budget/end-of-history boundaries for both function and native patch
items. Two simultaneously compacting subtasks also check independent sessions,
overlapping summary calls, and unchanged shared parent context. Debug dumps and
parent-context isolation are checked in the entrypoint simulations.

An entire latest tool group can itself exceed the keep budget. The oversized
probes verify intact fallback history, not a guarantee that the next request
fits the provider window; bounding/offloading those outputs remains necessary.
No live model's summary quality is evaluated. Run the full simulation module
and display its reports:

```bash
poetry -C "$REPO_ROOT" run python "$REPO_ROOT/tests/run_session_baseline.py" \
  -k test_run_subtask_compaction_simulation -s
```

On 2026-10-13, five complete repetitions each passed all 88 simulation cases.
Their long-chain matrix covered 240 scenarios, 4,560 model calls, 7,200 tool
calls, and 3,375 successful compactions (5–24 per scenario). These are repeated
deterministic schedules, not randomized provider testing. The combined offline
selection, including additional subtask fork/display/guard regressions, passed
883 cases with 3 existing legacy xfails and no unexpected network attempts.

### Shared compaction changes in the main flow

`test_shared_compaction_main_flow.py` exercises the real tokenizer and strategies
through temporary prepared main sessions, with only model-service responses and
external UI/memory boundaries replaced. Its 204 cases cover automatic/manual
compaction, both SDK modes, serial/parallel tools, function/native patch items,
chat/native provider payloads, keep-budget trimming, failure recovery, and the
IM turn-prune strategy. Requests are checked against committed effective context;
discarded tools must not return, and complete history remains unchanged by
compaction. Assistant-leading kept tails are tested explicitly, not inferred
from normal user-leading histories.

The shared repair helper still requires user-start by default. Only header-summary
kept-tail trimming opts out: assembly supplies the user summary before that tail.
IM summary-input pruning retains its original default contract. A differential
probe against the original public Git helpers checked 36 cases: 32 results were
unchanged, and four fitting assistant-leading tail cases changed from a trimming
error to retaining the complete latest tool group. These are intended fixes.

On 2026-10-13, all 204 main-flow cases passed (35.27s). The combined guarded
selection, including additional subtask fork/display/guard regressions, passed
1,087 cases with exactly the 3 existing legacy G01/G12/G14 xfails (60.76s),
with no unexpected network attempts. This is the reviewed selection, not the
entire repository test suite.

Oversized latest groups are not a solved overflow guarantee: a user-leading tail
may lose every tool group, while an assistant-leading tail can become empty and
fail compaction. Entry points preserve the original context on failure, which can
still exceed the provider window. These deterministic offline tests do not assess
live summary quality or guarantee behavior for every provider item ordering.

```bash
poetry -C "$REPO_ROOT" run python "$REPO_ROOT/tests/run_session_baseline.py" \
  --scope new -k test_shared_compaction_main_flow
```

### Validated snapshot

Validated on 2026-10-12 against parent revision
`4cb28f42ae7556354126f3f1fc1396152e871b84` with these uncommitted test/documentation
additions, using Python 3.12.2, pytest 8.4.2, pytest-asyncio 1.3.0,
openai-agents 0.22.3, openai 3.0.0, pydantic 2.13.5, and filelock 3.20.3.

| Selection | Result | Pytest elapsed time | Exit code |
| --- | --- | --- | --- |
| `--scope new` | 74 passed, 19 xfailed | 1.42s | 0 |
| Default full selection | 531 passed, 19 xfailed | 2.81s | 0 |
| `--scope new --runxfail` | 74 passed, 19 failed | 1.39s | 1 (expected) |

The selection contains one new directory and 34 reviewed existing test files
(457 existing cases). Normal runs made no unexpected guarded connection attempts.
An independent fault-injection audit confirmed that swallowed attempts during
collection and within a strict-xfail fixture still force exit 1; it also checked
import-time home/log paths and temporary-HOME cleanup. Reports remain outside the
checkout; record a fresh snapshot after changing source or dependencies.

### Storage foundation implementation milestone

The first implementation milestone adds explicit full-history and versioned
context APIs to FileSession, compare-and-swap replacement, conservative explicit
legacy migration, a shared ownership/storage lock, and recoverable multi-file
transactions. It does **not** activate the new default model reader: `get_items()`
and the existing request pipeline still use their legacy contracts. Legacy writes
invalidate prepared context instead of silently leaving a stale runtime snapshot.
History-only initialization requires explicit approval; invalid legacy snapshot
boundaries and damaged versioned files are errors, not history fallbacks.

`test_versioned_storage.py` adds 30 offline cases covering preparation, empty and
summary-only migration, pending delta, identity/boundary errors, immutable
replacement, version conflicts, routing preservation, failed writes, interrupted
transaction recovery (including real child-process exit), and invalid journals.
A persistent real-telemetry-hook test verifies full historical tool content,
injection selection, original counts, and no new-message event on replacement.
It does not test the full compression flow or real external reporting.

G11, G15, G16, and G17 now pass their desired assertions and are no longer xfailed.
At this milestone, **15 strict xfail cases remained**; the latest inventory is below.
The concurrent-append harness now observes contention outside lock acquisition,
rather than intentionally deadlocking two reads inside the new shared lock.

Transactions currently retain full-file undo data for legacy multi-file mutations;
runtime-only replacements journal only the context file. This adds local I/O and
has not been performance-benchmarked. At that milestone, the default-reader
cutover, identity-aware SDK admission, complete state/resume/checkpoint migration,
and removal of message mirrors remained future implementation phases, not
completed features.

Validated on 2026-10-12 in the same Poetry/dependency environment as the original
snapshot, with the implementation changes uncommitted:

| Selection | Result | Pytest elapsed time | Exit code |
| --- | --- | --- | --- |
| `--scope new` | 108 passed, 15 xfailed | 2.70s | 0 |
| Default full selection | 565 passed, 15 xfailed | 4.78s | 0 |
| `--scope new --runxfail` | 108 passed, 15 failed | 2.79s | 1 (expected) |

These results include all 457 originally reviewed existing cases and 123 cases
in the new directory. Reports remain outside the checkout.
The audit failures match the exact 15 strict-xfail nodes, with no fixture errors.

### Explicit request bridge and prepared consumers

The next incremental phase provides `EffectiveContextSession` for explicitly
prepared runs. It admits SDK input/results and post-filter hook additions into
versioned context and full native history, using durable message identities.
Compaction cannot resurrect discarded context through repeated SDK saves. UI/ACP
replay and existing telemetry explicitly read full history; context replacement
does not emit a new-message event.

Prepared verifier, memory, side-question, and resume paths use versioned context,
including empty and summary-only views, without a history fallback on corruption
or invalidation. Resume validates storage identity before mutating the live
session and bypasses obsolete snapshot tracking. Legacy state-only resume remains
compatible. Checkpoint capture waits for SDK tool-result persistence and captures
both durable views under one lock, rather than reading the message-state mirror
in `on_tool_end`. Parallel captures have distinct filenames.

Prepared checkpoint restore preserves admission receipts, advances a live restore
generation, and rejects late saves from an older SDK run without blocking normal
compaction. Project rollback snapshots compensate ordinary partial Git failures
and storage commit/flush failures; compensation failures are surfaced explicitly.
This is **not crash-atomic across Git and session storage**. Parallel tool captures
observe a completed SDK batch, not an isolated per-tool project state.

**At this earlier milestone, default activation remained disabled.** Mutable
workspace-cache consumers still needed coordinated session identity, including goal hooks, slash commands,
conversation interrupts, background-notice drainage, telemetry context lookup,
and readonly side-question forks. Complete todo/goal/counter/notification/usage
state recovery, crash recovery across Git/storage, and removal of legacy mirrors
remained unfinished. The 15 strict xfails described the legacy pipeline; the
explicit prepared-path tests did not justify silently removing those markers.

Validated on 2026-10-12 in the same Poetry environment, without live model calls
or unexpected guarded connection attempts:

| Selection | Result | Pytest elapsed time | Exit code |
| --- | --- | --- | --- |
| Default full selection (final rerun) | 653 passed, 15 xfailed | 6.50s | 0 |
| Focused effective/prepared tests | 78 passed, 132 deselected, 1 xfailed | 2.19s | 0 |
| Additional verifier/side-question/memory tests | 40 passed, 211 deselected | 0.47s | 0 |
| ControllerUI tests | 22 passed, 211 deselected | 0.73s | 0 |
| `--scope new --runxfail` | 196 passed, 15 failed | 4.91s | 1 (expected) |

At that milestone, the new directory contained 211 cases. The additional selection covered
`tests/services/goal/test_verifier.py`, `tests/services/test_btw_deny_guardrail.py`,
and `test_snapshot_view.py` / `test_updater.py` under
`tests/services/memory/memory_update/`; it is separate from the default baseline.
All six intermediate legacy state-only resume failures were fixed, without adding
xfail markers or weakening the prepared validation assertions.

The final report audit matches all 15 ordinary assertion failures to the exact
legacy strict-xfail nodes, with no fixture errors. All 41 changed/new Python files
parse and compile; tracked and new-file whitespace, terminal newlines, bilingual
links and gap inventories were checked. Dependency manifests/lockfiles are unchanged.
This validated the explicit prepared-path milestone, not the then-unfinished default cutover.

### Default execution cutover acceptance

The default streaming and nonstreaming `SiadaAgent` execution boundaries now
install `EffectiveContextSession`. Prepared `get_items()` reads the singular
`api_message.json`; SDK input, replies, tool results, and post-filter additions
are admitted transactionally with full native UI/telemetry history. Each request
uses authoritative context, including empty and summary-only views; compaction
does not resurrect discarded messages or rewrite display history. Custom
RunConfig settings are retained, but custom session-input callbacks/read settings
are rejected because the bridge owns that admission boundary.

New empty sessions are prepared automatically. Existing history-only sessions
still require explicit `migrate_legacy_context(allow_history_only=True)` approval;
a valid legacy snapshot can be migrated conservatively. Corrupt or unalignable
data is an error, not permission to rebuild runtime input from UI history.
Prepared writers reject obsolete snapshot/tracking writes; legacy files are not
deleted merely by migration.

Mutable context caches and lookups are session-owned. Versioned
`runtime_state.json` persists todos, reminder counters, pending/delivered notices,
request receipts, and actual response usage separately from token budgets. Goal,
ownership, and sub-agent indexes keep their existing storage responsibilities.
Resume supports legal empty state, restores title/workspace, and does not replay
delivered work. Checkpoints capture durable tool-result batches and structured
state, preserve actual usage/delivery receipts across rollback, and fence older
in-flight runs. Temporary real-Git tests prove journaled compensation after
abrupt worker exits before, during, and after project restore and before commit;
failed compensation retains its journal for retry. This is recoverable
compensation, not simultaneous visibility across Git and session files, nor a
power-loss test. Parallel tools still share a completed batch boundary.

Validated on 2026-10-12 against the same parent revision and Poetry/dependency
environment, with uncommitted implementation changes:

| Selection | Result | Pytest elapsed time | Exit code |
| --- | --- | --- | --- |
| `--scope new` | 244 passed, 3 xfailed | 9.30s | 0 |
| Default full selection | 701 passed, 3 xfailed | 11.19s | 0 |
| Final post-audit full rerun | 701 passed, 3 xfailed | 10.39s | 0 |
| Expanded consumers (20 additional modules) | 305 passed, 247 deselected | 5.79s | 0 |
| Real user-agent Runner / MCP stdio | 7 passed, 247 deselected | 1.30s | 0 |
| `--scope new --runxfail` | 244 passed, 3 failed | 9.43s | 1 (expected) |

The new directory contains 247 cases; the default regression inventory remains
34 files / 457 cases. The exact three audit failures match G01/G12/G14's desired
assertions, with no fixture errors or unexpected guarded connection attempts in
any selection. No guard was relaxed and no new xfail was added. Expanded
regressions updated obsolete Git PATH/lazy-initialization assertions and concrete
session-ID/Goal fixtures. Snapshot tests mock unrelated Lark daemon discovery,
not the Git snapshot behavior. User-agent tests use real Runner, synthetic
responses, and a temporary local MCP stdio process, without live services.

The post-audit rerun used the default launcher with
`--junitxml=/tmp/siada-cutover-post-audit-full.xml`, after terminal-newline fixes
only. All 68 changed/new Python files parse and compile without emitted artifacts.
Final tracked/new-file whitespace, document paths/links/anchors, shell syntax,
bilingual gap inventories, and exact expanded-module commands were checked.
Two tracked files retain their pre-existing missing terminal newline, confirmed
against the parent revision; all new files have terminal newlines. Dependency
manifests/lockfiles and the TypeScript UI remain unchanged.

Reproduce the separate expanded selection through the same guarded launcher:

```bash
poetry -C "$REPO_ROOT" run python "$REPO_ROOT/tests/run_session_baseline.py" --scope new \
  "$REPO_ROOT/tests/agent_hub/coder/test_glm_git_snapshot_lifecycle.py" \
  "$REPO_ROOT/tests/config/test_goal_config.py" \
  "$REPO_ROOT/tests/entrypoint/interaction/test_controller_goal_verifier.py" \
  "$REPO_ROOT/tests/entrypoint/interaction/test_controller_ui.py" \
  "$REPO_ROOT/tests/entrypoint/interaction/test_conversation_turn_notification.py" \
  "$REPO_ROOT/tests/entrypoint/interaction/test_turn_policy.py" \
  "$REPO_ROOT/tests/services/goal/test_turn_hooks_notification.py" \
  "$REPO_ROOT/tests/services/goal/test_verifier.py" \
  "$REPO_ROOT/tests/services/memory/memory_update/test_snapshot_view.py" \
  "$REPO_ROOT/tests/services/memory/memory_update/test_updater.py" \
  "$REPO_ROOT/tests/services/test_btw_deny_guardrail.py" \
  "$REPO_ROOT/tests/services/test_git_service.py" \
  "$REPO_ROOT/tests/services/test_git_snapshot.py" \
  "$REPO_ROOT/tests/services/test_model_wrapper_native_patch_normalization.py" \
  "$REPO_ROOT/tests/services/test_siada_runner_goal_reminder.py" \
  "$REPO_ROOT/tests/support/test_cmd_goal.py" \
  "$REPO_ROOT/tests/tools/agent/test_run_subtask_display.py" \
  "$REPO_ROOT/tests/tools/agent/test_run_subtask_fork_async.py" \
  "$REPO_ROOT/tests/tools/agent/test_run_subtask_user_agent.py" \
  "$REPO_ROOT/tests/tools/agent/test_subagent_guard.py" \
  -k 'not baseline' --junitxml=/tmp/siada-cutover-verified-extra.xml

poetry -C "$REPO_ROOT" run python "$REPO_ROOT/tests/run_session_baseline.py" --scope new \
  "$REPO_ROOT/tests/tools/agent/test_user_agent_end_to_end.py" \
  -k test_user_agent_end_to_end --junitxml=/tmp/siada-cutover-verified-user-e2e.xml
```

**Acceptance scope:** the default execution cutover passes the reviewed offline
selection; this does not complete every design requirement. `session_file`,
`from_file(api_history.json)`, session discovery/display loading, and legacy
message classes remain compatibility surfaces. Direct unprepared Runner/snapshot
paths retain the three documented legacy gaps; prepared/default equivalents pass.
Physical API/mirror removal and the design's single combined all-state lifecycle
scenario remain follow-up work. Full repository tests, interactive launch, live
models/services, production recovery, performance/power-loss testing, and
TypeScript UI builds were not run. No TypeScript source or dependency manifest/
lockfile was changed.

## Context and memory source diagnostics

INFO logs distinguish execution mode from the source of runtime or review input.
Search the normal CLI log (or the corresponding daemon log):

```bash
LOG_FILE="${SIADA_CLI_LOG_DIR:-$HOME/.siada-cli/logs}/siada_cli.log"
grep -E '\[effective-context\]|\[memory-source\]' "$LOG_FILE"
```

| Marker / fields | Meaning |
| --- | --- |
| `[effective-context][run] mode=prepared bridge=enabled` | The new per-run bridge is configured; `filter=default` or `custom` describes its input filter. |
| `[effective-context][run] mode=passthrough bridge=disabled` | Non-FileSession storage keeps its existing configuration; this is not necessarily the legacy filter. |
| `[effective-context][filter] mode=legacy` | The old `context_capture_filter` pipeline is executing. |
| `[effective-context][read] mode=prepared source=api_message.json` | A successful versioned-context read, including `version` and `items`; empty context remains valid. |
| `[effective-context][read] mode=legacy` | A legacy read from `api_history.json`, `api_messages.json`, or `api_messages.json+delta`. |
| `[effective-context][request] stage=filter_committed` | The bridge committed filtered input, with admission ID, request index, versions, and message counts. This is not post-filter hook admission or model-response success. |
| `[memory-source][read] source=runtime_items` | Memory read FileSession runtime items; correlate the session ID with `[effective-context][read]` for the actual storage source. Adapters report `in_memory_snapshot`, `effective_adapter`, or `items_adapter`. |
| `[memory-source][export]` | Correlates session ID with the exported Markdown filename and records message count and length truncation. |
| `[memory-source][review] trigger=pre_compaction source=in_memory_snapshot` | Review uses a detached snapshot before this compaction; it can already contain summaries from earlier compactions. |
| `[memory-source][analyze]` / `[memory-source][review] trigger=periodic source=session_markdown` | The analysis pipeline and subsequent review read the same exported Markdown, identified by filename; they do not re-read live JSON or infer how that file was originally exported. |

Review logs use `status=starting` before invocation, or `status=skipped` with a
reason when no text messages remain. Existing result logs still describe stage
completion; a start log does not guarantee successful extraction or memory writes.
These diagnostics do not add transcript bodies, tool output, or absolute workspace
paths. Prepared read failures still propagate without falling back to full history.

## Coverage matrix

| Area | New characterization | Reviewed regression coverage |
| --- | --- | --- |
| Main Runner | First and subsequent turns, streaming/nonstreaming, tool calls/results, cumulative versus last-response usage, no duplicate input/reply | Runtime stream-event translation and native tool presentation |
| History and context | Pre-request snapshot timing, effective snapshot plus unsent tail, in-loop compaction without losing full display history, snapshot-write failure | Compaction strategies, native patch/tool pairing, parallel call boundaries, goal reinjection, offloaded oversized outputs |
| Resume | Real `FileSession` swap, retained-anchor compacted input, todo ordering/all fields, goal status/all fields/audit history | Resume tracking fixes and frontend goal/sub-agent state pushes |
| Reminders and notifications | Durable todo reminder without duplication, queued user input, post-filter ephemeral notices, failure/retry behavior | Todo/repeated-tool thresholds, multimodal queued-input guards |
| Checkpoints | Actual JSON capture, tool result/usage at hook time, legacy optional fields, successful restore and compensating rollback for Git/snapshot failures | Existing session-management persistence regressions |
| Parent/child tasks | Recursive unfinished-task tree, finished logs/results, one-time pending-state consumption, completion/failure routing and wakeup isolation | Background registry cancellation/shutdown, persistence, recursion, sub-agent real-Runner compaction |
| Session state | Metadata/source/ownership retention, message/run identity and terminal states, detailed usage serialization, cache dimensions, per-run skill state | Display/classification, telemetry roles, reasoning settings across model switches |
| Storage boundaries | Single-instance concurrent append, atomic replace failure, callback failure, injection/native identity, missing/malformed snapshots | Existing file/session synchronization tests |
| Baseline launcher | Selection validation, sandbox/environment cleanup on success/failure, swallowed-network failure gate | No additional framework or dependency |

The legacy characterization harness uses production `context_capture_filter`, `ContextTrackProcessor`,
`FileSession`, and `agents.Runner.run`/`run_streamed`. Recovery and checkpoint
tests use the real service implementations. Token accounting and compaction
output in the main harness are deterministic stubs; actual compaction strategy
behavior is covered separately by the reviewed regressions. Interactive startup,
live providers, production Git restoration, memory scheduling, and the React terminal
UI are outside this selection.

## Current behavior versus desired invariants

Passing tests include deliberate characterization of legacy behavior:

- `api_messages.json` is saved before the model reply; it is not a complete UI
  history. Effective messages combine the snapshot with the subsequent native
  history delta.
- Session usage tracks the latest response, whereas SDK run usage accumulates
  all requests in that run.
- Message telemetry retains the full UI-history source, not the compacted
  effective context or display-stripped text. Preserve its current formatter,
  role mapping, injection-item selection, and history-count semantics.
- Post-filter `hook_pending_contexts` notices currently reach one request but are
  not durable. This is observed behavior, not a guarantee that a refactor must
  preserve message loss.
- Model-side `CancelledError` in the pinned SDK streaming path ends as an empty,
  complete result; caller cancellation is separately tested to propagate and
  close the model coroutine in both APIs.

Known gaps assert the desired behavior with
`pytest.mark.xfail(strict=True, raises=AssertionError)`. Unexpected exception
types still fail normally; a repaired gap becomes a failing `XPASS(strict)` until
the marker is removed. Do not convert regressions into xfails or treat the
absence of a new xfail as proof of feature completeness.

The bullets above characterize the legacy harness, not the prepared/default
execution contract. Its default-cutover regressions are recorded separately.

### Executable known-gap inventory

| ID | Current gap / desired invariant |
| --- | --- |
| G01 (legacy only) | Direct unprepared Runner loses post-filter notices on failure; prepared/default retry tests pass. |
| G02 (fixed) | Same-workspace/same-agent sessions do not share mutable cached context. |
| G03 (fixed) | Missing todo history and an explicit empty list clear stale recovered/context todos. |
| G04 (fixed) | All-completed todos stay cleared after resume. |
| G05 (fixed) | Goalless resume clears the cached goal. |
| G06 (fixed) | Resume recovers actual usage details separately from request token budget. |
| G07 (fixed) | Reminder counters have structured persisted recovery state. |
| G08 (fixed) | Repeated resume does not duplicate the unfinished-task notice. |
| G09 (fixed) | Persisted titles restore into `SessionState`. |
| G10 (fixed) | Cross-workspace resume rebinds workspace and storage. |
| G11 (fixed) | `limit=0` returns no items; negative limits are rejected. |
| G12 (legacy only) | Unprepared empty legacy snapshot falls back to history; prepared/default empty context stays empty. |
| G13 (fixed) | Clearing history clears effective context and stale counts. |
| G14 (legacy only) | Unprepared summary-only snapshot cannot align on resume; prepared/default summary-only resume passes. |
| G15 (fixed) | Failed metadata writes roll back history and signature. |
| G16 (fixed) | Shared locking and metadata merge retain ownership on interleaved writes. |
| G17 (fixed) | Separate `FileSession` instances serialize append transactions. |
| G18 (fixed) | Checkpoints capture structured todo/goal/counter/notification state. |

The original inventory has 18 gap categories and 19 expected-failure cases because
G03 has two variants. Fifteen categories are fixed; three strict expected-failure
cases remain only in the direct legacy harness (G01/G12/G14).
G16/G17 use controlled interleavings rather than probabilistic races;
when locking changes, update those harnesses to exercise the new transaction
boundary rather than inducing a deadlock inside it.

## Recording and evolving the baseline

Record the source revision, dependency versions, exact command, pass/xfail counts,
and elapsed time alongside the JUnit result when comparing a refactor. Timings
are observational, not a latency performance gate; token counts are not billing
accuracy measurements. No coverage percentage is claimed without measuring it.

After each change:

1. Run the new tests, then the full session selection in a fresh process.
2. Inspect every failure against this inventory. Fix new failures; remove xfail
   markers only when the corresponding desired invariant really passes.
3. Update contradictory legacy characterization when intentionally fixing a gap.
4. Add compatibility cases for changed message formats, new state fields, and
   old/malformed persisted data; keep the English and Chinese inventory aligned.
5. Preserve a sanitized report outside the checkout. Do not commit user sessions,
   credentials, logs, or machine-specific paths as fixtures.
