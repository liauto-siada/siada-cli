# Offline session regression tests

Run the session and context regression selection from the checkout's Poetry
environment:

```bash
export REPO_ROOT="$(git rev-parse --show-toplevel)"
poetry -C "$REPO_ROOT" run python "$REPO_ROOT/tests/run_session_baseline.py"
```

Use `--scope new` for the storage and request-boundary tests alone, or `--list`
to inspect the selected paths. The runner uses a disposable user environment
and in-memory model responses. Any unexpected network connection fails the run.

The selection covers versioned storage, legacy migration, recovery, checkpoints,
queued input, reminders, compaction, and streamed and non-streamed model request
admission. An active effective-context bridge persists hook additions before
calling the model and clears only committed queues. Legacy runs retain end-hook
reminder persistence.

Three strict expected failures document behavior of legacy paths: notification
loss after a failed request, an empty legacy snapshot falling back to history,
and summary-only legacy resume restoring history. Prepared-context tests cover
the corresponding supported behavior separately. Expected failures are gaps,
not successful validation of those legacy cases.

## Subtask and shared compaction coverage

The runner sets `LITELLM_LOCAL_MODEL_COST_MAP=True` before importing LiteLLM
so tokenizer-based regressions use its bundled cost map offline. Subtask tests
exercise both SDK execution loops with synthetic model responses: input
admission survives context replacement and retries, repeated fork messages and
identical inputs in separate runs remain distinct, and failed compaction leaves
the effective context intact.

Shared strategy tests cover parallel function and native apply-patch groups,
end-of-history boundary repair, trimming assistant-led kept tails, and durable
replacement through the main-session bridge. Complete contexts still require
a user start; kept tails receive their header from the compaction assembler.

Compaction cannot guarantee that an oversized newest tool group fits the
budget. If trimming leaves no recent context, compaction fails and the subtask
filter retains the previous context. These tests use synthetic data and mocked
summary responses; they do not validate live provider behavior.