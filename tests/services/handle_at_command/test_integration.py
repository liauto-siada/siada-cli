"""
Core integration tests for HandleAtCommand functionality
"""

import unittest
import asyncio
import os
from pathlib import Path
from unittest.mock import Mock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from siada.services.handle_at_command import handle_at_command


class MockConfig:
    """Mock configuration for testing"""
    
    def __init__(self, root_dir: str = None):
        self.root_dir = root_dir or os.getcwd()
        self.target_directory = self.root_dir


class TestHandleAtCommandIntegration(unittest.IsolatedAsyncioTestCase):
    """Core integration tests for handle_at_command function"""
    
    async def asyncSetUp(self):
        """Set up test environment"""
        self.test_dir = Path(__file__).parent / "test_data"
        self.config = MockConfig(str(self.test_dir))
        self.mock_add_item = Mock()
        self.mock_debug_message = Mock()
    
    async def test_end_to_end_no_at_commands(self):
        """Test end-to-end processing with no @ commands"""
        result = await handle_at_command(
            query="Just some regular text",
            config=self.config,
            add_item=self.mock_add_item,
            on_debug_message=self.mock_debug_message,
            message_id=1
        )
        
        self.assertTrue(result.should_proceed)
        self.assertIsNotNone(result.processed_query)
        self.assertEqual(len(result.processed_query), 1)
        self.assertEqual(result.processed_query[0]['text'], "Just some regular text")
    
    async def test_end_to_end_single_file(self):
        """Test end-to-end processing with single file"""
        result = await handle_at_command(
            query="Please explain @sample.py",
            config=self.config,
            add_item=self.mock_add_item,
            on_debug_message=self.mock_debug_message,
            message_id=2
        )
        
        self.assertTrue(result.should_proceed)
        self.assertIsNotNone(result.processed_query)
        # Text file contents are merged into a single text part together with
        # the user query, so the referenced file block lives inside user_input.
        self.assertEqual(len(result.processed_query), 1)
        
        # The referenced-file block is merged into the single text part. Its
        # payload is the file structure entry (ReadManyFilesTool returns the
        # file tree, not raw file contents).
        content_text = ''.join([part['text'] for part in result.processed_query if isinstance(part, dict) and 'text' in part])
        self.assertIn("--- Content from referenced files ---", content_text)
        self.assertIn("=== File Structure ===", content_text)
        self.assertIn("sample.py", content_text)
    
    async def test_end_to_end_multiple_files(self):
        """Test end-to-end processing with multiple files"""
        result = await handle_at_command(
            query="Compare @sample.py and @config.json",
            config=self.config,
            add_item=self.mock_add_item,
            on_debug_message=self.mock_debug_message,
            message_id=3
        )
        
        self.assertTrue(result.should_proceed)
        self.assertIsNotNone(result.processed_query)
        
        # Should contain the structure entries for both referenced files
        content_text = ''.join([part['text'] for part in result.processed_query if isinstance(part, dict) and 'text' in part])
        self.assertIn("sample.py", content_text)  # From sample.py
        self.assertIn("config.json", content_text)  # From config.json
    
    async def test_end_to_end_performance(self):
        """Test end-to-end processing performance"""
        import time
        
        start_time = time.time()
        
        result = await handle_at_command(
            query="Process @sample.py and @config.json",
            config=self.config,
            add_item=self.mock_add_item,
            on_debug_message=self.mock_debug_message,
            message_id=8
        )
        
        end_time = time.time()
        processing_time = end_time - start_time
        
        # Should complete within reasonable time (5 seconds)
        self.assertLess(processing_time, 5.0)
        self.assertTrue(result.should_proceed)


class TestHandleAtCommandUserInputTag(unittest.IsolatedAsyncioTestCase):
    """@-expansion must work on ``<user_input>``-wrapped queries.

    Every entry point wraps the human's literal text in a ``<user_input>``
    tag before the agent runs @-expansion (conversation_turn.py,
    nointeractive_controller.py, acp_server/runtime.py,
    lark_agent_executor.py). The parser stops paths at whitespace only, so
    without splitting the tag off first a trailing ``@foo.py</user_input>``
    parses as one path and is then rejected for containing '<' / '>' —
    silently skipping expansion. These tests pin that behavior.
    """

    async def asyncSetUp(self):
        self.test_dir = Path(__file__).parent / "test_data"
        self.config = MockConfig(str(self.test_dir))
        self.mock_add_item = Mock()
        self.mock_debug_message = Mock()

    async def _run(self, query: str):
        result = await handle_at_command(
            query=query,
            config=self.config,
            add_item=self.mock_add_item,
            on_debug_message=self.mock_debug_message,
            message_id=1,
        )
        text = ''.join(
            part['text'] for part in (result.processed_query or [])
            if isinstance(part, dict) and 'text' in part
        )
        return result, text

    async def test_at_path_at_end_of_wrapped_query_is_expanded(self):
        """The regression: @ reference immediately before ``</user_input>``."""
        result, text = await self._run("<user_input>Please explain @sample.py</user_input>")

        self.assertTrue(result.should_proceed)
        self.assertIn("--- Content from referenced files ---", text)
        self.assertIn("sample.py", text)

    async def test_at_path_mid_wrapped_query_is_expanded(self):
        """A trailing word already worked before; it must keep working."""
        result, text = await self._run("<user_input>Please explain @sample.py thanks</user_input>")

        self.assertTrue(result.should_proceed)
        self.assertIn("--- Content from referenced files ---", text)

    async def test_user_input_tag_wraps_the_expanded_content(self):
        """The tag must survive, and the file block must land INSIDE it.

        The @-expanded content is what the user asked for, so it belongs
        under the ``<user_input>`` label rather than dangling after the
        closing tag.
        """
        _, text = await self._run("<user_input>Please explain @sample.py</user_input>")

        self.assertTrue(text.startswith("<user_input>"))
        self.assertIn("</user_input>", text)
        # File block sits before the closing tag, i.e. inside the tag.
        self.assertLess(
            text.index("--- Content from referenced files ---"),
            text.index("</user_input>"),
        )
        inner = text[len("<user_input>"):text.rindex("</user_input>")]
        self.assertIn("--- Content from referenced files ---", inner)
        self.assertIn("--- End of content ---", inner)

    async def test_context_injected_after_closing_tag_stays_outside(self):
        """Callers may append their own blocks after the tag (Feishu IM
        context, ACP playbook suffix). Those must stay outside the tag and
        be handed back intact."""
        suffix = "\n\n<!--IM_CONTEXT_INJECTION:BEGIN-->\nquoted body\n<!--IM_CONTEXT_INJECTION:END-->"
        _, text = await self._run(f"<user_input>explain @sample.py</user_input>{suffix}")

        self.assertTrue(text.endswith(suffix))
        self.assertIn("quoted body", text)
        # The file block is inside the tag; the IM block remains after it.
        self.assertLess(
            text.index("--- Content from referenced files ---"),
            text.index("</user_input>"),
        )
        self.assertLess(
            text.index("</user_input>"),
            text.index("<!--IM_CONTEXT_INJECTION:BEGIN-->"),
        )

    async def test_no_empty_file_contents_header(self):
        """``=== File Contents ===`` must not be emitted.

        ``process_files_without_read_content`` deliberately reads no file
        bodies, so that header always sat above an empty section.
        """
        _, text = await self._run("<user_input>Please explain @sample.py</user_input>")

        self.assertNotIn("=== File Contents ===", text)
        self.assertIn("=== File Structure ===", text)
        # The tree must start on its own line, not run into the header.
        self.assertIn(
            "--- Content from referenced files ---\n=== File Structure ===", text
        )

    async def test_wrapped_query_without_at_commands_is_unchanged(self):
        result, text = await self._run("<user_input>no at commands here</user_input>")

        self.assertTrue(result.should_proceed)
        self.assertEqual(text, "<user_input>no at commands here</user_input>")

    async def test_unwrapped_query_still_works(self):
        """Untagged callers must keep the exact previous behavior."""
        result, text = await self._run("Please explain @sample.py")

        self.assertTrue(result.should_proceed)
        self.assertNotIn("<user_input>", text)
        self.assertIn("--- Content from referenced files ---", text)


if __name__ == '__main__':
    unittest.main(verbosity=2)
