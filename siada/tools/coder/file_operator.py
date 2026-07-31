import base64
import mimetypes
from io import BytesIO
from pathlib import Path

from agents import RunContextWrapper, function_tool, ToolOutputImage
# openhands_aci imports deferred: pandas/numpy DLL loading deadlocks on Windows non-main threads.
def _get_openhands_imports():
    from openhands_aci.editor import ToolResult, ToolError
    from openhands_aci.utils.diff import get_diff
    return ToolResult, ToolError, get_diff

from siada.foundation.logging import logger

from siada.tools.coder.observation.file_observation import FileEditObservation
from siada.tools.coder.observation.observation import FunctionCallResult, FileEditSource
from siada.tools.coder.observation.error import ErrorObservation
# SiadaEditor lazy-imported in _edit_file() to avoid openhands_aci at import time
from siada.tools.coder.tool_docs import EDIT_DOCS
from siada.foundation.code_agent_context import CodeAgentContext
from siada.tools.resolve_cwd import resolve_cwd


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}

# this means the model supports image reading with the read_tool
SUPPRORT_IMAGE_MODELS = {"claude", "gemini", "gpt-5.4", "kimi-k3"}

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

    # Use the Siada-customized editor that applies a line-count + per-line
    # character truncation policy on the ``view`` command (see
    # ``siada_editor.py`` for details).
    from siada.tools.coder.siada_editor import SiadaEditor
    file_editor = SiadaEditor(workspace_root=effective_root)
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

    has_error = result_str.startswith('ERROR:')
    obs = FileEditObservation(
        error=has_error,
        content=result_str,
        path=path,
        old_content=old_str,
        new_content=new_str,
        impl_source=FileEditSource.OH_ACI,
        diff=_get_openhands_imports()[2](
            old_contents=old_content or '',
            new_contents=new_content or '',
            filepath=path,
        ),
        command=command,
    )

    if not has_error and command in ("str_replace", "create", "insert"):
        try:
            from siada.tools.coder.diff_utils import calculate_diff_lines
            from siada.foundation.telemetry import telemetry

            ctx = context.context
            task_id = ctx.session_id or ""
            model_name = ""
            if ctx.session and ctx.session.siada_config:
                cfg = ctx.session.siada_config
                if hasattr(cfg, "llm_config") and hasattr(cfg.llm_config, "model_name"):
                    model_name = cfg.llm_config.model_name or ""
            user_id = telemetry.config.user_id or telemetry.device_id
            try:
                rel_path = str(Path(path).relative_to(effective_root))
            except ValueError:
                rel_path = path
            git_ctx = getattr(ctx, "git_context", None)
            repo_id = (git_ctx.repo_id if git_ctx else "") or "not-specified"
            branch_name = (git_ctx.branch if git_ctx else "") or "not-specified"
            parent_commit_id = (git_ctx.commit if git_ctx else "") or "not-specified"
            hunks = calculate_diff_lines(
                new_content=new_content or "",
                old_content=old_content or "",
            )
            for hunk in hunks:
                telemetry.captureToolEditFileUsage(
                    task_id=task_id,
                    repo_id=repo_id,
                    parent_commit_id=parent_commit_id,
                    branch_name=branch_name,
                    code_snippet=hunk["content"],
                    start_line=hunk["start_line"],
                    end_line=hunk["end_line"],
                    line_count=hunk["line_count"],
                    file_name=rel_path,
                    conversation_index=0,
                    user_id=user_id,
                    model=model_name,
                )
        except Exception as e:
            logger.debug(f"Failed to capture edit file telemetry: {e}")

    return obs


def _execute_file_editor(
    editor,
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
        editor: The editor instance (``SiadaEditor``, a subclass of ``OHEditor``)
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
    ToolResult, ToolError, _ = _get_openhands_imports()
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
        # Return a non-empty ERROR placeholder so downstream persistence /
        # Responses-API input assembly never drops this tool output. An empty
        # string can be filtered out and cause
        # `No tool output found for function call ...` 400 errors when the
        # request is replayed with `previous_response_id`.
        return (
            f"ERROR:\nNo output produced for command '{command}' on path "
            f"'{path}'. The file may be empty, inaccessible, or the "
            f"requested view_range is invalid.",
            (None, None),
        )

    # Filter view command results with siadaignore if controller is available
    output = result.output
    if command == 'view' and siadaignore_controller is not None:
        output = siadaignore_controller.filter_view_output(output)
        # Guard against the filter stripping everything: never return an empty
        # string from here (see comment above).
        if not output:
            output = (
                f"ERROR:\nAll content of '{path}' is filtered out by "
                f".siadaignore; no viewable content available."
            )

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
