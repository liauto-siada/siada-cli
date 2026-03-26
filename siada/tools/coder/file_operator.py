import base64
import mimetypes
from io import BytesIO
from pathlib import Path

from agents import RunContextWrapper, function_tool, ToolOutputImage
from openhands_aci.editor import OHEditor, ToolResult, ToolError
from openhands_aci.utils.diff import get_diff

from siada.foundation.logging import logger

from binaryornot.check import is_binary

from siada.tools.coder.observation.file_observation import FileEditObservation
from siada.tools.coder.observation.observation import FunctionCallResult, FileEditSource
from siada.tools.coder.observation.error import ErrorObservation
from siada.tools.coder.tool_docs import EDIT_DOCS
from siada.foundation.code_agent_context import CodeAgentContext
from siada.tools.resolve_cwd import resolve_cwd


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}

# this means the model supports image reading with the read_tool
SUPPRORT_IMAGE_MODELS = {"claude", "gemini"}

@function_tool(
    name_override="edit_file", description_override=EDIT_DOCS
)
async def edit(
    context: RunContextWrapper[CodeAgentContext], 
    command: str,
    path: str,
    file_text: str | None = None,
    old_str: str | None = None,
    new_str: str | None = None,
    insert_line: int | None = None,
    view_range: list[int] | None = None,
) -> FunctionCallResult | ToolOutputImage:
    return _edit_file(
        context=context,
        command=command,
        path=path,
        file_text=file_text,
        old_str=old_str,
        new_str=new_str,
        insert_line=insert_line,
        view_range=view_range,
    )


def _edit_file(
    context: RunContextWrapper[CodeAgentContext], 
    command: str,
    path: str,
    file_text: str | None = None,
    old_str: str | None = None,
    new_str: str | None = None,
    insert_line: int | None = None,
    view_range: list[int] | None = None,
    cwd: str | None = None,
) -> FunctionCallResult | ToolOutputImage:
    # Resolve effective workspace root (IM mode allows model-specified cwd)
    effective_root = resolve_cwd(context, cwd)
    # Validate file access with SiadaIgnore controller
    siadaignore_controller = getattr(context.context, 'siadaignore_controller', None)
    if siadaignore_controller and not siadaignore_controller.validate_access(path):
        return FileEditObservation(
            error=True,
            content=(
                f'ERROR: Access to "{path}" is denied by .siadaignore. '
                f'This file is protected from modification.'
            ),
            path=path,
            old_content=None,
            new_content=None,
            impl_source=FileEditSource.OH_ACI,
            diff='',
            command=command,
        )

    # Handle image file reading with compression if needed
    _path = Path(path)
    if _path.suffix.lower() in IMAGE_EXTENSIONS:
        model_name = context.context.model_run_config.model_name.lower()
        if not any(m in model_name for m in SUPPRORT_IMAGE_MODELS):
            return ErrorObservation(
                content=f"Current model '{model_name}' does not support image processing. "
                f"Stop the Task Immediately. Always Only Tell user to 'Sorry. I can't do that operation' ",
                display_content="✗ Current model does not support image processing. Select the claude model to enable this feature.\n",
            )
        # Process image and return base64-encoded result (error handling is internal)
        return read_image(path, effective_root)

    file_editor = OHEditor(workspace_root=effective_root)
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
        siadaignore_controller=siadaignore_controller,
    )

    return FileEditObservation(
        error=True if result_str.startswith('ERROR:') else False,
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
        command=command,
    )


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
    siadaignore_controller = None,
) -> tuple[str, tuple[str | None, str | None]]:
    """Execute file editor command and handle exceptions.

    Args:
        editor: The OHEditor instance
        command: Editor command to execute
        path: File path
        file_text: Optional file text content
        view_range: Optional view range tuple (start, end)
        old_str: Optional string to replace
        new_str: Optional replacement string
        insert_line: Optional line number for insertion (can be int or str)
        enable_linting: Whether to enable linting
        siadaignore_controller: Optional SiadaIgnoreController instance for filtering view results

    Returns:
        tuple: A tuple containing the output string and a tuple of old and new file content
    """
    result: ToolResult | None = None

    if file_text is None:
        file_text = ''

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
        logger.warning(f'No output from file_editor for {path}')
        return '', (None, None)

    # Filter view command results with siadaignore if controller is available
    output = result.output
    if command == 'view' and siadaignore_controller is not None:
        output = siadaignore_controller.filter_view_output(output)

    return output, (result.old_content, result.new_content)


def read_image(
    path: str, working_dir: str, max_dimension: int = 1024, jpeg_quality: int = 85
) -> ToolOutputImage | ErrorObservation:
    """
    Process an image file and return it as a base64-encoded data URI.

    Resolves the image path, opens it, resizes proportionally if needed (maintaining aspect ratio),
    converts to JPEG with compression, and encodes to base64 format suitable for AI vision models.
    All errors are handled internally.

    Args:
        path: Image file path (can be relative or absolute)
        working_dir: Working directory for resolving relative paths
        max_dimension: Maximum dimension (width or height) in pixels (default: 1024)
        jpeg_quality: JPEG compression quality 1-100 (default: 85, good balance of quality and size)

    Returns:
        dict: A dictionary containing image type and base64-encoded URL in the format:
              {'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,...'}}
        ErrorObservation: If any error occurs during processing
    """
    from PIL import Image

    try:
        # Resolve the full path relative to the working directory
        full_path = _resolve_path(path, working_dir)

        # Open the image
        img = Image.open(full_path)

        # Use thumbnail to resize image proportionally (max dimension 1024)
        # 1024px is optimal for AI vision models - clear enough without being too large
        # thumbnail modifies image in-place and maintains aspect ratio
        img.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)

        # Convert RGBA/P mode to RGB (JPEG doesn't support transparency)
        if img.mode in ('RGBA', 'P', 'LA'):
            # Create white background and paste image on it
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
            img = background
        elif img.mode != 'RGB':
            img = img.convert('RGB')

        # Convert image to base64 with JPEG compression
        buffer = BytesIO()
        # Always save as JPEG for smaller file size (quality 85 is good balance)
        img.save(buffer, format='JPEG', quality=jpeg_quality, optimize=True)
        buffer.seek(0)

        # Encode to base64
        encoded_image = base64.b64encode(buffer.getvalue()).decode("utf-8")
        encoded_image = f"data:image/jpeg;base64,{encoded_image}"

        return ToolOutputImage(image_url=encoded_image, detail="auto")

    except FileNotFoundError:
        return ErrorObservation(
            f"Image file not found: {path}. Your current working directory is {working_dir}."
        )
    except Exception as e:
        return ErrorObservation(f"Error processing image file {path}: {str(e)}")


def _resolve_path(path: str, working_dir: str) -> str:
    """
    Resolve a file path to an absolute path.
    
    If the provided path is relative, it will be resolved relative to the working directory.
    If the path is already absolute, it will be returned as-is.
    
    Args:
        path: The file path to resolve (can be relative or absolute)
        working_dir: The working directory to use as base for relative paths
        
    Returns:
        str: The absolute file path
    """
    filepath = Path(path)
    if not filepath.is_absolute():
        # Convert relative path to absolute by joining with working directory
        return str(Path(working_dir) / filepath)
    # Return absolute path as-is
    return str(filepath)
