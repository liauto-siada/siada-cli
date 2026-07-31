"""
Context management module

Provides global context management functionality, similar to ThreadLocal in Java
Supports storing multiple types of context variables
"""
import contextvars
from contextlib import contextmanager
from typing import Any, Dict, Iterator, Optional

# Create context variable dictionary
context_dict_var = contextvars.ContextVar('context_dict', default={})

MODEL_PROVIDER_NAME = 'MODEL_PROVIDER_NAME'
LLM_CONFIG = 'LLM_CONFIG'
SESSION_ID = 'session_id'
AGENT_NAME = 'agent_name'


def set_context_var(key: str, value: Any) -> None:
    """
    Set context variable
    
    Args:
        key: Variable name
        value: Variable value
    """
    context_dict = context_dict_var.get()
    new_dict = dict(context_dict)  # Create a copy to avoid modifying the original dictionary
    new_dict[key] = value
    context_dict_var.set(new_dict)


def set_context_var_inplace(key: str, value: Any) -> None:
    """
    Mutate the *current* context dictionary in place, without creating a new
    dict and without calling `ContextVar.set()`.

    Why this exists:
        The OpenAI `agents` SDK invokes hook callbacks inside
        `asyncio.gather(...)`, which wraps each coroutine in its own
        `asyncio.Task`. A new Task receives a COPY of the parent's Context,
        so any `ContextVar.set()` performed inside the gathered coroutine
        affects only the child Task's Context and is invisible to the
        parent Task that subsequently issues the LLM call.

        However, `ContextVar.get()` still returns the SAME underlying dict
        object in parent and child (the Context copy is shallow) as long as
        no one has re-assigned it via `.set()`. Mutating that dict in place
        is therefore visible to both tasks, which lets a hook running inside
        `asyncio.gather` propagate values (e.g. `AGENT_NAME`) back to the
        parent task's subsequent LLM request header construction.

        Precondition: the caller or some earlier parent-level code must
        have already done at least one `set_context_var(...)` so that
        `context_dict_var` is pointing at a task-owned dict (not the shared
        default). In this codebase that is guaranteed because
        `SiadaRunner.run_agent` sets `LLM_CONFIG` before running any agent.

    Args:
        key: Variable name
        value: Variable value
    """
    context_dict = context_dict_var.get()
    context_dict[key] = value

def get_context_var(key: str, default: Any = None) -> Any:
    """
    Get context variable
    
    Args:
        key: Variable name
        default: Default value, returns this value if variable doesn't exist
        
    Returns:
        Context variable value, returns default value if doesn't exist
    """
    context_dict = context_dict_var.get()
    return context_dict.get(key, default)

def remove_context_var(key: str) -> None:
    """
    Remove context variable
    
    Args:
        key: Variable name
    """
    context_dict = context_dict_var.get()
    new_dict = dict(context_dict)  # Create a copy to avoid modifying the original dictionary
    if key in new_dict:
        del new_dict[key]
    context_dict_var.set(new_dict)


def remove_context_var_inplace(key: str) -> None:
    """
    Delete a key from the current context dictionary in place.
    See `set_context_var_inplace` for the rationale.
    """
    context_dict = context_dict_var.get()
    if key in context_dict:
        del context_dict[key]

def clear_context() -> None:
    """
    Clear all context variables
    """
    context_dict_var.set({})

# To maintain backward compatibility, provide dedicated methods for session_id
def set_session_id(session_id: str) -> None:
    """
    Set session_id for current context
    
    Args:
        session_id: Session ID
    """
    set_context_var('session_id', session_id)

def get_session_id() -> Optional[str]:
    """
    Get session_id from current context
    
    Returns:
        Current context's session_id, returns None if doesn't exist
    """
    return get_context_var('session_id')


# Sentinel used to distinguish "key absent" from "key set to None" inside
# context_var_scope() so we can faithfully restore the prior state on exit.
_MISSING = object()


@contextmanager
def context_var_scope(key: str, value: Any) -> Iterator[None]:
    """
    Temporarily set a context variable for the duration of the `with` block.

    On exit, the variable is restored to its previous value, or removed
    entirely if it was not present before. This prevents a per-request
    override (e.g. AGENT_NAME for a specific LLM call) from leaking into
    subsequent work that runs on the same coroutine/task.

    Usage:
        with context_var_scope(AGENT_NAME, "MemoryAgent"):
            await llm_client.completion(...)
    """
    previous = get_context_var(key, _MISSING)
    set_context_var(key, value)
    try:
        yield
    finally:
        if previous is _MISSING:
            remove_context_var(key)
        else:
            set_context_var(key, previous)


@contextmanager
def agent_name_scope(agent_name: Optional[str]) -> Iterator[None]:
    """
    Convenience wrapper for temporarily overriding the AGENT_NAME context
    variable. When `agent_name` is falsy the scope is a no-op, so callers can
    pass through an optional value without an extra branch.

    Usage:
        with agent_name_scope("context_compaction"):
            await llm_client.completion(...)
    """
    if not agent_name:
        yield
        return
    with context_var_scope(AGENT_NAME, agent_name):
        yield
