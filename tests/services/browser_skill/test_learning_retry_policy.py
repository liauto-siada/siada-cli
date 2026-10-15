"""Learning retry limits across model calls, persistence and worker polling."""

import asyncio
import logging
import sqlite3
from types import SimpleNamespace

import pytest

from siada.services.browser_skill import distiller, llm_utils, pipeline, playbook
from siada.services.browser_skill.learning_errors import is_authentication_error
from siada.services.browser_skill.llm_utils import call_fast_llm
from siada.services.browser_skill.models import ExecutionRecord, VerificationResult


def record(execution_id="retry-run"):
    return ExecutionRecord(
        execution_id=execution_id, capacity_id="example.com::search", domain="example.com",
        goal="Search rows", events=[{"event_id": "e1", "response": "Rows loaded"}],
        verification=VerificationResult("unknown", ""), source="agent",
    )


def row(store):
    with store._connect() as connection:
        return dict(connection.execute(
            "SELECT * FROM executions WHERE execution_id='retry-run'"
        ).fetchone())


@pytest.fixture
def store(tmp_path):
    return playbook.PlaybookStore(tmp_path / "playbooks.sqlite3")


@pytest.mark.parametrize("agent_name", ["browser_skill_reflector", "browser_skill_curator"])
@pytest.mark.parametrize("status", [401, 403])
def test_auth_failure_pauses_without_nested_or_queue_retries(store, monkeypatch, agent_name, status):
    from siada.provider import fast_llm

    calls = []

    async def completion(prompt, **kwargs):
        calls.append(kwargs)
        error = RuntimeError("Rejected")
        error.status_code = status
        raise error

    monkeypatch.setattr(fast_llm, "fast_completion", completion)
    # Exercise the real learning wrapper behind the mocked network boundary.
    monkeypatch.setattr(distiller, "call_fast_llm", call_fast_llm)
    if agent_name == "browser_skill_curator":
        async def reflect(*args, **kwargs):
            return [{"kind": "strategy", "content": "Wait", "condition": "Loading",
                     "evidence_ids": ["e1"]}], []
        monkeypatch.setattr(distiller, "reflect_record", reflect)
    store.enqueue(record())
    assert asyncio.run(distiller.process_pending_updates(store)) == {"processed": 0, "failed": 1}
    assert row(store)["status"] == "paused"
    assert row(store)["failures"] == 1
    reopened = playbook.PlaybookStore(store.path)
    assert reopened.get_record("retry-run") is not None
    assert reopened.ready_count() == 0
    assert asyncio.run(distiller.process_pending_updates(reopened)) == {"processed": 0, "failed": 0}
    assert len(calls) == 1
    assert calls[0]["num_retries"] == 0


def test_three_failures_stop_across_restarts_but_do_not_block_other_work(store, monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(playbook.time, "time", lambda: now[0])
    calls = []

    async def completion(prompt, **kwargs):
        calls.append(prompt)
        raise TimeoutError

    monkeypatch.setattr(distiller, "call_fast_llm", completion)
    store.enqueue(record())
    for failure in range(1, 4):
        store = playbook.PlaybookStore(store.path)
        assert asyncio.run(distiller.process_pending_updates(store))["failed"] == 1
        assert row(store)["failures"] == failure
        assert store.ready_count() == 0
        now[0] += 301
    assert row(store)["status"] == "failed"
    assert store.claim() is None
    assert len(calls) == 3
    store.enqueue(record("another-run"))
    assert store.ready_count() == 1
    assert store.claim()["record"].execution_id == "another-run"


def test_cancellation_does_not_consume_failure_budget_and_stale_release_is_ignored(store):
    store.enqueue(record())
    for _ in range(5):
        claimed = store.claim()
        store.release("retry-run", claimed["token"])
    assert row(store)["failures"] == 0
    claimed = store.claim()
    assert store.release("retry-run", "stale", "unauthorized", retryable=False) is None
    assert row(store)["status"] == "claimed"
    assert store.release("retry-run", claimed["token"], "timeout") == "pending"
    assert row(store)["failures"] == 1


def test_ready_count_respects_backoff_and_global_lease(store, monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(playbook.time, "time", lambda: now[0])
    store.enqueue(record())
    claimed = store.claim()
    store.enqueue(record("another-run"))
    assert store.pending_count() == 2
    assert store.ready_count() == 0
    assert store.claim() is None
    now[0] += 120
    assert store.ready_count() == 2
    claimed = store.claim()
    store.release("retry-run", claimed["token"], "timeout")
    assert store.ready_count() == 1


def test_worker_avoids_deferred_work_and_logs_empty_drain_at_debug(store, monkeypatch, caplog):
    store.enqueue(record())
    claimed = store.claim()
    store.release("retry-run", claimed["token"], "timeout")
    worker = pipeline.BrowserLearningWorker(store=store)
    assert not worker._has_pending(store)

    async def empty(**kwargs):
        return {"processed": 0, "failed": 0}

    monkeypatch.setattr(pipeline, "_distiller",
                        lambda: SimpleNamespace(process_pending_updates=empty))
    # Siada's parent logger does not propagate to pytest's root handler.
    monkeypatch.setattr(pipeline.logger, "handlers", [caplog.handler])
    monkeypatch.setattr(pipeline.logger, "propagate", False)
    with caplog.at_level(logging.DEBUG, logger=pipeline.__name__):
        asyncio.run(worker.drain_once())
    records = [item for item in caplog.records if item.name == pipeline.__name__]
    assert len(records) == 2
    assert all(item.levelno == logging.DEBUG for item in records)


def test_legacy_queue_migrates_exhausted_failure_history(tmp_path):
    path = tmp_path / "legacy.sqlite3"
    schema = playbook._SCHEMA.replace("    failures INTEGER NOT NULL DEFAULT 0,\n", "")
    with sqlite3.connect(path) as connection:
        connection.executescript(schema)
    store = playbook.PlaybookStore(path)
    store.enqueue(record())
    # Recreate the old table shape with an exhausted retry record.
    with sqlite3.connect(path) as connection:
        connection.execute("ALTER TABLE executions DROP COLUMN failures")
        connection.execute(
            "UPDATE executions SET attempts=10, last_error='TimeoutError'"
        )
    reopened = playbook.PlaybookStore(path)
    assert row(reopened)["failures"] == 10
    assert row(reopened)["status"] == "failed"
    assert reopened.ready_count() == 0
    assert reopened.claim() is None


@pytest.mark.parametrize("error", [
    RuntimeError("Error code: 403 - Authentication failed"),
    RuntimeError("HTTP 401"),
])
def test_wrapped_authentication_status(error):
    assert is_authentication_error(error)


def test_unrelated_numeric_text_is_not_authentication():
    assert not is_authentication_error(RuntimeError("Processed 403 rows"))