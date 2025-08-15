"""
BugFixAgent 测试用例

专门测试 BugFixAgent 的 assemble_user_input 方法功能
"""
import unittest
import tempfile
import shutil
import os
import sys
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from siada.agent_hub.coder.bug_fix_agent import BugFixAgent
from siada.foundation.code_agent_context import CodeAgentContext


class TestBugFixAgentAssembleUserInput(unittest.TestCase):
    """测试 BugFixAgent 的 assemble_user_input 方法"""
    
    def setUp(self):
        """设置测试环境"""
        self.test_dir = tempfile.mkdtemp()
        self.agent = BugFixAgent()
        print(f"\n测试目录: {self.test_dir}")

    def tearDown(self):
        """清理测试环境"""
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_assemble_user_input_basic(self):
        """测试基本的用户输入组装功能"""
        print("\n=== 测试基本用户输入组装 ===")
        
        # 准备测试数据
        user_input = "修复登录功能的bug，用户无法正常登录"
        context = CodeAgentContext(root_dir=self.test_dir)
        
        # 模拟 generate_repo_map 方法返回空字符串
        with patch.object(self.agent, 'generate_repo_map', return_value=""):
            result = self.agent.assemble_user_input(user_input, context)
        
        # 验证结果
        self.assertIsInstance(result, str)
        self.assertIn("<task>", result)
        self.assertIn("修复登录功能的bug，用户无法正常登录", result)
        self.assertIn("</task>", result)
        self.assertIn("<environment_details>", result)
        self.assertIn("Repository Map:", result)
        self.assertIn("</environment_details>", result)
        
        print(f"组装结果长度: {len(result)}")
        print("✓ 基本用户输入组装测试通过")

    def test_assemble_user_input_with_repo_map(self):
        """测试包含仓库地图的用户输入组装"""
        print("\n=== 测试包含仓库地图的用户输入组装 ===")
        
        user_input = "分析代码中的性能问题"
        context = CodeAgentContext(root_dir=self.test_dir)
        
        # 模拟仓库地图内容
        mock_repo_map = """
siada/
├── agent_hub/
│   ├── coder/
│   │   ├── bug_fix_agent.py
│   │   └── code_context.py
│   └── siada_agent.py
└── tools/
    └── coder/
        ├── file_operator.py
        └── repo_map/
            └── repo_map.py
"""
        
        with patch.object(self.agent, 'generate_repo_map', return_value=mock_repo_map):
            result = self.agent.assemble_user_input(user_input, context)
        
        # 验证结果
        self.assertIn("分析代码中的性能问题", result)
        self.assertIn("siada/", result)
        self.assertIn("bug_fix_agent.py", result)
        self.assertIn("Repository Map:", result)
        
        # 验证结构完整性
        self.assertTrue(result.startswith("<task>"))
        self.assertIn("</task>", result)
        self.assertIn("<environment_details>", result)
        self.assertIn("</environment_details>", result)
        
        print("✓ 包含仓库地图的用户输入组装测试通过")

    def test_assemble_user_input_empty_repo_map(self):
        """测试仓库地图为空的情况"""
        print("\n=== 测试空仓库地图情况 ===")
        
        user_input = "检查代码质量"
        context = CodeAgentContext(root_dir=self.test_dir)
        
        # 模拟 generate_repo_map 返回空字符串
        with patch.object(self.agent, 'generate_repo_map', return_value=""):
            result = self.agent.assemble_user_input(user_input, context)
        
        # 验证结果
        self.assertIn("检查代码质量", result)
        self.assertIn("Repository Map: 无法生成仓库地图", result)
        
        print("✓ 空仓库地图情况测试通过")

    def test_assemble_user_input_none_repo_map(self):
        """测试仓库地图为 None 的情况"""
        print("\n=== 测试 None 仓库地图情况 ===")
        
        user_input = "优化算法性能"
        context = CodeAgentContext(root_dir=self.test_dir)
        
        # 模拟 generate_repo_map 返回 None
        with patch.object(self.agent, 'generate_repo_map', return_value=None):
            result = self.agent.assemble_user_input(user_input, context)
        
        # 验证结果
        self.assertIn("优化算法性能", result)
        self.assertIn("Repository Map: 无法生成仓库地图", result)
        
        print("✓ None 仓库地图情况测试通过")

    def test_assemble_user_input_special_characters(self):
        """测试包含特殊字符的用户输入"""
        print("\n=== 测试特殊字符用户输入 ===")
        
        user_input = "修复 <script> 标签解析问题，处理 & 符号和 \"引号\""
        context = CodeAgentContext(root_dir=self.test_dir)
        
        with patch.object(self.agent, 'generate_repo_map', return_value="简单的仓库地图"):
            result = self.agent.assemble_user_input(user_input, context)
        
        # 验证特殊字符被正确处理
        self.assertIn("<script>", result)
        self.assertIn("&", result)
        self.assertIn("\"引号\"", result)
        
        print("✓ 特殊字符用户输入测试通过")

    def test_assemble_user_input_long_input(self):
        """测试长用户输入"""
        print("\n=== 测试长用户输入 ===")
        
        # 创建一个很长的用户输入
        user_input = "修复以下问题：" + "这是一个很长的描述。" * 100
        context = CodeAgentContext(root_dir=self.test_dir)
        
        with patch.object(self.agent, 'generate_repo_map', return_value="仓库地图内容"):
            result = self.agent.assemble_user_input(user_input, context)
        
        # 验证长输入被正确处理
        self.assertIn("修复以下问题：", result)
        self.assertGreater(len(result), 1000)  # 确保结果足够长
        
        print(f"长输入结果长度: {len(result)}")
        print("✓ 长用户输入测试通过")

    def test_assemble_user_input_multiline_input(self):
        """测试多行用户输入"""
        print("\n=== 测试多行用户输入 ===")
        
        user_input = """修复以下问题：
1. 登录功能异常
2. 数据库连接超时
3. 前端页面加载缓慢

错误信息：
- ConnectionError: Unable to connect to database
- TimeoutError: Request timeout after 30 seconds"""
        
        context = CodeAgentContext(root_dir=self.test_dir)
        
        with patch.object(self.agent, 'generate_repo_map', return_value="多行仓库地图\n包含换行符"):
            result = self.agent.assemble_user_input(user_input, context)
        
        # 验证多行输入被正确处理
        self.assertIn("登录功能异常", result)
        self.assertIn("数据库连接超时", result)
        self.assertIn("ConnectionError", result)
        self.assertIn("TimeoutError", result)
        
        print("✓ 多行用户输入测试通过")


class TestBugFixAgentGenerateRepoMap(unittest.TestCase):
    """测试 BugFixAgent 的 generate_repo_map 方法"""
    
    def setUp(self):
        """设置测试环境"""
        self.test_dir = tempfile.mkdtemp()
        self.agent = BugFixAgent()
        print(f"\n测试目录: {self.test_dir}")

    def tearDown(self):
        """清理测试环境"""
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _create_test_python_file(self, filename, content):
        """创建测试用的 Python 文件"""
        filepath = os.path.join(self.test_dir, filename)
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return filepath

    def test_generate_repo_map_empty_directory(self):
        """测试空目录的仓库地图生成"""
        print("\n=== 测试空目录仓库地图生成 ===")
        
        context = CodeAgentContext(root_dir=self.test_dir)
        
        # 模拟 get_repo_map_instance 返回 None
        with patch.object(self.agent, 'get_repo_map_instance', return_value=None):
            result = self.agent.generate_repo_map(context)
        
        self.assertEqual(result, "")
        print("✓ 空目录仓库地图生成测试通过")

    def test_generate_repo_map_no_context_root_dir(self):
        """测试上下文没有根目录的情况"""
        print("\n=== 测试无根目录上下文 ===")
        
        context = CodeAgentContext(root_dir=None)
        result = self.agent.generate_repo_map(context)
        
        self.assertEqual(result, "")
        print("✓ 无根目录上下文测试通过")

    def test_generate_repo_map_with_python_files(self):
        """测试包含 Python 文件的仓库地图生成"""
        print("\n=== 测试包含 Python 文件的仓库地图生成 ===")
        
        # 创建测试 Python 文件
        self._create_test_python_file("main.py", """
def main():
    print("Hello, World!")
    return "success"

class TestClass:
    def __init__(self):
        self.value = 42
    
    def get_value(self):
        return self.value

if __name__ == "__main__":
    main()
""")
        
        self._create_test_python_file("utils/helper.py", """
def helper_function():
    return "helper"

class UtilityClass:
    @staticmethod
    def static_method():
        return "static"
""")
        
        context = CodeAgentContext(root_dir=self.test_dir)
        
        # 模拟 RepoMap 实例
        mock_repo_map = Mock()
        mock_repo_map.get_repo_map.return_value = "模拟的仓库地图内容"
        
        with patch.object(self.agent, 'get_repo_map_instance', return_value=mock_repo_map):
            result = self.agent.generate_repo_map(context)
        
        # 验证结果
        self.assertEqual(result, "模拟的仓库地图内容")
        
        # 验证 get_repo_map 被正确调用
        mock_repo_map.get_repo_map.assert_called_once()
        call_args = mock_repo_map.get_repo_map.call_args
        
        # 检查调用参数
        self.assertEqual(call_args[1]['chat_files'], [])
        self.assertIsInstance(call_args[1]['other_files'], list)
        self.assertEqual(call_args[1]['mentioned_fnames'], set())
        self.assertEqual(call_args[1]['mentioned_idents'], set(['class', 'def', 'function']))
        
        print("✓ 包含 Python 文件的仓库地图生成测试通过")

    def test_generate_repo_map_file_filtering(self):
        """测试文件过滤逻辑"""
        print("\n=== 测试文件过滤逻辑 ===")
        
        # 创建各种类型的文件
        # 创建一个满足条件的文件：内容长度>100，非注释行数>5
        good_content = """def function():
    '''这是一个函数'''
    print("Hello, World!")
    return "success"

class TestClass:
    def __init__(self):
        self.value = 42
    
    def get_value(self):
        return self.value
    
    def set_value(self, value):
        self.value = value

# 这是注释
# 更多注释
"""
        self._create_test_python_file("good_file.py", good_content)
        self._create_test_python_file("small_file.py", "# small")  # 太小的文件
        self._create_test_python_file("empty_file.py", "")  # 空文件
        self._create_test_python_file(".hidden_file.py", "def hidden(): pass")  # 隐藏文件
        
        # 创建非 Python 文件
        with open(os.path.join(self.test_dir, "readme.txt"), 'w') as f:
            f.write("This is a readme file")
        
        # 创建应该被跳过的目录
        os.makedirs(os.path.join(self.test_dir, "__pycache__"), exist_ok=True)
        self._create_test_python_file("__pycache__/cached.py", "cached content")
        
        context = CodeAgentContext(root_dir=self.test_dir)
        
        # 模拟 RepoMap 实例
        mock_repo_map = Mock()
        mock_repo_map.get_repo_map.return_value = "过滤后的仓库地图"
        
        with patch.object(self.agent, 'get_repo_map_instance', return_value=mock_repo_map):
            result = self.agent.generate_repo_map(context)
        
        # 验证结果
        self.assertEqual(result, "过滤后的仓库地图")
        
        # 检查传递给 get_repo_map 的文件列表
        call_args = mock_repo_map.get_repo_map.call_args
        other_files = call_args[1]['other_files']
        
        # 应该只包含 good_file.py
        self.assertEqual(len(other_files), 1)
        self.assertTrue(other_files[0].endswith("good_file.py"))
        
        print("✓ 文件过滤逻辑测试通过")

    def test_generate_repo_map_file_limit(self):
        """测试文件数量限制"""
        print("\n=== 测试文件数量限制 ===")
        
        # 创建超过 50 个文件
        for i in range(60):
            content = f"def function_{i}():\n    pass\n" + "# comment\n" * 10
            self._create_test_python_file(f"file_{i:02d}.py", content)
        
        context = CodeAgentContext(root_dir=self.test_dir)
        
        # 模拟 RepoMap 实例
        mock_repo_map = Mock()
        mock_repo_map.get_repo_map.return_value = "限制后的仓库地图"
        
        with patch.object(self.agent, 'get_repo_map_instance', return_value=mock_repo_map):
            result = self.agent.generate_repo_map(context)
        
        # 验证结果
        self.assertEqual(result, "限制后的仓库地图")
        
        # 检查文件数量限制
        call_args = mock_repo_map.get_repo_map.call_args
        other_files = call_args[1]['other_files']
        
        # 应该限制在 50 个文件以内
        self.assertLessEqual(len(other_files), 50)
        
        print(f"实际传递的文件数量: {len(other_files)}")
        print("✓ 文件数量限制测试通过")

    def test_generate_repo_map_exception_handling(self):
        """测试异常处理"""
        print("\n=== 测试异常处理 ===")
        
        context = CodeAgentContext(root_dir=self.test_dir)
        
        # 模拟 get_repo_map_instance 抛出异常
        with patch.object(self.agent, 'get_repo_map_instance', side_effect=Exception("模拟异常")):
            result = self.agent.generate_repo_map(context)
        
        # 应该返回错误信息而不是抛出异常
        self.assertIn("生成仓库地图时出错", result)
        self.assertIn("模拟异常", result)
        
        print("✓ 异常处理测试通过")

    def test_generate_repo_map_repo_map_exception(self):
        """测试 RepoMap.get_repo_map 抛出异常的情况"""
        print("\n=== 测试 RepoMap 异常处理 ===")
        
        self._create_test_python_file("test.py", "def test(): pass\n" + "# comment\n" * 10)
        
        context = CodeAgentContext(root_dir=self.test_dir)
        
        # 模拟 RepoMap 实例，但 get_repo_map 抛出异常
        mock_repo_map = Mock()
        mock_repo_map.get_repo_map.side_effect = Exception("RepoMap 异常")
        
        with patch.object(self.agent, 'get_repo_map_instance', return_value=mock_repo_map):
            result = self.agent.generate_repo_map(context)
        
        # 应该返回错误信息
        self.assertIn("生成仓库地图时出错", result)
        self.assertIn("RepoMap 异常", result)
        
        print("✓ RepoMap 异常处理测试通过")


class TestBugFixAgentIntegration(unittest.TestCase):
    """BugFixAgent 集成测试"""
    
    def setUp(self):
        """设置测试环境"""
        self.test_dir = tempfile.mkdtemp()
        self.agent = BugFixAgent()
        print(f"\n测试目录: {self.test_dir}")

    def tearDown(self):
        """清理测试环境"""
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_assemble_user_input_integration(self):
        """测试 assemble_user_input 的完整集成"""
        print("\n=== 测试完整集成 ===")
        
        # 创建一个真实的项目结构
        os.makedirs(os.path.join(self.test_dir, "src"), exist_ok=True)
        
        with open(os.path.join(self.test_dir, "src", "main.py"), 'w', encoding='utf-8') as f:
            f.write("""
def main():
    '''主函数'''
    print("Hello, World!")
    return 0

class Application:
    '''应用程序类'''
    def __init__(self):
        self.name = "TestApp"
    
    def run(self):
        '''运行应用程序'''
        return main()

if __name__ == "__main__":
    app = Application()
    app.run()
""")
        
        user_input = "修复应用程序启动时的内存泄漏问题"
        context = CodeAgentContext(root_dir=self.test_dir)
        
        # 执行完整的 assemble_user_input
        result = self.agent.assemble_user_input(user_input, context)
        
        # 验证结果的完整性
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 100)  # 确保有足够的内容
        
        # 验证基本结构
        self.assertIn("<task>", result)
        self.assertIn("修复应用程序启动时的内存泄漏问题", result)
        self.assertIn("</task>", result)
        self.assertIn("<environment_details>", result)
        self.assertIn("Repository Map:", result)
        self.assertIn("</environment_details>", result)
        
        print(f"集成测试结果长度: {len(result)}")
        print("结果预览:")
        print(result[:300] + "..." if len(result) > 300 else result)
        print("✓ 完整集成测试通过")


if __name__ == '__main__':
    print("=" * 60)
    print("BugFixAgent assemble_user_input 测试用例")
    print("=" * 60)
    
    # 运行测试
    unittest.main(verbosity=2)
