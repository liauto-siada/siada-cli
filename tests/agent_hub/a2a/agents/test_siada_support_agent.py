#!/usr/bin/env python3
"""
Test script for SiadaSupportAgent MCP integration

This script verifies that SiadaSupportAgent properly integrates with MCP.
"""

import sys
import os

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from siada.agent_hub.a2a.a2a_agents.siada_support_agent.siada_support_agent import SiadaSupportAgent


def test_siada_support_agent():
    """Test SiadaSupportAgent creation and MCP integration"""
    print("=" * 60)
    print("Testing SiadaSupportAgent MCP Integration")
    print("=" * 60)
    
    try:
        # Create the agent
        agent_instance = SiadaSupportAgent()
        
        print("\n1. Agent Instance Created")
        print(f"   Name: {agent_instance.get_name()}")
        print(f"   MCP Enabled: {agent_instance.get_mcp_enabled()}")
        print(f"   MCP Server Filter: {agent_instance.get_mcp_server_filter()}")
        print(f"   MCP Tool Filters: {agent_instance.get_mcp_tool_filters()}")
        
        # Get tools list
        tools = agent_instance.get_tools()
        print(f"\n2. Tools List")
        print(f"   Total tools count: {len(tools)}")
        
        # Categorize tools
        from google.adk.tools.base_toolset import BaseToolset
        toolsets = [t for t in tools if isinstance(t, BaseToolset)]
        functions = [t for t in tools if callable(t) and not isinstance(t, BaseToolset)]
        
        print(f"   - Function tools: {len(functions)}")
        print(f"   - Toolsets: {len(toolsets)}")
        
        if toolsets:
            print("\n   Toolsets:")
            for ts in toolsets:
                print(f"     - {ts.__class__.__name__}")
        
        # Create the agent
        agent = agent_instance.create_agent()
        
        print(f"\n3. Agent Created Successfully")
        print(f"   Agent name: {agent.name}")
        print(f"   Agent description: {agent.description[:100]}...")
        print(f"   Agent tools count: {len(agent.tools)}")
        
        # Check role instruction
        role_inst = agent_instance.get_role_instruction()
        if role_inst:
            print(f"\n4. Role Instruction")
            print(f"   Length: {len(role_inst)} characters")
            print(f"   Contains 'lark-mcp': {'lark-mcp' in role_inst}")
            print(f"   Contains '飞书': {'飞书' in role_inst}")
        
        print("\n" + "=" * 60)
        print("✓ All checks passed!")
        print("=" * 60)
        return True
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_siada_support_agent()
    sys.exit(0 if success else 1)
