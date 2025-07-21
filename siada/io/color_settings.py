from dataclasses import dataclass


@dataclass
class ColorSettings:
    user_input_color: str = "blue"
    tool_output_color: str = None
    tool_error_color: str = "red"
    tool_warning_color: str = "#FFA500"
    assistant_output_color: str = "blue"
    completion_menu_color: str = None
    completion_menu_bg_color: str = None
    completion_menu_current_color: str = None
    completion_menu_current_bg_color: str = None
    code_theme: str = "default" 