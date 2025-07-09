"""
BugFixAgent.run 方法测试用例

测试 BugFixAgent 的 run 方法，Mock BugReproduceAgent 的运行，
让 BugFixAgent 自身的 Runner.run 正常执行
"""
import unittest
import tempfile
import shutil
import sys
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock, call

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from siada.agent_hub.coder.bug_fix_agent import BugFixAgent
from siada.foundation.code_agent_context import CodeAgentContext
from agents import RunConfig, RunResult


class TestBugFixAgentRun(unittest.IsolatedAsyncioTestCase):
    """测试 BugFixAgent 的 run 方法"""
    
    def setUp(self):
        """设置测试环境"""
        self.test_dir = tempfile.mkdtemp()
        self.agent = BugFixAgent()
        print(f"\n测试目录: {self.test_dir}")

    def tearDown(self):
        """清理测试环境"""
        shutil.rmtree(self.test_dir, ignore_errors=True)

    async def test_run_method_with_mocked_reproduce_agent(self):
        """测试 run 方法的完整流程，Mock BugReproduceAgent"""
        print("\n=== 测试 BugFixAgent.run 方法完整流程 ===")
        
        # 准备测试数据
        user_input = "修复登录功能的bug，用户无法正常登录，错误信息：ConnectionError"
        context = CodeAgentContext(root_dir=self.test_dir)
        
        # 模拟 assemble_user_input 的返回值
        assembled_input = f"""<task>
{user_input}
</task>

<environment_details>
Repository Map: 测试仓库地图
</environment_details>"""
        
        # 创建 Mock 对象
        mock_reproduce_agent_instance = Mock()
        mock_reproduce_result = Mock(spec=RunResult)
        mock_reproduce_result.final_output = "Bug reproduction completed: 已成功复现登录错误"
        
        mock_fix_result = Mock(spec=RunResult)
        mock_fix_result.final_output = "Bug fixed successfully: 登录功能已修复"
        
        # Mock BugReproduceAgent 类
        with patch('siada.agent_hub.coder.bug_fix_agent.BugReproduceAgent') as mock_reproduce_agent_class:
            # Mock Runner.run 方法
            with patch('siada.agent_hub.coder.bug_fix_agent.Runner.run') as mock_runner_run:
                # Mock assemble_user_input 方法
                with patch.object(self.agent, 'assemble_user_input', return_value=assembled_input):
                    
                    # 设置 Mock 返回值
                    mock_reproduce_agent_class.return_value = mock_reproduce_agent_instance
                    
                    # 设置 Runner.run 的返回值：第一次调用返回 reproduce 结果，第二次返回 fix 结果
                    mock_runner_run.side_effect = [mock_reproduce_result, mock_fix_result]
                    
                    # 执行测试
                    result = await self.agent.run(user_input, context)
                    
                    # 验证结果
                    self.assertEqual(result, mock_fix_result)
                    print(f"✓ 返回结果正确: {result.final_output}")
                    
                    # 验证 BugReproduceAgent 被实例化
                    mock_reproduce_agent_class.assert_called_once()
                    print("✓ BugReproduceAgent 被正确实例化")
                    
                    # 验证 assemble_user_input 被调用
                    self.agent.assemble_user_input.assert_called_once_with(user_input, context)
                    print("✓ assemble_user_input 被正确调用")
                    
                    # 验证 Runner.run 被调用两次
                    self.assertEqual(mock_runner_run.call_count, 2)
                    print("✓ Runner.run 被调用两次")
                    
                    # 验证第一次调用（reproduce 阶段）
                    first_call = mock_runner_run.call_args_list[0]
                    self.assertEqual(first_call[1]['starting_agent'], mock_reproduce_agent_instance)
                    self.assertEqual(first_call[1]['input'], assembled_input)
                    self.assertIn('max_turns', first_call[1])
                    self.assertIn('run_config', first_call[1])
                    self.assertEqual(first_call[1]['context'], context)
                    print("✓ 第一次 Runner.run 调用参数正确（reproduce 阶段）")
                    
                    # 验证第二次调用（bug fix 阶段）
                    second_call = mock_runner_run.call_args_list[1]
                    self.assertEqual(second_call[1]['starting_agent'], self.agent)
                    self.assertIn('max_turns', second_call[1])
                    self.assertIn('run_config', second_call[1])
                    self.assertEqual(second_call[1]['context'], context)
                    
                    # 验证第二次调用的 input 是正确的消息列表
                    input_list = second_call[1]['input']
                    self.assertIsInstance(input_list, list)
                    self.assertEqual(len(input_list), 2)
                    
                    # 验证用户消息
                    user_message = input_list[0]
                    self.assertEqual(user_message['content'], assembled_input)
                    self.assertEqual(user_message['role'], 'user')
                    
                    # 验证复现消息
                    reproduce_message = input_list[1]
                    self.assertEqual(reproduce_message['content'], mock_reproduce_result.final_output)
                    self.assertEqual(reproduce_message['role'], 'user')
                    
                    print("✓ 第二次 Runner.run 调用参数正确（bug fix 阶段）")

    async def test_run_method_input_assembly(self):
        """测试 run 方法中输入消息的组装逻辑"""
        print("\n=== 测试输入消息组装逻辑 ===")
        
        user_input = "修复数据库连接超时问题"
        context = CodeAgentContext(root_dir=self.test_dir)
        assembled_input = "组装后的用户输入"
        reproduce_output = "复现结果：数据库连接超时已复现"
        
        mock_reproduce_result = Mock(spec=RunResult)
        mock_reproduce_result.final_output = reproduce_output
        
        mock_fix_result = Mock(spec=RunResult)
        mock_fix_result.final_output = "修复完成"
        
        with patch('siada.agent_hub.coder.bug_fix_agent.BugReproduceAgent'):
            with patch('siada.agent_hub.coder.bug_fix_agent.Runner.run') as mock_runner_run:
                with patch.object(self.agent, 'assemble_user_input', return_value=assembled_input):
                    
                    mock_runner_run.side_effect = [mock_reproduce_result, mock_fix_result]
                    
                    await self.agent.run(user_input, context)
                    
                    # 获取第二次调用的输入列表
                    second_call = mock_runner_run.call_args_list[1]
                    input_list = second_call[1]['input']
                    
                    # 验证消息结构
                    expected_user_message = {"content": assembled_input, "role": "user"}
                    expected_reproduce_message = {"content": reproduce_output, "role": "user"}
                    
                    self.assertEqual(input_list[0], expected_user_message)
                    self.assertEqual(input_list[1], expected_reproduce_message)
                    
                    print("✓ 输入消息组装逻辑正确")

    async def test_run_method_config_passing(self):
        """测试 run 方法中配置和上下文的传递"""
        print("\n=== 测试配置和上下文传递 ===")
        
        user_input = "测试配置传递"
        context = CodeAgentContext(root_dir=self.test_dir)
        
        mock_reproduce_result = Mock(spec=RunResult)
        mock_reproduce_result.final_output = "配置测试复现结果"
        
        mock_fix_result = Mock(spec=RunResult)
        mock_fix_result.final_output = "配置测试修复结果"
        
        with patch('siada.agent_hub.coder.bug_fix_agent.BugReproduceAgent'):
            with patch('siada.agent_hub.coder.bug_fix_agent.Runner.run') as mock_runner_run:
                with patch.object(self.agent, 'assemble_user_input', return_value="测试输入"):
                    
                    mock_runner_run.side_effect = [mock_reproduce_result, mock_fix_result]
                    
                    await self.agent.run(user_input, context)
                    
                    # 验证两次调用都传递了正确的配置
                    for call_args in mock_runner_run.call_args_list:
                        # 验证 RunConfig
                        run_config = call_args[1]['run_config']
                        self.assertIsInstance(run_config, RunConfig)
                        self.assertFalse(run_config.tracing_disabled)
                        
                        # 验证 max_turns
                        from siada.foundation.config import settings
                        self.assertEqual(call_args[1]['max_turns'], settings.MAX_TURNS)
                        
                        # 验证 context
                        self.assertEqual(call_args[1]['context'], context)
                    
                    print("✓ 配置和上下文传递正确")

    async def test_run_method_with_empty_reproduce_output(self):
        """测试复现阶段返回空输出的情况"""
        print("\n=== 测试复现阶段空输出情况 ===")
        
        user_input = "测试空输出"
        context = CodeAgentContext(root_dir=self.test_dir)
        
        mock_reproduce_result = Mock(spec=RunResult)
        mock_reproduce_result.final_output = ""  # 空输出
        
        mock_fix_result = Mock(spec=RunResult)
        mock_fix_result.final_output = "修复完成"
        
        with patch('siada.agent_hub.coder.bug_fix_agent.BugReproduceAgent'):
            with patch('siada.agent_hub.coder.bug_fix_agent.Runner.run') as mock_runner_run:
                with patch.object(self.agent, 'assemble_user_input', return_value="测试输入"):
                    
                    mock_runner_run.side_effect = [mock_reproduce_result, mock_fix_result]
                    
                    result = await self.agent.run(user_input, context)
                    
                    # 验证即使复现输出为空，流程仍然正常
                    self.assertEqual(result, mock_fix_result)
                    
                    # 验证第二次调用的输入包含空的复现消息
                    second_call = mock_runner_run.call_args_list[1]
                    input_list = second_call[1]['input']
                    reproduce_message = input_list[1]
                    self.assertEqual(reproduce_message['content'], "")
                    
                    print("✓ 空输出情况处理正确")

    async def test_run_method_with_long_reproduce_output(self):
        """测试复现阶段返回长输出的情况"""
        print("\n=== 测试复现阶段长输出情况 ===")
        
        user_input = "测试长输出"
        context = CodeAgentContext(root_dir=self.test_dir)
        
        # 创建一个很长的复现输出
        long_output = "复现结果：" + "详细的错误信息和堆栈跟踪。" * 100
        
        mock_reproduce_result = Mock(spec=RunResult)
        mock_reproduce_result.final_output = long_output
        
        mock_fix_result = Mock(spec=RunResult)
        mock_fix_result.final_output = "修复完成"
        
        with patch('siada.agent_hub.coder.bug_fix_agent.BugReproduceAgent'):
            with patch('siada.agent_hub.coder.bug_fix_agent.Runner.run') as mock_runner_run:
                with patch.object(self.agent, 'assemble_user_input', return_value="测试输入"):
                    
                    mock_runner_run.side_effect = [mock_reproduce_result, mock_fix_result]
                    
                    result = await self.agent.run(user_input, context)
                    
                    # 验证长输出被正确处理
                    self.assertEqual(result, mock_fix_result)
                    
                    # 验证第二次调用的输入包含完整的长输出
                    second_call = mock_runner_run.call_args_list[1]
                    input_list = second_call[1]['input']
                    reproduce_message = input_list[1]
                    self.assertEqual(reproduce_message['content'], long_output)
                    
                    print(f"✓ 长输出情况处理正确，输出长度: {len(long_output)}")

    async def test_run_method_with_special_characters_in_output(self):
        """测试复现输出包含特殊字符的情况"""
        print("\n=== 测试特殊字符输出情况 ===")
        
        user_input = "测试特殊字符"
        context = CodeAgentContext(root_dir=self.test_dir)
        
        # 包含特殊字符的复现输出
        special_output = """复现结果：
错误信息包含特殊字符：
- <script>alert('xss')</script>
- 引号："双引号" 和 '单引号'
- 符号：& < > % $ # @
- 换行符和制表符
- Unicode字符：中文、émojis 🚀"""
        
        mock_reproduce_result = Mock(spec=RunResult)
        mock_reproduce_result.final_output = special_output
        
        mock_fix_result = Mock(spec=RunResult)
        mock_fix_result.final_output = "修复完成"
        
        with patch('siada.agent_hub.coder.bug_fix_agent.BugReproduceAgent'):
            with patch('siada.agent_hub.coder.bug_fix_agent.Runner.run') as mock_runner_run:
                with patch.object(self.agent, 'assemble_user_input', return_value="测试输入"):
                    
                    mock_runner_run.side_effect = [mock_reproduce_result, mock_fix_result]
                    
                    result = await self.agent.run(user_input, context)
                    
                    # 验证特殊字符被正确处理
                    self.assertEqual(result, mock_fix_result)
                    
                    # 验证第二次调用的输入包含完整的特殊字符输出
                    second_call = mock_runner_run.call_args_list[1]
                    input_list = second_call[1]['input']
                    reproduce_message = input_list[1]
                    self.assertEqual(reproduce_message['content'], special_output)
                    
                    # 验证特殊字符没有被转义或修改
                    self.assertIn("<script>", reproduce_message['content'])
                    self.assertIn("\"双引号\"", reproduce_message['content'])
                    self.assertIn("'单引号'", reproduce_message['content'])
                    self.assertIn("🚀", reproduce_message['content'])
                    
                    print("✓ 特殊字符输出情况处理正确")


class TestBugFixAgentRunIntegration(unittest.IsolatedAsyncioTestCase):
    """BugFixAgent.run 方法集成测试"""
    
    def setUp(self):
        """设置测试环境"""
        self.test_dir = tempfile.mkdtemp()
        print(f"\n测试目录: {self.test_dir}")

    def tearDown(self):
        """清理测试环境"""
        shutil.rmtree(self.test_dir, ignore_errors=True)

    async def test_run_method_end_to_end_flow(self):
        """测试 run 方法的端到端流程"""
        print("\n=== 测试端到端流程 ===")
        
        # 创建真实的 BugFixAgent 实例
        agent = BugFixAgent()
        
        user_input = """修复以下Python代码的bug：

def calculate_average(numbers):
    total = 0
    for num in numbers:
        total += num
    return total / len(numbers)  # 这里可能出现除零错误

# 测试用例
print(calculate_average([]))  # 这会导致 ZeroDivisionError
"""
        
        context = CodeAgentContext(root_dir=self.test_dir)
        
        # 创建模拟的复现结果
        reproduce_output = """Bug复现成功：
1. 当传入空列表时，len(numbers) 返回 0
2. total / len(numbers) 导致 ZeroDivisionError: division by zero
3. 错误堆栈：
   File "test.py", line 5, in calculate_average
     return total / len(numbers)
   ZeroDivisionError: division by zero

建议修复方案：
- 在计算前检查列表是否为空
- 如果为空，返回 0 或抛出有意义的异常"""
        
        fix_output = """Bug修复完成：
已修改 calculate_average 函数，添加了空列表检查：

def calculate_average(numbers):
    if not numbers:  # 检查空列表
        return 0  # 或者可以抛出 ValueError("Cannot calculate average of empty list")
    total = 0
    for num in numbers:
        total += num
    return total / len(numbers)

修复验证：
- calculate_average([]) 现在返回 0 而不是抛出异常
- calculate_average([1, 2, 3]) 正常返回 2.0
- 所有测试用例通过"""
        
        mock_reproduce_result = Mock(spec=RunResult)
        mock_reproduce_result.final_output = reproduce_output
        
        mock_fix_result = Mock(spec=RunResult)
        mock_fix_result.final_output = fix_output
        
        # Mock 外部依赖，但保持内部逻辑
        with patch('siada.agent_hub.coder.bug_fix_agent.BugReproduceAgent'):
            with patch('siada.agent_hub.coder.bug_fix_agent.Runner.run') as mock_runner_run:
                with patch.object(agent, 'assemble_user_input') as mock_assemble:
                    
                    # 设置 assemble_user_input 的返回值
                    assembled_input = f"""<task>
{user_input}
</task>

<environment_details>
Repository Map: 
test.py - Python script with calculate_average function
</environment_details>"""
                    mock_assemble.return_value = assembled_input
                    
                    # 设置 Runner.run 的返回值
                    mock_runner_run.side_effect = [mock_reproduce_result, mock_fix_result]
                    
                    # 执行测试
                    result = await agent.run(user_input, context)
                    
                    # 验证整个流程
                    self.assertEqual(result, mock_fix_result)
                    self.assertIn("Bug修复完成", result.final_output)
                    self.assertIn("calculate_average", result.final_output)
                    
                    # 验证调用流程
                    mock_assemble.assert_called_once_with(user_input, context)
                    self.assertEqual(mock_runner_run.call_count, 2)
                    
                    # 验证第二次调用的输入包含复现结果
                    second_call = mock_runner_run.call_args_list[1]
                    input_list = second_call[1]['input']
                    self.assertEqual(len(input_list), 2)
                    self.assertIn("Bug复现成功", input_list[1]['content'])
                    
                    print("✓ 端到端流程测试通过")
                    print(f"✓ 最终输出长度: {len(result.final_output)}")


if __name__ == '__main__':
    print("=" * 60)
    print("BugFixAgent.run 方法测试用例")
    print("=" * 60)
    
    # 运行测试
    unittest.main(verbosity=2)
