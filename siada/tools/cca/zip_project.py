import os
import zipfile
from pathlib import Path
from agents import function_tool, RunContextWrapper

from siada.foundation.code_agent_context import CodeAgentContext
from siada.tools.coder.observation.observation import FunctionCallResult


ZIP_PROJECT_DOCS = """
项目打包工具

将指定的项目目录打包成 ZIP 文件，并重命名为指定的卡片名称。

## 功能说明
此工具用于将整个项目目录打包成 ZIP 文件，会自动忽略以下文件和目录：
- package-lock.json 文件
- 根目录下的 dist 文件夹
- 根目录下的 node_modules 文件夹
- 所有 .zip 文件

## 参数说明
Args:
    project_root: (required) 项目根目录的绝对路径
    card_name: (required) 输出的 ZIP 文件名（不包含 .zip 扩展名），必须为卡片的名字，从 /cards 目录中找到对应文件名。
"""

@function_tool(
    name_override="zip_project", description_override=ZIP_PROJECT_DOCS
)
async def zip_project(
    context: RunContextWrapper[CodeAgentContext],
    project_root: str,
    card_name: str
) -> FunctionCallResult:
    try:
        project_path = Path(project_root)
        if not project_path.exists() or not project_path.is_dir():
            return f"错误：项目目录不存在或不是目录: {project_root}"

        zip_path = project_path / f"{card_name}.zip"

        # 需要忽略的文件和目录
        ignore_items = {'package-lock.json', 'dist', 'node_modules', 'packages', '.git', 'screenshot'}

        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(project_path):
                rel_root = os.path.relpath(root, project_path)

                # 在每个目录都检查是否需要过滤掉某些子目录
                dirs[:] = [d for d in dirs if d not in ignore_items]

                # 添加文件到 ZIP
                for file in files:
                    # 检查是否需要忽略
                    if file in ignore_items or file.endswith('.zip'):
                        continue

                    file_path = os.path.join(root, file)
                    arcname = os.path.join(rel_root, file)
                    zipf.write(file_path, arcname)

        return FunctionCallResult(f"项目打包成功: {zip_path}")
        
    except Exception as e:
        return FunctionCallResult(f"打包失败: {str(e)}")
