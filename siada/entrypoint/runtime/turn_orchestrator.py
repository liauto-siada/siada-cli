"""Turn execution core shared by all controller surfaces.

Step-5 seed of the controller-runtime split (see
``design_docs/controller-runtime-sequence-analysis.md``): surfaces (terminal
Controller, IM controllers, ACP runtime) own input transport and rendering;
this package owns the surface-agnostic turn pipeline.

The ACP runtime migrates first (``SiadaTurnRunner._stream_turn`` consumes
``run_agent_turn``); the terminal and IM surfaces keep their direct
``SiadaRunner.run_agent`` + ``classify_stream_event`` call sites until their
cancellation plumbing (``ConversationTurn.current_result`` /
``ActiveTaskEntry.result``) is reworked onto the orchestrator.
"""

from typing import Any, AsyncIterator, Optional

from siada.entrypoint.runtime.turn_event import TurnEvent, translate_stream_events
from siada.services.siada_runner import SiadaRunner
from siada.session.session_models import RunningSession


class TurnOrchestrator:
    """Run one agent turn and translate its stream into surface-neutral TurnEvents."""

    async def run_agent_turn(
        self,
        *,
        session: RunningSession,
        user_input: Any,
        agent_name: str,
        workspace: str,
        extra_mcp_servers: Optional[list[Any]] = None,
        runtime_source: Optional[str] = None,
    ) -> AsyncIterator[TurnEvent]:
        """Execute ``SiadaRunner.run_agent`` and yield translated TurnEvents.

        The run_agent await happens lazily on the first iteration, so callers
        wrapping this in try/except (e.g. the ACP runtime's browser-record
        failure paths) observe run_agent errors at the same point as before.
        Surfaces that need the raw ``RunResultStreaming`` handle (cancellation
        via ``result.cancel()``, as the terminal and IM paths do) should keep
        calling ``SiadaRunner.run_agent`` directly until cancellation is
        reworked — this method intentionally does not expose the handle.
        """
        kwargs: dict[str, Any] = dict(
            agent_name=agent_name,
            user_input=user_input,
            workspace=workspace,
            session=session,
            stream=True,
        )
        if extra_mcp_servers:
            kwargs["extra_mcp_servers"] = extra_mcp_servers
        if runtime_source is not None:
            kwargs["runtime_source"] = runtime_source
        result = await SiadaRunner.run_agent(**kwargs)
        async for turn_event in translate_stream_events(result.stream_events()):
            yield turn_event
