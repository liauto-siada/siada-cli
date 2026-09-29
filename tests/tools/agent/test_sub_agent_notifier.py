"""Tests for siada/tools/agent/sub_agent_notifier.py"""
import unittest
from unittest.mock import patch

from siada.foundation.code_agent_context import CodeAgentContext
from siada.tools.agent import sub_agent_notifier as notifier


def _capture(test_case):
    """Patch _send_notification and return the recorded (method, params) list."""
    calls = []
    patcher = patch.object(notifier, "_send_notification", lambda m, p: calls.append((m, p)))
    patcher.start()
    test_case.addCleanup(patcher.stop)
    return calls


class TestPureHelpers(unittest.TestCase):
    def test_new_sub_agent_id_prefix_unique(self):
        ids = {notifier.new_sub_agent_id() for _ in range(50)}
        self.assertTrue(all(i.startswith("sa_") and len(i) == 11 for i in ids))
        self.assertEqual(len(ids), 50)

    def test_make_title_first_non_empty_line(self):
        self.assertEqual(notifier.make_title("\n\n  调研 todo 展示  \n第二行"), "调研 todo 展示")

    def test_make_title_truncates_to_60(self):
        self.assertEqual(notifier.make_title("x" * 100), "x" * 60 + "…")

    def test_make_title_empty(self):
        self.assertEqual(notifier.make_title(""), "(sub agent)")

    def test_truncate_text_within_limit(self):
        self.assertEqual(notifier.truncate_text("abc"), "abc")

    def test_truncate_text_over_limit(self):
        out = notifier.truncate_text("y" * 6000)
        self.assertTrue(out.endswith("… (truncated)"))
        self.assertTrue(out.startswith("y" * 100))

    def test_truncate_text_none(self):
        self.assertEqual(notifier.truncate_text(None), "")


class TestStateAndPush(unittest.TestCase):
    def test_start_pushes_running_snapshot(self):
        calls = _capture(self)
        ctx = CodeAgentContext()
        item = notifier.start_sub_agent(ctx, "做一件事")
        self.assertEqual(item.status, "running")
        self.assertEqual(ctx.sub_agent_items, [item])
        self.assertEqual(len(calls), 1)
        method, params = calls[0]
        self.assertEqual(method, "context/subAgentState")
        self.assertEqual(params["items"][0]["id"], item.id)
        self.assertEqual(params["items"][0]["status"], "running")
        self.assertEqual(params["items"][0]["summary"], "")

    def test_push_message_entry_shape_and_tool_name(self):
        calls = _capture(self)
        notifier.push_sub_agent_message("sa_x", "tool_call", "内容", tool_name="run_cmd")
        method, params = calls[0]
        self.assertEqual(method, "context/subAgentMessage")
        self.assertEqual(params, {"id": "sa_x", "entry": {"kind": "tool_call", "text": "内容", "toolName": "run_cmd"}})

    def test_push_message_truncates(self):
        calls = _capture(self)
        notifier.push_sub_agent_message("sa_x", "tool_output", "z" * 6000)
        self.assertTrue(calls[0][1]["entry"]["text"].endswith("… (truncated)"))

    def test_finish_updates_item_and_pushes_snapshot(self):
        calls = _capture(self)
        ctx = CodeAgentContext()
        item = notifier.start_sub_agent(ctx, "t")
        calls.clear()
        notifier.finish_sub_agent(ctx, item.id, "completed", "s" * 600)
        self.assertEqual(ctx.sub_agent_items[0].status, "completed")
        self.assertEqual(len(ctx.sub_agent_items[0].summary), 500 + len("\n… (truncated)"))
        self.assertEqual(calls[0][1]["items"][0]["status"], "completed")

    def test_none_context_is_safe(self):
        calls = _capture(self)
        item = notifier.start_sub_agent(None, "t")   # 无状态维护、无快照推送
        self.assertEqual(calls, [])
        notifier.finish_sub_agent(None, item.id, "failed", "e")  # 不抛异常
        self.assertEqual(calls, [])

    def test_send_notification_no_adapter_noop(self):
        with patch("siada.foundation.global_cache.get_global_cache", return_value=None):
            notifier._send_notification("context/subAgentState", {"items": []})  # 不抛异常

    def test_send_notification_swallows_adapter_errors(self):
        boom = type("Boom", (), {"acp_enabled": True, "builder": property(lambda s: None)})
        adapter = boom()
        with patch("siada.foundation.global_cache.get_global_cache", return_value=adapter):
            notifier._send_notification("context/subAgentMessage", {})  # AttributeError 被吞掉


if __name__ == "__main__":
    unittest.main()
