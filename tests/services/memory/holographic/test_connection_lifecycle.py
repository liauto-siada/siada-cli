"""Regression coverage for long-lived hosts retaining memory providers."""

from concurrent.futures import ThreadPoolExecutor
import sqlite3

import pytest

from siada.config.config_loader import HolographicConfig
from siada.services.memory.holographic import store as store_module
from siada.services.memory.holographic.provider import HolographicProvider


@pytest.fixture
def connections(monkeypatch):
    opened = []
    original = sqlite3.connect

    def connect(*args, **kwargs):
        connection = original(*args, **kwargs)
        opened.append(connection)
        return connection

    monkeypatch.setattr(store_module.sqlite3, "connect", connect)
    return opened


def assert_closed(connections):
    for connection in connections:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            connection.execute("SELECT 1")


def make_provider(tmp_path):
    provider = HolographicProvider(HolographicConfig(
        enabled=True, db_path=str(tmp_path / "facts.db"), hrr_dim=128,
    ))
    provider.initialize()
    return provider


def test_retained_providers_release_connections_after_each_operation(tmp_path, connections):
    # Keep all providers alive, just as the daemon's session cache does.
    providers = [make_provider(tmp_path) for _ in range(30)]
    for provider in providers:
        assert provider.fact_count() == 0
        assert_closed(connections)
    provider = providers[-1]
    added = provider.store.add_fact('Project "Phoenix" uses Postgres')
    for action, args in [
        ("search", {"query": "Postgres"}),
        ("probe", {"entity": "Phoenix"}),
        ("related", {"entity": "Phoenix"}),
        ("reason", {"entities": ["Phoenix", "Postgres"]}),
        ("contradict", {}),
    ]:
        result = provider.handle_tool_call("fact_store", {"action": action, **args})
        assert '"success": true' in result
        assert_closed(connections)
    assert provider.store.get_fact(added["fact_id"]) is not None
    assert_closed(connections)


def test_repeated_initialize_is_idempotent(tmp_path, connections):
    provider = make_provider(tmp_path)
    original = provider.store
    provider.initialize()
    assert provider.store is original
    provider.shutdown()
    provider.shutdown()
    assert_closed(connections)
    provider.initialize()
    assert provider.is_ready()
    assert_closed(connections)


def test_initialization_failure_closes_connection(tmp_path, connections, monkeypatch):
    monkeypatch.setattr(store_module, "_SCHEMA", "invalid SQL")
    with pytest.raises(sqlite3.OperationalError):
        make_provider(tmp_path)
    assert_closed(connections)


def test_write_failure_rolls_back_and_closes_connection(tmp_path, connections, monkeypatch):
    provider = make_provider(tmp_path)
    with monkeypatch.context() as patch:
        def fail(*args):
            raise RuntimeError("encoding failed")
        patch.setattr(provider.store, "_compute_and_store_hrr", fail)
        with pytest.raises(RuntimeError, match="encoding failed"):
            provider.store.add_fact("Failed fact")
    assert provider.fact_count() == 0
    assert_closed(connections)
    assert provider.store.add_fact("Successful retry")["success"]
    assert_closed(connections)


def test_concurrent_reads_and_writes_share_only_operation_connection(tmp_path, connections):
    provider = make_provider(tmp_path)
    def write(index):
        provider.store.add_fact(f"Fact {index}")
        return provider.fact_count()
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(write, range(20)))
    assert provider.fact_count() == 20
    assert_closed(connections)
    store = provider.store
    provider.shutdown()
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        # Retained references must not reopen a store after explicit shutdown.
        store.fact_count()