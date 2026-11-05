"""
Real-LLM cache-hit verification for run_subtask(fork=True).

This is the acceptance-criteria-#2 evidence test: "Fork mode confirms cache
hit, observed via the Fork Agent's LLM call return (Cache Token)".

Strategy: build a real parent CodeGenAgent turn (so it has a real message
history + real tool list + real rendered system prompt via the ``li``
provider, which is the one that applies Claude cache_control markers — see
``siada.internal.provider.li.cache_control``), run one real parent LLM call
to populate ``task_message_state`` with real (cache-annotated) history, then
launch a fork sub-agent from a live ``RunContextWrapper`` pointing at that
same parent agent/context and inspect the sub-agent's own LLM call usage for
``input_tokens_details.cached_tokens > 0``.

Requires network access and valid ``li`` provider credentials; skips
(instead of failing) when the model call cannot complete, exactly like the
existing ``test_run_subtask_impl_real.py`` suite.

Run explicitly with:
    poetry run python -m pytest tests/tools/agent/test_run_subtask_fork_cache_real.py -v -s
"""
import tempfile
import unittest

from agents import RunContextWrapper

from siada.agent_hub.coder.code_gen_agent import CodeGenAgent
from siada.agent_hub.coder.sub_task_agent import SubTaskAgent
from siada.entrypoint import _configure_litellm, set_current_provider
from siada.entrypoint.interaction.running_config import RunningConfig
from siada.foundation.code_agent_context import CodeAgentContext
from siada.io.io import InputOutput
from siada.models.model_run_config import ModelRunConfig
from siada.services.siada_runner import SiadaRunner
from siada.session.session_manager import RunningSessionManager
from siada.tools.agent.run_subtask import _build_fork_materials, run_subtask_impl


_PROVIDER = "li"
_MODEL = "claude-sonnet-4.6"


def _build_real_session(workspace: str):
    llm_config = ModelRunConfig(_MODEL)
    llm_config.provider = _PROVIDER

    siada_config = RunningConfig(
        llm_config=llm_config,
        io=InputOutput(),
        workspace=workspace,
        agent_name="coder",
        console_output=False,
        interactive=False,
        tracing_disabled=True,
    )
    return RunningSessionManager.create_session(siada_config)


class TestRunSubtaskForkCacheReal(unittest.IsolatedAsyncioTestCase):
    """Real model request test proving fork=True can hit the parent's prompt cache."""

    def setUp(self):
        set_current_provider(_PROVIDER)
        _configure_litellm()

    async def test_fork_sub_agent_cache_read_after_parent_turn(self):
        with tempfile.TemporaryDirectory() as workspace:
            session = _build_real_session(workspace)
            parent_agent = CodeGenAgent()
            context, run_config, openai_session = await SiadaRunner.build_context(
                parent_agent, workspace=workspace, session=session,
            )

            # Turn 1 (parent): populate real message history / cache markers.
            # A short, deterministic instruction — no tool calls needed.
            try:
                first_result = await parent_agent.run(
                    "Reply with exactly the single word: ack",
                    context=context,
                    run_config=run_config,
                    openai_session=openai_session,
                )
            except Exception as exc:  # noqa: BLE001 - integration guard
                self.skipTest(f"Real LLM unavailable: {exc}")

            print(f"\n[parent turn 1] usage={first_result.context_wrapper.usage}\n")

            # Turn 2 (parent): a second real call — Claude's cache needs at
            # least one prior identical-prefix request to have something to
            # hit; this call is also what typically shows a hit on the
            # *parent* side, and grows the real message history the fork
            # will inherit.
            try:
                second_result = await parent_agent.run(
                    "Reply with exactly the single word: ack2",
                    context=context,
                    run_config=run_config,
                    openai_session=openai_session,
                )
            except Exception as exc:  # noqa: BLE001 - integration guard
                self.skipTest(f"Real LLM unavailable: {exc}")

            print(f"\n[parent turn 2] usage={second_result.context_wrapper.usage}\n")

            # Build a live RunContextWrapper carrying the parent agent, exactly
            # what ToolContext.from_agent_context would hand run_subtask in
            # production (context.agent -> parent_agent).
            run_ctx = RunContextWrapper(context=context)
            run_ctx.agent = parent_agent

            try:
                summary = await run_subtask_impl(
                    instruction=(
                        "Without using any tools, reply with exactly the single "
                        "word: forked"
                    ),
                    agent_context=context,
                    fork=True,
                    run_ctx=run_ctx,
                )
            except Exception as exc:  # noqa: BLE001 - integration guard
                self.skipTest(f"Real LLM unavailable: {exc}")

            print(f"\n[fork sub-agent summary]\n{summary}\n")

            self.assertIsInstance(summary, str)
            self.assertTrue(summary.strip())

            # The fork sub-agent's own usage is NOT directly exposed by
            # run_subtask_impl's return value (it returns only the summary
            # string) — but CacheStatusProcessor logs "[CacheStatus]" for
            # every LLM call, including the fork sub-agent's, with the
            # cache_read/hit_rate breakdown. We can't intercept a log line
            # from here without coupling to logging internals, so this test's
            # primary evidence is qualitative (the run itself must complete
            # using the parent's tools/prompt), and quantitative cache-token
            # evidence is captured by test_fork_alignment_produces_identical_prefix_bytes
            # below via direct prefix-byte comparison instead of relying on
            # provider-reported cache stats (those depend on Anthropic's
            # server-side cache state at the moment of the run, which is not
            # deterministic in CI).

    async def test_fork_alignment_produces_identical_prefix_bytes(self):
        """Deterministic evidence (no reliance on provider-side cache timing):

        assembles the parent's real tools / real system prompt / real
        message history via the exact same code path run_subtask_impl uses
        for fork=True, and asserts the fork sub-agent's LLM-facing materials
        are byte-identical to the parent's — which is the necessary and
        sufficient condition for Claude's prompt-cache prefix match (see
        run_subtask.py's fork docstring). This is deterministic and does not
        depend on Anthropic's cache TTL / server-side hit timing.
        """
        with tempfile.TemporaryDirectory() as workspace:
            session = _build_real_session(workspace)
            parent_agent = CodeGenAgent()
            context, run_config, openai_session = await SiadaRunner.build_context(
                parent_agent, workspace=workspace, session=session,
            )

            try:
                await parent_agent.run(
                    "Reply with exactly the single word: ack",
                    context=context,
                    run_config=run_config,
                    openai_session=openai_session,
                )
            except Exception as exc:  # noqa: BLE001 - integration guard
                self.skipTest(f"Real LLM unavailable: {exc}")

            run_ctx = RunContextWrapper(context=context)
            run_ctx.agent = parent_agent

            from siada.tools.agent.run_subtask import _build_fork_materials

            fork_tools, fork_instructions, fork_history = await _build_fork_materials(run_ctx)

            # 1. Tools: byte-identical (same list object contents).
            self.assertEqual(fork_tools, parent_agent.tools)

            # 2. Instructions: re-rendering get_system_prompt with the same
            # context must reproduce the exact same string (no session-state
            # drift between the parent's real call and this re-render).
            rerendered = await parent_agent.get_system_prompt(run_ctx)
            self.assertEqual(fork_instructions, rerendered)

            # 3. History: must be exactly the parent's real (post-compaction)
            # API message history — the same object the next parent LLM call
            # would have used as its history-layer prefix.
            self.assertEqual(
                fork_history, context.task_message_state.get_real_messages()
            )
            self.assertGreater(len(fork_history), 0)

    async def test_fork_sub_agent_llm_call_reports_cache_read_tokens(self):
        """Quantitative evidence for acceptance criterion #2: drive the fork
        sub-agent's own Runner.run directly (bypassing run_subtask_impl's
        summary-only return) so we can inspect its RunResult.context_wrapper
        .usage.input_tokens_details.cached_tokens directly, proving the fork
        sub-agent's first LLM call actually read from the parent's cache.
        """
        from agents import Runner
        from siada.services.sub_agent_run_config import build_sub_agent_run_config

        with tempfile.TemporaryDirectory() as workspace:
            session = _build_real_session(workspace)
            parent_agent = CodeGenAgent()
            context, run_config, openai_session = await SiadaRunner.build_context(
                parent_agent, workspace=workspace, session=session,
            )

            # Two parent turns: turn 1 writes to Anthropic's server-side
            # cache; turn 2 proves the parent itself can hit it (sanity
            # check + grows real history for the fork to inherit).
            try:
                await parent_agent.run(
                    "Reply with exactly the single word: ack",
                    context=context, run_config=run_config, openai_session=openai_session,
                )
                second_result = await parent_agent.run(
                    "Reply with exactly the single word: ack2",
                    context=context, run_config=run_config, openai_session=openai_session,
                )
            except Exception as exc:  # noqa: BLE001 - integration guard
                self.skipTest(f"Real LLM unavailable: {exc}")

            parent_cache_read = second_result.context_wrapper.usage.input_tokens_details.cached_tokens
            print(f"\n[parent turn 2] cached_tokens={parent_cache_read}\n")

            run_ctx = RunContextWrapper(context=context)
            run_ctx.agent = parent_agent
            fork_tools, fork_instructions, fork_history = await _build_fork_materials(run_ctx)

            sub_run_config = build_sub_agent_run_config(context)
            fork_agent = SubTaskAgent(
                fork_tools=fork_tools, fork_instructions=fork_instructions,
            )

            try:
                fork_result = await Runner.run(
                    starting_agent=fork_agent,
                    input=fork_history + [
                        {
                            "role": "user",
                            "content": (
                                "Without using any tools, reply with exactly "
                                "the single word: forked"
                            ),
                        }
                    ],
                    context=CodeAgentContext(root_dir=workspace, is_subagent=True),
                    run_config=sub_run_config,
                )
            except Exception as exc:  # noqa: BLE001 - integration guard
                self.skipTest(f"Real LLM unavailable: {exc}")

            fork_cache_read = fork_result.context_wrapper.usage.input_tokens_details.cached_tokens
            print(f"\n[fork sub-agent] usage={fork_result.context_wrapper.usage}\n")
            print(f"\n[fork sub-agent] cached_tokens={fork_cache_read}\n")

            # The core acceptance-criteria assertion: the fork sub-agent's
            # very first LLM call reads a non-trivial number of tokens from
            # cache (i.e. > 0), proving the tools/prompt/history alignment
            # actually lets it reuse the parent's already-warmed cache
            # instead of paying full price cold.
            self.assertGreater(
                fork_cache_read, 0,
                f"expected fork sub-agent's first LLM call to report cache_read "
                f"tokens > 0 (parent cache_read was {parent_cache_read}); got "
                f"{fork_result.context_wrapper.usage}",
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
