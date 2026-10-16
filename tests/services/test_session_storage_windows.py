"""Exercise Windows flushing requirements without changing the host platform."""

import os
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from siada.services import git_service, session_storage


@pytest.fixture
def windows_io(monkeypatch):
    flushed = []

    def fsync(fd):
        # POSIX rejects even an empty write on a read-only descriptor, matching
        # the writable-handle requirement of Windows CRT _commit.
        os.write(fd, b"")
        os.fsync(fd)
        flushed.append(fd)

    directory_open = Mock(side_effect=PermissionError("Windows CRT cannot open directories"))
    proxy = SimpleNamespace(**{**vars(os), "name": "nt", "fsync": fsync, "open": directory_open})
    monkeypatch.setattr(session_storage, "os", proxy)
    monkeypatch.setattr(git_service, "os", proxy)
    return flushed, directory_open


def test_windows_directory_sync_does_not_open_a_directory(tmp_path, windows_io):
    flushed, directory_open = windows_io
    session_storage.sync_directory(tmp_path)
    directory_open.assert_not_called()
    assert flushed == []


@pytest.mark.skipif(os.name == "nt", reason="POSIX read-only file flushing")
def test_posix_transaction_can_flush_a_read_only_file(tmp_path):
    path = tmp_path / "api_history.json"
    path.write_bytes(b'{"unchanged": true}')
    path.chmod(0o400)
    try:
        with session_storage.storage_transaction(tmp_path, ("api_history.json",)):
            pass
        assert path.read_bytes() == b'{"unchanged": true}'
        assert not (tmp_path / ".storage-transaction.json").exists()
    finally:
        path.chmod(0o600)


@pytest.mark.parametrize("abort", [False, True])
def test_windows_transaction_flushes_writable_files_and_preserves_rollback(tmp_path, windows_io, abort):
    flushed, directory_open = windows_io
    path = tmp_path / "api_history.json"
    path.write_bytes(b'{"before": true}')

    def mutate():
        with session_storage.storage_transaction(tmp_path, ("api_history.json",)):
            path.write_bytes(b'{"after": true}')
            if abort:
                raise ValueError("synthetic mutation failure")

    if abort:
        with pytest.raises(ValueError, match="synthetic mutation"):
            mutate()
    else:
        mutate()
    assert path.read_bytes() == (b'{"before": true}' if abort else b'{"after": true}')
    assert not (tmp_path / ".storage-transaction.json").exists()
    assert len(flushed) >= 2
    directory_open.assert_not_called()


def test_windows_checkpoint_restore_flushes_writable_files(tmp_path, windows_io, monkeypatch):
    flushed, directory_open = windows_io
    project = tmp_path / "project"
    project.mkdir()
    restored = project / "restored.txt"
    restored.write_bytes(b"restored")
    service = git_service.GitService(str(project), str(tmp_path / "shadow"))
    repository = Mock()
    repository.git.ls_files.return_value = "restored.txt\0"
    monkeypatch.setattr(git_service.GitService, "shadow_git_repository", property(lambda _: repository))
    monkeypatch.setattr(service, "_protected_project_paths", lambda: [])

    service.restore_project_from_snapshot("a" * 40)

    repository.git.restore.assert_called_once()
    assert restored.read_bytes() == b"restored"
    assert len(flushed) == 1
    directory_open.assert_not_called()