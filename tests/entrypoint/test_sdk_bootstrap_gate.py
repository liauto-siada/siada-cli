"""Guards for the agents-SDK import gate in siada's entry modules.

Importing ``siada.foundation.sdk_patches`` installs a meta-path finder
(``_AgentsImportGate``) that routes the first import of ``agents`` / ``agents.*``
— from any thread — through ``ensure_agents_imported()``. That keeps concurrent
first imports from deadlocking (CPython ``_DeadlockError`` / module-lock ABBA) or
observing partially initialized modules, without requiring every import site to
call the helper. The entry modules must import sdk_patches before anything else
so the gate is installed first, and importing them must not itself pull the SDK
(that import is what used to delay the banner by ~0.5-0.6s).
"""

import re
import subprocess
import sys
from pathlib import Path

import pytest

# Modules that run the agent in-process and therefore gate unconditionally.
_AGENT_PROCESS_MODULES = (
    "siada.entrypoint.siadahub",
    "siada.acp_server.main",
)

# Any of these installs the gate; the entry modules must do it first.
_GATE_IMPORT_FORMS = (
    "import siada.foundation.sdk_patches",
    "from siada.foundation.sdk_patches import",
)

# The launcher still imports the helper explicitly (scoped to --acp) instead of
# relying on the gate, so its multiline import form is asserted separately.
_GATE_IMPORT_MULTILINE = "from siada.foundation.sdk_patches import ("


def _entry_source(module_name: str) -> str:
    repo_root = Path(__file__).resolve().parents[2]
    relative = Path(*module_name.split(".")[1:]).with_suffix(".py")
    return (repo_root / "siada" / relative).read_text(encoding="utf-8")


def _gate_position(source: str) -> int:
    positions = [source.index(form) for form in _GATE_IMPORT_FORMS if form in source]
    assert positions, "no sdk_patches import found — the gate would not be installed"
    return min(positions)


@pytest.mark.parametrize("module_name", _AGENT_PROCESS_MODULES)
def test_gate_runs_before_other_siada_imports(module_name):
    source = _entry_source(module_name)

    gate_position = _gate_position(source)
    siada_imports = [
        match.start()
        for match in re.finditer(r"^from siada\.", source, re.M)
        if match.start() != gate_position
    ]

    assert siada_imports, f"{module_name} has no siada imports?"
    assert gate_position < min(siada_imports), (
        "the sdk_patches import (which installs the gate) must stay before any "
        f"other siada import in {module_name}"
    )


def test_launcher_gate_is_scoped_to_acp_mode():
    """``siada-cli`` must not pay the SDK import on the plain UI path.

    The launcher only runs agent code in-process for ``--acp``; otherwise it
    spawns the Node UI / delegates to ``siadahub`` (each of which carries its
    own gate). An unconditional gate here added ~1 s to every CLI launch.
    """
    source = _entry_source("siada.entrypoint.launch_ui_with_acp")

    assert _GATE_IMPORT_MULTILINE in source
    gate_position = source.index(_GATE_IMPORT_MULTILINE)
    guard_position = source.index('if "--acp" in sys.argv:')

    assert guard_position < gate_position, "gate must live inside the --acp branch"
    # It must still precede the in-process ACP preload that imports siada code.
    preload_position = source.index(
        "import siada.services.memory.holographic.provider"
    )
    assert gate_position < preload_position


def test_launcher_plain_import_skips_sdk():
    code = (
        "import importlib, sys\n"
        "importlib.import_module('siada.entrypoint.launch_ui_with_acp')\n"
        "assert 'agents' not in sys.modules\n"
        "print('FAST_PATH_OK')\n"
    )

    completed = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=300,
    )

    assert completed.returncode == 0, completed.stderr[-2000:]
    assert "FAST_PATH_OK" in completed.stdout


def test_launcher_acp_mode_initializes_sdk():
    code = (
        "import importlib\n"
        "import sys\n"
        "sys.argv.append('--acp')\n"
        "importlib.import_module('siada.entrypoint.launch_ui_with_acp')\n"
        "import agents\n"
        "assert agents.__spec__._initializing is False\n"
        "print('ACP_GATE_OK')\n"
    )

    completed = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=300,
    )

    assert completed.returncode == 0, completed.stderr[-2000:]
    assert "ACP_GATE_OK" in completed.stdout


@pytest.mark.parametrize("module_name", _AGENT_PROCESS_MODULES)
def test_entry_module_import_installs_gate(module_name):
    """The entry module installs the gate; a later SDK import stays clean."""
    code = (
        "import importlib, sys\n"
        f"importlib.import_module({module_name!r})\n"
        "gate = [f for f in sys.meta_path if type(f).__name__ == '_AgentsImportGate']\n"
        "assert gate, 'the import gate was not installed'\n"
        "import agents\n"
        "assert agents.Agent is not None\n"
        "assert agents.__spec__._initializing is False\n"
        "print('BOOTSTRAP_OK')\n"
    )

    completed = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=300,
    )

    assert completed.returncode == 0, completed.stderr[-2000:]
    assert "BOOTSTRAP_OK" in completed.stdout
    combined = (completed.stdout + completed.stderr).lower()
    assert "deadlock" not in combined
    assert "partially initialized" not in combined


def test_siadahub_import_defers_sdk():
    """Importing siadahub must not import ``agents`` on the startup path.

    Regression guard for the placement the gate no longer requires: the SDK
    import holds the ``agents`` module lock while the package initializes, which
    delayed the banner by ~0.5-0.6s. It now runs on the ``agents-init`` worker
    thread while ``main()`` proceeds.
    """
    code = (
        "import importlib, sys\n"
        "importlib.import_module('siada.entrypoint.siadahub')\n"
        "assert 'agents' not in sys.modules, 'siadahub import pulled the SDK back in'\n"
        "print('DEFERRED_OK')\n"
    )

    completed = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=300,
    )

    assert completed.returncode == 0, completed.stderr[-2000:]
    assert "DEFERRED_OK" in completed.stdout


def test_gate_does_not_self_deadlock_on_explicit_call():
    """Calling ``ensure_agents_imported()`` directly must not re-enter the lock.

    The gate fires for the ``import agents`` executed *inside*
    ``ensure_agents_imported()``, so an explicit caller (the ``agents-init``
    warmup thread is one) self-deadlocks on the non-reentrant lock without the
    per-thread in-progress marker.
    """
    code = (
        "import siada.foundation.sdk_patches as sp\n"
        "sp.ensure_agents_imported()\n"
        "from agents.items import ToolCallItem  # noqa: F401\n"
        "print('EXPLICIT_OK')\n"
    )

    completed = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=180,
    )

    assert completed.returncode == 0, completed.stderr[-2000:]
    assert "EXPLICIT_OK" in completed.stdout


def test_gated_concurrent_imports_sdk_and_siada_chain():
    """Race regression for the production startup failures.

    Three threads enter the same import graph from different nodes at the same
    time — the SDK package root, ``agents.items``, and a siada chain that pulls
    ``agents.models.*``. Without the gate this reproduces the observed failures
    every time (``partially initialized module 'agents.items'`` /
    ``'agents.exceptions'``, plus ``KeyError: 'agents'`` from the concurrent
    import machinery). Importing ``siada.foundation.sdk_patches`` installs the
    gate in the import machinery; no thread calls the helper itself.
    """
    code = (
        "import threading\n"
        "import siada.foundation.sdk_patches  # noqa: F401 - installs the gate\n"
        "errors = []\n"
        "barrier = threading.Barrier(3)\n"
        "def load_siada():\n"
        "    barrier.wait()\n"
        "    try:\n"
        "        import siada.models.model_setting_converter  # noqa: F401\n"
        "    except BaseException as exc:\n"
        "        errors.append(repr(exc))\n"
        "def load_agents():\n"
        "    barrier.wait()\n"
        "    try:\n"
        "        import agents\n"
        "    except BaseException as exc:\n"
        "        errors.append(repr(exc))\n"
        "def load_items():\n"
        "    barrier.wait()\n"
        "    try:\n"
        "        from agents.items import ToolCallItem  # noqa: F401\n"
        "    except BaseException as exc:\n"
        "        errors.append(repr(exc))\n"
        "threads = [\n"
        "    threading.Thread(target=load_siada),\n"
        "    threading.Thread(target=load_agents),\n"
        "    threading.Thread(target=load_items),\n"
        "]\n"
        "for thread in threads:\n"
        "    thread.start()\n"
        "for thread in threads:\n"
        "    thread.join()\n"
        "import agents\n"
        "assert agents.__spec__._initializing is False\n"
        "print('RACE_OK' if not errors else 'RACE_FAIL ' + repr(errors))\n"
    )

    completed = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=300,
    )

    assert completed.returncode == 0, completed.stderr[-2000:]
    assert "RACE_OK" in completed.stdout, completed.stdout[-2000:]
    combined = (completed.stdout + completed.stderr).lower()
    assert "partially initialized" not in combined
    assert "deadlock" not in combined