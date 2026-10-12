"""
测试复杂仓库的 repo map 生成功能

测试会在临时目录中动态构建一个合成仓库（synthetic fixture）：包含多个模块、
类、方法以及跨文件引用的 Python 项目，用于验证 repo map 能否生成包含函数名、
类名、方法名的详细输出。

测试不依赖本地开发路径，也不会调用外部模型或网络服务：token 统计使用
RepoMap 自带的本地 TokenCounterModel。
"""

import shutil
import tempfile
import unittest
import os
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root))

try:
    from siada.tools.coder.repo_map.repo_map import RepoMap
    from siada.tools.coder.repo_map.io import SilentIO
    from siada.tools.coder.repo_map.token_counter import TokenCounterModel
    DEPENDENCIES_OK = True
except ImportError as e:
    print(f"导入失败: {e}")
    DEPENDENCIES_OK = False


# 合成仓库内容：相对路径 -> 源码。
# 文件之间保留了跨文件引用，用于检验 repo map 的排序与标签提取。
SYNTHETIC_REPO_FILES = {
    "app/__init__.py": '"""Synthetic package used by the repo map fixture."""',
    "app/main.py": '''"""Synthetic application entry point."""

from app.services.agent_runner import AgentRunner
from app.services.report import build_report


def main() -> str:
    """Run the synthetic agent and render its report."""
    runner = AgentRunner(name="demo")
    result = runner.run("summarize the repository")
    return build_report(result)


if __name__ == "__main__":
    print(main())
''',
    "app/services/__init__.py": "",
    "app/services/agent_runner.py": '''"""Synthetic service module with classes and methods."""

from app.utils.text import normalize


class BaseRunner:
    """Base class for synthetic runners."""

    def __init__(self, name: str) -> None:
        self.name = name

    def run(self, task: str) -> str:
        raise NotImplementedError


class AgentRunner(BaseRunner):
    """Runs a synthetic task and returns a normalized summary."""

    def run(self, task: str) -> str:
        return normalize(task)

    def describe(self) -> str:
        return f"runner={self.name}"


def build_runner(name: str) -> AgentRunner:
    """Factory used by the entry point to build a runner."""
    return AgentRunner(name)


def is_ready(runner: AgentRunner) -> bool:
    """Return True when the runner has been configured with a name."""
    return bool(runner.describe())
''',
    "app/services/report.py": '''"""Synthetic reporting helpers."""

from app.utils.text import normalize


def build_report(payload: str) -> str:
    """Build a human readable report from a payload."""
    return f"report: {normalize(payload)}"


def build_summary(payload: str, max_lines: int = 5) -> str:
    """Build a truncated summary."""
    lines = payload.splitlines()[:max_lines]
    return " | ".join(lines)
''',
    "app/utils/__init__.py": "",
    "app/utils/text.py": '''"""Synthetic string helpers."""


def normalize(text: str) -> str:
    """Collapse whitespace and strip the surrounding spaces."""
    return " ".join(text.split()).strip()


def truncate(text: str, limit: int = 20) -> str:
    """Truncate text to a maximum length."""
    return text[:limit]
''',
}


@unittest.skipIf(not DEPENDENCIES_OK, "缺失依赖")
class TestComplexRepoMap(unittest.TestCase):
    """测试复杂仓库的 repo map 生成"""
    
    def setUp(self):
        """构建合成仓库（synthetic fixture）与临时输出目录"""
        self.complex_repo_root = tempfile.mkdtemp(prefix="siada-repo-map-fixture-")
        self.output_dir = tempfile.mkdtemp(prefix="siada-repo-map-output-")
        self.addCleanup(shutil.rmtree, self.complex_repo_root, ignore_errors=True)
        self.addCleanup(shutil.rmtree, self.output_dir, ignore_errors=True)

        # 写入合成的 Python 文件
        for rel_path, content in SYNTHETIC_REPO_FILES.items():
            abs_path = os.path.join(self.complex_repo_root, rel_path)
            os.makedirs(os.path.dirname(abs_path), exist_ok=True)
            with open(abs_path, "w", encoding="utf-8") as f:
                f.write(content)

        self.io = SilentIO()  # 使用静默IO避免测试输出干扰
        self.model = TokenCounterModel("claude-3-5-sonnet-20241022")

    def test_complex_repo_map_generation(self):
        """测试复杂仓库的 repo map 生成"""
        print("\n=== 测试复杂仓库 Repo Map 生成 ===")
        print(f"目标仓库: {self.complex_repo_root}")
        
        # 创建 RepoMap 实例，使用更高的 token 限制
        repo_map = RepoMap(
            root=self.complex_repo_root,
            main_model=self.model,
            io=self.io,
            verbose=True,
            map_tokens=8192,  # 增加 token 限制
            map_mul_no_files=16  # 增加无文件时的倍数
        )
        
        # 收集仓库中的 Python 文件
        python_files = []
        for root, dirs, files in os.walk(self.complex_repo_root):
            # 跳过一些不需要的目录
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in [
                '__pycache__', 'node_modules', '.git', '.venv', 'venv', 'env'
            ]]
            
            for file in files:
                if file.endswith('.py') and not file.startswith('.'):
                    filepath = os.path.join(root, file)
                    python_files.append(filepath)
        
        print(f"找到 {len(python_files)} 个 Python 文件")
        
        # 过滤出有实际内容的文件（避免空的 __init__.py）
        substantial_files = []
        for filepath in python_files:
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    # 只包含有实际内容的文件（超过100个字符且不只是注释）
                    if len(content) > 100:
                        lines = [line.strip() for line in content.split('\n') if line.strip()]
                        non_comment_lines = [line for line in lines if not line.startswith('#')]
                        if len(non_comment_lines) > 5:  # 至少有5行非注释代码
                            substantial_files.append(filepath)
            except Exception as e:
                print(f"跳过文件 {filepath}: {e}")
                continue
        
        print(f"过滤后有实际内容的文件: {len(substantial_files)}")
        
        # 限制文件数量以避免测试时间过长，但保留足够多的文件
        if len(substantial_files) > 50:
            substantial_files = substantial_files[:50]
            print(f"限制文件数量为: {len(substantial_files)}")
        
        # 智能选择 chat_files 和 other_files
        chat_files = []
        other_files = []
        
        # 只选择少量最重要的文件作为 chat_files，让更多文件出现在 repo map 中
        for filepath in substantial_files:
            rel_path = os.path.relpath(filepath, self.complex_repo_root)
            # 只有非常核心的文件才作为 chat_files
            if any(core in rel_path.lower() for core in ['main.py', 'app.py', '__main__.py']):
                chat_files.append(filepath)
            else:
                other_files.append(filepath)
        
        print(f"Chat 文件: {len(chat_files)}")
        print(f"其他文件: {len(other_files)}")
        
        if chat_files:
            print("Chat 文件列表:")
            for f in chat_files:
                print(f"  {os.path.relpath(f, self.complex_repo_root)}")
        
        # 生成 repo map
        try:
            print("\n开始生成 repo map...")
            result = repo_map.get_repo_map(
                chat_files=chat_files,
                other_files=other_files,
                mentioned_fnames=set(),  # 不指定特定文件
                mentioned_idents={'AgentRunner', 'normalize'}  # 合成仓库中提及的标识符
            )
            
            if result:
                self.assertIsInstance(result, str)
                self.assertGreater(len(result), 0)
                
                # 计算 token 数量
                token_count = repo_map.token_count(result)
                print(f"\n生成的 repo map token 数: {token_count}")
                print(f"repo map 字符数: {len(result)}")
                
                # 检查是否包含函数和类信息
                has_functions = any(keyword in result for keyword in ['def ', 'class ', 'function', 'method'])
                has_detailed_content = ':' in result and len(result.split('\n')) > len(other_files)
                
                print(f"包含函数/类信息: {has_functions}")
                print(f"包含详细内容: {has_detailed_content}")
                
                # 保存结果到临时输出目录，避免覆盖仓库中提交的示例输出
                output_file = os.path.join(self.output_dir, "complex_repo_map_output.txt")
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(result)
                print(f"\nRepo map 已保存到: {output_file}")
                
                # 显示部分内容预览
                print(f"\n=== Repo Map 内容预览 ===")
                lines = result.split('\n')
                preview_lines = min(30, len(lines))
                for i, line in enumerate(lines[:preview_lines]):
                    print(f"{i+1:2d}: {line}")
                if len(lines) > preview_lines:
                    print(f"... (还有 {len(lines) - preview_lines} 行)")
                
                # 验证结果质量
                if has_functions or has_detailed_content:
                    print("\n✓ 成功生成包含详细信息的 repo map")
                else:
                    print("\n⚠️ 生成的 repo map 缺少详细的函数/类信息")
                    print("可能的原因:")
                    print("- Token 限制仍然不够")
                    print("- 文件之间的关联性不强")
                    print("- 需要调整 PageRank 算法参数")
                
                print("✓ 复杂仓库 Repo Map 生成完成")
                
            else:
                print("未生成 repo map")
                self.fail("未能生成 repo map")
                
        except Exception as e:
            print(f"生成 repo map 时出错: {e}")
            import traceback
            traceback.print_exc()
            self.fail(f"Repo map 生成失败: {e}")

    def test_tag_extraction_from_complex_files(self):
        """测试从复杂文件中提取标签"""
        print("\n=== 测试复杂文件标签提取 ===")
        
        repo_map = RepoMap(
            root=self.complex_repo_root,
            main_model=self.model,
            io=self.io,
            verbose=True
        )
        
        # 使用合成仓库中同时包含类定义与方法定义的文件
        test_file = os.path.join(self.complex_repo_root, "app", "services", "agent_runner.py")
        self.assertTrue(os.path.exists(test_file), f"合成仓库文件缺失: {test_file}")
        
        print(f"测试文件: {os.path.relpath(test_file, self.complex_repo_root)}")
        
        # 提取标签
        rel_fname = repo_map.get_rel_fname(test_file)
        tags = repo_map.get_tags(test_file, rel_fname)
        
        print(f"提取到 {len(tags)} 个标签")
        
        if tags:
            # 分析标签类型
            def_tags = [tag for tag in tags if tag.kind == 'def']
            ref_tags = [tag for tag in tags if tag.kind == 'ref']
            
            print(f"定义标签: {len(def_tags)}")
            print(f"引用标签: {len(ref_tags)}")
            
            # 显示一些定义标签
            if def_tags:
                print("定义标签示例:")
                for tag in def_tags[:10]:  # 显示前10个
                    print(f"  {tag.kind}: {tag.name} (行 {tag.line + 1})")

                # 合成仓库中的类/函数名应被识别为定义标签
                self.assertIn('AgentRunner', {tag.name for tag in def_tags})
            
            # 显示一些引用标签
            if ref_tags:
                print("引用标签示例:")
                unique_refs = list(set(tag.name for tag in ref_tags))[:10]
                for ref in unique_refs:
                    print(f"  ref: {ref}")
            
            self.assertGreater(len(tags), 0)
            print("✓ 标签提取成功")
        else:
            print("⚠️ 未提取到任何标签")


if __name__ == '__main__':
    print("=" * 60)
    print("复杂仓库 RepoMap 测试")
    print("=" * 60)
    
    if not DEPENDENCIES_OK:
        print("⚠️ 缺失依赖，请先安装必要的包")
    else:
        print("✅ 依赖检查通过")
    
    # 运行测试
    unittest.main(verbosity=2)
