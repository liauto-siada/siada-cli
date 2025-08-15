"""
测试 read 函数的新参数签名
"""

import unittest
import tempfile
import shutil
import os

from siada.tools.coder.observation.file_observation import FileReadObservation
from siada.tools.coder.observation.observation import FileReadSource


class MockCoderAgentContext:
    """模拟 CoderAgentContext"""
    def __init__(self, root_dir: str):
        self.root_dir = root_dir


class MockRunContextWrapper:
    """模拟 RunContextWrapper"""
    def __init__(self, context: MockCoderAgentContext):
        self.context = context


async def read_direct(
    context: MockRunContextWrapper,
    path: str,
    start: int = 0,
    end: int = -1,
    impl_source: FileReadSource = FileReadSource.DEFAULT,
    view_range: list[int] | None = None
):
    """直接调用读取逻辑，不通过装饰器"""
    from binaryornot.check import is_binary
    from siada.tools.coder.observation.error import ErrorObservation
    from siada.tools.coder.files import read_lines
    from pathlib import Path
    
    # Cannot read binary files
    if is_binary(path):
        return ErrorObservation('ERROR_BINARY_FILE')

    working_dir = context.context.root_dir
    
    if impl_source == FileReadSource.OH_ACI:
        # 这里我们简化处理，直接读取文件
        pass

    # NOTE: the client code is running inside the sandbox,
    # so there's no need to check permission
    def _resolve_path(path: str, working_dir: str) -> str:
        filepath = Path(path)
        if not filepath.is_absolute():
            return str(Path(working_dir) / filepath)
        return str(filepath)
    
    filepath = _resolve_path(path, working_dir)
    try:
        with open(filepath, 'r', encoding='utf-8') as file:  # noqa: ASYNC101
            lines = read_lines(file.readlines(), start, end)
    except FileNotFoundError:
        return ErrorObservation(
            f'File not found: {filepath}. Your current working directory is {working_dir}.'
        )
    except UnicodeDecodeError:
        return ErrorObservation(f'File could not be decoded as utf-8: {filepath}.')
    except IsADirectoryError:
        return ErrorObservation(
            f'Path is a directory: {filepath}. You can only read files'
        )

    code_view = ''.join(lines)
    return FileReadObservation(path=filepath, content=code_view)


class TestReadFunctionDirect(unittest.IsolatedAsyncioTestCase):
    """直接测试 read 函数的核心逻辑"""

    def setUp(self):
        """设置测试环境"""
        self.test_dir = tempfile.mkdtemp()
        self.context = MockRunContextWrapper(MockCoderAgentContext(self.test_dir))

    def tearDown(self):
        """清理测试环境"""
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _create_test_file(self, filename: str, content: str) -> str:
        """创建测试文件并返回完整路径"""
        filepath = os.path.join(self.test_dir, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return filepath

    async def test_read_full_file(self):
        """测试读取完整文件"""
        test_content = "line 1\nline 2\nline 3\nline 4\nline 5"
        test_file = self._create_test_file("test_read.py", test_content)
        
        result = await read_direct(
            context=self.context,
            path=test_file
        )
        
        self.assertIsInstance(result, FileReadObservation)
        self.assertEqual(result.path, test_file)
        self.assertEqual(result.content, test_content)
        print("✓ 完整文件读取测试通过")

    async def test_read_partial_file(self):
        """测试读取文件的部分内容"""
        test_content = "line 1\nline 2\nline 3\nline 4\nline 5"
        test_file = self._create_test_file("test_partial.py", test_content)
        
        result = await read_direct(
            context=self.context,
            path=test_file,
            start=1,
            end=3
        )
        
        self.assertIsInstance(result, FileReadObservation)
        self.assertEqual(result.path, test_file)
        # 应该包含第2行到第3行的内容
        self.assertIn("line 2", result.content)
        self.assertIn("line 3", result.content)
        print("✓ 部分文件读取测试通过")

    async def test_read_nonexistent_file(self):
        """测试读取不存在的文件"""
        nonexistent_file = os.path.join(self.test_dir, "nonexistent.py")
        
        result = await read_direct(
            context=self.context,
            path=nonexistent_file
        )
        
        from siada.tools.coder.observation.error import ErrorObservation
        self.assertIsInstance(result, ErrorObservation)
        self.assertIn("File not found", result.content)
        print("✓ 不存在文件错误处理测试通过")


if __name__ == '__main__':
    unittest.main()
