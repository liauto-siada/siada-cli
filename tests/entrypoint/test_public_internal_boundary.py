"""Open-source boundary guard for the modules touched by the public login fix.

The modules below must not reference private trees (``siada.internal``), the
closed-source provider package (``siada.provider.li``), or its credential
helpers, so an open-source checkout never raises ModuleNotFoundError while
signing in, configuring an API key, or issuing an LLM call.
"""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# Modules whose public behaviour the boundary fix touched.
SCOPED_MODULES = (
    "siada/entrypoint/__init__.py",
    "siada/entrypoint/login/login_prompt.py",
    "siada/entrypoint/interaction/controller.py",
    "siada/agent_hub/hooks/processors/token_usage_reporter_processor.py",
    "siada/provider/client_factory.py",
    "siada/provider/fast_llm.py",
    "siada/support/slash_commands.py",
)

FORBIDDEN_REFERENCES = (
    "siada.internal",
    "siada/internal",
    "siada.provider.li",
    "idaas",
    "IDaaS",
)


@pytest.mark.parametrize("relative_path", SCOPED_MODULES)
def test_scoped_module_has_no_private_source_references(relative_path):
    source = (REPO_ROOT / relative_path).read_text(encoding="utf-8")

    found = [needle for needle in FORBIDDEN_REFERENCES if needle in source]

    assert found == [], f"{relative_path} still references {found}"


def test_login_prompt_does_not_import_private_auth_at_import_time():
    """Importing the login module must not pull in any private package.

    The module is re-fetched (not re-imported) so that module identity is kept
    for the tests that monkeypatch its helpers.
    """
    import importlib
    import sys

    module = importlib.import_module("siada.entrypoint.login.login_prompt")

    assert module is not None
    assert not any(name.startswith("siada.internal") for name in sys.modules)