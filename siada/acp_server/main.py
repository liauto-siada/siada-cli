"""Console-script entry point for the standard ACP agent."""

import asyncio
import logging
from pathlib import Path

# ---------------------------------------------------------------------------
# Agents-SDK import gate — keep before any other siada import: importing
# ``siada.foundation.sdk_patches`` installs a meta-path finder that serializes
# the SDK's *first* import from whichever thread needs it, so no import site has
# to remember calling ``ensure_agents_imported()``. See ``_AgentsImportGate``.
# ---------------------------------------------------------------------------
import siada.foundation.sdk_patches  # noqa: F401  # installs the import gate

from acp import run_agent

from siada.acp_server.acp_agent import SiadaAcpAgent
from siada.acp_server.runtime import SiadaTurnRunner, is_slash_command

ACP_LOG_PATH = Path.home() / ".siada-cli" / "logs" / "acp_server.log"


def _configure_file_logging() -> None:
    """Mirror errors and JSON-RPC traffic to a dedicated file.

    The ACP agent runs as a standalone subprocess spawned by the client
    (e.g. an editor extension) — its stderr is not surfaced anywhere, so
    without this, unhandled errors reported back to the client as
    "Internal error" are impossible to diagnose.

    Only *this module's* loggers write here (with propagate=False), so
    normal usage keeps stdout/stderr clean for the JSON-RPC transport —
    exceptions still reach this file via the root logger's existing
    ERROR-level threshold.
    """
    ACP_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(ACP_LOG_PATH)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.getLogger().addHandler(handler)

    wire_logger = logging.getLogger("siada.acp_server.wire")
    wire_logger.setLevel(logging.INFO)
    wire_logger.propagate = False
    wire_logger.addHandler(handler)


def _log_stream_event(event) -> None:
    """Log every JSON-RPC message; error payloads carry the real exception
    message in `error.data`, which the SDK otherwise discards (see
    acp.connection.Connection._run_request's `raise err from None`).
    """
    logging.getLogger("siada.acp_server.wire").info("%s %s", event.direction.value, event.message)


def main() -> None:
    """Run the Siada ACP agent over the official SDK stdio transport."""
    _configure_file_logging()
    logger = logging.getLogger(__name__)

    async def _run() -> None:
        turn_runner = SiadaTurnRunner()
        agent = SiadaAcpAgent(
            turn_runner,
            turn_runner.create_session,
            model_lister=turn_runner.list_available_models,
            model_getter=turn_runner.get_model,
            model_setter=turn_runner.set_model,
            command_matcher=is_slash_command,
            command_lister=turn_runner.list_available_commands,
            command_runner=turn_runner.run_slash_command,
            # Session history (session/list, session/load, session/resume),
            # backed by the same disk persistence as /resume.
            session_lister=turn_runner.list_sessions,
            session_restorer=turn_runner.restore_session,
            history_lister=turn_runner.load_history_messages,
            # Browser-skill ACE bridge: connection / tab binding / trajectory
            # notifications / explicit browser tasks / cancellation.
            connection_setter=turn_runner.set_connection,
            tab_registrar=turn_runner.register_tab,
            trajectory_handler=turn_runner.queue_trajectory_event,
            task_setter=turn_runner.set_browser_task,
            canceller=turn_runner.cancel_browser_task,
        )
        try:
            # use_unstable_protocol enables the session/resume route (marked
            # unstable in the SDK router, rejected with method-not-found
            # otherwise). The JS SDK's unstable_resumeSession sends exactly the
            # "session/resume" method, so this must be on for resume support.
            await run_agent(
                agent,
                observers=[_log_stream_event],
                use_unstable_protocol=True,
            )
        finally:
            # Cancel in-flight browser skill/trajectory tasks and shut down
            # the lazy learning worker before the process exits.
            await turn_runner.close()

    try:
        asyncio.run(_run())
    except Exception:
        logger.exception("ACP agent terminated with an unhandled exception")
        raise
