from __future__ import annotations
from typing import Any, List
import hashlib
import json

from agents.models.chatcmpl_converter import Converter
from siada.foundation.logging import logger

# Safety margin for char-based token estimation (20% buffer)
_ESTIMATION_SAFETY_MARGIN = 1.2

# Fixed overhead for tools definitions (~4000 tokens typical)
DEFAULT_TOOLS_TOKEN_OVERHEAD = 4000


def compute_message_signature(message: Any) -> str:
    """
    Compute MD5 signature for a message.
    
    Args:
        message: The message to compute signature for
        
    Returns:
        MD5 hash string of the message
    """
    # Convert message to string for MD5 calculation
    message_str = json.dumps(message, sort_keys=True, ensure_ascii=False)
    return hashlib.md5(message_str.encode('utf-8')).hexdigest()


def calculate_tokens(
    model_name: str,
    messages_or_text: List | str,
) -> int:
    """
    Calculate token count using litellm's model-aware tokenizer.

    Shared utility used by both ApiMessageTransferFilter and
    TurnPruneSummaryCompaction for accurate token counting.

    Args:
        model_name: LLM model name (e.g. "claude-4-sonnet")
        messages_or_text: list of API message items, or a plain string

    Returns:
        Token count
    """
    import litellm

    if isinstance(messages_or_text, str):
        return litellm.token_counter(model=model_name, text=messages_or_text)

    return litellm.token_counter(
        model=model_name,
        messages=Converter.items_to_messages(
            items=messages_or_text,
            model=model_name,
            preserve_thinking_blocks=True,
            preserve_tool_output_all_content=True,
        ),
    ) + DEFAULT_TOOLS_TOKEN_OVERHEAD


def estimate_tokens(messages: List, *, safety_margin: float = _ESTIMATION_SAFETY_MARGIN) -> int:
    """
    Rough token estimate: ~4 chars per token with safety margin.

    Fast fallback when litellm is unavailable (e.g. in tests).
    Can be used standalone without a CodeAgentContext.

    Args:
        messages: list of message items to estimate
        safety_margin: multiplier for estimation buffer (default 1.2)

    Returns:
        Estimated token count
    """
    total_chars = sum(
        len(json.dumps(m, sort_keys=True, ensure_ascii=False, default=str))
        for m in messages
    )
    return int(total_chars / 4 * safety_margin)


def calculate_tokens_with_fallback(
    model_name: str | None,
    messages: List,
) -> int:
    """
    Count tokens using litellm when model_name is available,
    falling back to char-based estimate otherwise.

    Args:
        model_name: if provided, uses litellm model-aware tokenizer
        messages: message items to count

    Returns:
        Token count
    """
    if model_name is not None:
        try:
            return calculate_tokens(model_name, messages)
        except Exception as e:
            logger.debug(
                f"litellm token_counter failed, falling back to estimate: {e}"
            )
    return estimate_tokens(messages)
