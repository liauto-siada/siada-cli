#!/usr/bin/env python3
"""
Color Settings Demo - Tool Result and Tool Call Colors

Demonstrates the new tool_result_color and tool_call_color features
"""

from siada.io.color_settings import ColorSettings


def demo_new_colors():
    """演示新的工具颜色配置"""
    
    print("=== 新增颜色配置演示 ===\n")
    
    # 获取所有主题
    themes = ColorSettings.get_available_themes()
    
    for theme_name in themes:
        print(f"--- {theme_name.upper()} 主题 ---")
        
        # 创建主题配置
        color_config = ColorSettings.from_theme(theme_name)
        
        # 显示新增的颜色配置
        print(f"工具调用颜色 (tool_call_color): {color_config.tool_call_color}")
        print(f"工具结果颜色 (tool_result_color): {color_config.tool_result_color}")
        print()
    
    print("=== 颜色对比表 ===")
    print("| 主题    | Tool Call Color | Tool Result Color |")
    print("|---------|-----------------|-------------------|")
    
    for theme_name in themes:
        config = ColorSettings.from_theme(theme_name)
        print(f"| {theme_name:7} | {config.tool_call_color:15} | {config.tool_result_color:17} |")
    
    print("\n=== 使用方式 ===")
    print("在命令行中使用:")
    print("  siadahub --theme dark     # 深色主题，工具调用: #FFA500, 工具结果: #00FF7F")
    print("  siadahub --theme light    # 浅色主题，工具调用: #FF8C00, 工具结果: #008000")
    print("  siadahub --theme default  # 默认主题，工具调用: #FFD700, 工具结果: #00FF00")


def demo_color_application():
    """演示颜色应用到参数对象"""
    
    print("\n=== 参数应用演示 ===")
    
    class MockArgs:
        """模拟参数对象"""
        def __init__(self):
            self.tool_call_color = None
            self.tool_result_color = None
    
    # 应用深色主题
    args = MockArgs()
    dark_theme = ColorSettings.from_theme("dark")
    dark_theme.apply_to_args(args)
    
    print(f"应用深色主题后:")
    print(f"  args.tool_call_color = {args.tool_call_color}")
    print(f"  args.tool_result_color = {args.tool_result_color}")


if __name__ == "__main__":
    demo_new_colors()
    demo_color_application() 