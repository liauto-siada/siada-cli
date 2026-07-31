"""Tests for the per-session scheduler registry.

The registry replaces the previous ``CodeAgentContext.memory_scheduler``
property to keep service-layer state out of the foundation-layer data
model. Contracts under test:

* ``get_memory_scheduler`` returns the SAME instance for repeated
  ``session_id`` lookups (i.e. cached).
* Different ``session_id`` values yield different instances.
* Empty / falsy ``session_id`` yields ``None`` (no usable cache key).
* If the lazy factory raises, ``None`` is returned and nothing is
  cached (so a later retry can still succeed).
* ``release_memory_scheduler`` pops the entry and returns it.
* ``reset_memory_scheduler_registry`` clears all entries.
"""
from __future__ import annotations

import pytest

from siada.services.memory.memory_update import (
    MemoryUpdateScheduler,
    get_memory_scheduler,
    release_memory_scheduler,
    reset_memory_scheduler_registry,
)
from siada.services.memory.memory_update import registry as registry_module


@pytest.fixture(autouse=True)
def _clean_registry():
    """Per-test isolation: clear any state leaked from previous tests."""
    reset_memory_scheduler_registry()
    yield
    reset_memory_scheduler_registry()


def test_returns_scheduler_for_session_id():
    sched = get_memory_scheduler("sess-A")
    assert isinstance(sched, MemoryUpdateScheduler)


def test_caches_same_instance_per_session_id():
    """Idempotent — repeated lookups must return the same object."""
    a1 = get_memory_scheduler("sess-A")
    a2 = get_memory_scheduler("sess-A")
    assert a1 is a2, "registry must cache by session_id"


def test_distinct_sessions_get_distinct_schedulers():
    a = get_memory_scheduler("sess-A")
    b = get_memory_scheduler("sess-B")
    assert a is not b


@pytest.mark.parametrize("falsy", [None, ""])
def test_falsy_session_id_returns_none(falsy):
    """No usable cache key → caller treats as 'memory update disabled'."""
    assert get_memory_scheduler(falsy) is None


def test_release_pops_and_returns_instance():
    sched = get_memory_scheduler("sess-pop")
    assert sched is not None

    popped = release_memory_scheduler("sess-pop")
    assert popped is sched

    # After release, a fresh lookup builds a NEW scheduler.
    fresh = get_memory_scheduler("sess-pop")
    assert fresh is not sched


def test_release_returns_none_for_unknown_session():
    assert release_memory_scheduler("never-seen") is None


def test_release_with_falsy_session_id_returns_none():
    assert release_memory_scheduler(None) is None
    assert release_memory_scheduler("") is None


def test_factory_failure_returns_none_and_does_not_cache(monkeypatch):
    """If ``build_default_memory_scheduler`` raises, retry is allowed."""
    import siada.services.memory.memory_update as pkg

    failures = []

    def _failing_factory():
        failures.append(1)
        raise RuntimeError("simulated init failure")

    # Patch the package-level factory the registry resolves via local import.
    monkeypatch.setattr(pkg, "build_default_memory_scheduler", _failing_factory)

    assert get_memory_scheduler("sess-fail") is None
    # Nothing was cached → a second call retries the factory.
    assert get_memory_scheduler("sess-fail") is None
    assert len(failures) == 2, "failed builds must NOT be cached"


def test_reset_clears_all_entries():
    a = get_memory_scheduler("sess-A")
    b = get_memory_scheduler("sess-B")
    assert a is not None and b is not None

    reset_memory_scheduler_registry()

    # New lookups must build fresh instances.
    a_new = get_memory_scheduler("sess-A")
    b_new = get_memory_scheduler("sess-B")
    assert a_new is not a
    assert b_new is not b


def test_registry_is_module_private():
    """Smoke check: the cache dict is intentionally not part of the public API."""
    # If someone exposes ``_SCHEDULERS`` later, that's a design break.
    assert hasattr(registry_module, "_SCHEDULERS")
    assert "_SCHEDULERS" not in registry_module.__dict__.get("__all__", [])
