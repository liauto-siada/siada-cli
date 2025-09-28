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

if __name__ == "__main__":
    # Run tests directly
    asyncio.run(TestRealMessageTransferFilter().test_call_llm_to_compact_with_real_llm())
