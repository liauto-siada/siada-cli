import json
from pathlib import Path

import pytest

from siada.services.goal import goal_storage
from siada.services.goal.models import Goal


@pytest.fixture
def temp_session_dir(tmp_path):
    return tmp_path


def test_save_and_load_round_trip(temp_session_dir):
    goal = Goal.create("implement the thing")
    assert goal_storage.save_goal(temp_session_dir, goal) is True

    goal_file = temp_session_dir / "goal.json"
    assert goal_file.exists()

    loaded = goal_storage.load_goal(temp_session_dir)
    assert loaded == goal


def test_load_returns_none_when_missing(temp_session_dir):
    assert goal_storage.load_goal(temp_session_dir) is None


def test_load_returns_none_on_corrupted_file(temp_session_dir):
    goal_file = temp_session_dir / "goal.json"
    goal_file.write_text("{not valid json", encoding="utf-8")
    assert goal_storage.load_goal(temp_session_dir) is None


def test_save_overwrites_previous_goal(temp_session_dir):
    first = Goal.create("first objective")
    goal_storage.save_goal(temp_session_dir, first)

    second = Goal.create("second objective")
    goal_storage.save_goal(temp_session_dir, second)

    loaded = goal_storage.load_goal(temp_session_dir)
    assert loaded.objective == "second objective"


def test_save_creates_parent_directory(tmp_path):
    nested_dir = tmp_path / "nested" / "session_dir"
    goal = Goal.create("nested save")
    assert goal_storage.save_goal(nested_dir, goal) is True
    assert (nested_dir / "goal.json").exists()


def test_save_uses_atomic_write_no_leftover_temp_files(temp_session_dir):
    goal = Goal.create("atomic check")
    goal_storage.save_goal(temp_session_dir, goal)
    leftovers = list(temp_session_dir.glob(".goal_*.tmp"))
    assert leftovers == []


def test_clear_goal_removes_file(temp_session_dir):
    goal = Goal.create("to be cleared")
    goal_storage.save_goal(temp_session_dir, goal)
    assert (temp_session_dir / "goal.json").exists()

    goal_storage.clear_goal(temp_session_dir)
    assert not (temp_session_dir / "goal.json").exists()
    assert goal_storage.load_goal(temp_session_dir) is None


def test_clear_goal_is_noop_when_file_absent(temp_session_dir):
    # Must not raise even if there was never a goal saved.
    goal_storage.clear_goal(temp_session_dir)


def test_saved_file_is_valid_json_with_expected_fields(temp_session_dir):
    goal = Goal.create("check schema")
    goal_storage.save_goal(temp_session_dir, goal)

    with open(temp_session_dir / "goal.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["objective"] == "check schema"
    assert data["status"] == "active"
    assert data["consecutive_failures"] == 0
    assert "created_at" in data
    assert "updated_at" in data


# ---------------------------------------------------------------------------
# append_goal_history / load_goal_history
# ---------------------------------------------------------------------------

def test_load_goal_history_returns_empty_list_when_missing(temp_session_dir):
    assert goal_storage.load_goal_history(temp_session_dir) == []


def test_append_goal_history_writes_one_jsonl_line(temp_session_dir):
    goal = Goal.create("archived objective")
    goal_storage.append_goal_history(temp_session_dir, goal)

    history_file = temp_session_dir / "goal_history.jsonl"
    assert history_file.exists()
    lines = history_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1

    record = json.loads(lines[0])
    assert record["objective"] == "archived objective"
    assert record["status"] == "active"
    assert "archived_at" in record


def test_append_goal_history_accumulates_across_calls(temp_session_dir):
    goal_storage.append_goal_history(temp_session_dir, Goal.create("first"))
    goal_storage.append_goal_history(temp_session_dir, Goal.create("second"))
    goal_storage.append_goal_history(temp_session_dir, Goal.create("third"))

    history = goal_storage.load_goal_history(temp_session_dir)
    assert [h["objective"] for h in history] == ["first", "second", "third"]


def test_load_goal_history_skips_malformed_lines(temp_session_dir):
    goal_storage.append_goal_history(temp_session_dir, Goal.create("valid one"))
    history_file = temp_session_dir / "goal_history.jsonl"
    with open(history_file, "a", encoding="utf-8") as f:
        f.write("{not valid json\n")
    goal_storage.append_goal_history(temp_session_dir, Goal.create("valid two"))

    history = goal_storage.load_goal_history(temp_session_dir)
    assert [h["objective"] for h in history] == ["valid one", "valid two"]


def test_append_goal_history_does_not_affect_current_goal_json(temp_session_dir):
    current = Goal.create("still current")
    goal_storage.save_goal(temp_session_dir, current)
    goal_storage.append_goal_history(temp_session_dir, Goal.create("archived one"))

    loaded = goal_storage.load_goal(temp_session_dir)
    assert loaded.objective == "still current"

