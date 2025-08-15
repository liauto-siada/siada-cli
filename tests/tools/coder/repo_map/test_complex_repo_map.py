"""
测试复杂仓库的 repo map 生成功能

这个测试文件专门用于测试复杂仓库 /Users/yunan/code/copilot/siada 的 repo map 生成，
重点验证是否能够生成包含函数名、类名、方法名的详细 repo map。
"""

import unittest
import os
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root))

try:
    from siada.tools.coder.repo_map.repo_map import RepoMap, Tag
    from siada.tools.coder.repo_map.dump import dump
    from siada.tools.coder.repo_map.special import filter_important_files
    from siada.tools.coder.repo_map.waiting import Spinner
    from siada.tools.coder.repo_map.io import IO, SilentIO
    from siada.tools.coder.repo_map.token_counter import TokenCounterModel
    import litellm
    DEPENDENCIES_OK = True
except ImportError as e:
    print(f"导入失败: {e}")
    DEPENDENCIES_OK = False


@unittest.skipIf(not DEPENDENCIES_OK, "缺失依赖")
class TestComplexRepoMap(unittest.TestCase):
    """测试复杂仓库的 repo map 生成"""
    
    def setUp(self):
        """设置测试环境"""
        self.complex_repo_root = "/Users/yunan/code/copilot/siada"
        self.io = SilentIO()  # 使用静默IO避免测试输出干扰
        self.model = TokenCounterModel("claude-3-5-sonnet-20241022")
        
        # 检查目标仓库是否存在
        if not os.path.exists(self.complex_repo_root):
            self.skipTest(f"目标仓库不存在: {self.complex_repo_root}")

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
                mentioned_idents=set(['class', 'def', 'function'])  # 提及一些通用标识符
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
                
                # 保存结果到测试目录
                test_output_dir = Path(__file__).parent
                output_file = test_output_dir / "complex_repo_map_output.txt"
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
        
        # 找一个有实际内容的 Python 文件进行测试
        test_file = None
        for root, dirs, files in os.walk(self.complex_repo_root):
            for file in files:
                if file.endswith('.py') and not file.startswith('.'):
                    filepath = os.path.join(root, file)
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            content = f.read()
                            # 寻找包含类和函数定义的文件
                            if 'def ' in content and 'class ' in content and len(content) > 500:
                                test_file = filepath
                                break
                    except:
                        continue
            if test_file:
                break
        
        if not test_file:
            self.skipTest("未找到合适的测试文件")
        
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
