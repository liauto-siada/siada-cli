"""
ASCII Art Banner Display Module for Siada CLI

Provides colorful banner display with gradient effects and fallback for non-pretty terminals.
"""

from rich.text import Text
from rich.console import Console


class BannerDisplay:
    """Handle ASCII art banner display with color gradients."""
    
    # ASCII art for SIADA CLI
    BANNER_LINES = [
        "  ███████╗██╗ █████╗ ██████╗  █████╗      ██████╗██╗     ██╗",
        "  ██╔════╝██║██╔══██╗██╔══██╗██╔══██╗    ██╔════╝██║     ██║",
        "  ███████╗██║███████║██║  ██║███████║    ██║     ██║     ██║",
        "  ╚════██║██║██╔══██║██║  ██║██╔══██║    ██║     ██║     ██║",
        "  ███████║██║██║  ██║██████╔╝██║  ██║    ╚██████╗███████╗██║",
        "  ╚══════╝╚═╝╚═╝  ╚═╝╚═════╝ ╚═╝  ╚═╝     ╚═════╝╚══════╝╚═╝"
    ]
    
    # Color gradient from left to right
    GRADIENT_COLORS = [
        "bold blue",
        "bold bright_blue", 
        "bold cyan",
        "bold bright_cyan",
        "bold green",
        "bold bright_green",
        "bold yellow",
        "bold bright_yellow"
    ]
    
    @classmethod
    def show_banner(cls, pretty: bool = True, console: Console = None):
        """
        Display the SIADA CLI banner.
        
        Args:
            pretty: Whether to use colorful output
            console: Rich console instance (optional)
        """
        if pretty:
            try:
                cls._show_pretty_banner(console)
            except Exception:
                # Fallback to plain banner if rich output fails
                cls._show_plain_banner()
        else:
            cls._show_plain_banner()
    
    @classmethod
    def _show_pretty_banner(cls, console: Console = None):
        """Show colorful banner with left-to-right gradient."""
        if console is None:
            console = Console()
        
        banner = Text()
        
        for line in cls.BANNER_LINES:
            # Calculate smooth gradient across the line
            line_length = len(line.rstrip())  # Remove trailing spaces for better gradient
            if line_length == 0:
                banner.append(line + "\n")
                continue
            
            # Create smoother gradient distribution
            for i, char in enumerate(line):
                if char.isspace() and i >= line_length:
                    # Keep trailing spaces uncolored
                    banner.append(char)
                else:
                    # Calculate gradient position (0.0 to 1.0)
                    gradient_pos = i / max(1, line_length - 1) if line_length > 1 else 0
                    # Map to color index with smooth transition
                    color_index = min(int(gradient_pos * len(cls.GRADIENT_COLORS)), 
                                    len(cls.GRADIENT_COLORS) - 1)
                    color = cls.GRADIENT_COLORS[color_index]
                    banner.append(char, style=color)
            
            banner.append("\n")
        
        console.print(banner)
    
    @classmethod 
    def _show_plain_banner(cls):
        """Show plain text banner for non-pretty terminals."""
        print()
        try:
            for line in cls.BANNER_LINES:
                print(line)
        except UnicodeEncodeError:
            # Fallback to ASCII-only banner if Unicode fails
            cls._show_ascii_fallback_banner()
        print()
    
    @classmethod
    def _show_ascii_fallback_banner(cls):
        """Show ASCII-only fallback banner."""
        ascii_banner = [
            "  ===== SIADA CLI =====",
            "  S I A D A   C L I",
            "  ====================="
        ]
        for line in ascii_banner:
            print(line)
    
    @classmethod
    def get_simple_banner(cls) -> str:
        """
        Get a simple text version of the banner.
        
        Returns:
            Simple ASCII text banner
        """
        return "\n".join([
            "",
            "  ███████╗██╗ █████╗ ██████╗  █████╗      ██████╗██╗     ██╗",
            "  ██╔════╝██║██╔══██╗██╔══██╗██╔══██╗    ██╔════╝██║     ██║",
            "  ███████╗██║███████║██║  ██║███████║    ██║     ██║     ██║",
            "  ╚════██║██║██╔══██║██║  ██║██╔══██║    ██║     ██║     ██║",
            "  ███████║██║██║  ██║██████╔╝██║  ██║    ╚██████╗███████╗██║",
            "  ╚══════╝╚═╝╚═╝  ╚═╝╚═════╝ ╚═╝  ╚═╝     ╚═════╝╚══════╝╚═╝",
            ""
        ])


def show_siada_banner(pretty: bool = True, console: Console = None):
    """
    Convenience function to display SIADA CLI banner.
    
    Args:
        pretty: Whether to use colorful output
        console: Rich console instance (optional)
    """
    BannerDisplay.show_banner(pretty, console)


def get_banner_text() -> str:
    """
    Get the plain text version of the banner.
    
    Returns:
        String containing the ASCII art banner
    """
    return BannerDisplay.get_simple_banner() 