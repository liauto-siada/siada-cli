class ColorUtils:
    """A utility class for color-related operations."""

    @staticmethod
    def ensure_hash_prefix(color: str) -> str:
        """Ensure hex color values have a # prefix."""
        if not color:
            return color
        if isinstance(color, str) and color.strip() and not color.startswith("#"):
            # Check if it's a valid hex color (3 or 6 hex digits)
            if all(c in "0123456789ABCDEFabcdef" for c in color) and len(color) in (
                3,
                6,
            ):
                return f"#{color}"
        return color 