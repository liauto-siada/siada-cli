"""
Tests for memory_impl (Step 2 acceptance criteria).
Uses real MemoryStore instances with tmp_path — no mocking.
"""
import json
import pytest
from pathlib import Path

from siada.tools.memory.memory_write_tool import memory_impl
from siada.services.memory.memory_store import MemoryStore


def make_store(tmp_path) -> MemoryStore:
    store = MemoryStore(memory_dir=tmp_path)
    store.load_from_disk()
    return store


def test_add_dispatch(tmp_path):
    store = make_store(tmp_path)
    result_str = memory_impl(store, "add", "memory", "Project uses Python 3.12", None)
    result = json.loads(result_str)
    assert isinstance(result_str, str)
    assert result["success"] is True
    assert "Project uses Python 3.12" in result["entries"]


def test_replace_dispatch(tmp_path):
    store = make_store(tmp_path)
    memory_impl(store, "add", "memory", "Project uses Go 1.20", None)
    result_str = memory_impl(store, "replace", "memory", "Project uses Go 1.22", "Go 1.20")
    result = json.loads(result_str)
    assert result["success"] is True
    content = (tmp_path / "MEMORY.md").read_text()
    assert "Go 1.22" in content
    assert "Go 1.20" not in content


def test_remove_dispatch(tmp_path):
    store = make_store(tmp_path)
    memory_impl(store, "add", "memory", "Temp fact to remove", None)
    result_str = memory_impl(store, "remove", "memory", None, "Temp fact")
    result = json.loads(result_str)
    assert result["success"] is True
    assert result["entries"] == []


def test_store_none():
    result_str = memory_impl(None, "add", "memory", "some content", None)
    result = json.loads(result_str)
    assert result["success"] is False
    assert "Memory disabled" in result["error"]


def test_missing_content_for_add(tmp_path):
    store = make_store(tmp_path)
    result_str = memory_impl(store, "add", "memory", None, None)
    result = json.loads(result_str)
    assert result["success"] is False
    assert "content" in result["error"]


def test_missing_old_text_for_replace(tmp_path):
    store = make_store(tmp_path)
    result_str = memory_impl(store, "replace", "memory", "new content", None)
    result = json.loads(result_str)
    assert result["success"] is False
    assert "old_text" in result["error"]


def test_missing_old_text_for_remove(tmp_path):
    store = make_store(tmp_path)
    result_str = memory_impl(store, "remove", "memory", None, None)
    result = json.loads(result_str)
    assert result["success"] is False
    assert "old_text" in result["error"]


def test_return_is_json_string(tmp_path):
    store = make_store(tmp_path)
    result_str = memory_impl(store, "add", "user", "User is Alice", None)
    assert isinstance(result_str, str)
    parsed = json.loads(result_str)
    assert isinstance(parsed, dict)
