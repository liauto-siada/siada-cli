"""
Session title generation via the fast LLM.

Generates a short, human-readable title for a CLI session from the user's
first message, so the frontend can display it as the terminal tab/window
title (analogous to Claude Code's Haiku-generated session title).

Routed through ``siada.provider.fast_llm.fast_completion`` so this stays
cheap and fast — it must never block or slow down the main agent turn.
"""

from typing import Any, Optional

from siada.foundation.logging import logger

# Keep the input small: only the first N characters of the user's first
# message are relevant to the topic, and it caps prompt cost.
MAX_TITLE_INPUT_LENGTH: int = 1000

# Never let a hung fast-LLM call delay the session — this call is fire-and
# -forget from the caller's perspective.
TITLE_TIMEOUT: float = 15.0

SESSION_TITLE_PROMPT = """Generate a concise title (3-7 words, or roughly 6-15 characters for CJK languages) that captures the main topic or goal of this coding session.

The title MUST be in the SAME language as the conversation below (e.g. if the conversation is in Chinese, reply in Chinese; if English, reply in English). If the conversation mixes languages, use whichever language dominates.

For English titles, use sentence case: capitalize only the first word and proper nouns. For other languages, follow that language's normal casing/punctuation conventions.

Reply with ONLY the title text, nothing else — no quotes, no punctuation at the end, no explanation.

Good examples:
Fix login button on mobile
Add OAuth authentication
Debug failing CI tests
修复移动端登录按钮问题
新增 OAuth 认证

Bad (too vague): Code changes
Bad (too long): Investigate and fix the issue where the login button does not respond on mobile devices
Bad (wrong case): Fix Login Button On Mobile
Bad (wrong language): title in English when the conversation is in Chinese

Conversation:
{content}"""


def _extract_title_from_response(response: Any) -> Optional[str]:
    """Extract and clean the title text from a fast LLM completion response."""
    if not response or not hasattr(response, "choices") or len(response.choices) == 0:
        return None

    choice = response.choices[0]
    if not hasattr(choice, "message") or not hasattr(choice.message, "content"):
        return None

    content = choice.message.content
    if not content:
        return None

    # Fast models sometimes wrap the answer in quotes or a trailing period —
    # strip both since the caller writes this straight into a terminal title.
    title = content.strip().strip('"').strip("'").rstrip(".").strip()
    return title or None


async def generate_session_title(text: str) -> Optional[str]:
    """Generate a short sentence-case session title from the user's message.

    Args:
        text: The user's first message (or a description of the session).

    Returns:
        A short title string, or None on error / empty input / unparseable
        response. Callers should fall back to a default title on None.
    """
    trimmed = text.strip() if text else ""
    if not trimmed:
        return None

    try:
        # Lazy import so callers that never generate a title don't pay for
        # pulling in the provider/model plumbing.
        from siada.provider.fast_llm import fast_completion

        content_preview = trimmed[:MAX_TITLE_INPUT_LENGTH]
        prompt = SESSION_TITLE_PROMPT.format(content=content_preview)

        import asyncio

        response = await asyncio.wait_for(
            fast_completion(prompt, agent_name="session_title_generator"),
            timeout=TITLE_TIMEOUT,
        )

        title = _extract_title_from_response(response)
        if title:
            logger.info(f"[session-title] Generated title via fast LLM: {title}")
            return title

        logger.debug("[session-title] Fast LLM response did not contain a usable title")
        return None

    except Exception as e:
        logger.debug(f"[session-title] Failed to generate session title: {e}")
        return None
