"""
ASCII Art Banner Display Module for Siada CLI

Provides colorful banner display with gradient effects and fallback for non-pretty terminals.
"""

import math
from rich.text import Text
from rich.console import Console
from rich.panel import Panel
from rich.columns import Columns
from rich.align import Align
from rich.table import Table
from rich.layout import Layout

try:
    from drawille import Canvas
    HAS_DRAWILLE = True
except ImportError:
    HAS_DRAWILLE = False


class BannerDisplay:
    """Handle ASCII art banner display with color gradients."""
    
    # ASCII art for SIADA CLI
    # Using lower half block characters (▆) for better spacing and visual separation
    BANNER_LINES = [
        "  ▆▆▆▆▆▆▆╗▆▆╗ ▆▆▆▆▆╗ ▆▆▆▆▆▆╗  ▆▆▆▆▆╗      ▆▆▆▆▆▆╗▆▆╗     ▆▆╗",
        "  ▆▆╔════╝▆▆║▆▆╔══▆▆╗▆▆╔══▆▆╗▆▆╔══▆▆╗    ▆▆╔════╝▆▆║     ▆▆║",
        "  ▆▆▆▆▆▆▆╗▆▆║▆▆▆▆▆▆▆║▆▆║  ▆▆║▆▆▆▆▆▆▆║    ▆▆║     ▆▆║     ▆▆║",
        "  ╚════▆▆║▆▆║▆▆╔══▆▆║▆▆║  ▆▆║▆▆╔══▆▆║    ▆▆║     ▆▆║     ▆▆║",
        "  ▆▆▆▆▆▆▆║▆▆║▆▆║  ▆▆║▆▆▆▆▆▆╔╝▆▆║  ▆▆║    ╚▆▆▆▆▆▆╗▆▆▆▆▆▆▆╗▆▆║",
        "  ╚══════╝╚═╝╚═╝  ╚═╝╚═════╝ ╚═╝  ╚═╝     ╚═════╝╚══════╝╚═╝"
    ]
    
    # Compatible version using block characters for better cross-terminal compatibility
    # BANNER_LINES = [
    #     "   ███████ ██  █████  ██████   █████       ██████ ██      ██",
    #     "   ██      ██ ██   ██ ██   ██ ██   ██     ██      ██      ██",
    #     "   ███████ ██ ███████ ██   ██ ███████     ██      ██      ██",
    #     "        ██ ██ ██   ██ ██   ██ ██   ██     ██      ██      ██",
    #     "   ███████ ██ ██   ██ ██████  ██   ██     ██████  ███████ ██",
    #     "                                                               "
    # ]

    # Helper functions for drawille-based circle drawing
    @staticmethod
    def _draw_circle(canvas, cx, cy, radius, fill=False):
        """绘制圆形"""
        if fill:
            # 填充圆形
            for r in range(int(radius)):
                circumference = int(2 * math.pi * r)
                for i in range(circumference):
                    angle = 2 * math.pi * i / circumference
                    x = int(cx + r * math.cos(angle))
                    y = int(cy + r * math.sin(angle))
                    canvas.set(x, y)
        else:
            # 只画轮廓
            for angle in range(360):
                rad = math.radians(angle)
                x = int(cx + radius * math.cos(rad))
                y = int(cy + radius * math.sin(rad))
                canvas.set(x, y)

    @staticmethod
    def _draw_filled_ellipse(canvas, cx, cy, rx, ry):
        """绘制填充椭圆"""
        for y in range(-int(ry), int(ry) + 1):
            # 椭圆方程: x²/a² + y²/b² = 1
            # 解出 x = a * sqrt(1 - y²/b²)
            if ry > 0:
                x_max = int(rx * math.sqrt(max(0, 1 - (y * y) / (ry * ry))))
                for x in range(-x_max, x_max + 1):
                    canvas.set(int(cx + x), int(cy + y))

    @staticmethod
    def _generate_circle_drawille() -> str:
        """
        Generate a circle with eyes using drawille library for high-resolution Braille characters.
        
        Returns:
            String representation of the circle with eyes using Braille characters
        """
        if not HAS_DRAWILLE:
            # Fallback to mathematical method if drawille is not available
            return BannerDisplay._generate_circle_fallback()
        
        c = Canvas()
        
        # 中心和缩放
        center_x, center_y = 35, 18
        scale = 0.5
        
        # 绘制外圆（多层以增加粗细）
        outer_radius = 33 * scale
        for offset in range(-1, 2):
            BannerDisplay._draw_circle(c, center_x, center_y, outer_radius + offset, fill=False)
        
        # 绘制左眼
        left_eye_x = center_x - 13 * scale
        left_eye_y = center_y - 5 * scale
        eye_width = 4.5 * scale
        eye_height = 7 * scale
        
        BannerDisplay._draw_filled_ellipse(c, int(left_eye_x), int(left_eye_y), eye_width, eye_height)
        
        # 绘制右眼
        right_eye_x = center_x + 13 * scale
        right_eye_y = center_y - 5 * scale
        
        BannerDisplay._draw_filled_ellipse(c, int(right_eye_x), int(right_eye_y), eye_width, eye_height)
        
        return "\n" + c.frame() + "\n"

    @staticmethod
    def _generate_circle_fallback(radius: int = 5) -> str:
        """
        Fallback: Generate a circle with eyes using mathematical calculation.
        Used when drawille library is not available.
        
        Args:
            radius: The radius of the circle
            
        Returns:
            String representation of the circle with eyes
        """
        lines = []
        # Aspect ratio adjustment for terminal characters (characters are taller than wide)
        aspect_ratio = 2.4
        
        # Eye positions (relative to center)
        left_eye_x = -radius * aspect_ratio * 0.5
        right_eye_x = radius * aspect_ratio * 0.3
        eye_y = -radius * 0.3
        
        for y in range(-radius, radius + 1):
            line = ""
            for x in range(-int(radius * aspect_ratio), int(radius * aspect_ratio) + 1):
                # Calculate distance from center using Pythagorean theorem
                dist = math.sqrt((x / aspect_ratio) ** 2 + y ** 2)
                
                # Check if this position is an eye
                is_left_eye = abs(x - left_eye_x) < 1.5 and abs(y - eye_y) < 1.2
                is_right_eye = abs(x - right_eye_x) < 1.5 and abs(y - eye_y) < 1.2
                
                # Check if point is on the circle boundary (with small tolerance)
                if abs(dist - radius) < 0.4:
                    line += "█"
                elif (is_left_eye or is_right_eye):
                    line += "█"  # Draw eyes
                else:
                    line += " "
            lines.append(line)
        
        return "\n" + "\n".join(lines) + "\n"
    
    # Generate circle using drawille (or fallback to mathematical method)
    @staticmethod
    def _generate_circle(radius: int = 5) -> str:
        """
        Generate a circle with eyes. Uses drawille if available, otherwise falls back to mathematical method.
        
        Args:
            radius: The radius of the circle (only used in fallback method)
            
        Returns:
            String representation of the circle with eyes
        """
        if HAS_DRAWILLE:
            # Call the drawille method directly without class reference
            c = Canvas()
            
            # 中心和缩放
            center_x, center_y = 35, 18
            scale = 0.5
            
            # 绘制外圆（多层以增加粗细）
            outer_radius = 33 * scale
            for offset in range(-1, 2):
                BannerDisplay._draw_circle(c, center_x, center_y, outer_radius + offset, fill=False)
            
            # 绘制左眼
            left_eye_x = center_x - 13 * scale
            left_eye_y = center_y - 5 * scale
            eye_width = 4.5 * scale
            eye_height = 7 * scale
            
            BannerDisplay._draw_filled_ellipse(c, int(left_eye_x), int(left_eye_y), eye_width, eye_height)
            
            # 绘制右眼
            right_eye_x = center_x + 13 * scale
            right_eye_y = center_y - 5 * scale
            
            BannerDisplay._draw_filled_ellipse(c, int(right_eye_x), int(right_eye_y), eye_width, eye_height)
            
            return "\n" + c.frame() + "\n"
        else:
            # Fallback to mathematical method
            lines = []
            aspect_ratio = 2.4
            
            left_eye_x = -radius * aspect_ratio * 0.5
            right_eye_x = radius * aspect_ratio * 0.3
            eye_y = -radius * 0.3
            
            for y in range(-radius, radius + 1):
                line = ""
                for x in range(-int(radius * aspect_ratio), int(radius * aspect_ratio) + 1):
                    dist = math.sqrt((x / aspect_ratio) ** 2 + y ** 2)
                    
                    is_left_eye = abs(x - left_eye_x) < 1.5 and abs(y - eye_y) < 1.2
                    is_right_eye = abs(x - right_eye_x) < 1.5 and abs(y - eye_y) < 1.2
                    
                    if abs(dist - radius) < 0.4:
                        line += "█"
                    elif (is_left_eye or is_right_eye):
                        line += "█"
                    else:
                        line += " "
                lines.append(line)
            
            return "\n" + "\n".join(lines) + "\n"
    
    # ASCII art for SIADA logo (circle) - will be generated after class definition
    li_siada = None
    
    # Color gradient from left to right (inspired by GitHub theme)
    # GitHub theme uses: #79B8FF (light blue) -> #85E89D (light green)
    
    # Original RGB hex colors (commented out - may display differently in Apple Terminal vs iTerm2)
    # GRADIENT_COLORS = [
    #     "#5B9BD5",  # Blue
    #     "#6BA5E7",  # Bright blue
    #     "#79B8FF",  # Light blue (GitHub theme start)
    #     "#7FC9E8",  # Cyan
    #     "#85D89D",  # Light cyan-green
    #     "#85E89D"   # Light green (GitHub theme end)
    # ]
    
    # 256-color codes for consistent display across Apple Terminal and iTerm2
    # These colors provide similar visual effect to the RGB hex colors above
    GRADIENT_COLORS = [
        "color(75)",   # Blue (similar to #5B9BD5)
        "color(111)",  # Bright blue (similar to #6BA5E7)
        "color(117)",  # Light blue (similar to #79B8FF, GitHub theme start)
        "color(116)",  # Cyan (similar to #7FC9E8)
        "color(115)",  # Light cyan-green (similar to #85D89D)
        "color(121)"   # Light green (similar to #85E89D, GitHub theme end)
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
            "  ▆▆▆▆▆▆▆╗▆▆╗ ▆▆▆▆▆╗ ▆▆▆▆▆▆╗  ▆▆▆▆▆╗      ▆▆▆▆▆▆╗▆▆╗     ▆▆╗",
            "  ▆▆╔════╝▆▆║▆▆╔══▆▆╗▆▆╔══▆▆╗▆▆╔══▆▆╗    ▆▆╔════╝▆▆║     ▆▆║",
            "  ▆▆▆▆▆▆▆╗▆▆║▆▆▆▆▆▆▆║▆▆║  ▆▆║▆▆▆▆▆▆▆║    ▆▆║     ▆▆║     ▆▆║",
            "  ╚════▆▆║▆▆║▆▆╔══▆▆║▆▆║  ▆▆║▆▆╔══▆▆║    ▆▆║     ▆▆║     ▆▆║",
            "  ▆▆▆▆▆▆▆║▆▆║▆▆║  ▆▆║▆▆▆▆▆▆╔╝▆▆║  ▆▆║    ╚▆▆▆▆▆▆╗▆▆▆▆▆▆▆╗▆▆║",
            "  ╚══════╝╚═╝╚═╝  ╚═╝╚═════╝ ╚═╝  ╚═╝     ╚═════╝╚══════╝╚═╝",
            ""
        ])
    
    @classmethod
    def show_welcome_panel(cls, announcements: list = None, console: Console = None, siada_version: str = "Siada CLI"):
        """
        Display a welcome panel similar to Claude Code style.
        
        Args:
            announcements: List of announcement strings to display
            console: Rich console instance (optional)
        """
        if console is None:
            console = Console()
        
        # Create logo (li_siada) - using RGB color for consistency
        # Temporarily disabled - logo generation
        # logo_text = Text(cls.li_siada, style="bold #FFFFFF")
        
        # Create BANNER_LINES with gradient
        banner_text = Text()
        for line in cls.BANNER_LINES:
            line_length = len(line.rstrip())
            if line_length == 0:
                banner_text.append(line + "\n")
                continue
            
            for i, char in enumerate(line):
                if char.isspace() and i >= line_length:
                    banner_text.append(char)
                else:
                    gradient_pos = i / max(1, line_length - 1) if line_length > 1 else 0
                    color_index = min(int(gradient_pos * len(cls.GRADIENT_COLORS)), 
                                    len(cls.GRADIENT_COLORS) - 1)
                    color = cls.GRADIENT_COLORS[color_index]
                    banner_text.append(char, style=color)
            banner_text.append("\n")
        
        # Create right side content (banner + announcements + info)
        right_content = Table.grid(padding=(0, 0))
        right_content.add_column()
        
        # Add banner
        right_content.add_row(banner_text)
        
        # Add spacing
        right_content.add_row(Text(""))
        
        # Add announcements
        if announcements:
            for line in announcements:
                # Use normal style instead of dim for better readability
                right_content.add_row(Text(line))
            # Add spacing after announcements
            # right_content.add_row(Text(""))
        
        # # Add tips section
        # right_content.add_row(Text("Tips for getting started", style="bold"))
        # right_content.add_row(Text("Run /help to see available commands", style="dim"))
        # right_content.add_row(Text("─" * 50, style="dim"))
        
        # # Add recent activity section
        # right_content.add_row(Text(""))
        # right_content.add_row(Text("Recent activity", style="bold"))
        # right_content.add_row(Text("No recent activity", style="dim"))
        
        # Create main layout: logo on left, all content on right
        # Temporarily disabled - using logo
        # main_content = Columns([
        #     Align.center(logo_text, vertical="top"),
        #     Align.center(right_content, vertical="bottom")
        # ], equal=False, expand=True)
        
        # Without logo - just show the content
        main_content = Align.left(right_content, vertical="bottom")
        
        # Create panel with title and width limit
        # Using RGB colors for consistent display across different terminals
        panel = Panel(
            main_content,
            title=f"[bold #6BA5E7]{siada_version}[/bold #6BA5E7]",  # DarkTurquoise
            border_style="#6BA5E7",  # DarkTurquoise          "#6BA5E7",  # Bright blue
            title_align="left",
            padding=(1, 0),
            width=90  # Limit maximum width to 100 characters
        )
        
        console.print(panel)


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


# Initialize li_siada after class definition
# Temporarily disabled - logo generation
# BannerDisplay.li_siada = BannerDisplay._generate_circle(radius=5)
