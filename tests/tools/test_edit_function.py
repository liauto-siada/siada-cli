"""
直接测试 edit 函数的核心逻辑
"""

import unittest
import tempfile
import shutil
import os

from siada.tools.coder.observation.file_observation import FileEditObservation
from siada.tools.coder.observation.observation import FileEditSource
from openhands_aci.editor import OHEditor
from openhands_aci.utils.diff import get_diff


class MockCoderAgentContext:
    """模拟 CoderAgentContext"""
    def __init__(self, root_dir: str):
        self.root_dir = root_dir


class MockRunContextWrapper:
    """模拟 RunContextWrapper"""
    def __init__(self, context: MockCoderAgentContext):
        self.context = context


def _execute_file_editor(
    editor: OHEditor,
    command: str,
    path: str,
    file_text: str | None = None,
    view_range: list[int] | None = None,
    old_str: str | None = None,
    new_str: str | None = None,
    insert_line: int | str | None = None,
    enable_linting: bool = False,
) -> tuple[str, tuple[str | None, str | None]]:
    """Execute file editor command and handle exceptions."""
    from openhands_aci.editor import ToolResult, ToolError
    
    result = None

    # Convert insert_line from string to int if needed
    if insert_line is not None and isinstance(insert_line, str):
        try:
            insert_line = int(insert_line)
        except ValueError:
            return (
                f"ERROR:\nInvalid insert_line value: '{insert_line}'. Expected an integer.",
                (None, None),
            )

    try:
        result = editor(
            command=command,
            path=path,
            file_text=file_text,
            view_range=view_range,
            old_str=old_str,
            new_str=new_str,
            insert_line=insert_line,
            enable_linting=enable_linting,
        )
    except ToolError as e:
        result = ToolResult(error=e.message)
    except TypeError as e:
        # Handle unexpected arguments or type errors
        return f'ERROR:\n{str(e)}', (None, None)

    if result.error:
        return f'ERROR:\n{result.error}', (None, None)

    if not result.output:
        return '', (None, None)

    return result.output, (result.old_content, result.new_content)


async def edit_direct(
    context: MockRunContextWrapper, 
    command: str,
    path: str,
    file_text: str | None = None,
    old_str: str | None = None,
    new_str: str | None = None,
    insert_line: int | None = None,
    view_range: list[int] | None = None
):
    """直接调用编辑逻辑，不通过装饰器"""
    file_editor = OHEditor(workspace_root=context.context.root_dir)
    result_str, (old_content, new_content) = _execute_file_editor(
        file_editor,
        command=command,
        path=path,
        file_text=file_text,
        old_str=old_str,
        new_str=new_str,
        insert_line=insert_line,
        view_range=view_range,
        enable_linting=False,
    )

    return FileEditObservation(
        content=result_str,
        path=path,
        old_content=old_str,
        new_content=new_str,
        impl_source=FileEditSource.OH_ACI,
        diff=get_diff(
            old_contents=old_content or '',
            new_contents=new_content or '',
            filepath=path,
        ),
    )


class TestEditFunctionDirect(unittest.IsolatedAsyncioTestCase):
    """直接测试 edit 函数的核心逻辑"""

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

    def _read_file_content(self, filepath: str) -> str:
        """读取文件内容"""
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()

    async def test_edit_create_file(self):
        """测试创建新文件"""
        new_file_path = os.path.join(self.test_dir, "test_create.py")
        file_content = "def test(): pass"
        
        result = await edit_direct(
            context=self.context,
            command="create",
            path=new_file_path,
            file_text=file_content
        )
        
        self.assertIsInstance(result, FileEditObservation)
        self.assertEqual(result.path, new_file_path)
        self.assertEqual(result.impl_source, FileEditSource.OH_ACI)
        self.assertTrue(os.path.exists(new_file_path))
        
        actual_content = self._read_file_content(new_file_path)
        self.assertEqual(actual_content, file_content)
        print("✓ 文件创建测试通过")

    async def test_edit_str_replace(self):
        """测试字符串替换"""
        original_content = "def test(): pass"
        test_file = self._create_test_file("test_replace.py", original_content)
        
        result = await edit_direct(
            context=self.context,
            command="str_replace",
            path=test_file,
            old_str="pass",
            new_str="return True"
        )
        
        self.assertIsInstance(result, FileEditObservation)
        self.assertEqual(result.path, test_file)
        
        new_content = self._read_file_content(test_file)
        self.assertEqual(new_content, "def test(): return True")
        print("✓ 字符串替换测试通过")

    async def test_edit_insert(self):
        """测试插入内容"""
        original_content = "line 1\nline 2"
        test_file = self._create_test_file("test_insert.py", original_content)
        
        result = await edit_direct(
            context=self.context,
            command="insert",
            path=test_file,
            insert_line=1,
            new_str="inserted line"
        )
        
        self.assertIsInstance(result, FileEditObservation)
        
        new_content = self._read_file_content(test_file)
        self.assertIn("inserted line", new_content)
        print("✓ 插入内容测试通过")


if __name__ == '__main__':
    unittest.main()
