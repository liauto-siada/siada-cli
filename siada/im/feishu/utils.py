"""Utility functions for Lark IM integration.

Extracted from lark_controller.py for reuse across IM components.
"""

import ast
import logging
import re

logger = logging.getLogger("siada.im.lark.utils")

# Match bytes literals like b'...' or b"..." in exception messages.
# Uses non-VERBOSE mode so spaces are matched literally.
_BYTES_LITERAL_PATTERN = re.compile(
    r"""(?<![\w])b(?P<quote>['"])(?P<body>(?:\\.|(?!(?P=quote)).)*)(?P=quote)"""
)


def get_default_workspace() -> str:
    """Get default workspace path for Lark IM mode."""
    from siada.foundation.constants import SIADA_HOME

    workspace = SIADA_HOME / "workspace" / "lark"
    workspace.mkdir(parents=True, exist_ok=True)
    return str(workspace)


def format_exception_for_user(
    exc: BaseException | None, max_length: int = 200
) -> str:
    """Format an exception into a user-friendly message for IM delivery."""
    if exc is None:
        return "Unknown error"
    message = str(exc).strip() or exc.__class__.__name__
    message = decode_embedded_bytes_literals(message)
    if len(message) > max_length:
        return message[: max_length - 3] + "..."
    return message


def decode_embedded_bytes_literals(text: str) -> str:
    """Decode bytes literals embedded in exception strings.

    Example:
        ``AnthropicException - b'{"message":"\\xe4\\xbe..."}'``
        becomes a readable UTF-8 string before sending to IM users.
    """

    def _replace(match: re.Match[str]) -> str:
        literal = match.group(0)
        # Guard against extremely large literals that could consume excessive resources
        if len(literal) > 2000:
            return literal
        try:
            value = ast.literal_eval(literal)
        except Exception:
            return literal

        if isinstance(value, (bytes, bytearray)):
            return value.decode("utf-8", errors="replace")
        return literal

    try:
        return _BYTES_LITERAL_PATTERN.sub(_replace, text)
    except Exception:
        logger.debug("Failed to decode embedded bytes literals", exc_info=True)
        return text