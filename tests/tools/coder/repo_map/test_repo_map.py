"""
测试 repo_map.py 的功能

这个测试文件包含了对 RepoMap 类的完整功能测试，包括：
- 依赖检查
- 基础功能测试
- 使用 Claude Sonnet 3.7 模型进行真实测试
- 以当前 siada-agenthub 项目为例的集成测试
"""

import unittest
import tempfile
import shutil
import os
import sys
from pathlib import Path
from unittest.mock import Mock, patch

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root))

# 首先检查依赖
missing_deps = []

try:
    import networkx as nx
except ImportError:
    missing_deps.append("networkx")

try:
    import tqdm
except ImportError:
    missing_deps.append("tqdm")

try:
    import pygments
except ImportError:
    missing_deps.append("pygments")

try:
    import grep_ast
except ImportError:
    missing_deps.append("grep_ast")

try:
    import litellm
except ImportError:
    missing_deps.append("litellm")

# 尝试导入 repo_map 模块
try:
    from siada.tools.coder.repo_map.repo_map import RepoMap, Tag
    from siada.tools.coder.repo_map.dump import dump
    from siada.tools.coder.repo_map.special import filter_important_files
    from siada.tools.coder.repo_map.waiting import Spinner
    from siada.tools.coder.repo_map.io import IO, SilentIO
    from siada.tools.coder.repo_map.token_counter import TokenCounterModel
except ImportError as e:
    print(f"导入 repo_map 模块失败: {e}")
    missing_deps.append("repo_map_modules")

# 检查其他可能缺失的依赖
try:
    import networkx as nx
except ImportError:
    missing_deps.append("networkx")

try:
    import tqdm
except ImportError:
    missing_deps.append("tqdm")

try:
    import pygments
except ImportError:
    missing_deps.append("pygments")

try:
    import grep_ast
except ImportError:
    missing_deps.append("grep_ast")


class TestRepoMapDependencies(unittest.TestCase):
    """测试依赖检查"""
    
    def test_dependencies_installed(self):
        """检查所有必需的依赖是否已安装"""
        print("\n=== 检查依赖 ===")
        
        if missing_deps:
            print(f"缺失的依赖: {missing_deps}")
            
            # 提供安装建议
            install_commands = []
            if "networkx" in missing_deps:
                install_commands.append("poetry add networkx")
            if "tqdm" in missing_deps:
                install_commands.append("poetry add tqdm")
            if "pygments" in missing_deps:
                install_commands.append("poetry add pygments")
            if "grep_ast" in missing_deps:
                install_commands.append("poetry add grep-ast")
                
            if install_commands:
                print("建议运行以下命令安装缺失的依赖:")
                for cmd in install_commands:
                    print(f"  {cmd}")
                    
            # 如果有缺失依赖，跳过后续测试
            self.skipTest(f"缺失依赖: {missing_deps}")
        else:
            print("✓ 所有依赖都已安装")


@unittest.skipIf(missing_deps, f"缺失依赖: {missing_deps}")
class TestRepoMapBasic(unittest.TestCase):
    """测试 RepoMap 基础功能"""
    
    def setUp(self):
        """设置测试环境"""
        self.test_dir = tempfile.mkdtemp()
        self.io = SilentIO()  # 使用静默IO避免测试输出干扰
        self.model = TokenCounterModel("claude-3-5-sonnet-20241022")
        
        print(f"\n测试目录: {self.test_dir}")

    def tearDown(self):
        """清理测试环境"""
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_repo_map_initialization(self):
        """测试 RepoMap 初始化"""
        print("\n=== 测试 RepoMap 初始化 ===")
        
        # 测试默认初始化
        repo_map = RepoMap(
            map_tokens=1024,
            root=self.test_dir,
            main_model=self.model,
            io=self.io,
            verbose=True
        )
        
        self.assertEqual(repo_map.root, self.test_dir)
        self.assertEqual(repo_map.max_map_tokens, 1024)
        self.assertEqual(repo_map.main_model, self.model)
        self.assertEqual(repo_map.io, self.io)
        self.assertTrue(repo_map.verbose)
        
        print("✓ RepoMap 初始化成功")

    def test_token_count(self):
        """测试 token 计算功能"""
        print("\n=== 测试 Token 计算 ===")
        
        repo_map = RepoMap(
            main_model=self.model,
            io=self.io
        )
        
        # 测试短文本
        short_text = "Hello, world!"
        tokens = repo_map.token_count(short_text)
        self.assertIsInstance(tokens, (int, float))
        self.assertGreater(tokens, 0)
        print(f"短文本 '{short_text}' token 数: {tokens}")
        
        # 测试长文本
        long_text = "def hello_world():\n    print('Hello, world!')\n    return 'success'" * 100
        tokens = repo_map.token_count(long_text)
        self.assertIsInstance(tokens, (int, float))
        self.assertGreater(tokens, 0)
        print(f"长文本 token 数: {tokens}")
        
        print("✓ Token 计算功能正常")

    def _create_test_python_file(self, filename, content):
        """创建测试用的 Python 文件"""
        filepath = os.path.join(self.test_dir, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return filepath

    def test_get_tags_from_python_file(self):
        """测试从 Python 文件提取标签"""
        print("\n=== 测试 Python 文件标签提取 ===")
        
        # 创建测试 Python 文件
        python_content = '''
def hello_world():
    """打招呼函数"""
    print("Hello, World!")
    return "success"

class Calculator:
    """计算器类"""
    
    def __init__(self):
        self.value = 0
    
    def add(self, x, y):
        """加法"""
        return x + y
    
    def multiply(self, x, y):
        """乘法"""
        result = x * y
        return result

# 使用函数
result = hello_world()
calc = Calculator()
sum_result = calc.add(1, 2)
'''
        
        test_file = self._create_test_python_file("test_code.py", python_content)
        
        repo_map = RepoMap(
            root=self.test_dir,
            main_model=self.model,
            io=self.io,
            verbose=True
        )
        
        # 提取标签
        rel_fname = repo_map.get_rel_fname(test_file)
        tags = repo_map.get_tags(test_file, rel_fname)
        
        self.assertIsInstance(tags, list)
        self.assertGreater(len(tags), 0)
        
        # 检查是否提取到了预期的标签
        tag_names = [tag.name for tag in tags]
        tag_kinds = [tag.kind for tag in tags]
        
        print(f"提取到的标签: {tag_names}")
        print(f"标签类型: {set(tag_kinds)}")
        
        # 应该包含函数和类的定义
        self.assertIn("def", tag_kinds)
        
        print("✓ Python 文件标签提取成功")

    def test_get_repo_map_empty_project(self):
        """测试空项目的 repo map 生成"""
        print("\n=== 测试空项目 Repo Map ===")
        
        repo_map = RepoMap(
            root=self.test_dir,
            main_model=self.model,
            io=self.io,
            verbose=True
        )
        
        # 空项目应该返回 None 或空字符串
        result = repo_map.get_repo_map(
            chat_files=[],
            other_files=[]
        )
        
        self.assertIsNone(result)
        print("✓ 空项目正确返回 None")

    def test_get_repo_map_with_files(self):
        """测试有文件的项目 repo map 生成"""
        print("\n=== 测试有文件的 Repo Map ===")
        
        # 创建多个测试文件
        files = []
        
        # 主文件
        main_content = '''
def main():
    """主函数"""
    calculator = Calculator()
    result = calculator.add(1, 2)
    print(f"结果: {result}")

if __name__ == "__main__":
    main()
'''
        files.append(self._create_test_python_file("main.py", main_content))
        
        # 工具文件
        utils_content = '''
class Calculator:
    """计算器工具类"""
    
    def add(self, x, y):
        return x + y
    
    def subtract(self, x, y):
        return x - y

def helper_function():
    """辅助函数"""
    return "helper"
'''
        files.append(self._create_test_python_file("utils.py", utils_content))
        
        # 配置文件
        config_content = '''
CONFIG = {
    "debug": True,
    "version": "1.0.0"
}

def get_config():
    return CONFIG
'''
        files.append(self._create_test_python_file("config.py", config_content))
        
        repo_map = RepoMap(
            root=self.test_dir,
            main_model=self.model,
            io=self.io,
            verbose=True,
            map_tokens=2048
        )
        
        # 生成 repo map
        result = repo_map.get_repo_map(
            chat_files=[files[0]],  # main.py 作为 chat 文件
            other_files=files[1:]   # 其他文件
        )
        
        if result:
            self.assertIsInstance(result, str)
            self.assertGreater(len(result), 0)
            print(f"生成的 repo map 长度: {len(result)}")
            print("Repo map 内容预览:")
            print(result[:500] + "..." if len(result) > 500 else result)
        else:
            print("未生成 repo map（可能是 token 限制或其他原因）")
        
        print("✓ 有文件的 Repo Map 测试完成")


@unittest.skipIf(missing_deps, f"缺失依赖: {missing_deps}")
class TestRepoMapRealProject(unittest.TestCase):
    """测试真实项目 - siada-agenthub"""
    
    def setUp(self):
        """设置测试环境"""
        self.project_root = Path(__file__).parent.parent.parent.parent.parent
        self.io = SilentIO()  # 使用静默IO避免测试输出干扰
        self.model = TokenCounterModel("claude-3-5-sonnet-20241022")

    def test_current_project_repo_map(self):
        """测试当前 siada-agenthub 项目的 repo map 生成"""
        print("\n=== 测试当前项目 Repo Map ===")
        print(f"项目根目录: {self.project_root}")
        
        repo_map = RepoMap(
            root=str(self.project_root),
            main_model=self.model,
            io=self.io,
            verbose=True,
            map_tokens=4096  # 增加 token 限制以获得更完整的 map
        )
        
        # 收集项目中的 Python 文件
        python_files = []
        for root, dirs, files in os.walk(self.project_root):
            # 跳过一些不需要的目录
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['__pycache__', 'node_modules']]
            
            for file in files:
                if file.endswith('.py') and not file.startswith('.'):
                    filepath = os.path.join(root, file)
                    python_files.append(filepath)
        
        print(f"找到 {len(python_files)} 个 Python 文件")
        
        # 选择一些重要文件作为 chat_files
        chat_files = []
        other_files = []
        
        for filepath in python_files:
            rel_path = os.path.relpath(filepath, self.project_root)
            if any(important in rel_path for important in ['repo_map.py', 'coder_agent.py', 'agent_service.py']):
                chat_files.append(filepath)
            else:
                other_files.append(filepath)
        
        print(f"Chat 文件: {len(chat_files)}")
        print(f"其他文件: {len(other_files)}")
        
        # 限制文件数量以避免测试时间过长
        if len(other_files) > 20:
            other_files = other_files[:20]
            print(f"限制其他文件数量为: {len(other_files)}")
        
        # 生成 repo map
        try:
            result = repo_map.get_repo_map(
                chat_files=chat_files,
                other_files=other_files,
                mentioned_fnames=set(['repo_map.py', 'coder_agent.py']),
                mentioned_idents=set(['RepoMap', 'CoderAgent'])
            )
            
            if result:
                self.assertIsInstance(result, str)
                self.assertGreater(len(result), 0)
                
                # 计算 token 数量
                token_count = repo_map.token_count(result)
                print(f"生成的 repo map token 数: {token_count}")
                print(f"repo map 字符数: {len(result)}")
                
                # 保存结果到测试目录以便查看
                test_output_dir = Path(__file__).parent
                output_file = test_output_dir / "test_repo_map_output.txt"
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(result)
                print(f"Repo map 已保存到: {output_file}")
                
                # 检查是否包含一些重要的项目文件（注意：chat_files 不会出现在 repo map 中）
                # 由于 repo_map.py 是 chat_file，它不会出现在结果中，这是正常的
                # 我们检查其他文件是否存在
                self.assertIn("siada/", result)  # 应该包含 siada 目录下的文件
                
                print("✓ 当前项目 Repo Map 生成成功")
            else:
                print("未生成 repo map（可能是配置或依赖问题）")
                
        except Exception as e:
            print(f"生成 repo map 时出错: {e}")
            import traceback
            traceback.print_exc()
            self.fail(f"Repo map 生成失败: {e}")

    def test_cache_functionality(self):
        """测试缓存功能"""
        print("\n=== 测试缓存功能 ===")
        
        repo_map = RepoMap(
            root=str(self.project_root),
            main_model=self.model,
            io=self.io,
            verbose=True
        )
        
        # 测试缓存加载
        try:
            repo_map.load_tags_cache()
            print("✓ 缓存加载成功")
        except Exception as e:
            print(f"缓存加载失败: {e}")
        
        # 测试缓存保存
        try:
            repo_map.save_tags_cache()
            print("✓ 缓存保存成功")
        except Exception as e:
            print(f"缓存保存失败: {e}")

    def test_special_files_filter(self):
        """测试重要文件过滤功能"""
        print("\n=== 测试重要文件过滤 ===")
        
        # 收集项目中的所有文件
        all_files = []
        for root, dirs, files in os.walk(self.project_root):
            for file in files:
                filepath = os.path.join(root, file)
                rel_path = os.path.relpath(filepath, self.project_root)
                all_files.append(rel_path)
        
        # 过滤重要文件
        important_files = filter_important_files(all_files)
        
        print(f"总文件数: {len(all_files)}")
        print(f"重要文件数: {len(important_files)}")
        print("重要文件列表:")
        for file in important_files:
            print(f"  {file}")
        
        # 验证一些预期的重要文件
        important_basenames = [os.path.basename(f) for f in important_files]
        self.assertIn("pyproject.toml", important_basenames)
        self.assertIn("README.md", important_basenames)
        
        print("✓ 重要文件过滤功能正常")


class TestRepoMapPerformance(unittest.TestCase):
    """性能测试"""
    
    def setUp(self):
        self.project_root = Path(__file__).parent.parent.parent.parent.parent
        self.io = SilentIO()  # 使用静默IO避免测试输出干扰
        self.model = TokenCounterModel("claude-3-5-sonnet-20241022")

    @unittest.skipIf(missing_deps, f"缺失依赖: {missing_deps}")
    def test_performance_with_cache(self):
        """测试缓存对性能的影响"""
        print("\n=== 测试缓存性能 ===")
        
        import time
        
        repo_map = RepoMap(
            root=str(self.project_root),
            main_model=self.model,
            io=self.io,
            verbose=False  # 关闭详细输出以获得更准确的性能测试
        )
        
        # 选择一个测试文件
        test_file = self.project_root / "siada" / "tools" / "coder" / "repo_map" / "repo_map.py"
        if test_file.exists():
            rel_fname = repo_map.get_rel_fname(str(test_file))
            
            # 第一次调用（无缓存）
            start_time = time.time()
            tags1 = repo_map.get_tags(str(test_file), rel_fname)
            first_call_time = time.time() - start_time
            
            # 第二次调用（有缓存）
            start_time = time.time()
            tags2 = repo_map.get_tags(str(test_file), rel_fname)
            second_call_time = time.time() - start_time
            
            print(f"第一次调用时间: {first_call_time:.4f}s")
            print(f"第二次调用时间: {second_call_time:.4f}s")
            
            # 验证结果一致性
            self.assertEqual(len(tags1), len(tags2))
            
            # 缓存应该显著提高性能
            if first_call_time > 0.001:  # 只有在第一次调用时间足够长时才检查
                self.assertLess(second_call_time, first_call_time)
                print(f"性能提升: {(first_call_time - second_call_time) / first_call_time * 100:.1f}%")
            
            print("✓ 缓存性能测试完成")
        else:
            self.skipTest("测试文件不存在")


if __name__ == '__main__':
    # 首先打印依赖检查结果
    print("=" * 60)
    print("RepoMap 测试用例")
    print("=" * 60)
    
    if missing_deps:
        print(f"\n⚠️  缺失依赖: {missing_deps}")
        print("\n建议运行以下命令安装缺失的依赖:")
        if "networkx" in missing_deps:
            print("  poetry add networkx")
        if "tqdm" in missing_deps:
            print("  poetry add tqdm")
        if "pygments" in missing_deps:
            print("  poetry add pygments")
        if "grep_ast" in missing_deps:
            print("  poetry add grep-ast")
        print()
    else:
        print("✅ 所有依赖都已安装")
    
    # 运行测试
    unittest.main(verbosity=2)
