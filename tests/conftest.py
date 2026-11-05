"""Keep the test suite offline.

``ModelRunConfig`` and other callers resolve model settings through
``get_model_settings()``, which lazily starts a fetch of the remote
model-configuration list (``_ensure_remote_fetch_started``, an internal
siada-server / Apollo endpoint). The fetch is enabled by default, so leaving it
alone would make otherwise pure unit tests depend on intranet reachability and
on whatever the remote list happens to contain.

The autouse fixture below pins the local model settings (the built-in
``MODEL_SETTING`` registry, or the user-defined list when one is active) as the
only source of truth for the whole suite. Tests that exercise the remote path
call the fetch helpers directly, and ``tests/models/test_remote_model_config_switch.py``
covers the switch itself.

The switch is read from the environment on every fetch attempt (see
``_is_remote_model_config_fetch_enabled``), so setting the variable here
disables the network call without patching any fetch implementation.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _no_remote_model_config(monkeypatch):
    """Stop the lazy remote model-config fetch from starting during tests."""
    monkeypatch.setenv("SIADA_REMOTE_MODEL_CONFIG", "0")