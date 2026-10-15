"""Authentication failures that require intervention before learning can retry."""

import re


class LearningAuthenticationError(RuntimeError):
    """The learning model rejected authentication or authorization."""


def is_authentication_error(error: Exception) -> bool:
    """Recognize SDK status codes, including errors wrapped by a gateway."""
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, LearningAuthenticationError):
            return True
        status = getattr(current, "status_code", None)
        response = getattr(current, "response", None)
        if status in (401, 403) or getattr(response, "status_code", None) in (401, 403):
            return True
        if type(current).__name__ in ("AuthenticationError", "PermissionDeniedError"):
            return True
        # Some compatible gateways wrap HTTP errors in a generic APIError.
        if re.search(r"\b(?:error code|status(?: code)?|http)\s*[:=]?\s*(401|403)\b",
                     str(current), re.IGNORECASE):
            return True
        current = current.__cause__ or current.__context__
    return False