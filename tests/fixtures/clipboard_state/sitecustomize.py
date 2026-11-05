"""Isolate user state for installed clipboard smoke tests without changing HOME."""

import os
from pathlib import Path

_state = os.environ.get("SIADA_TEST_STATE_DIR")
if _state:
    Path.home = classmethod(lambda cls: cls(_state))
    _expanduser = os.path.expanduser

    def _test_expanduser(path):
        if isinstance(path, str) and (path == "~" or path.startswith("~/")):
            return str(Path(_state)) + path[1:]
        return _expanduser(path)

    os.path.expanduser = _test_expanduser