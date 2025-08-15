import base64
import mimetypes
from pathlib import Path

from agents import RunContextWrapper, function_tool
from openhands_aci.editor import OHEditor, ToolResult, ToolError
from openhands_aci.utils.diff import get_diff

from siada.foundation.logging import logger

from binaryornot.check import is_binary


from siada.tools.coder.files import read_lines
from siada.tools.coder.observation.file_observation import FileReadObservation, FileEditObservation
from siada.tools.coder.observation.observation import FunctionCallResult, FileEditSource
from siada.tools.coder.observation.error import ErrorObservation
from siada.tools.coder.observation.observation import FileReadSource
from siada.tools.coder.tool_docs import EDIT_DOCS
from siada.foundation.code_agent_context import CodeAgentContext


@function_tool(
    name_override="read_file", description_override="Read the file."
)
async def read(
    context: RunContextWrapper[CodeAgentContext],
    path: str,
    start: int = 0,
    end: int = -1,
    impl_source: FileReadSource = FileReadSource.DEFAULT,
    view_range: list[int] | None = None
) -> FunctionCallResult:
    """
    Read file content with support for various file types including text, images, PDFs, and videos.
    
    This function handles different file types and returns appropriate observations:
    - Text files: Returns content as string with optional line range selection
    - Image files: Returns base64-encoded data URI
    - PDF files: Returns base64-encoded data URI
    - Video files: Returns base64-encoded data URI
    - Binary files: Returns error observation
    
    Args:
        context: The run context wrapper containing agent context and root directory
        path: File path to read (relative to working directory or absolute)
        start: Starting line number for text files (0-based, default: 0)
        end: Ending line number for text files (-1 means end of file, default: -1)
        impl_source: Implementation source for reading (DEFAULT or OH_ACI)
        view_range: Optional line range for OH_ACI implementation [start, end]
        
    Returns:
        Observation: FileReadObservation with file content or ErrorObservation on failure
        
    Raises:
        No exceptions are raised directly - all errors are captured and returned as ErrorObservation
    """

    # Cannot read binary files
    if is_binary(path):
        return ErrorObservation('ERROR_BINARY_FILE')

    # Get the working directory from context and initialize file editor
    working_dir = context.context.root_dir
    file_editor = OHEditor(workspace_root=working_dir)
    
    # Use OH_ACI implementation if specified
    if impl_source == FileReadSource.OH_ACI:
        result_str, _ = _execute_file_editor(
            file_editor,
            command='view',
            path=path,
            view_range=view_range,
        )

        return FileReadObservation(
            content=result_str,
            path=path,
            impl_source=FileReadSource.OH_ACI,
        )

    # NOTE: the client code is running inside the sandbox,
    # so there's no need to check permission
    # Resolve the file path (convert relative to absolute if needed)
    filepath = _resolve_path(path, working_dir)
    try:
        # Handle image files - return as base64-encoded data URI
        if filepath.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif')):
            with open(filepath, 'rb') as file:  # noqa: ASYNC101
                image_data = file.read()
                encoded_image = base64.b64encode(image_data).decode('utf-8')
                mime_type, _ = mimetypes.guess_type(filepath)
                if mime_type is None:
                    mime_type = 'image/png'  # default to PNG if mime type cannot be determined
                encoded_image = f'data:{mime_type};base64,{encoded_image}'

            return FileReadObservation(path=filepath, content=encoded_image)
        # Handle PDF files - return as base64-encoded data URI
        elif filepath.lower().endswith('.pdf'):
            with open(filepath, 'rb') as file:  # noqa: ASYNC101
                pdf_data = file.read()
                encoded_pdf = base64.b64encode(pdf_data).decode('utf-8')
                encoded_pdf = f'data:application/pdf;base64,{encoded_pdf}'
            return FileReadObservation(path=filepath, content=encoded_pdf)
        # Handle video files - return as base64-encoded data URI
        elif filepath.lower().endswith(('.mp4', '.webm', '.ogg')):
            with open(filepath, 'rb') as file:  # noqa: ASYNC101
                video_data = file.read()
                encoded_video = base64.b64encode(video_data).decode('utf-8')
                mime_type, _ = mimetypes.guess_type(filepath)
                if mime_type is None:
                    mime_type = 'video/mp4'  # default to MP4 if MIME type cannot be determined
                encoded_video = f'data:{mime_type};base64,{encoded_video}'

            return FileReadObservation(path=filepath, content=encoded_video)

        # Handle text files - read with UTF-8 encoding and apply line range if specified
        with open(filepath, 'r', encoding='utf-8') as file:  # noqa: ASYNC101
            lines = read_lines(file.readlines(), start, end)
    except FileNotFoundError:
        # File does not exist at the specified path
        return ErrorObservation(
            f'File not found: {filepath}. Your current working directory is {working_dir}.'
        )
    except UnicodeDecodeError:
        # File contains non-UTF-8 content that cannot be decoded
        return ErrorObservation(f'File could not be decoded as utf-8: {filepath}.')
    except IsADirectoryError:
        # Path points to a directory instead of a file
        return ErrorObservation(
            f'Path is a directory: {filepath}. You can only read files'
        )

    # Join the lines back into a single string and return the observation
    code_view = ''.join(lines)
    return FileReadObservation(path=filepath, content=code_view)

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
    view_range: list[int] | None = None
) -> FunctionCallResult:
    return _edit_file(
        context=context,
        command=command,
        path=path,
        file_text=file_text,
        old_str=old_str,
        new_str=new_str,
        insert_line=insert_line,
        view_range=view_range
    )

def _edit_file(
    context: RunContextWrapper[CodeAgentContext], 
    command: str,
    path: str,
    file_text: str | None = None,
    old_str: str | None = None,
    new_str: str | None = None,
    insert_line: int | None = None,
    view_range: list[int] | None = None
) -> FunctionCallResult:
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

    Returns:
        tuple: A tuple containing the output string and a tuple of old and new file content
    """
    result: ToolResult | None = None

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

    return result.output, (result.old_content, result.new_content)

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
