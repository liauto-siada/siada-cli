"""Unit tests for FactStoreFormatter and FactFeedbackFormatter.

Covers:
1. fact_store rendering for each supported action (TUI ``format_input``).
2. fact_store IM rendering (``format_input_im``) matches the TUI output.
3. fact_feedback rendering with / without comment.
4. Malformed JSON falls back to a generic, non-raising label.
5. Both tools are registered in ToolCallFormatterFactory.
6. The IM batcher classifies both tools into the "memory" category.
"""

import json
import unittest

from siada.tools.tool_call_format.formatters import (
    FactStoreFormatter,
    FactFeedbackFormatter,
)
# Importing the package triggers auto-registration of all formatters.
from siada.tools.tool_call_format import ToolCallFormatterFactory
from siada.tools.tool_call_format.tool_call_batcher import classify_tool


class TestFactStoreFormatter(unittest.TestCase):
    """FactStoreFormatter must render the action plus its key argument."""

    def setUp(self):
        self.fmt = FactStoreFormatter()

    def _format(self, args: dict):
        return self.fmt.format_input("c1", "fact_store", json.dumps(args))

    def test_add_with_category(self):
        content, complete = self._format(
            {"action": "add", "category": "project", "content": "Phoenix uses Postgres 14"}
        )
        self.assertEqual(content, "Fact memory [add/project] Phoenix uses Postgres 14")
        self.assertTrue(complete)

    def test_add_without_category(self):
        content, _ = self._format({"action": "add", "content": "a bare fact"})
        self.assertEqual(content, "Fact memory [add] a bare fact")

    def test_add_long_content_is_truncated(self):
        long_content = "x" * 100
        content, _ = self._format({"action": "add", "content": long_content})
        self.assertTrue(content.startswith("Fact memory [add] "))
        self.assertIn("...", content)
        # 60 char preview + ellipsis
        self.assertIn("x" * 60 + "...", content)

    def test_search(self):
        content, _ = self._format({"action": "search", "query": "what db does Phoenix use"})
        self.assertEqual(content, "Fact memory [search] what db does Phoenix use")

    def test_probe(self):
        content, _ = self._format({"action": "probe", "entity": "Phoenix"})
        self.assertEqual(content, "Fact memory [probe] Phoenix")

    def test_related(self):
        content, _ = self._format({"action": "related", "entity": "Postgres"})
        self.assertEqual(content, "Fact memory [related] Postgres")

    def test_reason_joins_entities(self):
        content, _ = self._format({"action": "reason", "entities": ["Phoenix", "Postgres"]})
        self.assertEqual(content, "Fact memory [reason] Phoenix, Postgres")

    def test_contradict(self):
        content, _ = self._format({"action": "contradict"})
        self.assertEqual(content, "Fact memory [contradict]")

    def test_update_with_fact_id(self):
        content, _ = self._format({"action": "update", "fact_id": 12, "content": "new text"})
        self.assertEqual(content, "Fact memory [update] #12 new text")

    def test_update_without_fact_id(self):
        content, _ = self._format({"action": "update", "content": "new text"})
        self.assertEqual(content, "Fact memory [update] new text")

    def test_remove(self):
        content, _ = self._format({"action": "remove", "fact_id": 7})
        self.assertEqual(content, "Fact memory [remove] #7")

    def test_list_with_category(self):
        content, _ = self._format({"action": "list", "category": "tool"})
        self.assertEqual(content, "Fact memory [list] tool")

    def test_list_without_category(self):
        content, _ = self._format({"action": "list"})
        self.assertEqual(content, "Fact memory [list]")

    def test_im_matches_standard(self):
        args = json.dumps({"action": "add", "category": "env", "content": "uses Python 3.12"})
        std, _ = self.fmt.format_input("c1", "fact_store", args)
        im, complete = self.fmt.format_input_im("c1", "fact_store", args)
        self.assertEqual(std, im)
        self.assertTrue(complete)

    def test_malformed_json_does_not_raise(self):
        content, complete = self.fmt.format_input("c1", "fact_store", "{bad json")
        self.assertEqual(content, "Fact memory")
        self.assertTrue(complete)
        im_content, _ = self.fmt.format_input_im("c1", "fact_store", "{bad json")
        self.assertEqual(im_content, "Fact memory")


class TestFactFeedbackFormatter(unittest.TestCase):
    """FactFeedbackFormatter renders fact id, action and optional comment."""

    def setUp(self):
        self.fmt = FactFeedbackFormatter()

    def _format(self, args: dict):
        return self.fmt.format_input("c1", "fact_feedback", json.dumps(args))

    def test_basic(self):
        content, complete = self._format({"fact_id": 12, "action": "helpful"})
        self.assertEqual(content, "Fact feedback #12 helpful")
        self.assertTrue(complete)

    def test_with_comment(self):
        content, _ = self._format(
            {"fact_id": 3, "action": "correct", "comment": "user confirmed"}
        )
        self.assertEqual(content, "Fact feedback #3 correct: user confirmed")

    def test_long_comment_truncated(self):
        content, _ = self._format(
            {"fact_id": 1, "action": "unhelpful", "comment": "y" * 100}
        )
        self.assertTrue(content.startswith("Fact feedback #1 unhelpful: "))
        self.assertIn("...", content)

    def test_missing_fact_id(self):
        content, _ = self._format({"action": "helpful"})
        self.assertEqual(content, "Fact feedback helpful")

    def test_im_matches_standard(self):
        args = json.dumps({"fact_id": 5, "action": "helpful"})
        std, _ = self.fmt.format_input("c1", "fact_feedback", args)
        im, _ = self.fmt.format_input_im("c1", "fact_feedback", args)
        self.assertEqual(std, im)

    def test_malformed_json_does_not_raise(self):
        content, complete = self.fmt.format_input("c1", "fact_feedback", "{bad json")
        self.assertEqual(content, "Fact feedback")
        self.assertTrue(complete)


class TestFactFormatterRegistration(unittest.TestCase):
    """The formatters must be discoverable via the factory and IM batcher."""

    def test_factory_returns_correct_formatter(self):
        self.assertIsInstance(
            ToolCallFormatterFactory.get_formatter("fact_store"), FactStoreFormatter
        )
        self.assertIsInstance(
            ToolCallFormatterFactory.get_formatter("fact_feedback"), FactFeedbackFormatter
        )

    def test_supported_function_names(self):
        self.assertEqual(FactStoreFormatter().supported_function, "fact_store")
        self.assertEqual(FactFeedbackFormatter().supported_function, "fact_feedback")

    def test_im_batcher_classifies_as_memory(self):
        self.assertEqual(classify_tool("fact_store"), "memory")
        self.assertEqual(classify_tool("fact_feedback"), "memory")


if __name__ == "__main__":
    unittest.main()
