"""
Language configuration for Siada CLI

This module defines language mappings and default settings.
"""

# Default language setting
DEFAULT_LANGUAGE = "en"

# Language mapping table
# Maps user input to standardized language codes
LANGUAGE_MAPPINGS = {
    'en': 'en',
    'english': 'en',
    'zh': 'zh-CN',
    'zh-cn': 'zh-CN',
    'chinese': 'zh-CN',
    '中文': 'zh-CN',
    'cn': 'zh-CN'
}

# Supported languages
SUPPORTED_LANGUAGES = ['en', 'zh-CN']


def normalize_language(lang_input: str) -> str:
    """
    Normalize language input to standard language code.
    
    Args:
        lang_input: User's language input (case-insensitive)
        
    Returns:
        str: Normalized language code ('en' or 'zh-CN'), or None if invalid
    """
    if not lang_input:
        return None
    
    normalized = lang_input.strip().lower()
    return LANGUAGE_MAPPINGS.get(normalized)


def get_language_display_name(lang_code: str) -> str:
    """
    Get display name for a language code.
    
    Args:
        lang_code: Language code ('en' or 'zh-CN')
        
    Returns:
        str: Display name
    """
    display_names = {
        'en': 'English',
        'zh-CN': 'Chinese'
    }
    return display_names.get(lang_code, lang_code)


def get_agent_default_language(agent_name: str) -> str:
    """
    Get the default language for a specific agent.
    
    Some agents have different default languages based on their purpose.
    For example, Card agent defaults to Chinese as it's commonly used for
    Chinese documentation.
    
    Args:
        agent_name: Name of the agent
        
    Returns:
        str: Default language code for the agent
    """
    # Agent-specific language defaults
    agent_language_map = {
        'card': 'zh-CN',
        'cardagent': 'zh-CN',
    }
    
    normalized_name = agent_name.lower() if agent_name else ''
    return agent_language_map.get(normalized_name, DEFAULT_LANGUAGE)
