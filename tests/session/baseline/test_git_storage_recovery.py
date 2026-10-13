"""Exercise checkpoint compensation with real Git and abruptly exited workers."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from git import Repo

from siada.services import session_storage
from siada.services.git_service import GitService
from siada.services.session_storage import SessionStorageError, storage_transaction
from siada.utils import DirectoryUtils


WORKER = """
import os
import sys
from pathlib import Path
from siada.services import session_storage as storage
from siada.services.git_service import GitService
from siada.utils import DirectoryUtils

folder, root, shadow = map(Path, sys.argv[1:4])
target, point = sys.argv[4:6]
DirectoryUtils.get_project_temp_dir = staticmethod(lambda _: str(shadow.parent))
DirectoryUtils.get_global_sessions_dir = staticmethod(lambda _: str(folder.parent))
git = GitService(str(root), str(shadow))
with storage.storage_transaction(folder):
    (folder / "api_history.json").write_text("partial history")
    (folder / "runtime_state.json").write_text("partial state")
    rollback = git.create_snapshot("synthetic compensation")
    storage.enlist_project_restore(folder, git, rollback)
    if point == "before_project":
        os._exit(7)
    if point == "partial_project":
        (root / "tracked.txt").write_text("partially restored")
        (root / "later.txt").unlink()
        os._exit(7)
    git.restore_project_from_snapshot(target)
    if point == "after_project":
        os._exit(7)
    (folder / "signature.json").write_text("partial signature")
    if point == "before_commit":
        os._exit(7)
os._exit(8)
"""


def real_repository(baseline):
    session = baseline.session()
    store = session.openai_session
    root = Path(session.siada_config.workspace)
    # Keep a genuine user repository independent of the shadow index and HEAD.
    repo = Repo.init(root, initial_branch="main")
    with repo.config_writer() as config:
        config.set_value("user", "name", "Synthetic Test")
        config.set_value("user", "email", "test@example.invalid")
        config.set_value("commit", "gpgsign", False)
    (root / "tracked.txt").write_text("checkpoint contents")
    repo.index.add(["tracked.txt"])
    repo.index.commit("synthetic user commit")
    shadow = Path(DirectoryUtils.get_project_temp_dir(str(root))) / "shadow_repo"
    git = GitService(str(root), str(shadow))
    target = git.create_snapshot("synthetic checkpoint")
    (root / "tracked.txt").write_text("uncommitted contents")
    (root / "later.txt").write_text("new uncommitted file")
    store.add_items_sync([{"role": "user", "content": "before interruption"}])
    store.migrate_legacy_context_sync(allow_history_only=True)
    return store, root, shadow, git, target, repo


@pytest.mark.parametrize("point", ["before_project", "partial_project", "after_project", "before_commit"])
def test_process_exit_restores_project_and_session_together(baseline, point):
    store, root, shadow, git, target, repo = real_repository(baseline)
    before = {path.name: path.read_bytes() for path in store.session_folder.glob("*.json")}
    user_head = repo.head.commit.hexsha
    user_index = (root / ".git" / "index").read_bytes()
    result = subprocess.run(
        [sys.executable, "-c", WORKER, str(store.session_folder), str(root), str(shadow), target, point],
        capture_output=True, text=True, timeout=30,
        env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[3])},
    )
    assert result.returncode == 7, result.stderr
    assert (store.session_folder / ".storage-transaction.json").exists()
    assert store.get_history_items_sync() == [{"role": "user", "content": "before interruption"}]
    assert (root / "tracked.txt").read_text() == "uncommitted contents"
    assert (root / "later.txt").read_text() == "new uncommitted file"
    assert before == {path.name: path.read_bytes() for path in store.session_folder.glob("*.json")}
    assert repo.head.commit.hexsha == user_head
    assert (root / ".git" / "index").read_bytes() == user_index
    # A second read must not reapply compensation or resurrect a journal.
    assert store.get_checkpoint_snapshot_sync()["context_snapshot"]["items"][0]["content"] == "before interruption"
    assert not (store.session_folder / ".storage-transaction.json").exists()


def test_committed_project_restore_is_not_undone_on_restart(baseline):
    store, root, shadow, git, target, repo = real_repository(baseline)
    rollback = git.create_snapshot("synthetic rollback")
    with storage_transaction(store.session_folder):
        session_storage.enlist_project_restore(store.session_folder, git, rollback)
        git.restore_project_from_snapshot(target)
    assert (root / "tracked.txt").read_text() == "checkpoint contents"
    assert not (root / "later.txt").exists()
    store.get_context_snapshot_sync()
    assert (root / "tracked.txt").read_text() == "checkpoint contents"


@pytest.mark.parametrize("field,value", [
    ("root", "/invalid-workspace"), ("shadow_repo", "/invalid-shadow"),
    ("rollback_hash", "--unsafe-option"), ("rollback_hash", None),
])
def test_invalid_project_journal_never_mutates_workspace(baseline, field, value):
    store, root, shadow, git, target, repo = real_repository(baseline)
    before = (root / "tracked.txt").read_bytes()
    journal = store.session_folder / ".storage-transaction.json"
    journal.write_text(json.dumps({"version": 1, "before": {}, "project": {
        "root": str(root), "shadow_repo": str(shadow), "rollback_hash": target, field: value,
    }}))
    with pytest.raises(SessionStorageError, match="project recovery journal"):
        store.get_history_items_sync()
    assert (root / "tracked.txt").read_bytes() == before
    assert journal.exists()


def test_failed_git_compensation_retains_journal_for_retry(baseline, monkeypatch):
    store, root, shadow, git, target, repo = real_repository(baseline)
    before = {path.name: path.read_bytes() for path in store.session_folder.glob("*.json")}
    restore = GitService.restore_project_from_snapshot

    def fail(self, commit):
        raise OSError("synthetic recovery interruption")

    with pytest.raises(SessionStorageError, match="journal retained"):
        with storage_transaction(store.session_folder):
            rollback = git.create_snapshot("synthetic rollback")
            session_storage.enlist_project_restore(store.session_folder, git, rollback)
            (root / "tracked.txt").write_text("partially changed")
            monkeypatch.setattr(GitService, "restore_project_from_snapshot", fail)
            raise RuntimeError("synthetic failure")
    assert (store.session_folder / ".storage-transaction.json").exists()
    monkeypatch.setattr(GitService, "restore_project_from_snapshot", restore)
    store.get_history_items_sync()
    assert (root / "tracked.txt").read_text() == "uncommitted contents"
    assert before == {path.name: path.read_bytes() for path in store.session_folder.glob("*.json")}