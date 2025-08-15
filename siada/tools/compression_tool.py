"""
Context Compression Tool - Intelligently compresses conversation history using a model.
"""
from __future__ import annotations

import json
from typing import Any

from agents import RunContextWrapper, function_tool
from agents.items import TResponseInputItem
from openai.types.chat import ChatCompletionMessageParam
from siada.foundation.code_agent_context import CodeAgentContext
from siada.foundation.config import settings
from siada.provider.client_factory import get_client_with_kwargs
COMPRESS_DOCS = """Intelligently compress or summarize the conversation history within a specified range.

    This tool should be called when the following situations occur:
    1. The conversation history is too long and needs to be partially archived.
    2. A task or topic has concluded, and the relevant conversation can be compressed.
    3. Some messages are no longer important for resolving the current main task and need to be cleared.
    4. The current conversation has deviated from the original topic and needs to be refocused.
    5. The message list contains a lot of redundant information, which reduces the efficiency of accessing important content.
    6. If the test required multiple steps to complete — or was not completed — you need to summarize the testing process.
    7. If the search involved multiple steps — or returned too many results — you need to summarize the search process.
    ===

    After summarizing, you must provide a recommendation for the next step.

    Args:
        reason: The reason why context compression is needed (required).
        start_index: The starting index of the compression range (inclusive).
        end_index: The ending index of the compression range (exclusive).

    Returns:
        A dictionary containing:
        - status (int): 1 for success, 0 for failure.
        - start_index (int): The starting index of the compression.
        - end_index (int): The ending index of the compression.
        - summary (str): The compression summary or error/status information.

    Example Usage:
    
    Original conversation history (messages 1-6):
    [1] assistant: Search for files containing "config" keyword to find configuration files.
    [2] tool: {"status": "success", "results": ["config.py", "app_config.py", "db_config.py", "test_config.py", "config.yaml", "nginx.conf", "docker-compose.yml"], "total": 47}
    [3] assistant: Too many results. Search for "database config" specifically.
    [4] tool: {"status": "success", "results": ["db_config.py", "database.conf", "config/db.yaml", "tests/db_config_test.py", "migrations/config.py"], "total": 23}
    [5] assistant: Still too broad. Search for "database connection" in Python files only.
    [6] tool: {"status": "success", "results": ["db_config.py", "models/base.py", "utils/db_helper.py", "services/db_service.py"], "total": 18}
    [7] assistant: The search results are still not specific enough. Let me try a different approach.
    [8] tool: {"status": "success", "message": "Search strategy needs refinement - too many generic matches"}

    Compression call:
    compress_context_tool(
        reason="Search attempts yielded too many results, need to restart with better strategy",
        start_index=1,
        end_index=7,
    )

    Compressed result:
    {
        "status": 1,
        "start_index": 1,
        "end_index": 7,
        "summary": "[Smart Compression Summary]\nReason for compression: Search attempts yielded too many results, need to restart with better strategy\nMultiple search attempts for configuration files returned excessive results (47, 23, 18 matches respectively), indicating search terms were too broad and strategy needs refinement."
    }
    """

@function_tool(
    name_override="compress_context_tool", description_override=COMPRESS_DOCS, failure_error_function=None
)
async def compress_context_tool(
    context: RunContextWrapper[CodeAgentContext],
    reason: str,
    start_index: int,
    end_index: int,
) -> dict[str, Any]:

    return await _compress_context_tool(
        context=context,
        reason=reason,
        start_index=start_index,
        end_index=end_index
    )

async def _compress_messages_with_model(messages: list[TResponseInputItem], reason: str, context: RunContextWrapper[CodeAgentContext]) -> str:
    
    
    # Format messages
    formatted_messages_content = []
    for msg in messages:
        role = msg.get("role", "unknown")
        content_text = msg.get("content", "")
        formatted_messages_content.append(f"{role}: {content_text}")
    
    conversation_text = "\n".join(formatted_messages_content)

    # Build the system prompt to guide the model for a high-quality summary
    system_prompt = f"""You are a professional conversation summarization assistant. Your task is to generate a concise, accurate, and fluent English summary based on the provided conversation history.

The summary must meet the following requirements:
1.  **Preserve Core Information**: Accurately capture the key topics, important decisions, and critical information of the conversation.
2.  **Reflect Context**: The summary should clearly reflect the context and flow of the conversation, facilitating a seamless continuation.
3.  **State the Reason for Compression**: Clearly state the reason for this compression at the beginning of the summary: "{reason}".
4.  **Concise Language**: Use refined language, avoiding redundancy and unnecessary information.
5.  **Clear Format**: The summary should start with "[Smart Compression Summary]".

Please generate a summary based on the following conversation history:
---
{conversation_text}
---
"""

    # Construct the request to be sent to the model
    model_messages: list[ChatCompletionMessageParam] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "Please generate a summary based on the above conversation history and requirements."}
    ]

    # Call the model for a non-streaming request
    default_kwargs = {
        "model": settings.Claude_4_0_SONNET,
        "messages": model_messages,
        "stream": False,
        "temperature": 0.2,  # Lower temperature to ensure the determinism and accuracy of the summary
    }
    
    # Use get_client_with_kwargs to support context parameter overrides
    client, complete_kwargs = get_client_with_kwargs(context.context, default_kwargs)
    response = await client.chat_complete(**complete_kwargs)
    
    # Extract the summary content from the response
    if response and response.choices and response.choices[0].message:
        summary = response.choices[0].message.content
        if summary:
            return summary.strip()

    # If a valid summary cannot be obtained, return a default error message
    return f"[Smart Compression Summary]\nReason for compression: {reason}\nSummary generation failed: Unable to retrieve valid summary content from the model."


def _create_failure_response(start_index: int, end_index: int, summary: str) -> dict[str, Any]:
    """Creates a response dictionary indicating failure."""
    return {
        "status": 0,
        "start_index": start_index,
        "end_index": end_index,
        "summary": summary
    }


async def _compress_context_tool(
    context: RunContextWrapper[CodeAgentContext],
    reason: str,
    start_index: int,
    end_index: int,
) -> dict[str, Any]:
    if not context.context:
        return _create_failure_response(start_index, end_index, "Error: Unable to get context information")

    conversation_history = context.context.message_history
    total_messages = len(conversation_history)
    
    original_start_index = start_index
    original_end_index = end_index

    # --- Input Validation ---
    if start_index < 0 or end_index > total_messages or start_index >= end_index:
        summary = f"Error: Invalid compression range. Valid range: 0 <= start < end <= {total_messages}"
        return _create_failure_response(original_start_index, original_end_index, summary)

    # As per user requirements, never compress the first message
    if start_index == 0:
        start_index = 1  # Force start from index 1
        if start_index >= end_index:
            summary = "No compression needed: The specified range only contains or is invalid after the first message."
            return _create_failure_response(original_start_index, original_end_index, summary)

    messages_to_compress = conversation_history[start_index:end_index]
    messages_to_compress_count = len(messages_to_compress)

    if messages_to_compress_count == 0:
        summary = f"No compression needed: No messages within the range {start_index}-{end_index}."
        return _create_failure_response(start_index, end_index, summary)

    # --- Compress using the model ---
    try:
        compression_summary = await _compress_messages_with_model(messages_to_compress, reason)
    except Exception as e:
        return _create_failure_response(start_index, end_index, f"Error: Model compression failed - {str(e)}")

    # As per user requirements, this tool is only responsible for generating a summary and does not modify message_history
    # The actual replacement operation will be completed by other tools

    return {
        "status": 1,
        "start_index": start_index,
        "end_index": end_index,
        "summary": compression_summary
    }
