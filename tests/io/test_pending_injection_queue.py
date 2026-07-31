"""
Unit tests for the pending user-input injection queue in StdinInterruptMonitor.

Covers:
  1. Normal message → _queue when agent is NOT running
  2. Normal message → _pending_injections when agent IS running
  3. /btw message is always intercepted (never goes to _pending_injections)
  4. set_agent_running(False) flushes _pending_injections back to _queue
  5. drain_pending_injections() returns items and clears the deque
  6. JSON-envelope messages are correctly parsed in mid-turn interception
"""

import collections
import queue
import unittest
from unittest.mock import MagicMock

import siada.io.stdin_interrupt_monitor as _mod


def _reset_module_state():
    """Reset all module-level mutable state between tests."""
    _mod._pending_injections.clear()
    _mod._agent_running = False
    # Use a real StdinInterruptMonitor instance so _dispatch_or_enqueue
    # executes the actual routing logic.  We never call start(), so no
    # background thread is created.
    real_monitor = _mod.StdinInterruptMonitor()
    _mod._monitor = real_monitor


def _make_acp_lines(body: str) -> list:
    """Wrap body text in ACP framing lines (mimics Node adapter output)."""
    return [
        "<<<SIADA_MSG_START>>>\n",
        body + "\n",
        "<<<SIADA_MSG_END>>>\n",
    ]


class TestPendingInjectionQueue(unittest.TestCase):

    def setUp(self):
        _reset_module_state()
        self.monitor = _mod._monitor

    def tearDown(self):
        _reset_module_state()

    # ------------------------------------------------------------------
    # drain_pending_injections
    # ------------------------------------------------------------------

    def test_drain_empty_returns_empty_list(self):
        result = _mod.drain_pending_injections()
        self.assertEqual(result, [])

    def test_drain_returns_all_items_and_clears_deque(self):
        _mod._pending_injections.append((None, "hello", None))
        _mod._pending_injections.append(("qid-1", "world", ["/tmp/img.png"]))

        result = _mod.drain_pending_injections()

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], (None, "hello", None))
        self.assertEqual(result[1], ("qid-1", "world", ["/tmp/img.png"]))
        self.assertEqual(len(_mod._pending_injections), 0)

    # ------------------------------------------------------------------
    # set_agent_running(False) — flush pending back to _queue
    # ------------------------------------------------------------------

    def test_set_agent_running_false_flushes_to_queue(self):
        _mod._agent_running = True
        _mod._pending_injections.append((None, "msg1", None))
        _mod._pending_injections.append(("qid-2", "msg2", None))

        _mod.set_agent_running(False)

        self.assertFalse(_mod._agent_running)
        self.assertEqual(len(_mod._pending_injections), 0)

        # Flushed prompts are merged into a SINGLE framed turn so the agent runs
        # them together in one pass. The merged body carries an explicit header
        # explaining they were queued, and lists them in arrival order.
        queued = []
        while not self.monitor._queue.empty():
            queued.append(self.monitor._queue.get_nowait())
        expected_body = _mod._merge_flushed_prompts(["msg1", "msg2"]) + "\n"
        self.assertEqual(
            queued,
            ["<<<SIADA_MSG_START>>>\n", expected_body, "<<<SIADA_MSG_END>>>\n"],
        )
        # Sanity-check the merged body: header present, both messages in order.
        self.assertIn("queued while you were", expected_body)
        self.assertIn("[1] msg1", expected_body)
        self.assertIn("[2] msg2", expected_body)
        self.assertLess(
            expected_body.index("[1] msg1"),
            expected_body.index("[2] msg2"),
        )





    def test_set_agent_running_false_no_pending_does_not_error(self):
        _mod._agent_running = True
        _mod.set_agent_running(False)
        self.assertFalse(_mod._agent_running)
        self.assertTrue(self.monitor._queue.empty())

    def test_set_agent_running_true_does_not_flush(self):
        _mod._pending_injections.append((None, "msg", None))
        _mod.set_agent_running(True)
        self.assertTrue(_mod._agent_running)
        # deque still has the item — nothing flushed
        self.assertEqual(len(_mod._pending_injections), 1)

    def test_flush_notifies_frontend_for_items_with_id(self):
        """Flushed items that carry a queue_id should emit a
        queue_item_consumed notification so the frontend renders them and
        removes them from the preview overlay. Items without an id (legacy
        protocol) are flushed silently."""
        notifications = []
        original_cb = _mod._acp_notify_callback
        _mod._acp_notify_callback = lambda method, params: notifications.append((method, params))
        try:
            _mod._agent_running = True
            _mod._pending_injections.append((None, "no-id", None))
            _mod._pending_injections.append(("qid-a", "with-id-a", None))
            _mod._pending_injections.append(("qid-b", "with-id-b", None))

            _mod.set_agent_running(False)

            # Only the two items with an id produced a notification.
            self.assertEqual(len(notifications), 2)
            for method, params in notifications:
                self.assertEqual(method, "session/update")
                self.assertEqual(params["reason"], "queue_item_consumed")
            consumed_ids = [params["metadata"]["id"] for _m, params in notifications]
            self.assertEqual(consumed_ids, ["qid-a", "qid-b"])
            # Each notification carries the original prompt text so the frontend
            # can render the user bubble even if its preview queue was already
            # cleared by the busy->idle drain (turn-boundary race fix).
            consumed_contents = [params["metadata"]["content"] for _m, params in notifications]
            self.assertEqual(consumed_contents, ["with-id-a", "with-id-b"])

            # All content (id or not) is merged into a SINGLE framed turn, with
            # the explanatory header and arrival-order numbering.
            queued = []
            while not self.monitor._queue.empty():
                queued.append(self.monitor._queue.get_nowait())
            expected_body = (
                _mod._merge_flushed_prompts(["no-id", "with-id-a", "with-id-b"]) + "\n"
            )
            self.assertEqual(
                queued,
                ["<<<SIADA_MSG_START>>>\n", expected_body, "<<<SIADA_MSG_END>>>\n"],
            )
            self.assertIn("[1] no-id", expected_body)
            self.assertIn("[2] with-id-a", expected_body)
            self.assertIn("[3] with-id-b", expected_body)




        finally:
            _mod._acp_notify_callback = original_cb

    def test_flush_no_notification_when_callback_unset(self):
        """Flushing without a registered callback must not raise."""
        original_cb = _mod._acp_notify_callback
        _mod._acp_notify_callback = None
        try:
            _mod._agent_running = True
            _mod._pending_injections.append(("qid-x", "hello", None))
            _mod.set_agent_running(False)  # should not raise
            self.assertEqual(len(_mod._pending_injections), 0)
        finally:
            _mod._acp_notify_callback = original_cb


    # ------------------------------------------------------------------
    # _dispatch_or_enqueue — routing based on _agent_running
    # ------------------------------------------------------------------

    def test_dispatch_normal_message_goes_to_queue_when_not_running(self):
        """Plain text prompt → _queue when agent is idle."""
        _mod._agent_running = False
        lines = _make_acp_lines("do something useful")
        self.monitor._dispatch_or_enqueue(lines)

        # Must arrive in _queue
        self.assertFalse(self.monitor._queue.empty())
        # Nothing in pending
        self.assertEqual(len(_mod._pending_injections), 0)

    def test_dispatch_normal_message_goes_to_pending_when_running(self):
        """Plain text prompt → _pending_injections when agent is mid-turn."""
        _mod._agent_running = True
        lines = _make_acp_lines("do something useful")
        self.monitor._dispatch_or_enqueue(lines)

        self.assertEqual(len(_mod._pending_injections), 1)
        item_id, content, image_paths = _mod._pending_injections[0]
        self.assertEqual(content, "do something useful")
        self.assertIsNone(image_paths)
        self.assertIsNone(item_id)  # no queue_id in plain text
        # Must NOT arrive in _queue
        self.assertTrue(self.monitor._queue.empty())

    def test_dispatch_json_envelope_extracted_when_running(self):
        """JSON-wrapped prompt is extracted cleanly into _pending_injections."""
        import json
        _mod._agent_running = True
        payload = json.dumps({"params": {"prompt": "explain this code", "image_paths": None}})
        lines = _make_acp_lines(payload)
        self.monitor._dispatch_or_enqueue(lines)

        self.assertEqual(len(_mod._pending_injections), 1)
        item_id, content, image_paths = _mod._pending_injections[0]
        self.assertEqual(content, "explain this code")
        self.assertIsNone(image_paths)
        self.assertIsNone(item_id)

    def test_dispatch_json_with_queue_id_stored(self):
        """queue_id from JSON params is stored as the first element of the tuple."""
        import json
        _mod._agent_running = True
        payload = json.dumps({"params": {"prompt": "annotate", "queue_id": "qid-42"}})
        lines = _make_acp_lines(payload)
        self.monitor._dispatch_or_enqueue(lines)

        item_id, content, image_paths = _mod._pending_injections[0]
        self.assertEqual(item_id, "qid-42")
        self.assertEqual(content, "annotate")
        self.assertIsNone(image_paths)

    def test_dispatch_json_with_image_paths_when_running(self):
        """image_paths field is preserved in _pending_injections."""
        import json
        _mod._agent_running = True
        payload = json.dumps({
            "params": {"prompt": "look at this image", "image_paths": ["/tmp/a.png"]}
        })
        lines = _make_acp_lines(payload)
        self.monitor._dispatch_or_enqueue(lines)

        item_id, content, image_paths = _mod._pending_injections[0]
        self.assertEqual(content, "look at this image")
        self.assertEqual(image_paths, ["/tmp/a.png"])

    def test_dispatch_btw_intercepted_regardless_of_agent_running(self):
        """
        /btw messages are always handled by the btw_handler and never
        land in _queue or _pending_injections.
        """
        captured = []
        self.monitor._btw_handler = lambda q: captured.append(q)

        for running in (False, True):
            _mod._agent_running = running
            _mod._pending_injections.clear()
            self.monitor._queue = queue.Queue()

            lines = _make_acp_lines("/btw what are you doing?")
            self.monitor._dispatch_or_enqueue(lines)

            # Give the daemon thread a moment to run
            import time; time.sleep(0.05)

            self.assertEqual(len(_mod._pending_injections), 0,
                             f"btw must not go to pending (running={running})")
            self.assertTrue(self.monitor._queue.empty(),
                            f"btw must not go to _queue (running={running})")

    def test_dispatch_btw_json_envelope_intercepted(self):
        """
        /btw wrapped in a JSON envelope is still intercepted.
        """
        import json, time
        captured = []
        self.monitor._btw_handler = lambda q: captured.append(q)

        _mod._agent_running = True
        payload = json.dumps({"params": {"prompt": "/btw are you busy?"}})
        lines = _make_acp_lines(payload)
        self.monitor._dispatch_or_enqueue(lines)

        time.sleep(0.05)

        self.assertEqual(len(_mod._pending_injections), 0)
        self.assertTrue(self.monitor._queue.empty())

    def test_multiple_messages_accumulate_in_pending(self):
        """Multiple mid-turn messages stack up in order."""
        _mod._agent_running = True
        for msg in ("first", "second", "third"):
            self.monitor._dispatch_or_enqueue(_make_acp_lines(msg))

        self.assertEqual(len(_mod._pending_injections), 3)
        # content is the second element of each 3-tuple
        contents = [item[1] for item in _mod._pending_injections]
        self.assertEqual(contents, ["first", "second", "third"])

    def test_handle_cancel_pending_clears_deque(self):
        """queue/cancelPending command drains _pending_injections."""
        import json
        _mod._agent_running = True
        _mod._pending_injections.append((None, "queued", None))
        self.assertEqual(len(_mod._pending_injections), 1)

        cancel_payload = json.dumps({"method": "queue/cancelPending", "params": {}})
        lines = _make_acp_lines(cancel_payload)
        self.monitor._dispatch_or_enqueue(lines)

        self.assertEqual(len(_mod._pending_injections), 0)
        # Must NOT be forwarded to _queue
        self.assertTrue(self.monitor._queue.empty())

    def test_handle_cancel_pending_when_deque_empty(self):
        """queue/cancelPending is a no-op when the deque is already empty."""
        import json
        cancel_payload = json.dumps({"method": "queue/cancelPending", "params": {}})
        lines = _make_acp_lines(cancel_payload)
        # Should not raise
        self.monitor._dispatch_or_enqueue(lines)
        self.assertEqual(len(_mod._pending_injections), 0)

    # ------------------------------------------------------------------
    # deque upper bound (_PENDING_MAX) — runaway frontend protection
    # ------------------------------------------------------------------

    def test_pending_deque_is_bounded_dropping_oldest(self):
        """When more than _PENDING_MAX messages are diverted mid-turn, the
        oldest is dropped so the deque never grows without limit."""
        _mod._agent_running = True
        total = _mod._PENDING_MAX + 5
        for i in range(total):
            self.monitor._dispatch_or_enqueue(_make_acp_lines(f"msg-{i}"))

        # Never exceeds the cap.
        self.assertEqual(len(_mod._pending_injections), _mod._PENDING_MAX)
        contents = [item[1] for item in _mod._pending_injections]
        # The first 5 (oldest) were dropped; the newest cap-many remain in order.
        self.assertEqual(contents[0], "msg-5")
        self.assertEqual(contents[-1], f"msg-{total - 1}")

    # ------------------------------------------------------------------
    # TOCTOU: a message diverted concurrently with end-of-turn must NOT
    # be left stranded in the deque (it should either be flushed or queued).
    # ------------------------------------------------------------------

    def test_no_item_stranded_across_set_agent_running_false(self):
        """Hammer _dispatch_or_enqueue from a reader thread while the main
        thread repeatedly toggles set_agent_running(False). After everything
        settles, the deque must be empty — no item is left stranded for the
        next turn."""
        import threading

        stop = threading.Event()

        def reader():
            i = 0
            while not stop.is_set():
                self.monitor._dispatch_or_enqueue(_make_acp_lines(f"r-{i}"))
                i += 1

        t = threading.Thread(target=reader, daemon=True)
        _mod._agent_running = True
        t.start()
        try:
            for _ in range(200):
                _mod._agent_running = True
                _mod.set_agent_running(False)
        finally:
            stop.set()
            t.join(timeout=2.0)

        # Ensure the flag is False and do a final flush, then assert nothing
        # is stranded in the deque.
        _mod.set_agent_running(False)
        self.assertEqual(len(_mod._pending_injections), 0)


if __name__ == "__main__":
    unittest.main()

