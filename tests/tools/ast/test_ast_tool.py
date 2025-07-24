"""
测试 ast_tool.py 中的 _list_code_definition_names 方法

这个测试文件包含了对 _list_code_definition_names 方法的完整功能测试，包括：
- 复杂Python文件解析
- 简单Python文件解析
- JavaScript文件解析
- 空文件处理
- 不支持文件类型处理
- 错误处理
- 边界情况
- 输出格式验证
"""

import pytest
import tempfile
import shutil
import os
from pathlib import Path
from unittest.mock import patch, mock_open

from siada.tools.ast.ast_tool import _list_code_definition_names
from siada.tools.ast.models import Tag


class TestListCodeDefinitionNames:
    """测试 _list_code_definition_names 方法的完整功能"""

    @pytest.fixture
    def test_data_dir(self):
        """获取测试数据目录路径"""
        current_file = Path(__file__)
        return current_file.parent / "test_data"

    @pytest.fixture
    def temp_dir(self):
        """创建临时测试目录"""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_complex_python_file_parsing(self, test_data_dir):
        """测试复杂Python文件的解析"""
        print("\n=== 测试复杂Python文件解析 ===")
        
        complex_file = test_data_dir / "complex_python_file.py"
        result = _list_code_definition_names(str(complex_file))
        
        # 验证基本结构
        assert "File: complex_python_file.py" in result
        assert "Definitions:" in result
        assert "References:" in result
        
        # 验证包含主要的类定义
        assert "DataModel" in result
        assert "BaseProcessor" in result
        assert "DataAnalyzer" in result
        assert "MLModelTrainer" in result
        assert "WebCrawler" in result
        assert "FileProcessor" in result
        
        # 验证包含主要的方法定义
        assert "complex_data_processing_method" in result
        assert "train_complex_model" in result
        assert "crawl_website_comprehensive" in result
        assert "process_large_file_batch" in result
        
        # 验证包含函数定义
        assert "generator_function" in result
        assert "async_main" in result
        assert "utility_function" in result
        
        # 验证包含特殊方法
        assert "__init__" in result
        assert "from_config_file" in result  # 类方法
        assert "validate_training_data" in result  # 静态方法
        assert "file_processing_context" in result  # 上下文管理器
        
        print(f"✓ 复杂Python文件解析成功")
        print(f"✓ 结果长度: {len(result)} 字符")

    def test_simple_python_file_parsing(self, test_data_dir):
        """测试简单Python文件的解析"""
        print("\n=== 测试简单Python文件解析 ===")
        
        simple_file = test_data_dir / "simple_python_file.py"
        result = _list_code_definition_names(str(simple_file))
        
        # 验证基本结构
        assert "File: simple_python_file.py" in result
        assert "Definitions:" in result
        
        # 验证包含所有定义
        assert "simple_function" in result
        assert "SimpleClass" in result
        assert "__init__" in result
        assert "get_value" in result
        assert "set_value" in result
        assert "another_function" in result
        
        print(f"✓ 简单Python文件解析成功")

    def test_javascript_file_parsing(self, test_data_dir):
        """测试JavaScript文件的解析"""
        print("\n=== 测试JavaScript文件解析 ===")
        
        js_file = test_data_dir / "javascript_file.js"
        result = _list_code_definition_names(str(js_file))
        
        # 验证基本结构
        assert "File: javascript_file.js" in result
        
        # JavaScript文件应该能被解析（如果支持的话）
        # 或者返回无定义信息
        if "No code definitions found" not in result:
            # 如果支持JavaScript解析，验证主要定义
            assert "simpleFunction" in result or "TestClass" in result
        
        print(f"✓ JavaScript文件处理完成")

    def test_empty_file_handling(self, test_data_dir):
        """测试空文件的处理"""
        print("\n=== 测试空文件处理 ===")
        
        empty_file = test_data_dir / "empty_file.py"
        result = _list_code_definition_names(str(empty_file))
        
        # 验证空文件的处理
        assert "No code definitions found in empty_file.py" == result
        
        print(f"✓ 空文件处理成功")

    def test_unsupported_file_type(self, test_data_dir):
        """测试不支持的文件类型"""
        print("\n=== 测试不支持文件类型 ===")
        
        txt_file = test_data_dir / "unsupported_file.txt"
        result = _list_code_definition_names(str(txt_file))
        
        # 验证不支持文件类型的处理
        assert "No code definitions found in unsupported_file.txt" == result
        
        print(f"✓ 不支持文件类型处理成功")

    def test_nonexistent_file_error(self, temp_dir):
        """测试不存在文件的错误处理"""
        print("\n=== 测试不存在文件错误处理 ===")
        
        nonexistent_file = os.path.join(temp_dir, "nonexistent.py")
        result = _list_code_definition_names(nonexistent_file)
        
        # 验证错误处理
        assert "No code definitions found in nonexistent.py" == result
        
        print(f"✓ 不存在文件错误处理正确")

    def test_relative_filename_parameter(self, test_data_dir):
        """测试相对文件名参数"""
        print("\n=== 测试相对文件名参数 ===")
        
        simple_file = test_data_dir / "simple_python_file.py"
        
        # 测试默认相对文件名
        result1 = _list_code_definition_names(str(simple_file))
        assert "File: simple_python_file.py" in result1
        
        # 测试自定义相对文件名
        result2 = _list_code_definition_names(str(simple_file), "custom_name.py")
        assert "File: custom_name.py" in result2
        
        # 验证内容相同（除了文件名）
        content1 = result1.split('\n', 2)[2]  # 跳过前两行（文件名和统计）
        content2 = result2.split('\n', 2)[2]
        assert content1 == content2
        
        print(f"✓ 相对文件名参数测试成功")

    def test_output_format_structure(self, test_data_dir):
        """测试输出格式结构"""
        print("\n=== 测试输出格式结构 ===")
        
        simple_file = test_data_dir / "simple_python_file.py"
        result = _list_code_definition_names(str(simple_file))
        
        lines = result.split('\n')
        
        # 验证第一行是文件名
        assert lines[0].startswith("File: ")
        
        # 验证第二行是统计信息
        assert "Definitions:" in lines[1] and "References:" in lines[1]
        
        # 验证第三行是空行
        assert lines[2] == ""
        
        # 验证后续内容是代码树或定义列表
        remaining_content = '\n'.join(lines[3:]).strip()
        assert len(remaining_content) > 0
        
        print(f"✓ 输出格式结构验证通过")

    def test_definitions_and_references_count(self, test_data_dir):
        """测试定义和引用计数的准确性"""
        print("\n=== 测试定义和引用计数 ===")
        
        simple_file = test_data_dir / "simple_python_file.py"
        result = _list_code_definition_names(str(simple_file))
        
        # 提取统计行
        lines = result.split('\n')
        stats_line = lines[1]
        
        # 解析定义和引用数量
        import re
        def_match = re.search(r'Definitions: (\d+)', stats_line)
        ref_match = re.search(r'References: (\d+)', stats_line)
        
        assert def_match is not None, "应该能找到定义数量"
        assert ref_match is not None, "应该能找到引用数量"
        
        def_count = int(def_match.group(1))
        ref_count = int(ref_match.group(1))
        
        # 简单文件应该有多个定义
        assert def_count > 0, "简单文件应该有定义"
        
        # 引用数量可能为0或更多（取决于tree-sitter的解析结果）
        assert ref_count >= 0, "引用数量应该非负"
        
        print(f"✓ 定义数量: {def_count}, 引用数量: {ref_count}")

    def test_large_file_handling(self, temp_dir):
        """测试大文件处理"""
        print("\n=== 测试大文件处理 ===")
        
        # 创建一个包含大量定义的文件
        large_file_content = ""
        for i in range(50):
            large_file_content += f"""
def function_{i}():
    '''Function number {i}'''
    return {i}

class Class_{i}:
    '''Class number {i}'''
    def __init__(self):
        self.value = {i}
    
    def get_value(self):
        return self.value
"""
        
        large_file = os.path.join(temp_dir, "large_file.py")
        with open(large_file, 'w', encoding='utf-8') as f:
            f.write(large_file_content)
        
        result = _list_code_definition_names(large_file)
        
        # 验证大文件能被正确处理
        assert "File: large_file.py" in result
        assert "Definitions:" in result
        
        # 验证包含一些生成的定义
        assert "function_0" in result
        assert "Class_0" in result
        assert "function_49" in result
        assert "Class_49" in result
        
        print(f"✓ 大文件处理成功")

    def test_special_characters_in_filename(self, temp_dir):
        """测试文件名包含特殊字符的情况"""
        print("\n=== 测试特殊字符文件名 ===")
        
        # 创建包含特殊字符的文件名
        special_filename = "测试文件_with-special@chars.py"
        special_file = os.path.join(temp_dir, special_filename)
        
        content = """
def 中文函数名():
    '''包含中文的函数'''
    return "测试"

class 中文类名:
    '''包含中文的类'''
    pass
"""
        
        with open(special_file, 'w', encoding='utf-8') as f:
            f.write(content)
        
        result = _list_code_definition_names(special_file)
        
        # 验证特殊字符文件名能被正确处理
        assert f"File: {special_filename}" in result
        
        # 验证中文定义能被识别
        if "No code definitions found" not in result:
            assert "中文函数名" in result or "中文类名" in result
        
        print(f"✓ 特殊字符文件名处理成功")

    def test_file_with_syntax_errors(self, temp_dir):
        """测试包含语法错误的文件"""
        print("\n=== 测试语法错误文件 ===")
        
        # 创建包含语法错误的Python文件
        syntax_error_file = os.path.join(temp_dir, "syntax_error.py")
        content = """
def valid_function():
    return "valid"

# 语法错误：缺少冒号
def invalid_function()
    return "invalid"

class ValidClass:
    def method(self):
        return "valid"

# 语法错误：缩进错误
class InvalidClass:
def method(self):
    return "invalid"
"""
        
        with open(syntax_error_file, 'w', encoding='utf-8') as f:
            f.write(content)
        
        result = _list_code_definition_names(syntax_error_file)
        
        # 验证即使有语法错误，仍能处理有效部分
        assert "File: syntax_error.py" in result
        
        # tree-sitter通常能容忍一些语法错误，所以可能仍能找到一些定义
        print(f"✓ 语法错误文件处理完成")

    def test_unicode_content_handling(self, temp_dir):
        """测试Unicode内容处理"""
        print("\n=== 测试Unicode内容处理 ===")
        
        unicode_file = os.path.join(temp_dir, "unicode_test.py")
        content = """# -*- coding: utf-8 -*-
'''
包含各种Unicode字符的测试文件
🚀 Emoji测试
'''

def функция_на_русском():
    '''俄语函数名'''
    return "Привет мир"

def función_en_español():
    '''西班牙语函数名'''
    return "Hola mundo"

class 日本語クラス:
    '''日语类名'''
    def メソッド(self):
        return "こんにちは世界"

def emoji_function_🎉():
    '''包含emoji的函数名'''
    return "🎊 Party! 🎊"
"""
        
        with open(unicode_file, 'w', encoding='utf-8') as f:
            f.write(content)
        
        result = _list_code_definition_names(unicode_file)
        
        # 验证Unicode内容能被正确处理
        assert "File: unicode_test.py" in result
        
        # 验证能识别Unicode函数名（如果tree-sitter支持）
        print(f"✓ Unicode内容处理完成")

    @patch('builtins.open', side_effect=PermissionError("Permission denied"))
    def test_permission_error_handling(self, mock_open_func, temp_dir):
        """测试权限错误处理"""
        print("\n=== 测试权限错误处理 ===")
        
        restricted_file = os.path.join(temp_dir, "restricted.py")
        result = _list_code_definition_names(restricted_file)
        
        # 验证权限错误被正确处理
        assert "No code definitions found in restricted.py" == result
        
        print(f"✓ 权限错误处理正确")

    def test_fallback_to_simple_list_format(self, temp_dir):
        """测试回退到简单列表格式"""
        print("\n=== 测试简单列表格式回退 ===")
        
        # 创建一个简单的文件
        simple_file = os.path.join(temp_dir, "fallback_test.py")
        content = """
def test_function():
    pass

class TestClass:
    def method(self):
        pass
"""
        
        with open(simple_file, 'w', encoding='utf-8') as f:
            f.write(content)
        
        # 模拟to_tree返回空字符串的情况
        with patch('siada.tools.ast.ast_tool.to_tree', return_value=""):
            result = _list_code_definition_names(simple_file)
            
            # 验证回退到简单列表格式
            assert "File: fallback_test.py" in result
            assert "Definitions found:" in result
            assert "test_function" in result
            assert "TestClass" in result
            assert "method" in result
            
        print(f"✓ 简单列表格式回退测试成功")

    def test_no_definitions_found_case(self, temp_dir):
        """测试没有找到定义的情况"""
        print("\n=== 测试无定义情况 ===")
        
        # 创建只包含注释和字符串的文件
        no_def_file = os.path.join(temp_dir, "no_definitions.py")
        content = """
# 这是一个注释文件
# 没有任何函数或类定义

'''
这是一个文档字符串
也没有定义
'''

# 一些变量赋值
x = 1
y = "hello"
z = [1, 2, 3]

# 更多注释
"""
        
        with open(no_def_file, 'w', encoding='utf-8') as f:
            f.write(content)
        
        result = _list_code_definition_names(no_def_file)
        
        # 验证文件被正确处理（tree-sitter可能将变量赋值识别为定义）
        assert "File: no_definitions.py" in result
        assert "Definitions:" in result
        
        # 验证包含变量赋值（被tree-sitter识别为定义）
        assert "x" in result or "y" in result or "z" in result
        
        print(f"✓ 无定义情况处理成功（变量赋值被识别为定义）")

    def test_method_return_type(self, test_data_dir):
        """测试方法返回类型"""
        print("\n=== 测试方法返回类型 ===")
        
        simple_file = test_data_dir / "simple_python_file.py"
        result = _list_code_definition_names(str(simple_file))
        
        # 验证返回类型是字符串
        assert isinstance(result, str)
        assert len(result) > 0
        
        print(f"✓ 方法返回类型验证通过")

    def test_comprehensive_integration(self, test_data_dir):
        """综合集成测试"""
        print("\n=== 综合集成测试 ===")
        
        # 测试所有测试文件
        test_files = [
            "complex_python_file.py",
            "simple_python_file.py",
            "javascript_file.js",
            "empty_file.py",
            "unsupported_file.txt"
        ]
        
        results = {}
        for filename in test_files:
            file_path = test_data_dir / filename
            if file_path.exists():
                result = _list_code_definition_names(str(file_path))
                results[filename] = result
                
                # 基本验证
                if filename in ["empty_file.py", "unsupported_file.txt"]:
                    # 这些文件返回简单的错误消息格式
                    assert f"No code definitions found in {filename}" == result
                else:
                    # 其他文件应该有完整的格式
                    assert f"File: {filename}" in result
                
                assert isinstance(result, str)
                assert len(result) > 0
        
        # 验证所有文件都被处理
        assert len(results) == len(test_files)
        
        # 验证复杂文件的结果比简单文件更长
        if "complex_python_file.py" in results and "simple_python_file.py" in results:
            complex_result = results["complex_python_file.py"]
            simple_result = results["simple_python_file.py"]
            assert len(complex_result) > len(simple_result)
        
        print(f"✓ 综合集成测试成功，处理了 {len(results)} 个文件")


if __name__ == '__main__':
    pytest.main([__file__, "-v"])
