# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Integration tests for BaseCodeAgent

These tests verify the core functionality of BaseCodeAgent including:
- Agent interaction with real model calls
- Tool integration and availability
- Multi-turn conversations
- Code generation capabilities

Note: These tests require a valid DEEPSEEK_KEY environment variable.
"""

import asyncio
import os
import pytest
from dotenv import load_dotenv
from google.adk.runners import InMemoryRunner
from google.genai import types

from siada.agent_hub.a2a.a2a_agents.base_code_agent import BaseCodeAgent
from siada.tools.coder.file_operator import edit_for_adk
from siada.tools.coder.file_search.search import regex_search_for_adk
from siada.tools.coder.run_cmd import run_command_for_adk
from siada.tools.ast.ast_tool import list_code_definitions_for_adk

# Load environment variables
load_dotenv(override=True)

# Test configuration
APP_NAME = 'test_base_code_agent'
USER_ID = 'test_user'
TIMEOUT = 60  # seconds for model calls


@pytest.fixture
def agent():
    """Create a BaseCodeAgent instance for testing."""
    return BaseCodeAgent().create_agent()


@pytest.fixture
def runner():
    """Create an InMemoryRunner with a fresh agent for each test."""
    agent = BaseCodeAgent().create_agent()
    runner = InMemoryRunner(
        agent=agent,
        app_name=APP_NAME,
    )
    return runner


async def send_message(runner, session_id: str, message: str, timeout: int = TIMEOUT):
    """
    Helper function to send a message and collect responses.
    
    Args:
        runner: The InMemoryRunner instance
        session_id: The session ID to use
        message: The message to send
        timeout: Timeout in seconds
        
    Returns:
        List of response texts from the agent
    """
    content = types.Content(
        role='user',
        parts=[types.Part.from_text(text=message)]
    )
    
    responses = []
    got_final_response = False
    
    try:
        async with asyncio.timeout(timeout):
            async for event in runner.run_async(
                user_id=USER_ID,
                session_id=session_id,
                new_message=content,
            ):
                # Collect text responses
                if event.content.parts and event.content.parts[0].text:
                    responses.append(event.content.parts[0].text)
                
                # Check if this is the final event (role='model' and no tool calls)
                if (event.content.role == 'model' and 
                    event.content.parts and 
                    not any(hasattr(part, 'function_call') and part.function_call for part in event.content.parts)):
                    got_final_response = True
                    break
                    
    except asyncio.TimeoutError:
        pytest.fail(f"Message timed out after {timeout} seconds")
    
    return responses


# ============================================================================
# 3. Agent 交互测试（真实模型调用）
# ============================================================================

@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.slow
async def test_agent_simple_conversation(runner):
    """测试简单对话功能，验证 agent 能正常响应。"""
    # Create session
    session = await runner.session_service.create_session(
        app_name=APP_NAME,
        user_id=USER_ID
    )
    
    # Send a simple greeting
    responses = await send_message(runner, session.id, "你好，请介绍一下你自己")
    
    # Verify we got responses
    assert len(responses) > 0, "Agent should respond to greeting"
    
    # Verify response is not empty
    full_response = " ".join(responses)
    assert len(full_response) > 0, "Response should not be empty"
    
    print(f"\n[test_agent_simple_conversation] Response: {full_response[:200]}...")


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.slow
async def test_agent_code_generation(runner):
    """测试代码生成能力，让 agent 生成一个简单的 Python 函数。"""
    # Create session
    session = await runner.session_service.create_session(
        app_name=APP_NAME,
        user_id=USER_ID
    )
    
    # Request code generation
    message = "请写一个计算斐波那契数列第n项的Python函数，函数名为fibonacci"
    responses = await send_message(runner, session.id, message)
    
    # Verify we got responses
    assert len(responses) > 0, "Agent should respond to code generation request"
    
    # Verify response contains code-like content
    full_response = " ".join(responses)
    assert len(full_response) > 0, "Response should not be empty"
    
    # Check for common code indicators
    has_code_indicators = any(
        indicator in full_response.lower()
        for indicator in ['def', 'fibonacci', 'return', 'function', '函数']
    )
    assert has_code_indicators, "Response should contain code or code-related content"
    
    print(f"\n[test_agent_code_generation] Response length: {len(full_response)}")
    print(f"Contains code indicators: {has_code_indicators}")


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.slow
async def test_agent_tool_usage(runner):
    """测试 agent 使用工具的能力。"""
    # Create session
    session = await runner.session_service.create_session(
        app_name=APP_NAME,
        user_id=USER_ID
    )
    
    # Request to search for Python files
    message = "请搜索当前目录下所有的 .py 文件，使用正则搜索工具"
    responses = await send_message(runner, session.id, message, timeout=90)
    
    # Verify we got responses
    assert len(responses) > 0, "Agent should respond to tool usage request"
    
    full_response = " ".join(responses)
    assert len(full_response) > 0, "Response should not be empty"
    
    print(f"\n[test_agent_tool_usage] Response length: {len(full_response)}")
    print(f"First 300 chars: {full_response[:300]}...")


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.slow
async def test_agent_multi_turn_conversation(runner):
    """测试多轮对话，验证上下文保持。"""
    # Create session
    session = await runner.session_service.create_session(
        app_name=APP_NAME,
        user_id=USER_ID
    )
    
    # First turn: Ask about a topic
    responses1 = await send_message(
        runner, session.id,
        "请记住这个数字：42。这是一个重要的数字。"
    )
    assert len(responses1) > 0, "Agent should respond to first message"
    
    # Second turn: Reference the previous context
    responses2 = await send_message(
        runner, session.id,
        "我刚才让你记住的数字是多少？"
    )
    assert len(responses2) > 0, "Agent should respond to second message"
    
    # Verify the agent remembers the context
    full_response2 = " ".join(responses2)
    assert '42' in full_response2, "Agent should remember the number from previous turn"
    
    print(f"\n[test_agent_multi_turn_conversation] Context maintained: '42' found in response")


# ============================================================================
# 4. 工具集成测试
# ============================================================================

def test_edit_tool_available(agent):
    """验证文件编辑工具在 agent 中可用。"""
    tools = agent.tools
    assert tools is not None, "Agent should have tools"
    
    # Check if edit_for_adk is in the tools list
    tool_names = [tool.__name__ if hasattr(tool, '__name__') else str(tool) for tool in tools]
    assert 'edit_for_adk' in tool_names, "edit_for_adk should be in agent tools"
    
    # Verify the tool is the correct function
    assert edit_for_adk in tools, "edit_for_adk function should be in tools"
    
    print(f"\n[test_edit_tool_available] Tool found: edit_for_adk")


def test_search_tool_available(agent):
    """验证搜索工具在 agent 中可用。"""
    tools = agent.tools
    assert tools is not None, "Agent should have tools"
    
    # Check if regex_search_for_adk is in the tools list
    tool_names = [tool.__name__ if hasattr(tool, '__name__') else str(tool) for tool in tools]
    assert 'regex_search_for_adk' in tool_names, "regex_search_for_adk should be in agent tools"
    
    # Verify the tool is the correct function
    assert regex_search_for_adk in tools, "regex_search_for_adk function should be in tools"
    
    print(f"\n[test_search_tool_available] Tool found: regex_search_for_adk")


def test_command_tool_available(agent):
    """验证命令执行工具在 agent 中可用。"""
    tools = agent.tools
    assert tools is not None, "Agent should have tools"
    
    # Check if run_command_for_adk is in the tools list
    tool_names = [tool.__name__ if hasattr(tool, '__name__') else str(tool) for tool in tools]
    assert 'run_command_for_adk' in tool_names, "run_command_for_adk should be in agent tools"
    
    # Verify the tool is the correct function
    assert run_command_for_adk in tools, "run_command_for_adk function should be in tools"
    
    print(f"\n[test_command_tool_available] Tool found: run_command_for_adk")


def test_ast_tool_available(agent):
    """验证 AST 分析工具在 agent 中可用。"""
    tools = agent.tools
    assert tools is not None, "Agent should have tools"
    
    # Check if list_code_definitions_for_adk is in the tools list
    tool_names = [tool.__name__ if hasattr(tool, '__name__') else str(tool) for tool in tools]
    assert 'list_code_definitions_for_adk' in tool_names, "list_code_definitions_for_adk should be in agent tools"
    
    # Verify the tool is the correct function
    assert list_code_definitions_for_adk in tools, "list_code_definitions_for_adk function should be in tools"
    
    print(f"\n[test_ast_tool_available] Tool found: list_code_definitions_for_adk")


def test_all_default_tools_available(agent):
    """验证所有默认工具都在 agent 中可用。"""
    tools = agent.tools
    assert tools is not None, "Agent should have tools"
    
    expected_tools = [
        edit_for_adk,
        regex_search_for_adk,
        run_command_for_adk,
        list_code_definitions_for_adk,
    ]
    
    for expected_tool in expected_tools:
        assert expected_tool in tools, f"{expected_tool.__name__} should be in agent tools"
    
    print(f"\n[test_all_default_tools_available] All {len(expected_tools)} default tools found")


# ============================================================================
# Additional helper tests
# ============================================================================

def test_agent_creation():
    """测试 agent 能够成功创建。"""
    agent = BaseCodeAgent().create_agent()
    assert agent is not None, "Agent should be created successfully"
    assert agent.name == "code_agent", "Agent should have correct name"
    assert agent.description is not None, "Agent should have description"
    assert agent.tools is not None, "Agent should have tools"
    assert len(agent.tools) > 0, "Agent should have at least one tool"
    
    print(f"\n[test_agent_creation] Agent created with {len(agent.tools)} tools")


@pytest.mark.skipif(
    not os.environ.get("DEEPSEEK_KEY"),
    reason="DEEPSEEK_KEY environment variable not set"
)
def test_deepseek_key_configured():
    """验证 DeepSeek API key 已配置。"""
    api_key = os.environ.get("DEEPSEEK_KEY")
    assert api_key is not None, "DEEPSEEK_KEY should be set"
    assert len(api_key) > 0, "DEEPSEEK_KEY should not be empty"
    
    print(f"\n[test_deepseek_key_configured] API key configured (length: {len(api_key)})")
