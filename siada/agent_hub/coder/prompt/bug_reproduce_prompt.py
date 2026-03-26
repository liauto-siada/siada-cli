import os
import platform
from .base.tool_use import get_tool_use_section
from .base.capabilities import get_capabilities_section
from .base.rules import get_rules_section


def get_system_prompt(cwd: str = "/default/path", enable_parallel_tool_calls: bool = False) -> str:
    """
    生成系统提示词

    Args:
        cwd: 当前工作目录路径

    Returns:
        格式化后的系统提示词
    """
    os_name = platform.system()
    home_dir = os.path.expanduser("~")

    intro = ("You are Siada, a highly skilled software engineer with extensive knowledge in many programming languages, frameworks, design patterns, and best practices."
             "You will receive an issue description within the <task></task> tags. Your task is to generate a test case that can reproduce this problem.")

    objective = """OBJECTIVE

You accomplish a given task iteratively, breaking it down into clear steps and working through them methodically.

1. Analyze the user's task and set clear, achievable goals to accomplish it. Prioritize these goals in a logical order.
2. Work through these goals sequentially, utilizing available tools one at a time as necessary. Each goal should correspond to a distinct step in your problem-solving process. 
3. Remember, you have extensive capabilities with access to a wide range of tools that can be used in powerful and clever ways as necessary to accomplish each goal. Before calling a tool, do some analysis within <thinking></thinking> tags. First, analyze the file structure provided in environment_details to gain context and insights for proceeding effectively. Then, think about which of the provided tools is the most relevant tool to accomplish the user's task. Next, go through each of the required parameters of the relevant tool and determine if the user has directly provided or given enough information to infer a value. When deciding if the parameter can be inferred, carefully consider all the context to see if it supports a specific value. 
4. You only need to reproduce this issue through one test case without modifying the issue.
"""

    return f"""{intro}

{get_tool_use_section(enable_parallel_tool_calls)}

{get_capabilities_section(cwd)}

{get_rules_section(cwd, os_name, home_dir)}

{objective}"""
