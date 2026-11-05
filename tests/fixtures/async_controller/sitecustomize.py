"""Isolate the real CLI's user state during the opt-in PTY runtime test."""

import os
from pathlib import Path

state_dir = os.environ.get("SIADA_TEST_STATE_DIR")
if state_dir:
    # The production entry points and config loaders run unchanged. Only the
    # test process's home lookup is redirected; the user's HOME is untouched.
    Path.home = classmethod(lambda cls: Path(state_dir))