from dataclasses import dataclass
from typing import Dict, ClassVar


@dataclass
class ColorSettings:
    user_input_color: str = "blue"
    tool_output_color: str = None
    tool_error_color: str = "red"
    tool_warning_color: str = "#FFA500"
    tool_result_color: str = "#00FF00"
    tool_call_color: str = "#FFD700"
    assistant_output_color: str = "blue"
    completion_menu_color: str = None
    completion_menu_bg_color: str = None
    completion_menu_current_color: str = None
    completion_menu_current_bg_color: str = None
    code_theme: str = "default"
    split_line_color: str = "#0000FF"
    shell_model_color: str = "#FF00FF"
    at_file_reference_color: str = "#FF6B6B"
    
    # Predefined theme configurations
    THEMES: ClassVar[Dict[str, Dict[str, str]]] = {
        "default": {
            "user_input_color": "blue",
            "tool_output_color": None,
            "tool_error_color": "red", 
            "tool_warning_color": "#FFA500",
            "tool_result_color": "#00FF00",
            "tool_call_color": "#FFD700",
            "assistant_output_color": "blue",
            "completion_menu_color": None,
            "completion_menu_bg_color": None,
            "completion_menu_current_color": None,
            "completion_menu_current_bg_color": None,
            "code_theme": "default",
            "split_line_color": "#0000FF",
            "shell_model_color": "#FF00FF",
            "at_file_reference_color": "#FF6B6B"
        },
        "dark": {
            "user_input_color": "#32FF32",
            "tool_output_color": None,
            "tool_error_color": "#FF3333",
            "tool_warning_color": "#FFFF00", 
            "tool_result_color": "#00FF7F",
            "tool_call_color": "#FFA500",
            "assistant_output_color": "#00FFFF",
            "completion_menu_color": None,
            "completion_menu_bg_color": None,
            "completion_menu_current_color": None,
            "completion_menu_current_bg_color": None,
            "code_theme": "monokai",
            "split_line_color": "#4169E1",
            "shell_model_color": "#DA70D6",
            "at_file_reference_color": "#FF8A80"
        },
        "light": {
            "user_input_color": "green",
            "tool_output_color": None,
            "tool_error_color": "red",
            "tool_warning_color": "#FFA500",
            "tool_result_color": "#008000",
            "tool_call_color": "#FF8C00",
            "assistant_output_color": "blue", 
            "completion_menu_color": None,
            "completion_menu_bg_color": None,
            "completion_menu_current_color": None,
            "completion_menu_current_bg_color": None,
            "code_theme": "default",
            "split_line_color": "#1E90FF",
            "shell_model_color": "#9370DB",
            "at_file_reference_color": "#E91E63"
        }
    }
    
    @classmethod
    def from_theme(cls, theme_name: str) -> 'ColorSettings':
        """Create ColorSettings instance from theme name"""
        if theme_name not in cls.THEMES:
            raise ValueError(f"Unknown theme: {theme_name}. Available themes: {list(cls.THEMES.keys())}")
        
        theme_config = cls.THEMES[theme_name]
        return cls(**theme_config)
    
    @classmethod
    def get_available_themes(cls) -> list:
        """Get list of all available themes"""
        return list(cls.THEMES.keys())
    
    def apply_to_args(self, args):
        """Apply color settings to args object"""
        args.user_input_color = self.user_input_color
        args.tool_output_color = self.tool_output_color
        args.tool_error_color = self.tool_error_color
        args.tool_warning_color = self.tool_warning_color
        args.tool_result_color = self.tool_result_color
        args.tool_call_color = self.tool_call_color
        args.assistant_output_color = self.assistant_output_color
        args.completion_menu_color = self.completion_menu_color
        args.completion_menu_bg_color = self.completion_menu_bg_color
        args.completion_menu_current_color = self.completion_menu_current_color
        args.completion_menu_current_bg_color = self.completion_menu_current_bg_color
        args.code_theme = self.code_theme
        args.split_line_color = self.split_line_color
        args.shell_model_color = self.shell_model_color
        args.at_file_reference_color = self.at_file_reference_color


class RunningConfigColorSettings:
    """Runtime color settings with processed color values."""
    
    def __init__(self, color_settings=None, pretty=True):
        """Initialize running color settings.
        
        Args:
            color_settings (ColorSettings, optional): Base color settings
            pretty (bool): Whether to apply colors (if False, most colors will be None)
        """
        from .color_utils import ColorUtils
        
        self.color_settings = color_settings or ColorSettings()
        self.user_input_color = (
            ColorUtils.ensure_hash_prefix(self.color_settings.user_input_color) if pretty else None
        )
        self.tool_output_color = (
            ColorUtils.ensure_hash_prefix(self.color_settings.tool_output_color) if pretty else None
        )
        self.tool_error_color = (
            ColorUtils.ensure_hash_prefix(self.color_settings.tool_error_color) if pretty else None
        )
        self.tool_warning_color = (
            ColorUtils.ensure_hash_prefix(self.color_settings.tool_warning_color) if pretty else None
        )
        self.tool_result_color = (
            ColorUtils.ensure_hash_prefix(self.color_settings.tool_result_color) if pretty else None
        )
        self.tool_call_color = (
            ColorUtils.ensure_hash_prefix(self.color_settings.tool_call_color) if pretty else None
        )
        self.assistant_output_color = ColorUtils.ensure_hash_prefix(
            self.color_settings.assistant_output_color
        )
        self.completion_menu_color = (
            ColorUtils.ensure_hash_prefix(self.color_settings.completion_menu_color) if pretty else None
        )
        self.completion_menu_bg_color = (
            ColorUtils.ensure_hash_prefix(self.color_settings.completion_menu_bg_color)
            if pretty
            else None
        )
        self.completion_menu_current_color = (
            ColorUtils.ensure_hash_prefix(self.color_settings.completion_menu_current_color)
            if pretty
            else None
        )
        self.completion_menu_current_bg_color = (
            ColorUtils.ensure_hash_prefix(self.color_settings.completion_menu_current_bg_color)
            if pretty
            else None
        )
        self.split_line_color = (
            ColorUtils.ensure_hash_prefix(self.color_settings.split_line_color) if pretty else None
        )
        self.shell_model_color = (
            ColorUtils.ensure_hash_prefix(self.color_settings.shell_model_color) if pretty else None
        )
        self.at_file_reference_color = (
            ColorUtils.ensure_hash_prefix(self.color_settings.at_file_reference_color) if pretty else None
        )
        
        self.code_theme = self.color_settings.code_theme
        
        # Validate color settings after initialization
        self._validate_color_settings()
    
    def _validate_color_settings(self):
        """Validate configured color strings and reset invalid ones."""
        from rich.color import ColorParseError
        from rich.style import Style as RichStyle
        
        color_attributes = [
            "user_input_color",
            "tool_output_color", 
            "tool_error_color",
            "tool_warning_color",
            "assistant_output_color",
            "completion_menu_color",
            "completion_menu_bg_color",
            "completion_menu_current_color",
            "completion_menu_current_bg_color",
            "split_line_color",
            "shell_model_color",
            "at_file_reference_color",
        ]
        
        for attr_name in color_attributes:
            color_value = getattr(self, attr_name, None)
            if color_value:
                try:
                    # Try creating a style to validate the color
                    RichStyle(color=color_value)
                except ColorParseError as e:
                    # Print warning and reset invalid color to None
                    print(f"Warning: Invalid configuration for {attr_name}: '{color_value}'. {e}. Disabling this color.")
                    setattr(self, attr_name, None)
