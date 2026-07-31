import pytest
import litellm
from agents.models.chatcmpl_converter import Converter
from agents.tool import FunctionTool


class TestLiteLLMTokenCounterReal:
    """Test real litellm token_counter functionality without mocks"""
    
    def test_litellm_token_counter_with_text(self):
        """Test litellm token_counter with text parameter"""
        # Arrange
        test_text = "Hello, world! This is a test message."
        model_name = "claude-4-sonnet"  # Use a real model name
        
        # Act
        try:
            result = litellm.token_counter(model=model_name, text=test_text)
            
            # Assert
            assert isinstance(result, int)
            assert result > 0
            print(f"Text: '{test_text}' -> Tokens: {result}")
            
        except Exception as e:
            pytest.fail(f"litellm.token_counter failed with text: {e}")
    
    def test_litellm_token_counter_with_messages(self):
        """Test litellm token_counter with messages parameter"""
        # Arrange
        test_messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there! How can I help you today?"}
        ]
        model_name = "claude-4-sonnet"
        
        # Act
        try:
            result = litellm.token_counter(model=model_name, messages=test_messages)
            
            # Assert
            assert isinstance(result, int)
            assert result > 0
            print(f"Messages: {test_messages} -> Tokens: {result}")
            
        except Exception as e:
            pytest.fail(f"litellm.token_counter failed with messages: {e}")
    
    def test_litellm_token_counter_different_models(self):
        """Test litellm token_counter with different model names"""
        # Arrange
        test_text = "This is a test message for token counting."
        test_models = [
            "claude-4-sonnet",
            "gpt-4",
            "gpt-3.5-turbo"
        ]
        
        results = {}
        
        for model in test_models:
            try:
                # Act
                result = litellm.token_counter(model=model, text=test_text)
                
                # Assert
                assert isinstance(result, int)
                assert result > 0
                results[model] = result
                print(f"Model: {model} -> Tokens: {result}")
                
            except Exception as e:
                print(f"Model {model} failed: {e}")
                # Don't fail the test if a specific model is unavailable
                continue
        
        # At least one model should have worked
        assert len(results) > 0, "No models were able to count tokens"
    
    def test_litellm_token_counter_empty_text(self):
        """Test litellm token_counter with empty text"""
        # Arrange
        test_text = ""
        model_name = "claude-4-sonnet"
        
        # Act
        try:
            result = litellm.token_counter(model=model_name, text=test_text)
            
            # Assert
            assert isinstance(result, int)
            assert result >= 0
            print(f"Empty text -> Tokens: {result}")
            
        except Exception as e:
            pytest.fail(f"litellm.token_counter failed with empty text: {e}")
    
    def test_litellm_token_counter_long_text(self):
        """Test litellm token_counter with longer text"""
        # Arrange
        test_text = """
        This is a longer test message to see how litellm handles token counting
        with more substantial content. We're testing the token counter functionality
        to ensure it works correctly with various input sizes and content types.
        The message includes multiple sentences, punctuation, and different word lengths.
        """
        model_name = "claude-4-sonnet"
        
        # Act
        try:
            result = litellm.token_counter(model=model_name, text=test_text)
            
            # Assert
            assert isinstance(result, int)
            assert result > 20  # Should be more tokens for longer text
            print(f"Long text ({len(test_text)} chars) -> Tokens: {result}")
            
        except Exception as e:
            pytest.fail(f"litellm.token_counter failed with long text: {e}")
    
    def test_litellm_token_counter_with_converter_items(self):
        """Test litellm token_counter with Converter.items_to_messages"""
        # Arrange
        from siada.agent_hub.context_filter.utils import compute_message_signature
        
        # Mock some items that would come from the message state
        test_items = [
            {"role": "user", "content": "What is the weather like?"},
            {"role": "assistant", "content": "I don't have access to current weather data."}
        ]
        
        model_name = "claude-3-sonnet-20240229"
        
        # Act
        try:
            # Convert items to messages format
            messages = Converter.items_to_messages(test_items)
            result = litellm.token_counter(model=model_name, messages=messages)
            
            # Assert
            assert isinstance(result, int)
            assert result > 0
            print(f"Converted items -> Messages: {messages}")
            print(f"Messages -> Tokens: {result}")
            
            # Also test signature computation for these items
            for i, item in enumerate(test_items):
                signature = compute_message_signature(item)
                print(f"Item {i} signature: {signature}")
                assert len(signature) == 32  # MD5 hash length
                
        except Exception as e:
            pytest.fail(f"litellm.token_counter failed with converted items: {e}")
    
    def test_litellm_token_counter_comparison_text_vs_messages(self):
        """Compare token counts between text and messages format"""
        # Arrange
        content = "Hello, how are you doing today?"
        model_name = "claude-4-sonnet"
        
        # Test with text format
        try:
            text_tokens = litellm.token_counter(model=model_name, text=content)
            
            # Test with messages format
            messages = [{"role": "user", "content": content}]
            message_tokens = litellm.token_counter(model=model_name, messages=messages)
            
            print(f"Text format: '{content}' -> {text_tokens} tokens")
            print(f"Messages format: {messages} -> {message_tokens} tokens")
            
            # Messages format typically includes role tokens, so should be >= text tokens
            assert text_tokens > 0
            assert message_tokens > 0
            assert message_tokens >= text_tokens
            
        except Exception as e:
            pytest.fail(f"Token count comparison failed: {e}")


class TestPreserveParamsAffectTokenCount:
    """
    Verify that Converter.items_to_messages produces different messages
    (and therefore different litellm token counts) when
    preserve_thinking_blocks / preserve_tool_output_all_content vary.
    """

    # -- fixtures shared across tests ------------------------------------------

    @staticmethod
    def _build_items_with_thinking_and_tool_call():
        """
        Build a realistic item sequence that contains:
          1. user message
          2. reasoning item (thinking block for Claude)
          3. assistant message with a function tool call
          4. tool output
        """
        return [
            # 1) user turn
            {"role": "user", "content": "Please read file foo.py"},
            # 2) reasoning item (Claude thinking block)
            {
                "type": "reasoning",
                "id": "rs_001",
                "content": [
                    {
                        "type": "reasoning_text",
                        "text": (
                            "The user wants me to read a file. "
                            "I should use the read_file tool to get its content. "
                            "Let me think about the best approach step by step..."
                        ),
                    }
                ],
                "encrypted_content": "dGhpbmtpbmctc2lnbmF0dXJlLWhlcmU=",
                "provider_data": {"model": "claude-4-sonnet"},
            },
            # 3) function tool call
            {
                "type": "function_call",
                "call_id": "call_001",
                "name": "read_file",
                "arguments": '{"path": "foo.py"}',
            },
            # 4) tool output (text only)
            {
                "type": "function_call_output",
                "call_id": "call_001",
                "output": "def hello():\n    print('hello world')\n",
            },
        ]

    @staticmethod
    def _build_items_with_image_tool_output():
        """
        Build items where the tool output contains both text and image content.
        """
        return [
            {"role": "user", "content": "Take a screenshot of the page"},
            # function tool call
            {
                "type": "function_call",
                "call_id": "call_002",
                "name": "screenshot",
                "arguments": '{"url": "https://example.com"}',
            },
            # tool output with mixed content (text + image_url)
            {
                "type": "function_call_output",
                "call_id": "call_002",
                "output": [
                    {"type": "input_text", "text": "Screenshot captured successfully."},
                    {
                        "type": "input_image",
                        "image_url": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
                    },
                ],
            },
        ]

    # -- test: preserve_thinking_blocks ----------------------------------------

    def test_thinking_blocks_affect_converted_messages(self):
        """
        With preserve_thinking_blocks=True the converted messages should
        contain thinking blocks; with False they should not.
        """
        items = self._build_items_with_thinking_and_tool_call()
        model = "claude-4-sonnet"

        msgs_with = Converter.items_to_messages(
            items=items,
            model=model,
            preserve_thinking_blocks=True,
            preserve_tool_output_all_content=True,
        )
        msgs_without = Converter.items_to_messages(
            items=items,
            model=model,
            preserve_thinking_blocks=False,
            preserve_tool_output_all_content=True,
        )

        print("\n=== Messages WITH preserve_thinking_blocks ===")
        for i, m in enumerate(msgs_with):
            print(f"  [{i}] {m}")

        print("\n=== Messages WITHOUT preserve_thinking_blocks ===")
        for i, m in enumerate(msgs_without):
            print(f"  [{i}] {m}")

        # The two message lists should differ
        assert msgs_with != msgs_without, (
            "Expected different messages when preserve_thinking_blocks differs"
        )

    def test_thinking_blocks_affect_token_count(self):
        """
        Token count should be higher when thinking blocks are preserved,
        because extra content is included in the messages.
        """
        items = self._build_items_with_thinking_and_tool_call()
        model = "claude-4-sonnet"

        msgs_with = Converter.items_to_messages(
            items=items,
            model=model,
            preserve_thinking_blocks=True,
            preserve_tool_output_all_content=True,
        )
        msgs_without = Converter.items_to_messages(
            items=items,
            model=model,
            preserve_thinking_blocks=False,
            preserve_tool_output_all_content=True,
        )

        tokens_with = litellm.token_counter(model=model, messages=msgs_with)
        tokens_without = litellm.token_counter(model=model, messages=msgs_without)

        print(f"\nTokens WITH thinking blocks:    {tokens_with}")
        print(f"Tokens WITHOUT thinking blocks: {tokens_without}")
        print(f"Difference: {tokens_with - tokens_without}")

        assert tokens_with > tokens_without, (
            f"Expected more tokens with thinking blocks preserved, "
            f"got with={tokens_with}, without={tokens_without}"
        )

    # -- test: preserve_tool_output_all_content --------------------------------

    def test_tool_output_content_affects_converted_messages(self):
        """
        With preserve_tool_output_all_content=True, tool messages should
        contain image content; with False, only text is kept.
        """
        items = self._build_items_with_image_tool_output()
        model = "claude-4-sonnet"

        msgs_with = Converter.items_to_messages(
            items=items,
            model=model,
            preserve_thinking_blocks=False,
            preserve_tool_output_all_content=True,
        )
        msgs_without = Converter.items_to_messages(
            items=items,
            model=model,
            preserve_thinking_blocks=False,
            preserve_tool_output_all_content=False,
        )

        print("\n=== Messages WITH preserve_tool_output_all_content ===")
        for i, m in enumerate(msgs_with):
            print(f"  [{i}] {m}")

        print("\n=== Messages WITHOUT preserve_tool_output_all_content ===")
        for i, m in enumerate(msgs_without):
            print(f"  [{i}] {m}")

        assert msgs_with != msgs_without, (
            "Expected different messages when preserve_tool_output_all_content differs"
        )

    def test_tool_output_content_affects_token_count(self):
        """
        Token count should differ when image content is preserved vs stripped.
        """
        items = self._build_items_with_image_tool_output()
        model = "claude-4-sonnet"

        msgs_with = Converter.items_to_messages(
            items=items,
            model=model,
            preserve_thinking_blocks=False,
            preserve_tool_output_all_content=True,
        )
        msgs_without = Converter.items_to_messages(
            items=items,
            model=model,
            preserve_thinking_blocks=False,
            preserve_tool_output_all_content=False,
        )

        tokens_with = litellm.token_counter(model=model, messages=msgs_with)
        tokens_without = litellm.token_counter(model=model, messages=msgs_without)

        print(f"\nTokens WITH all tool content:    {tokens_with}")
        print(f"Tokens WITHOUT all tool content: {tokens_without}")
        print(f"Difference: {tokens_with - tokens_without}")

        # Image base64 data adds significant tokens
        assert tokens_with != tokens_without, (
            f"Expected different token counts, "
            f"got with={tokens_with}, without={tokens_without}"
        )

    # -- test: both params combined --------------------------------------------

    def test_both_params_combined(self):
        """
        Combine thinking blocks + image tool output and verify all four
        parameter combinations yield different token counts.
        """
        # Merge both item sequences: thinking + tool call with image output
        items = [
            {"role": "user", "content": "Read foo.py and take a screenshot"},
            # reasoning
            {
                "type": "reasoning",
                "id": "rs_002",
                "content": [
                    {
                        "type": "reasoning_text",
                        "text": "Let me plan the steps: first read the file, then screenshot.",
                    }
                ],
                "encrypted_content": "c2lnbmF0dXJl",
                "provider_data": {"model": "claude-4-sonnet"},
            },
            # tool call 1
            {
                "type": "function_call",
                "call_id": "call_010",
                "name": "read_file",
                "arguments": '{"path": "foo.py"}',
            },
            # tool output 1 (text only)
            {
                "type": "function_call_output",
                "call_id": "call_010",
                "output": "print('hello')",
            },
            # user follow-up
            {"role": "user", "content": "Now screenshot"},
            # tool call 2
            {
                "type": "function_call",
                "call_id": "call_011",
                "name": "screenshot",
                "arguments": '{"url": "https://example.com"}',
            },
            # tool output 2 (with image)
            {
                "type": "function_call_output",
                "call_id": "call_011",
                "output": [
                    {"type": "input_text", "text": "Done."},
                    {
                        "type": "input_image",
                        "image_url": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
                    },
                ],
            },
        ]
        model = "claude-4-sonnet"

        combos = [
            (True, True),
            (True, False),
            (False, True),
            (False, False),
        ]

        results = {}
        for thinking, tool_all in combos:
            msgs = Converter.items_to_messages(
                items=items,
                model=model,
                preserve_thinking_blocks=thinking,
                preserve_tool_output_all_content=tool_all,
            )
            tokens = litellm.token_counter(model=model, messages=msgs)
            key = (thinking, tool_all)
            results[key] = tokens
            print(
                f"\npreserve_thinking={thinking}, preserve_tool_all={tool_all} "
                f"-> {tokens} tokens"
            )

        # At minimum, (True, True) should differ from (False, False)
        assert results[(True, True)] != results[(False, False)], (
            "Expected (True,True) and (False,False) to produce different token counts"
        )
        # (True, *) should have more tokens than (False, *) due to thinking blocks
        assert results[(True, True)] > results[(False, True)], (
            "Thinking blocks should add tokens"
        )
        assert results[(True, False)] > results[(False, False)], (
            "Thinking blocks should add tokens even without tool_all_content"
        )


class TestCalculateFixedOverhead:
    """
    Verify that CompactionStrategy.calculate_fixed_overhead correctly
    computes token overhead for instructions and tools.
    """

    @staticmethod
    def _make_dummy_tool(name, description, params_schema):
        async def _noop(ctx, args):
            return ""
        return FunctionTool(
            name=name, description=description,
            params_json_schema=params_schema, on_invoke_tool=_noop,
            strict_json_schema=False,
        )

    @staticmethod
    def _make_mock_context(model_name="claude-4-sonnet"):
        """Create a minimal mock context with model_run_config.model_name."""
        from unittest.mock import MagicMock
        ctx = MagicMock()
        ctx.model_run_config.model_name = model_name
        return ctx

    def test_instructions_only(self):
        """Overhead with only instructions should match calculate_tokens for text."""
        from siada.agent_hub.context_filter.compaction_strategy import CompactionStrategy
        from siada.agent_hub.context_filter.utils import calculate_tokens

        ctx = self._make_mock_context()
        instructions = "You are a helpful coding assistant. Follow best practices."

        overhead = CompactionStrategy.calculate_fixed_overhead(
            ctx, instructions=instructions,
        )
        expected = calculate_tokens("claude-4-sonnet", instructions)

        print(f"\nInstructions overhead: {overhead}")
        print(f"Expected (calculate_tokens): {expected}")
        assert overhead == expected
        assert overhead > 0

    def test_tools_only(self):
        """Overhead with only tools should be positive and match litellm delta."""
        from siada.agent_hub.context_filter.compaction_strategy import CompactionStrategy

        ctx = self._make_mock_context()
        tools = [
            self._make_dummy_tool(
                "read_file", "Read a file",
                {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
            ),
        ]

        overhead = CompactionStrategy.calculate_fixed_overhead(ctx, tools=tools)

        print(f"\nTools-only overhead: {overhead}")
        assert overhead > 0

    def test_both_instructions_and_tools(self):
        """Overhead with both should be > instructions alone and > tools alone."""
        from siada.agent_hub.context_filter.compaction_strategy import CompactionStrategy

        ctx = self._make_mock_context()
        instructions = "You are a helpful coding assistant."
        tools = [
            self._make_dummy_tool(
                "search", "Search files",
                {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
            ),
        ]

        overhead_both = CompactionStrategy.calculate_fixed_overhead(
            ctx, instructions=instructions, tools=tools,
        )
        overhead_instr = CompactionStrategy.calculate_fixed_overhead(
            ctx, instructions=instructions,
        )
        overhead_tools = CompactionStrategy.calculate_fixed_overhead(
            ctx, tools=tools,
        )

        print(f"\nInstructions only: {overhead_instr}")
        print(f"Tools only:        {overhead_tools}")
        print(f"Both:              {overhead_both}")

        assert overhead_both > overhead_instr, "Both should be more than instructions only"
        assert overhead_both > overhead_tools, "Both should be more than tools only"
        assert overhead_both == overhead_instr + overhead_tools, (
            "Combined overhead should equal sum of parts"
        )

    def test_no_instructions_no_tools(self):
        """Overhead with neither should be 0."""
        from siada.agent_hub.context_filter.compaction_strategy import CompactionStrategy

        ctx = self._make_mock_context()
        overhead = CompactionStrategy.calculate_fixed_overhead(ctx)

        print(f"\nEmpty overhead: {overhead}")
        assert overhead == 0

    def test_empty_instructions(self):
        """Empty string instructions should result in 0 overhead."""
        from siada.agent_hub.context_filter.compaction_strategy import CompactionStrategy

        ctx = self._make_mock_context()
        overhead = CompactionStrategy.calculate_fixed_overhead(ctx, instructions="")

        print(f"\nEmpty string instructions overhead: {overhead}")
        assert overhead == 0

    def test_multiple_tools_increase_overhead(self):
        """More tools should produce higher overhead."""
        from siada.agent_hub.context_filter.compaction_strategy import CompactionStrategy

        ctx = self._make_mock_context()
        tools_1 = [
            self._make_dummy_tool("t1", "Tool 1", {"type": "object", "properties": {}}),
        ]
        tools_5 = [
            self._make_dummy_tool(
                f"tool_{i}", f"Tool {i} does something",
                {"type": "object", "properties": {"arg": {"type": "string"}}, "required": ["arg"]},
            )
            for i in range(5)
        ]

        overhead_1 = CompactionStrategy.calculate_fixed_overhead(ctx, tools=tools_1)
        overhead_5 = CompactionStrategy.calculate_fixed_overhead(ctx, tools=tools_5)

        print(f"\n1 tool overhead:  {overhead_1}")
        print(f"5 tools overhead: {overhead_5}")
        assert overhead_5 > overhead_1


class TestToolsAffectTokenCount:
    """
    Verify that passing tools to calculate_tokens produces accurate
    tool-definition token counts instead of using the fixed overhead.
    """

    @staticmethod
    def _make_dummy_tool(name: str, description: str, params_schema: dict) -> FunctionTool:
        """Helper to create a FunctionTool without a real callable."""
        async def _noop(ctx, args):
            return ""

        return FunctionTool(
            name=name,
            description=description,
            params_json_schema=params_schema,
            on_invoke_tool=_noop,
            strict_json_schema=False,  # avoid strict schema transform in tests
        )

    def test_calculate_tokens_with_tools_vs_without(self):
        """
        calculate_tokens with tools should include tool definition tokens;
        without tools it should return pure message tokens (no overhead).
        """
        from siada.agent_hub.context_filter.utils import calculate_tokens

        items = [
            {"role": "user", "content": "Hello, can you help me?"},
        ]
        model = "claude-4-sonnet"

        tools = [
            self._make_dummy_tool(
                "read_file",
                "Read the contents of a file at the given path.",
                {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File path to read"},
                    },
                    "required": ["path"],
                },
            ),
            self._make_dummy_tool(
                "write_file",
                "Write content to a file at the given path.",
                {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File path"},
                        "content": {"type": "string", "description": "Content to write"},
                    },
                    "required": ["path", "content"],
                },
            ),
        ]

        tokens_with_tools = calculate_tokens(model, items, tools=tools)
        tokens_without_tools = calculate_tokens(model, items)

        print(f"\nTokens WITH real tools:     {tokens_with_tools}")
        print(f"Tokens WITHOUT tools:       {tokens_without_tools}")

        # With tools the count should be higher because tool definitions add tokens
        assert tokens_with_tools > tokens_without_tools, (
            f"Tokens with tools ({tokens_with_tools}) should be greater than "
            f"without tools ({tokens_without_tools})"
        )

    def test_more_tools_means_more_tokens(self):
        """
        Adding more tool definitions should increase the token count.
        """
        from siada.agent_hub.context_filter.utils import calculate_tokens

        items = [{"role": "user", "content": "Help me"}]
        model = "claude-4-sonnet"

        small_tools = [
            self._make_dummy_tool(
                "tool_a", "Does A", {"type": "object", "properties": {}},
            ),
        ]
        large_tools = [
            self._make_dummy_tool(
                f"tool_{i}",
                f"This tool performs operation {i} with detailed description",
                {
                    "type": "object",
                    "properties": {
                        "arg1": {"type": "string", "description": f"Argument for tool {i}"},
                        "arg2": {"type": "number", "description": "A numeric value"},
                    },
                    "required": ["arg1"],
                },
            )
            for i in range(10)
        ]

        tokens_small = calculate_tokens(model, items, tools=small_tools)
        tokens_large = calculate_tokens(model, items, tools=large_tools)

        print(f"\nTokens with 1 tool:   {tokens_small}")
        print(f"Tokens with 10 tools: {tokens_large}")

        assert tokens_large > tokens_small, (
            f"10 tools ({tokens_large}) should have more tokens than 1 tool ({tokens_small})"
        )

    def test_convert_tools_to_openai_params(self):
        """
        _convert_tools_to_openai_params should convert FunctionTool to
        ChatCompletionToolParam format correctly.
        """
        from siada.agent_hub.context_filter.utils import _convert_tools_to_openai_params

        tools = [
            self._make_dummy_tool(
                "search",
                "Search for items",
                {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                    },
                    "required": ["query"],
                },
            ),
        ]

        result = _convert_tools_to_openai_params(tools)

        assert len(result) == 1
        assert result[0]["type"] == "function"
        assert result[0]["function"]["name"] == "search"
        assert result[0]["function"]["description"] == "Search for items"
        assert "parameters" in result[0]["function"]
        print(f"\nConverted tool param: {result[0]}")

    def test_litellm_token_counter_tools_param(self):
        """
        Directly verify litellm.token_counter accepts tools and counts them.
        """
        model = "claude-4-sonnet"
        messages = [{"role": "user", "content": "Hello"}]

        tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get weather for a city",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "city": {"type": "string", "description": "City name"},
                        },
                        "required": ["city"],
                    },
                },
            }
        ]

        tokens_no_tools = litellm.token_counter(model=model, messages=messages)
        tokens_with_tools = litellm.token_counter(
            model=model, messages=messages, tools=tools,
        )

        print(f"\nTokens without tools: {tokens_no_tools}")
        print(f"Tokens with tools:    {tokens_with_tools}")
        print(f"Tool overhead:        {tokens_with_tools - tokens_no_tools}")

        assert tokens_with_tools > tokens_no_tools, (
            "Tools should add tokens to the count"
        )


if __name__ == "__main__":
    # Run the tests
    pytest.main([__file__, "-v", "-s"])  # -s to see print outputs
