class ColorUtils:
    """A utility class for color-related operations."""

    @staticmethod
    def ensure_hash_prefix(color: str) -> str:
        """
        Ensure hex color values have a # prefix.
        Supports both simple colors and colors with backgrounds (e.g., "#FFF on #000").
        """
        if not color:
            return color
        
        if not isinstance(color, str):
            return color
            
        # Handle colors with background (e.g., "#FFF on #000" or "red on blue")
        if " on " in color:
            parts = color.split(" on ")
            if len(parts) == 2:
                fg_color = ColorUtils._ensure_single_color_prefix(parts[0].strip())
                bg_color = ColorUtils._ensure_single_color_prefix(parts[1].strip())
                return f"{fg_color} on {bg_color}"
        
        # Handle simple color
        return ColorUtils._ensure_single_color_prefix(color)
    
    @staticmethod
    def _ensure_single_color_prefix(color: str) -> str:
        """Ensure a single hex color value has a # prefix."""
        if not color or not color.strip():
            return color
            
        color = color.strip()
        
        # Already has prefix or is a named color
        if color.startswith("#") or not all(c in "0123456789ABCDEFabcdef" for c in color):
            return color
        
        # Check if it's a valid hex color (3 or 6 hex digits)
        if len(color) in (3, 6):
            return f"#{color}"
            
        return color
