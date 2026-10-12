"""Public-build tests for the litellm pre-call hook in ``siada.entrypoint``.

Audit regression: the pre-call callback imported
``siada.internal.services.idaas.auth_store`` for every call that was not gated
out, so any provider other than ``default`` — or the literal ``api_key="li"``
marker used by the closed-source proxy — raised ModuleNotFoundError in an
open-source checkout.

The hook now only normalizes the outgoing messages and must behave identically
for every provider, without importing private modules or touching credentials,
headers, or the ``model``/``api_key`` values it receives.
"""

import sys
from contextlib import contextmanager

import litellm
import pytest

import siada.entrypoint as entrypoint


@contextmanager
def _forbid_private_imports():
    """Fail if anything under ``siada.internal`` is imported while active."""

    attempted = []

    class _Finder:
        def find_spec(self, fullname, path=None, target=None):
            if fullname == "siada.internal" or fullname.startswith("siada.internal."):
                attempted.append(fullname)
                raise AssertionError(f"unexpected private import: {fullname}")
            return None

    finder = _Finder()
    sys.meta_path.insert(0, finder)
    try:
        yield attempted
    finally:
        sys.meta_path.remove(finder)


@pytest.fixture
def pre_call_hook(monkeypatch):
    """Return the hook instance ``_register_pre_call_hook`` installs."""
    # Start from an empty callback list so the assertion below is independent of
    # whatever earlier tests in the session already registered.
    monkeypatch.setattr(litellm, "callbacks", [])
    monkeypatch.setattr(entrypoint, "_PRE_CALL_HOOK_REGISTERED", False)

    entrypoint._register_pre_call_hook()

    assert len(litellm.callbacks) == 1, "expected exactly one pre-call hook"
    hook = litellm.callbacks[0]

    # Registration is idempotent: a second call must not add another hook.
    entrypoint._register_pre_call_hook()
    assert len(litellm.callbacks) == 1

    return hook


@pytest.mark.asyncio
async def test_default_provider_call_keeps_user_headers(pre_call_hook):
    entrypoint.set_current_provider("default")
    messages = [{"role": "user", "content": "hello"}]
    kwargs = {
        "model": "gpt-5.2",
        "messages": messages,
        "api_key": "sk-user-key",
        "extra_headers": {"uuid": "call-1"},
    }

    with _forbid_private_imports() as attempted:
        result = await pre_call_hook.async_pre_call_deployment_hook(
            kwargs, "acompletion"
        )

    assert result is kwargs
    assert kwargs["extra_headers"] == {"uuid": "call-1"}
    assert kwargs["api_key"] == "sk-user-key"
    assert kwargs["messages"] == messages
    assert attempted == []
    assert not any(name.startswith("siada.internal") for name in sys.modules)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tracked_provider,api_key",
    [
        ("li", "li"),
        ("li", "sk-user-key"),
        ("openai", "sk-user-key"),
        ("openrouter", "sk-user-key"),
        ("", "li"),
    ],
)
async def test_other_providers_never_import_private_auth(
    pre_call_hook, tracked_provider, api_key
):
    """Any provider key, including the literal ``li`` marker, stays offline."""
    entrypoint.set_current_provider(tracked_provider)
    kwargs = {
        "model": "claude-sonnet-5",
        "messages": [{"role": "user", "content": "hi"}],
        "api_key": api_key,
        "extra_headers": {"uuid": "call-2"},
    }

    with _forbid_private_imports() as attempted:
        result = await pre_call_hook.async_pre_call_deployment_hook(
            kwargs, "acompletion"
        )

    assert result is kwargs
    assert attempted == []
    assert "X-Siada-Token" not in kwargs.get("extra_headers", {})
    assert "X-Siada-User-ID" not in kwargs.get("extra_headers", {})
    assert not any(name.startswith("siada.internal") for name in sys.modules)


@pytest.mark.asyncio
async def test_hook_still_normalizes_empty_assistant_content(pre_call_hook):
    """The public-purpose behaviour of the hook must be preserved."""
    entrypoint.set_current_provider("default")
    messages = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": ""},
        {"role": "user", "content": "still there?"},
    ]
    kwargs = {"model": "gpt-4o", "messages": messages}

    with _forbid_private_imports():
        await pre_call_hook.async_pre_call_deployment_hook(kwargs, "acompletion")

    assert [m["content"] for m in messages] == ["hi", "still there?"]


@pytest.mark.asyncio
async def test_hook_tolerates_missing_messages(pre_call_hook):
    entrypoint.set_current_provider("default")
    kwargs = {"model": "gpt-4o"}

    result = await pre_call_hook.async_pre_call_deployment_hook(kwargs, "acompletion")

    assert result is kwargs


def test_configure_litellm_registers_hook_without_private_imports(monkeypatch):
    """``_configure_litellm`` is the real entry point the CLI calls at startup."""
    for attribute in (
        "set_verbose",
        "turn_off_message_logging",
        "suppress_debug_info",
        "drop_params",
        "num_retries",
        "success_callback",
        "failure_callback",
    ):
        monkeypatch.setattr(litellm, attribute, getattr(litellm, attribute), raising=False)
    monkeypatch.setattr(litellm, "callbacks", [])
    monkeypatch.setattr(entrypoint, "_PRE_CALL_HOOK_REGISTERED", False)

    with _forbid_private_imports() as attempted:
        entrypoint._configure_litellm()

    assert attempted == []
    assert len(litellm.callbacks) == 1
    assert litellm.success_callback == []
    assert litellm.failure_callback == []