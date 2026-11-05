"""Fresh headless goal commands remain visible before interruption on a real TTY."""

import os
import sys
import textwrap

import pexpect
import pytest

from siada.services.goal import goal_storage


@pytest.mark.skipif(sys.platform == "win32", reason="Requires a POSIX PTY.")
def test_goal_start_and_pause_are_visible_before_first_turn_finishes(tmp_path):
    script = textwrap.dedent("""
        import asyncio
        import socket
        import sys
        from pathlib import Path
        from types import SimpleNamespace

        def deny_network(*args, **kwargs):
            raise AssertionError("The synthetic TTY run must remain offline")

        socket.socket.connect = deny_network
        socket.socket.connect_ex = deny_network
        socket.create_connection = deny_network

        from siada.entrypoint import siadahub
        from siada.entrypoint.interaction.nointeractive_controller import NoInteractiveController
        from siada.entrypoint.interaction.running_config import RunningConfig
        from siada.entrypoint.interaction.turn.conversation_turn import ConversationTurn
        from siada.foundation.execution_progress import publish_execution_progress
        from siada.services.file_session import FileSession
        from siada.services.siada_runner import SiadaRunner
        from siada.session.session_models import RunningSession
        from siada.support.slash_commands import SlashCommands

        assert sys.stdin.isatty() and sys.stdout.isatty()
        siadahub._ensure_litellm_ready = lambda: None
        siadahub._ensure_agents_ready = lambda: None
        io = SimpleNamespace(
            print=print, print_info=print, print_error=print, print_warning=print,
            acp_enabled=False, acp_adapter=None,
        )
        config = RunningConfig(
            llm_config=SimpleNamespace(model_name="synthetic"), io=io,
            workspace=sys.argv[1], agent_name="coder", interactive=False,
            console_output=True, memory_enabled=False, enable_notification=False,
        )
        session = RunningSession(config, session_id="synthetic-tty-goal")
        session.state.openai_session = FileSession(session.session_id, Path(sys.argv[1]))
        commands = SlashCommands.__new__(SlashCommands)
        commands.io = io
        commands.hook_runner = None
        commands.get_commands = lambda session=None: ["/goal"]
        current = {"context": None}
        SiadaRunner.find_session_context = lambda session: current["context"]

        async def execute(self, turn_input):
            goal = session.state.pending_goal
            assert goal is not None and goal.objective == "合成终端目标"
            current["context"] = SimpleNamespace(goal=goal)
            session.state.pending_goal = None
            publish_execution_progress("MODEL_WORK_STARTED")
            await asyncio.sleep(60)
            raise AssertionError("The test must interrupt the unfinished turn")

        ConversationTurn.execute = execute
        raise SystemExit(NoInteractiveController(config, session, commands).run("/goal 合成终端目标"))
    """)
    env = dict(os.environ)
    env.update({
        "HOME": str(tmp_path), "SIADA_ACP_MODE": "0", "SIADA_REMOTE_MODEL_CONFIG": "0",
    })
    child = pexpect.spawn(
        sys.executable, ["-c", script, str(tmp_path)],
        env=env, encoding="utf-8", timeout=30,
    )
    try:
        child.expect_exact("[Goal started]")
        child.expect_exact("MODEL_WORK_STARTED")
        child.sendcontrol("c")
        child.expect_exact("[Goal paused]")
        child.expect(pexpect.EOF)
        child.close()
        assert child.exitstatus == 130
    finally:
        child.close(force=True)

    saved = goal_storage.load_goal(tmp_path / "synthetic-tty-goal")
    assert saved.objective == "合成终端目标"
    assert saved.status == "paused"
    assert saved.turns == 0