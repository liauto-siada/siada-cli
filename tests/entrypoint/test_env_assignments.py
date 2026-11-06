"""Environment parsing must not initialize the launcher from the backend."""

import os
import subprocess
import sys
import textwrap
from types import SimpleNamespace

import pytest

from siada.entrypoint.env_assignments import parse_env_assignments


@pytest.mark.parametrize("args", [None, SimpleNamespace(), SimpleNamespace(set_env=None),
                                SimpleNamespace(set_env=[])])
def test_empty_assignments(args):
    assert parse_env_assignments(args) == {}


def test_assignments_preserve_existing_value_semantics(monkeypatch):
    monkeypatch.setenv("SIADA_ENV_TEST", "original")
    args = SimpleNamespace(set_env=[
        " SIADA_ENV_TEST = first ",
        "SIADA_ENV_EMPTY=",
        "SIADA_ENV_EQUALS=a=b",
        "SIADA_ENV_TEST=last",
    ])

    assert parse_env_assignments(args) == {
        "SIADA_ENV_TEST": "last",
        "SIADA_ENV_EMPTY": "",
        "SIADA_ENV_EQUALS": "a=b",
    }
    assert os.environ["SIADA_ENV_TEST"] == "original"


@pytest.mark.parametrize("invalid", [
    "PRIVATE_VALUE_SENTINEL",
    "=PRIVATE_VALUE_SENTINEL",
    "  =PRIVATE_VALUE_SENTINEL",
    "SIADA_ENV_TEST=PRIVATE_VALUE_SENTINEL\0",
    "SIADA_ENV_\0TEST=value",
    None,
    123,
])
def test_invalid_assignment_is_redacted_and_does_not_mutate_environment(monkeypatch, invalid):
    monkeypatch.setenv("SIADA_ENV_TEST", "original")
    with pytest.raises(ValueError) as error:
        parse_env_assignments(SimpleNamespace(set_env=["SIADA_ENV_TEST=changed", invalid]))
    assert "PRIVATE_VALUE_SENTINEL" not in str(error.value)
    assert os.environ["SIADA_ENV_TEST"] == "original"


@pytest.mark.parametrize(("assignments", "status", "expected"), [
    (None, 0, "original"),
    ([], 0, "original"),
    (["SIADA_ENV_TEST=updated=with_equals"], 0, "updated=with_equals"),
    (["SIADA_ENV_TEST=changed", "=PRIVATE_VALUE_SENTINEL"], 1, "original"),
])
def test_backend_environment_setup_does_not_import_launcher_under_acp(
    tmp_path, assignments, status, expected,
):
    code = textwrap.dedent(f"""
        import importlib
        import importlib.abc
        import os
        import sys
        from types import SimpleNamespace

        sys.argv = ["siadahub", "--acp"]

        class ForbidLauncher(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, path=None, target=None):
                if fullname == "siada.entrypoint.launch_ui_with_acp":
                    raise AssertionError("Backend environment parsing imported launcher")
                return None

        sys.meta_path.insert(0, ForbidLauncher())
        backend = importlib.import_module("siada.entrypoint.siadahub")
        os.environ["SIADA_ENV_TEST"] = "original"
        errors = []
        io = SimpleNamespace(print_error=errors.append)
        args = SimpleNamespace(set_env={assignments!r})
        assert backend.set_env(args, io) == {status}
        assert os.environ["SIADA_ENV_TEST"] == {expected!r}
        assert bool(errors) == bool({status})
        assert all("PRIVATE_VALUE_SENTINEL" not in message for message in errors)
        assert "siada.entrypoint.launch_ui_with_acp" not in sys.modules
        assert "siada.services.memory.holographic.provider" not in sys.modules
        assert "agents" not in sys.modules
        print("ENV_SETUP_WITHOUT_LAUNCHER_OK")
    """)
    env = os.environ.copy()
    env["SIADA_CLI_LOG_DIR"] = str(tmp_path / "logs")
    env["SIADA_REMOTE_MODEL_CONFIG"] = "0"
    env["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"
    completed = subprocess.run(
        [sys.executable, "-c", code],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr[-2000:]
    assert "ENV_SETUP_WITHOUT_LAUNCHER_OK" in completed.stdout