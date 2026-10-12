"""Serialize SDK startup without patching tool or response dispatch.

Unknown tool recovery is configured through RunConfig.
Provider-specific compatibility patches remain separate from SDK initialization.
"""

from __future__ import annotations

import logging
import sys
import threading

logger = logging.getLogger(__name__)


def configure_sdk_run_config(run_config=None):
    """Use the SDK's public missing-tool recovery without changing caller state."""
    import copy

    from agents import RunConfig

    config = copy.copy(run_config) if run_config is not None else RunConfig()
    config.tool_not_found_behavior = "return_error_to_model"
    return config


_PATCHED = False
_LITELLM_PATCHED = False

# Serializes the agents-SDK import/patch gate; see ensure_agents_imported().
_AGENTS_IMPORT_LOCK = threading.Lock()
_AGENTS_IMPORTED = False

# Per-thread marker: True while this thread is inside the critical section of
# ensure_agents_imported(). The ``_AgentsImportGate`` meta-path finder calls back
# into ensure_agents_imported() for the very ``import agents`` performed there,
# so without this the non-reentrant lock above would self-deadlock.
_AGENTS_IMPORT_IN_PROGRESS = threading.local()
_PATCH_LOCK = threading.Lock()

# Warmup coordination: the "agents-init" thread does the SDK import, patching
# and provider discovery; other siada threads wait for it (bounded) before
# importing agent classes. Without that handshake two threads can drive the
# SDK's first import concurrently, which surfaces either as partially
# initialized modules ("cannot import name X from partially initialized module
# 'agents.items'") or as an import deadlock detected by CPython's _ModuleLock.
_AGENTS_WARMUP_STARTED = threading.Event()
_AGENTS_READY = threading.Event()


def begin_agents_warmup() -> None:
    """Mark that the agents warmup thread has been started."""
    _AGENTS_WARMUP_STARTED.set()


def mark_agents_ready() -> None:
    """Mark the warmup thread's SDK work (import + patches + providers) as done."""
    _AGENTS_READY.set()


def agents_warmup_active() -> bool:
    """True while a started warmup has not finished yet."""
    return _AGENTS_WARMUP_STARTED.is_set() and not _AGENTS_READY.is_set()


def wait_agents_ready(timeout: float = 20.0) -> bool:
    """Block (bounded) until the warmup thread finished its SDK work."""
    return _AGENTS_READY.wait(timeout)


def ensure_agents_imported() -> None:
    """Import the ``agents`` package once, under a process-wide lock.

    Importing a *submodule* first (``from agents.items import ...``) while
    another thread is still executing ``agents/__init__.py`` fails with
    "cannot import name X from partially initialized module 'agents.items'".
    openai-agents 0.22.x widened that window: ``__init__`` now imports
    ``sandbox`` -> ``run_config`` -> ``guardrail`` -> ``items`` -> ``tool``.

    A package-level ``import agents`` blocks until a concurrent first import
    has completed (CPython's per-module import lock), so calling this before
    touching SDK submodules gives every siada thread one serialization point.
    """
    global _AGENTS_IMPORTED
    if _AGENTS_IMPORTED:
        return
    if getattr(_AGENTS_IMPORT_IN_PROGRESS, "value", False):
        # This thread is already driving the import: the gate re-entered here
        # through the in-flight ``import agents`` below. There is nothing to
        # wait for, and re-acquiring the (non-reentrant) lock would deadlock.
        return
    with _AGENTS_IMPORT_LOCK:
        if _AGENTS_IMPORTED:
            return
        _AGENTS_IMPORT_IN_PROGRESS.value = True
        try:
            import agents  # noqa: F401  # blocks until a concurrent init finishes
        finally:
            _AGENTS_IMPORT_IN_PROGRESS.value = False
        _AGENTS_IMPORTED = True


class _AgentsImportGate:
    """Meta-path finder that routes the SDK's first import through the lock.

    Without it the serialization point only holds for code that remembers to
    call ``ensure_agents_imported()`` first — entry modules and the two warmup
    threads do, but any of the other siada modules that import ``agents`` (or a
    submodule such as ``agents.models.*``) at module level can do so from any
    thread. Those imports are the ones that observe partially initialized
    modules or deadlock, so the gate is installed in the import machinery
    itself: ``find_spec`` runs for every not-yet-imported name, and any
    ``agents`` / ``agents.*`` import waits on the same lock before the real
    loader runs. Once the package is in ``sys.modules`` the finder is not
    consulted for it anymore, so the steady-state cost is a prefix check.

    Reentrancy is handled inside ``ensure_agents_imported()`` (per-thread
    in-progress marker), not here: the finder also fires for the
    ``import agents`` that ``ensure_agents_imported()`` itself performs, and for
    the same reason it must fire for callers that already entered the critical
    section directly.
    """

    def find_spec(self, fullname, path=None, target=None):
        if fullname != "agents" and not fullname.startswith("agents."):
            return None
        ensure_agents_imported()
        return None  # let the remaining finders perform the real import


def _install_agents_import_gate() -> None:
    """Install the gate once, at the front of ``sys.meta_path``."""
    gate = _AgentsImportGate()
    if not any(isinstance(finder, _AgentsImportGate) for finder in sys.meta_path):
        sys.meta_path.insert(0, gate)


# Install on import: every entry module imports this module before anything else
# that could pull in the SDK.
_install_agents_import_gate()


def apply_sdk_patches() -> None:
    """Keep the legacy startup entry point as an idempotent SDK import gate.

    NOTE: this runs inside the agents warmup background thread, which may race
    with the main thread's ``import litellm``. Do NOT import litellm submodules
    here — that can trigger a "partially initialized module 'litellm'" circular
    import. litellm-side patches live in ``apply_litellm_patches`` and must be
    applied only once litellm is fully loaded (see ``apply_litellm_patches``).

    The same race applies to the agents SDK itself, so startup waits for the
    package import (``ensure_agents_imported``) and serializes on
    ``_PATCH_LOCK``. Failures keep ``_PATCHED`` false so the next caller (e.g.
    the ``siada_runner`` safety net) can retry.
    """
    global _PATCHED
    if _PATCHED:
        return
    with _PATCH_LOCK:
        if _PATCHED:
            return
        try:
            ensure_agents_imported()
            _PATCHED = True
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                "Failed to initialize agents SDK: %s", exc, exc_info=True
            )


def apply_litellm_patches() -> None:
    """Apply litellm-side monkey-patches. Idempotent.

    Must be called only *after* litellm has been fully imported — e.g. right
    before ``litellm.acompletion`` in the request path — to avoid a partial
    import race with the concurrent agents warmup thread.
    """
    global _LITELLM_PATCHED
    if _LITELLM_PATCHED:
        return
    try:
        _patch_disable_gemini_function_call_id_forwarding()
        _LITELLM_PATCHED = True
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to apply litellm patches: %s", exc, exc_info=True)



def _patch_disable_gemini_function_call_id_forwarding() -> None:
    """Stop litellm from adding an ``id`` field to Gemini function call parts.

    litellm >= 1.91 forwards the OpenAI tool-call ``id`` onto the Gemini
    ``function_call`` / ``function_response`` parts for "gemini-3+" models when
    ``custom_llm_provider == "gemini"`` (Google AI Studio semantics). Note that
    ``gemini-3.5-flash`` is classified as gemini-3+ because litellm only checks
    for the substring ``"gemini-3"``.

    Some compatible gateways serve Gemini traffic through Vertex AI, which
    rejects the extra ``id`` field with an HTTP 400::

        Unknown name "id" at 'contents[..].parts[0].function_call': Cannot find field.

    Disable forwarding for compatibility with those gateways. This leaves the
    existing API-key transport and URL unchanged.

    NOTE: this depends on litellm's private ``_forward_gemini_function_call_id``;
    re-check it when bumping litellm. The caller in ``apply_litellm_patches`` wraps
    this in try/except, so a rename would only make the bug resurface, never crash.
    """

    try:
        from litellm.llms.vertex_ai.gemini.vertex_and_google_ai_studio_gemini import (
            VertexGeminiConfig,
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug(
            "Skip gemini function_call id patch; litellm import failed: %s", exc
        )
        return

    # ``_forward_gemini_function_call_id`` is a @staticmethod on the config class;
    # keep it a staticmethod so existing call sites keep working unchanged.
    VertexGeminiConfig._forward_gemini_function_call_id = staticmethod(
        lambda model, custom_llm_provider=None: False
    )
    logger.debug(
        "Patched litellm VertexGeminiConfig._forward_gemini_function_call_id -> False"
    )
