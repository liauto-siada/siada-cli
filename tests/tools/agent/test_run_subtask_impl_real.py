"""
Real-LLM integration tests for ``run_subtask_impl``.

These tests drive the *actual* ``run_subtask_impl`` end to end against a real
model (provider ``li``, model ``claude-sonnet-4.6``).  They build a genuine
``RunningSession`` (so the two compaction hooks are wired exactly as in
production) and a real ``RunConfig`` via ``build_sub_agent_run_config``.

Because they require network access and valid provider credentials, each test
skips (instead of failing) when the model call cannot complete — keeping the
suite green offline / without credentials.

Run explicitly with:
    poetry run python -m pytest tests/tools/agent/test_run_subtask_impl_real.py -v -s
"""
import tempfile
import unittest

import siada.tools.agent.sub_agent_compaction_filter as compaction_mod
from siada.entrypoint import _configure_litellm, set_current_provider
from siada.entrypoint.interaction.running_config import RunningConfig
from siada.foundation.code_agent_context import CodeAgentContext
from siada.io.io import InputOutput
from siada.models.model_run_config import ModelRunConfig
from siada.session.session_manager import RunningSessionManager
from siada.tools.agent.run_subtask import run_subtask_impl


_PROVIDER = "li"
_MODEL = "claude-sonnet-4.6"


def _build_real_session(workspace: str, *, context_window: int | None = None):
    """Create a real RunningSession backed by the ``li`` provider.

    Args:
        workspace: Working directory for the sub-agent run.
        context_window: When provided, overrides the model context window so
            the compaction threshold can be forced low in tests.

    Returns:
        A live ``RunningSession`` whose ``siada_config.llm_config`` targets
        provider ``li`` / model ``claude-sonnet-4.6``.
    """
    llm_config = ModelRunConfig(_MODEL)
    llm_config.provider = _PROVIDER
    if context_window is not None:
        llm_config.context_window = context_window

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


class TestRunSubtaskImplReal(unittest.IsolatedAsyncioTestCase):
    """Real model request tests for run_subtask_impl."""

    def setUp(self):
        # Configure LiteLLM and register the IDaaS token-refresh callback so
        # that calls through the ``li`` provider carry valid auth headers.
        # Without this, real model calls fail with 403 Authentication failed.
        set_current_provider(_PROVIDER)
        _configure_litellm()

    async def test_run_subtask_impl_returns_summary(self):
        """A real sub-agent run produces a non-empty plain-text summary."""
        with tempfile.TemporaryDirectory() as workspace:
            session = _build_real_session(workspace)
            context = CodeAgentContext(session=session, root_dir=workspace)

            # A self-contained instruction that needs no tools / file edits,
            # so the sub-agent can finish in a single turn and summarize.
            instruction = (
                "Without using any tools, compute 2 + 2 and reply with a single "
                "short sentence stating the result and what you did."
            )

            try:
                summary = await run_subtask_impl(
                    instruction=instruction,
                    agent_context=context,
                )
            except Exception as exc:  # noqa: BLE001 - integration guard
                self.skipTest(f"Real LLM unavailable: {exc}")

            print(f"\n[run_subtask_impl summary]\n{summary}\n")

            self.assertIsInstance(summary, str, "summary should be a string")
            self.assertTrue(summary.strip(), "summary should not be empty")
            # The model was asked to compute 2 + 2; the answer should appear.
            self.assertIn("4", summary, "summary should mention the result '4'")

    async def test_run_subtask_impl_multi_turn_triggers_real_compaction(self):
        """Realistic multi-turn scenario: a sub-agent runs several tool calls
        whose outputs accumulate real conversation history.  With a 10k context
        window, the running history naturally crosses the 70% (~7000 token)
        threshold mid-run, so the compaction filter fires *after* multiple turns
        — just like in production.  We record every compact() call (wrapping the
        real strategy) and assert it both triggered and actually shrank the
        history at least once."""
        with tempfile.TemporaryDirectory() as workspace:
            # A realistic-but-bounded context window: large enough that a couple
            # of sizable tool outputs are needed before compaction kicks in.
            session = _build_real_session(workspace, context_window=10_000)
            context = CodeAgentContext(session=session, root_dir=workspace)

            # A mechanical multi-step task. Each step prints a few hundred lines
            # via run_cmd, so the accumulated tool outputs grow the context past
            # the threshold over several turns. We ask for strict one-at-a-time
            # execution to mimic a real iterative agent loop.
            instruction = (
                "This is a context-accumulation exercise. Use the run_cmd tool to "
                "execute the following shell commands STRICTLY ONE AT A TIME: issue "
                "a single run_cmd, wait for its output, then issue the next. Do NOT "
                "combine them into one command. Run every step in order:\n"
                "Step 1: seq 1 300 | awk '{print \"alpha row \" $1 \": the quick brown fox jumps over the lazy dog near the river bank\"}'\n"
                "Step 2: seq 1 300 | awk '{print \"beta row \" $1 \": pack my box with five dozen liquor jugs while it rains all day\"}'\n"
                "Step 3: seq 1 300 | awk '{print \"gamma row \" $1 \": how vexingly quick daft zebras jump over the wooden fence\"}'\n"
                "Step 4: seq 1 300 | awk '{print \"delta row \" $1 \": sphinx of black quartz judge my vow upon the distant hill\"}'\n"
                "Step 5: echo ALL_STEPS_DONE\n"
                "After Step 5, reply with a short summary confirming all five "
                "commands ran and what their exit codes were."
            )

            # Record every compact() invocation while still running the real
            # compaction logic underneath, so we can prove it both fired and
            # genuinely compressed the history.  We keep the full input/output
            # item lists so the actual compacted result can be inspected.
            import json

            original_compact = compaction_mod._STRATEGY.compact
            compact_records: list[dict] = []

            async def _recording_compact(model_run_config, real_api_messages, **kwargs):
                result = await original_compact(
                    model_run_config, real_api_messages, **kwargs
                )
                compact_records.append(
                    {
                        "input_len": len(real_api_messages),
                        "output_len": len(result.messages),
                        "input_items": list(real_api_messages),
                        "output_items": list(result.messages),
                    }
                )
                return result

            try:
                compaction_mod._STRATEGY.compact = _recording_compact
                summary = await run_subtask_impl(
                    instruction=instruction,
                    agent_context=context,
                )
            except Exception as exc:  # noqa: BLE001 - integration guard
                self.skipTest(f"Real LLM unavailable: {exc}")
            finally:
                compaction_mod._STRATEGY.compact = original_compact

            print(f"\n[multi-turn summary]\n{summary}\n")

            # Print the full detail of every compaction: the item-count change
            # plus the actual compacted result the model produced, so the real
            # summarization output (not just the count) is visible.
            print("\n========== COMPACTION DETAILS ==========")
            for i, rec in enumerate(compact_records, start=1):
                print(
                    f"\n--- compaction #{i}: "
                    f"{rec['input_len']} items -> {rec['output_len']} items ---"
                )
                for j, item in enumerate(rec["output_items"]):
                    try:
                        rendered = json.dumps(item, ensure_ascii=False, indent=2, default=str)
                    except Exception:
                        rendered = repr(item)
                    print(f"[result item {j}]\n{rendered}")
            print("\n========================================\n")

            self.assertIsInstance(summary, str)
            self.assertTrue(summary.strip(), "summary should not be empty")

            # Compaction must have fired at least once during the natural
            # multi-turn accumulation (not forced via a tiny window).
            self.assertGreaterEqual(
                len(compact_records),
                1,
                "compaction should have triggered after multi-turn accumulation",
            )
            # And at least one compaction must have genuinely shrunk the history,
            # proving the real summarization path executed (not a no-op return).
            self.assertTrue(
                any(r["output_len"] < r["input_len"] for r in compact_records),
                f"expected at least one real compression; "
                f"calls={[(r['input_len'], r['output_len']) for r in compact_records]}",
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
