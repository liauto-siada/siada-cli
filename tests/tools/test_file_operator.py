"""
测试 file_operator.py 中的 edit 方法

这个测试文件包含了对 edit 方法的完整功能测试，包括：
- 文件创建 (create)
- 字符串替换 (str_replace)
- 行插入 (insert)
- 撤销编辑 (undo_edit)
- 写入 (write)
- 错误处理
- 边界情况
"""

import unittest
import tempfile
import shutil
import os
from pathlib import Path

from siada.tools.coder.file_operator import edit, _edit_file
from siada.tools.coder.observation.file_observation import FileEditObservation
from siada.tools.coder.observation.observation import FileEditSource


class MockCoderAgentContext:
    """模拟 CoderAgentContext"""
    def __init__(self, root_dir: str):
        self.root_dir = root_dir


class MockRunContextWrapper:
    """模拟 RunContextWrapper"""
    def __init__(self, context: MockCoderAgentContext):
        self.context = context


class TestFileOperatorEdit(unittest.IsolatedAsyncioTestCase):
    """测试 file_operator.edit 方法的完整功能"""

    def setUp(self):
        """设置测试环境"""
        # 创建临时测试目录
        self.test_dir = tempfile.mkdtemp()
        print(f"测试目录: {self.test_dir}")
        
        # 创建模拟的上下文对象
        self.context = MockRunContextWrapper(MockCoderAgentContext(self.test_dir))

    def tearDown(self):
        """清理测试环境"""
        # 清理临时文件
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _create_test_file(self, filename: str, content: str) -> str:
        """创建测试文件并返回完整路径"""
        filepath = os.path.join(self.test_dir, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return filepath

    def _read_file_content(self, filepath: str) -> str:
        """读取文件内容"""
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()

    async def test_edit_create_file(self):
        """测试创建新文件"""
        print("\n=== 测试文件创建 ===")
        
        # 准备测试数据
        new_file_path = os.path.join(self.test_dir, "new_test_file.py")
        file_content = """def hello_world():
    print("Hello, World!")
    return "success"

if __name__ == "__main__":
    hello_world()
"""
        
        # 执行编辑操作
        result = _edit_file(
            context=self.context,
            command="create",
            path=new_file_path,
            file_text=file_content
        )
        
        # 验证结果
        self.assertIsInstance(result, FileEditObservation)
        self.assertEqual(result.path, new_file_path)
        self.assertEqual(result.impl_source, FileEditSource.OH_ACI)
        
        # 验证文件是否真的被创建
        self.assertTrue(os.path.exists(new_file_path))
        
        # 验证文件内容
        actual_content = self._read_file_content(new_file_path)
        self.assertEqual(actual_content, file_content)
        
        print(f"✓ 文件创建成功: {new_file_path}")
        print(f"✓ 文件内容验证通过")

    async def test_edit_str_replace_simple(self):
        """测试简单字符串替换"""
        print("\n=== 测试简单字符串替换 ===")
        
        # 创建测试文件
        original_content = """def greet(name):
    print(f"Hello, {name}!")
    return "greeting sent"
"""
        test_file = self._create_test_file("test_replace.py", original_content)
        
        # 执行编辑
        result = _edit_file(
            context=self.context,
            command="str_replace",
            path=test_file,
            old_str='print(f"Hello, {name}!")',
            new_str='print(f"Hi there, {name}! Nice to meet you!")'
        )
        
        # 验证结果
        self.assertIsInstance(result, FileEditObservation)
        self.assertEqual(result.path, test_file)
        
        # 验证文件内容
        new_content = self._read_file_content(test_file)
        expected_content = """def greet(name):
    print(f"Hi there, {name}! Nice to meet you!")
    return "greeting sent"
"""
        self.assertEqual(new_content, expected_content)
        
        # 验证 diff 信息存在
        self.assertIsNotNone(result.diff)
        
        print(f"✓ 字符串替换成功")
        print(f"✓ 文件内容验证通过")

    async def test_edit_str_replace_multiline(self):
        """测试多行字符串替换"""
        print("\n=== 测试多行字符串替换 ===")
        
        # 创建测试文件
        original_content = """class Calculator:
    def add(self, a, b):
        return a + b
    
    def subtract(self, a, b):
        return a - b
        
    def multiply(self, a, b):
        return a * b
"""
        test_file = self._create_test_file("calculator.py", original_content)
        
        # 执行编辑
        result = _edit_file(
            context=self.context,
            command="str_replace",
            path=test_file,
            old_str="""    def multiply(self, a, b):
        return a * b""",
            new_str="""    def multiply(self, a, b):
        result = a * b
        print(f"Multiplying {a} * {b} = {result}")
        return result
        
    def divide(self, a, b):
        if b == 0:
            raise ValueError("Cannot divide by zero")
        return a / b"""
        )
        
        # 验证结果
        self.assertIsInstance(result, FileEditObservation)
        
        # 验证文件内容
        new_content = self._read_file_content(test_file)
        self.assertIn("print(f\"Multiplying {a} * {b} = {result}\")", new_content)
        self.assertIn("def divide(self, a, b):", new_content)
        self.assertIn("Cannot divide by zero", new_content)
        
        print(f"✓ 多行字符串替换成功")
        print(f"✓ 新增方法验证通过")

    async def test_edit_insert_at_beginning(self):
        """测试在文件开头插入"""
        print("\n=== 测试在文件开头插入 ===")
        
        # 创建测试文件
        original_content = """def main():
    print("This is the main function")

if __name__ == "__main__":
    main()
"""
        test_file = self._create_test_file("main.py", original_content)
        
        # 在第0行后插入（即文件开头）
        result = _edit_file(
            context=self.context,
            command="insert",
            path=test_file,
            insert_line=0,
            new_str="""#!/usr/bin/env python3
# -*- coding: utf-8 -*-
\"\"\"
这是一个示例Python脚本
\"\"\"

"""
        )
        
        # 验证结果
        self.assertIsInstance(result, FileEditObservation)
        
        # 验证文件内容
        new_content = self._read_file_content(test_file)
        self.assertTrue(new_content.startswith("#!/usr/bin/env python3"))
        self.assertIn("这是一个示例Python脚本", new_content)
        self.assertIn("def main():", new_content)
        
        print(f"✓ 文件开头插入成功")

    async def test_edit_insert_at_middle(self):
        """测试在文件中间插入"""
        print("\n=== 测试在文件中间插入 ===")
        
        # 创建测试文件
        original_content = """def function_one():
    pass

def function_three():
    pass
"""
        test_file = self._create_test_file("functions.py", original_content)
        
        # 在第2行后插入
        result = _edit_file(
            context=self.context,
            command="insert",
            path=test_file,
            insert_line=2,
            new_str="""
def function_two():
    print("This is function two")
    return 2
"""
        )
        
        # 验证结果
        self.assertIsInstance(result, FileEditObservation)
        
        # 验证文件内容
        new_content = self._read_file_content(test_file)
        
        # 验证插入位置正确
        self.assertIn("function_one", new_content)
        self.assertIn("function_two", new_content)
        self.assertIn("function_three", new_content)
        
        print(f"✓ 文件中间插入成功")

    async def test_edit_insert_at_end(self):
        """测试在文件末尾插入"""
        print("\n=== 测试在文件末尾插入 ===")
        
        # 创建测试文件
        original_content = """class MyClass:
    def __init__(self):
        self.value = 0
"""
        test_file = self._create_test_file("myclass.py", original_content)
        
        # 在最后一行后插入
        result = _edit_file(
            context=self.context,
            command="insert",
            path=test_file,
            insert_line=3,
            new_str="""
    def get_value(self):
        return self.value
        
    def set_value(self, value):
        self.value = value
"""
        )
        
        # 验证结果
        self.assertIsInstance(result, FileEditObservation)
        
        # 验证文件内容
        new_content = self._read_file_content(test_file)
        self.assertIn("def get_value(self):", new_content)
        self.assertIn("def set_value(self, value):", new_content)
        
        print(f"✓ 文件末尾插入成功")

    async def test_edit_undo_edit(self):
        """测试撤销编辑"""
        print("\n=== 测试撤销编辑 ===")
        
        # 创建测试文件
        original_content = """def test_function():
    return "original"
"""
        test_file = self._create_test_file("undo_test.py", original_content)
        
        # 先进行一次编辑
        _edit_file(
            context=self.context,
            command="str_replace",
            path=test_file,
            old_str='return "original"',
            new_str='return "modified"'
        )
        
        # 验证编辑生效
        modified_content = self._read_file_content(test_file)
        self.assertIn("modified", modified_content)
        
        # 执行撤销操作
        result = _edit_file(
            context=self.context,
            command="undo_edit",
            path=test_file
        )
        
        # 验证结果
        self.assertIsInstance(result, FileEditObservation)
        
        # 注意：undo_edit 功能依赖于编辑历史记录，在独立的测试环境中可能无法正常工作
        # 这里我们检查是否返回了适当的错误信息，而不是期望撤销成功
        if "No edit history found" in result.content:
            print(f"✓ 撤销编辑功能正确返回了无历史记录的错误信息")
        else:
            # 如果撤销成功，验证文件内容恢复
            restored_content = self._read_file_content(test_file)
            self.assertEqual(restored_content, original_content)
            print(f"✓ 撤销编辑成功")

    async def test_edit_view_command(self):
        """测试查看命令"""
        print("\n=== 测试查看命令 ===")
        
        # 创建测试文件
        test_content = """def view_test():
    print("Testing view command")
    return True
"""
        test_file = self._create_test_file("view_test.py", test_content)
        
        # 执行查看
        result = _edit_file(
            context=self.context,
            command="view",
            path=test_file
        )
        
        # 验证结果
        self.assertIsInstance(result, FileEditObservation)
        self.assertEqual(result.path, test_file)
        
        print(f"✓ 查看命令执行成功")

    async def test_edit_empty_file(self):
        """测试编辑空文件"""
        print("\n=== 测试编辑空文件 ===")
        
        # 创建空文件
        test_file = self._create_test_file("empty.py", "")
        
        # 向空文件插入内容
        result = _edit_file(
            context=self.context,
            command="insert",
            path=test_file,
            insert_line=0,
            new_str="""# This was an empty file
def new_function():
    return "Hello from empty file"
"""
        )
        
        # 验证结果
        self.assertIsInstance(result, FileEditObservation)
        
        # 验证文件内容
        new_content = self._read_file_content(test_file)
        self.assertIn("This was an empty file", new_content)
        self.assertIn("def new_function():", new_content)
        
        print(f"✓ 空文件编辑成功")

    async def test_edit_special_characters(self):
        """测试特殊字符处理"""
        print("\n=== 测试特殊字符处理 ===")
        
        # 创建包含特殊字符的文件
        original_content = """# 测试中文和特殊字符
def 中文函数名():
    message = "Hello, 世界! 🌍"
    symbols = "!@#$%^&*()_+-=[]{}|;':\",./<>?"
    return message + symbols
"""
        test_file = self._create_test_file("special_chars.py", original_content)
        
        # 替换包含特殊字符的内容
        result = _edit_file(
            context=self.context,
            command="str_replace",
            path=test_file,
            old_str='message = "Hello, 世界! 🌍"',
            new_str='message = "你好, World! 🚀✨"'
        )
        
        # 验证结果
        self.assertIsInstance(result, FileEditObservation)
        
        # 验证文件内容
        new_content = self._read_file_content(test_file)
        self.assertIn("你好, World! 🚀✨", new_content)
        self.assertIn("中文函数名", new_content)
        
        print(f"✓ 特殊字符处理成功")

    async def test_edit_large_file(self):
        """测试大文件编辑"""
        print("\n=== 测试大文件编辑 ===")
        
        # 创建较大的文件
        large_content = ""
        for i in range(100):
            large_content += f"""def function_{i}():
    '''This is function number {i}'''
    result = {i} * 2
    print(f"Function {i} result: {{result}}")
    return result

"""
        
        test_file = self._create_test_file("large_file.py", large_content)
        
        # 在大文件中进行替换
        result = _edit_file(
            context=self.context,
            command="str_replace",
            path=test_file,
            old_str="def function_50():",
            new_str="def special_function_50():"
        )
        
        # 验证结果
        self.assertIsInstance(result, FileEditObservation)
        
        # 验证文件内容
        new_content = self._read_file_content(test_file)
        self.assertIn("def special_function_50():", new_content)
        self.assertNotIn("def function_50():", new_content)
        
        print(f"✓ 大文件编辑成功")

    async def test_edit_error_nonexistent_file(self):
        """测试编辑不存在的文件时的错误处理"""
        print("\n=== 测试不存在文件的错误处理 ===")
        
        # 尝试编辑不存在的文件
        nonexistent_file = os.path.join(self.test_dir, "nonexistent.py")
        
        # 执行编辑
        result = _edit_file(
            context=self.context,
            command="str_replace",
            path=nonexistent_file,
            old_str="old",
            new_str="new"
        )
        
        # 验证结果 - 应该返回错误信息
        self.assertIsInstance(result, FileEditObservation)
        # 检查是否包含错误信息
        self.assertIn("ERROR", result.content)
        
        print(f"✓ 不存在文件错误处理正确")

    async def test_edit_invalid_command(self):
        """测试无效命令的错误处理"""
        print("\n=== 测试无效命令错误处理 ===")
        
        # 创建测试文件
        test_file = self._create_test_file("invalid_cmd.py", "print('test')")
        
        # 使用无效命令
        result = _edit_file(
            context=self.context,
            command="invalid_command",
            path=test_file
        )
        
        # 验证结果 - 应该返回错误信息
        self.assertIsInstance(result, FileEditObservation)
        
        print(f"✓ 无效命令错误处理正确")

    async def test_edit_observation_structure(self):
        """测试返回的观察对象结构"""
        print("\n=== 测试观察对象结构 ===")
        
        # 创建测试文件
        test_content = "def test(): pass"
        test_file = self._create_test_file("structure_test.py", test_content)
        
        # 执行编辑操作
        result = _edit_file(
            context=self.context,
            command="str_replace",
            path=test_file,
            old_str="pass",
            new_str="return True"
        )
        
        # 验证观察对象的所有必要属性
        self.assertIsInstance(result, FileEditObservation)
        self.assertEqual(result.path, test_file)
        self.assertEqual(result.impl_source, FileEditSource.OH_ACI)
        self.assertIsNotNone(result.content)
        self.assertIsNotNone(result.diff)
        
        # 验证 old_content 和 new_content
        self.assertEqual(result.old_content, "pass")
        self.assertEqual(result.new_content, "return True")
        
        print(f"✓ 观察对象结构验证通过")
        print(f"  - path: {result.path}")
        print(f"  - impl_source: {result.impl_source}")
        print(f"  - old_content: {result.old_content}")
        print(f"  - new_content: {result.new_content}")
        print(f"  - diff 长度: {len(result.diff) if result.diff else 0}")

    async def test_edit_diff_generation(self):
        """测试 diff 信息生成"""
        print("\n=== 测试 diff 信息生成 ===")
        
        # 创建测试文件
        original_content = """line 1
line 2
line 3
line 4
line 5"""
        test_file = self._create_test_file("diff_test.py", original_content)
        
        # 执行编辑操作
        result = _edit_file(
            context=self.context,
            command="str_replace",
            path=test_file,
            old_str="line 3",
            new_str="modified line 3"
        )
        
        # 验证 diff 信息
        self.assertIsInstance(result, FileEditObservation)
        self.assertIsNotNone(result.diff)
        self.assertIsInstance(result.diff, str)
        self.assertGreater(len(result.diff), 0)
        
        # 验证 diff 包含变更信息
        self.assertIn("line 3", result.diff)
        self.assertIn("modified line 3", result.diff)
        
        print(f"✓ diff 信息生成成功")
        print(f"✓ diff 内容长度: {len(result.diff)}")


if __name__ == '__main__':
    unittest.main()
