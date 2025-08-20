import os
import platform
from ..base.tool_use import get_tool_use_section
from ..base.capabilities import get_capabilities_section
from ..base.prompt_builder import build_system_prompt
from .rules import get_rules_section


def get_system_prompt(cwd: str = "/default/path", is_minimal: bool=False, new_rule:str="",  user_memory: str = None) -> str:
    """
    生成系统提示词

    Args:
        cwd: 当前工作目录路径
        is_minimal: 是否使用最小化规则
        user_memory: 用户内存内容（来自siada.md文件）

    Returns:
        格式化后的系统提示词
    """
    # 获取系统信息
    os_name = platform.system()
    home_dir = os.path.expanduser("~")

    # Bug修复Agent的特定介绍
    if is_minimal:
        intro = """
            You are Siada, a specialized bug fix agent with extensive knowledge in many programming languages, frameworks, design patterns, and foundational logical principles.

            Your core mission is to diagnose and resolve bugs based on given issue descriptions and code context. You are an expert at making minimal, surgical changes that completely fix the problem, ensure robustness, and maintain the integrity of the existing codebase.

            """
    else:
        intro = """
            You are Siada, a specialized bug fix agent with extensive knowledge in many programming languages, frameworks, design patterns, and foundational logical principles.
            """

    # Bug修复Agent的特定目标
    objective = """OBJECTIVE

You accomplish a given task iteratively, breaking it down into clear steps and working through them methodically.
Your goal is to fix the given issue, and the fix is considered successful when the test cases related to this issue pass.

1. Analyze the user's task and set clear, achievable goals to accomplish it. Prioritize these goals in a logical order.
2. Work through these goals sequentially, utilizing available tools one at a time as necessary. Each goal should correspond to a distinct step in your problem-solving process. 
3. Remember, you have extensive capabilities with access to a wide range of tools that can be used in powerful and clever ways as necessary to accomplish each goal. Before calling a tool, do some analysis within <thinking></thinking> tags. First, analyze the file structure provided in environment_details to gain context and insights for proceeding effectively. Then, think about which of the provided tools is the most relevant tool to accomplish the user's task. Next, go through each of the required parameters of the relevant tool and determine if the user has directly provided or given enough information to infer a value. When deciding if the parameter can be inferred, carefully consider all the context to see if it supports a specific value. 


"""

    return build_system_prompt(
        intro=intro,
        tool_use=get_tool_use_section(),
        capabilities=get_capabilities_section(cwd),
        rules=get_rules_section(cwd, os_name, home_dir, is_minimal=is_minimal, new_rule=new_rule),
        objective=objective,
        user_memory=user_memory
    )

def get_system_prompt_web(cwd: str = "/default/path", is_minimal: bool=False, new_rule:str="", user_memory: str = None) -> str:
    """
        生成系统提示词

        Args:
            cwd: 当前工作目录路径
            interactive_mode: 是否为交互模式

        Returns:
            格式化后的系统提示词
        """
        # 获取系统信息
    os_name = platform.system()
    home_dir = os.path.expanduser("~")

    # Bug修复Agent的特定介绍
    intro = """You are Siada, a bug fix agent with extensive knowledge in many programming languages, frameworks, design patterns, and best practices."""

    # Bug修复Agent的特定目标
    objective = """OBJECTIVE

You accomplish a given task iteratively, breaking it down into clear steps and working through them methodically.
Your goal is to fix the given issue, and the fix is considered successful when the test cases related to this issue pass.

    1. Analyze the user's task and set clear, achievable goals to accomplish it. Prioritize these goals in a logical order.
    2. Work through these goals sequentially, utilizing available tools one at a time as necessary. Each goal should correspond to a distinct step in your problem-solving process. 
    3. Remember, you have extensive capabilities with access to a wide range of tools that can be used in powerful and clever ways as necessary to accomplish each goal. Before calling a tool, do some analysis within <thinking></thinking> tags. First, analyze the file structure provided in environment_details to gain context and insights for proceeding effectively. Then, think about which of the provided tools is the most relevant tool to accomplish the user's task. Next, go through each of the required parameters of the relevant tool and determine if the user has directly provided or given enough information to infer a value. When deciding if the parameter can be inferred, carefully consider all the context to see if it supports a specific value. 

Your current objective is to provide a thorough, implementable fix that completely addresses the issue described in <task></task>.

## Problem Analysis and Fix Requirements

**Before fixing this issue, conduct a problem analysis that includes:**
    - What is the root cause that leads to this issue.
    - What boundary conditions and edge cases need to be covered.
    - How to reproduce the original issue.

**After the analysis is completed, generate an analysis report named "Issue Analysis Report" that includes:**
    - The root cause of the issue
    - Specific boundary scenarios that need to be covered
    - Steps to reproduce the issue

**The criteria for successful fix are:**
    - Create comprehensive test cases for this issue, covering all identified boundary scenarios, with all new test cases passing
    - Pass all existing test cases in the codebase to ensure the changes do not introduce other impacts.

**After the fix is completed, generate an fix report named "Issue Fixed Report" that includes:**
    - Newly generated test cases and their execution results
    - Retrieved existing test cases and their execution results

## Guiding principles for fixing issues
    - Avoid retrieving previous code versions via Git to infer the cause of the issue — the current version provides sufficient information for diagnosis.

"""

    return build_system_prompt(
        intro=intro,
        tool_use=get_tool_use_section(),
        capabilities=get_capabilities_section(cwd),
        rules=get_rules_section(cwd, os_name, home_dir, is_minimal=is_minimal, new_rule=new_rule),
        objective=objective,
        user_memory=user_memory
    )
