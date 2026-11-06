"""Directory durability skips unsupported operations but surfaces I/O errors."""

import errno
from unittest.mock import Mock

import pytest

from siada.services import session_storage


def test_windows_does_not_open_directory(monkeypatch, tmp_path):
    monkeypatch.setattr(session_storage.os, "name", "nt")
    opened = Mock()
    monkeypatch.setattr(session_storage.os, "open", opened)
    session_storage.sync_directory(tmp_path)
    opened.assert_not_called()


@pytest.mark.parametrize("error_code", [errno.EINVAL, errno.ENOTSUP, errno.EIO])
def test_directory_flush_only_ignores_unsupported_errors(monkeypatch, tmp_path, error_code):
    monkeypatch.setattr(session_storage.os, "name", "posix")
    monkeypatch.setattr(session_storage.os, "open", Mock(return_value=123))
    monkeypatch.setattr(
        session_storage.os, "fsync", Mock(side_effect=OSError(error_code, "synthetic flush failure"))
    )
    closed = Mock()
    monkeypatch.setattr(session_storage.os, "close", closed)
    if error_code == errno.EIO:
        with pytest.raises(OSError) as error:
            session_storage.sync_directory(tmp_path)
        assert error.value.errno == errno.EIO
    else:
        session_storage.sync_directory(tmp_path)
    closed.assert_called_once_with(123)