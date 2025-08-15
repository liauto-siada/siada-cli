"""
Test CodeGenAgent @ command processing functionality
"""

import unittest
import asyncio
import os
import tempfile
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from siada.agent_hub.coder.code_gen_agent import CodeGenAgent
from siada.foundation.code_agent_context import CodeAgentContext


class TestCodeGenAgentAtCommand(unittest.IsolatedAsyncioTestCase):
    """Test suite for CodeGenAgent @ command processing"""
    
    async def asyncSetUp(self):
        """Set up test environment"""
        # Create a temporary directory for testing
        self.test_dir = tempfile.mkdtemp()
        
        # Create some test files
        self.test_file_py = os.path.join(self.test_dir, "test_file.py")
        with open(self.test_file_py, 'w') as f:
            f.write("""
def hello_world():
    \"\"\"A simple hello world function\"\"\"
    return "Hello, World!"

class TestClass:
    def __init__(self):
        self.value = 42
    
    def get_value(self):
        return self.value
""")
        
        self.test_file_txt = os.path.join(self.test_dir, "readme.txt")
        with open(self.test_file_txt, 'w') as f:
            f.write("This is a test readme file.\nIt contains some documentation.")
        
        # Create CodeGenAgent instance
        self.agent = CodeGenAgent()
        
        # Create context
        self.context = CodeAgentContext(root_dir=self.test_dir)
    
    async def asyncTearDown(self):
        """Clean up test environment"""
        import shutil
        shutil.rmtree(self.test_dir, ignore_errors=True)
    
    async def test_process_at_commands_no_at_symbol(self):
        """Test processing input without @ commands"""
        user_input = "Create a new function that adds two numbers"
        print(f"\n=== test_process_at_commands_no_at_symbol ===")
        print(f"原始输入: {user_input}")
        
        result = await self.agent.process_at_commands(user_input, self.context)
        
        print(f"处理后输入: {result}")
        print(f"输入长度变化: {len(user_input)} -> {len(result)}")
        print(f"内容是否相同: {user_input == result}")
        
        # Should return original input unchanged
        self.assertEqual(result, user_input)
    
    async def test_process_at_commands_with_valid_file(self):
        """Test processing input with valid @ command"""
        user_input = f"Please explain @test_file.py and improve it"
        print(f"\n=== test_process_at_commands_with_valid_file ===")
        print(f"原始输入: {user_input}")
        
        result = await self.agent.process_at_commands(user_input, self.context)
        
        print(f"处理后输入长度: {len(result)}")
        print(f"输入长度变化: {len(user_input)} -> {len(result)}")
        print(f"处理后输入预览: {result[:200]}...")
        print(f"包含 'def hello_world': {'def hello_world' in result}")
        print(f"包含 'class TestClass': {'class TestClass' in result}")
        
        # Result should contain the file content
        self.assertIn("def hello_world", result)
        self.assertIn("class TestClass", result)
        self.assertIn("Please explain", result)
    
    async def test_process_at_commands_with_invalid_file(self):
        """Test processing input with invalid @ command"""
        user_input = "Please explain @nonexistent_file.py"
        print(f"\n=== test_process_at_commands_with_invalid_file ===")
        print(f"原始输入: {user_input}")
        
        result = await self.agent.process_at_commands(user_input, self.context)
        
        print(f"处理后输入: {result}")
        print(f"输入长度变化: {len(user_input)} -> {len(result)}")
        print(f"内容是否相同: {user_input == result}")
        
        # Should return original input if file doesn't exist
        self.assertEqual(result, user_input)
    
    async def test_process_at_commands_multiple_files(self):
        """Test processing input with multiple @ commands"""
        user_input = f"Compare @test_file.py and @readme.txt"
        print(f"\n=== test_process_at_commands_multiple_files ===")
        print(f"原始输入: {user_input}")
        
        result = await self.agent.process_at_commands(user_input, self.context)
        
        print(f"处理后输入长度: {len(result)}")
        print(f"输入长度变化: {len(user_input)} -> {len(result)}")
        print(f"处理后输入预览: {result[:300]}...")
        print(f"包含 'def hello_world': {'def hello_world' in result}")
        print(f"包含 'test readme file': {'test readme file' in result}")
        print(f"包含 'Compare': {'Compare' in result}")
        
        # Result should contain content from both files
        self.assertIn("def hello_world", result)
        self.assertIn("test readme file", result)
        self.assertIn("Compare", result)
    
    async def test_process_at_commands_error_handling(self):
        """Test error handling in @ command processing"""
        # Create context with invalid root directory
        invalid_context = CodeAgentContext(root_dir="/nonexistent/directory")
        
        user_input = "Please explain @test_file.py"
        print(f"\n=== test_process_at_commands_error_handling ===")
        print(f"原始输入: {user_input}")
        print(f"使用无效目录: /nonexistent/directory")
        
        result = await self.agent.process_at_commands(user_input, invalid_context)
        
        print(f"处理后输入: {result}")
        print(f"输入长度变化: {len(user_input)} -> {len(result)}")
        print(f"内容是否相同: {user_input == result}")
        
        # Should return original input on error
        self.assertEqual(result, user_input)
    
    async def test_run_integration_with_at_commands(self):
        """Test full run method integration with @ commands"""
        # This test would require a full agent setup with LLM provider
        # For now, we'll just test that the method can be called without errors
        
        user_input = f"Analyze @test_file.py"
        print(f"\n=== test_run_integration_with_at_commands ===")
        print(f"原始输入: {user_input}")
        
        # We can't actually run the full agent without proper LLM setup,
        # but we can test that the @ command processing part works
        processed_input = await self.agent.process_at_commands(user_input, self.context)
        
        print(f"处理后输入长度: {len(processed_input)}")
        print(f"输入长度变化: {len(user_input)} -> {len(processed_input)}")
        print(f"处理后输入预览: {processed_input[:200]}...")
        print(f"包含 'def hello_world': {'def hello_world' in processed_input}")
        print(f"包含 'Analyze': {'Analyze' in processed_input}")
        
        # Verify that @ command was processed
        self.assertIn("def hello_world", processed_input)
        self.assertIn("Analyze", processed_input)
    
    async def test_run_streamed_integration_with_at_commands(self):
        """Test full run_streamed method integration with @ commands"""
        # Similar to above, test the @ command processing part
        
        user_input = f"Review @test_file.py and @readme.txt"
        print(f"\n=== test_run_streamed_integration_with_at_commands ===")
        print(f"原始输入: {user_input}")
        
        processed_input = await self.agent.process_at_commands(user_input, self.context)
        
        print(f"处理后输入长度: {len(processed_input)}")
        print(f"输入长度变化: {len(user_input)} -> {len(processed_input)}")
        print(f"处理后输入预览: {processed_input[:300]}...")
        print(f"包含 'def hello_world': {'def hello_world' in processed_input}")
        print(f"包含 'test readme file': {'test readme file' in processed_input}")
        print(f"包含 'Review': {'Review' in processed_input}")
        
        # Verify that both @ commands were processed
        self.assertIn("def hello_world", processed_input)
        self.assertIn("test readme file", processed_input)
        self.assertIn("Review", processed_input)

    # 私有测试用例
    # async def test_process_at_commands_with_cmd_runner_file(self):
    #     """Test processing input with @ command referencing cmd_runner.py file"""
    #     user_input = "介绍一下这个文件的作用 @cmd_runner.py"
    #     print(f"\n=== test_process_at_commands_with_cmd_runner_file ===")
    #     print(f"原始输入: {user_input}")
    #
    #     self.context.root_dir = '/Users/yunan/code/copilot/siada-agenthub'
    #     result = await self.agent.process_at_commands(user_input, self.context)
    #
    #     print(f"处理后输入长度: {len(result)}")
    #     print(f"输入长度变化: {len(user_input)} -> {len(result)}")
    #     print(f"处理后输入预览: {result[:300]}...")
    #     print(f"包含 'get_windows_parent_process_name': {'get_windows_parent_process_name' in result}")
    #     print(f"包含 '介绍一下这个文件的作用': {'介绍一下这个文件的作用' in result}")
    #
    #     # Verify that @ command was processed and contains the expected function
    #     self.assertIn("get_windows_parent_process_name", result)
    #     self.assertIn("介绍一下这个文件的作用", result)


if __name__ == '__main__':
    unittest.main(verbosity=2)
