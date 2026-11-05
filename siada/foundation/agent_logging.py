"""Use SDK runners with attribution for every specialized agent invocation."""

from uuid import uuid4

from agents import Agent, Runner

from siada.foundation.context import get_context_var
from siada.foundation.log_context import log_scope, REQUEST_ID
from siada.foundation.sdk_patches import configure_sdk_run_config


def _configure_run(args, kwargs):
    agent = kwargs.get("starting_agent") or (args[0] if args else None)
    if isinstance(agent, Agent):
        config = kwargs.get("run_config")
        # A dictionary without model_provider keeps implicit provider creation
        # and cleanup with the SDK in both streamed and non-streamed runs.
        config = {} if config is None else config
        kwargs = {**kwargs, "run_config": configure_sdk_run_config(config)}
    return kwargs


def _scope(args, kwargs):
    agent = kwargs.get("starting_agent") or kwargs.get("agent") or (args[0] if args else None)
    session = kwargs.get("session")
    context = kwargs.get("context")
    running_session = getattr(context, "session", None)
    session_id = getattr(running_session, "session_id", None) or getattr(session, "session_id", None)
    return log_scope(
        session_id=session_id, agent=getattr(agent, "name", None),
        request_id=get_context_var(REQUEST_ID) or uuid4().hex,
        agent_run_id=uuid4().hex,
    )


class LoggingRunner:
    @staticmethod
    async def run(*args, **kwargs):
        from siada.foundation.tool_recovery import tool_recovery_scope

        kwargs = _configure_run(args, kwargs)
        with _scope(args, kwargs), tool_recovery_scope():
            return await Runner.run(*args, **kwargs)

    @staticmethod
    def run_streamed(*args, **kwargs):
        from siada.foundation.tool_recovery import tool_recovery_scope

        kwargs = _configure_run(args, kwargs)
        # SDK creates the producer task synchronously; it retains this scope
        # through stream completion or cancellation after the caller returns.
        with _scope(args, kwargs), tool_recovery_scope():
            return Runner.run_streamed(*args, **kwargs)