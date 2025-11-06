"""
Utility functions for serializing and deserializing Usage objects.
"""
from typing import Optional

from agents.usage import Usage
from openai.types.responses.response_usage import InputTokensDetails, OutputTokensDetails
from siada.foundation.logging import logger


def serialize_usage(usage) -> Optional[dict]:
    """
    Serialize Usage object to dictionary for JSON storage.
    
    Args:
        usage: Usage object from agents library
        
    Returns:
        Dictionary representation of usage, or None if serialization fails
    """
    if not usage:
        return None
        
    try:
        usage_dict = {
            'requests': usage.requests,
            'input_tokens': usage.input_tokens,
            'output_tokens': usage.output_tokens,
            'total_tokens': usage.total_tokens,
            'input_tokens_details': {
                'cached_tokens': usage.input_tokens_details.cached_tokens
            } if usage.input_tokens_details else None,
            'output_tokens_details': {
                'reasoning_tokens': usage.output_tokens_details.reasoning_tokens
            } if usage.output_tokens_details else None
        }
        return usage_dict
    except Exception as e:
        logger.warning(f"Failed to serialize usage: {e}")
        return None


def deserialize_usage(usage_data: dict) -> Optional[Usage]:
    """
    Deserialize dictionary to Usage object.
    
    Args:
        usage_data: Dictionary containing usage data
        
    Returns:
        Usage object, or None if deserialization fails
    """
    if not usage_data:
        return None
        
    try:
        restored_usage = Usage(
            requests=usage_data.get('requests', 0),
            input_tokens=usage_data.get('input_tokens', 0),
            output_tokens=usage_data.get('output_tokens', 0),
            total_tokens=usage_data.get('total_tokens', 0),
            input_tokens_details=InputTokensDetails(
                cached_tokens=usage_data.get('input_tokens_details', {}).get('cached_tokens', 0)
            ) if usage_data.get('input_tokens_details') else InputTokensDetails(cached_tokens=0),
            output_tokens_details=OutputTokensDetails(
                reasoning_tokens=usage_data.get('output_tokens_details', {}).get('reasoning_tokens', 0)
            ) if usage_data.get('output_tokens_details') else OutputTokensDetails(reasoning_tokens=0)
        )
        return restored_usage
    except Exception as e:
        logger.warning(f"Failed to deserialize usage: {e}")
        return None
