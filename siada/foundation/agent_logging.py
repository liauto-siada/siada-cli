"""Use SDK runners with attribution for every specialized agent invocation."""

from uuid import uuid4

from agents import Runner

from siada.foundation.context import get_context_var
from siada.foundation.log_context import log_scope, REQUEST_ID


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
        with _scope(args, kwargs):
            return await Runner.run(*args, **kwargs)

    @staticmethod
    def run_streamed(*args, **kwargs):
        # SDK creates the producer task synchronously; it retains this scope
        # through stream completion or cancellation after the caller returns.
        with _scope(args, kwargs):
            return Runner.run_streamed(*args, **kwargs)