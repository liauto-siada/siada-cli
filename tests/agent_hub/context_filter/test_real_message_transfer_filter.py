import asyncio
import pytest
from typing import List
from unittest.mock import Mock, AsyncMock

from siada.agent_hub.context_filter.api_message_transfer_filter import ApiMessageTransferFilter
from siada.models.model_run_config import ModelRunConfig
from siada.foundation.code_agent_context import CodeAgentContext


class TestRealMessageTransferFilter:
    @pytest.mark.asyncio
    async def test_call_llm_to_compact_with_real_llm(self):
        """Test _call_llm_to_compact with real LLM response"""
        
        # Initialize filter
        filter = ApiMessageTransferFilter()
        
        # Create mock context with real provider settings
        context = Mock(spec=CodeAgentContext)
        
        # Configure for real LLM - using openrouter provider with a model
        context.provider = "li"
        context.model_run_config = Mock(spec=ModelRunConfig)
        context.model_run_config.model_name ="claude-sonnet-4"  # Using a cheaper model for testing
        
        # Create sample history to compact
        history_to_compact = [
            {
                "role": "user",
                "content": "Hello, I need help with a Python script"
            },
            {
                "role": "assistant", 
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": "I'll help you with your Python script. What would you like to do?"
                    }
                ]
            },
            {
                "role": "user",
                "content": "I want to create a function that reads a CSV file and filters rows based on a condition"
            },
            {
                "role": "assistant",
                "type": "message", 
                "content": [
                    {
                        "type": "output_text",
                        "text": "I'll help you create a function to read and filter CSV data. Let me write that for you."
                    }
                ]
            },
            {   
                "call_id": "tool1",
                "role": "assistant",
                "type": "function_call",
                "name": "str_replace_editor",
                "arguments": "{}"
            },
            {
                "call_id": "tool1",
                "role": "tool",
                "type": "function_call_output",
                "output": "File created successfully"
            },
            {
                "role": "user",
                "content": "Great! Now can you add error handling to the function?"
            }
        ]
        
        # Call the method with real LLM
        result = await filter._call_llm_to_compact(context, history_to_compact)
        
        # Assertions
        assert result is not None, "LLM should return a summary"
        assert isinstance(result, str), "Result should be a string"
        assert len(result) > 0, "Summary should not be empty"
        
        # Check that the summary contains relevant information
        # The LLM should generate a state snapshot based on the conversation
        print(f"\nGenerated Summary:\n{result}\n")
        
        # Basic content validation - the summary should mention key aspects
        assert any(keyword in result.lower() for keyword in ["csv", "filter", "python", "function"]), \
            "Summary should contain relevant keywords from the conversation"

    def test_adjust_compression_index_for_boundary_cases(self):
        """Test _adjust_compression_index_for_boundary_cases with various scenarios"""
        
        filter = ApiMessageTransferFilter()
        
        # Test Case 1: Last message is a user message - should keep it
        messages_case1 = [
            {"role": "user", "content": "First message"},
            {"role": "assistant", "type": "message", "content": [{"type": "output_text", "text": "Response"}]},
            {"role": "user", "content": "Last user message"},
        ]
        result1 = filter._adjust_compression_index_for_boundary_cases(messages_case1, len(messages_case1))
        assert result1 == 2, f"Expected index 2 for last user message, got {result1}"
        
        # Test Case 2: Last message is a function response - should keep the complete sequence
        messages_case2 = [
            {"role": "user", "content": "First message"},
            {"role": "assistant", "type": "message", "content": [{"type": "output_text", "text": "Response"}]},
            {"role": "assistant", "type": "function_call", "call_id": "tool1", "name": "test_tool", "arguments": "{}"},
            {"role": "tool", "type": "function_call_output", "call_id": "tool1", "output": "Tool result"},
        ]
        result2 = filter._adjust_compression_index_for_boundary_cases(messages_case2, len(messages_case2))
        # Should keep from the assistant message before the tool call (index 1)
        assert result2 == 1, f"Expected index 1 for complete tool call sequence, got {result2}"
        
        # Test Case 3: Index not at boundary - should return original index
        messages_case3 = [
            {"role": "user", "content": "First message"},
            {"role": "assistant", "type": "message", "content": [{"type": "output_text", "text": "Response"}]},
            {"role": "user", "content": "Second message"},
            {"role": "assistant", "type": "message", "content": [{"type": "output_text", "text": "Response 2"}]},
        ]
        result3 = filter._adjust_compression_index_for_boundary_cases(messages_case3, 2)
        assert result3 == 2, f"Expected index 2 (unchanged), got {result3}"
        
        # Test Case 4: Complex tool call sequence with multiple assistant messages (reasoning + response)
        messages_case4 = [
            {"role": "user", "content": "First message"},
            {"role": "assistant", "type": "reasoning", "content": [{"type": "reasoning", "text": "Let me think..."}]},
            {"role": "assistant", "type": "message", "content": [{"type": "output_text", "text": "I'll help"}]},
            {"role": "assistant", "type": "function_call", "call_id": "tool1", "name": "test_tool", "arguments": "{}"},
            {"role": "tool", "type": "function_call_output", "call_id": "tool1", "output": "Tool result"},
        ]
        result4 = filter._adjust_compression_index_for_boundary_cases(messages_case4, len(messages_case4))
        # Should keep from the first assistant message (reasoning) in the sequence (index 1)
        assert result4 == 1, f"Expected index 1 for complete sequence with reasoning + response + tool call, got {result4}"
        
        # Test Case 5: Tool call sequence with only one assistant message before
        messages_case5 = [
            {"role": "user", "content": "First message"},
            {"role": "assistant", "type": "message", "content": [{"type": "output_text", "text": "I'll help"}]},
            {"role": "assistant", "type": "function_call", "call_id": "tool1", "name": "test_tool", "arguments": "{}"},
            {"role": "tool", "type": "function_call_output", "call_id": "tool1", "output": "Tool result"},
        ]
        result5 = filter._adjust_compression_index_for_boundary_cases(messages_case5, len(messages_case5))
        # Should keep from the assistant message before the tool call (index 1)
        assert result5 == 1, f"Expected index 1 for sequence with single assistant message before tool call, got {result5}"
        
        print("All boundary case tests passed!")

if __name__ == "__main__":
    # Run tests directly
    test_instance = TestRealMessageTransferFilter()
    
    # Run synchronous test
    test_instance.test_adjust_compression_index_for_boundary_cases()
    
    # Run async test
    asyncio.run(test_instance.test_call_llm_to_compact_with_real_llm())
