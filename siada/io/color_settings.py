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
            "code_theme": "default"
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
            "code_theme": "monokai"
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
            "code_theme": "default"
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