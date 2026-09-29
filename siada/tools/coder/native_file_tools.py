"""Native patch file tools for GPT-5-or-newer models and the Astra alias.

``read_file`` deliberately exposes only the ``view`` branch of ``edit_file``.
``apply_patch`` uses the OpenAI Agents SDK's native Responses tool and V4A
patch parser, while this module supplies the workspace-specific editor policy.
"""

from __future__ import annotations

from pathlib import Path, PureWindowsPath

from agents import ApplyPatchTool, RunContextWrapper, ToolOutputImage, function_tool
from agents.apply_diff import apply_diff
from agents.editor import ApplyPatchEditor, ApplyPatchOperation, ApplyPatchResult

from siada.foundation.code_agent_context import CodeAgentContext
from siada.tools.coder.native_file_contract import (
    APPLY_PATCH_DESCRIPTION,
    READ_FILE_DESCRIPTION,
)
from siada.tools.coder.apply_patch_presentation import PatchPresentationRecorder
from siada.tools.coder.file_operator import _edit_file
from siada.tools.coder.observation.observation import FunctionCallResult

__all__ = [
    "NativeApplyPatchTool",
    "READ_FILE_DESCRIPTION",
    "APPLY_PATCH_DESCRIPTION",
    "SiadaNativeApplyPatchEditor",
    "create_native_apply_patch_tool",
    "read_file",
]


@function_tool(name_override="read_file", description_override=READ_FILE_DESCRIPTION)
async def read_file(
    context: RunContextWrapper[CodeAgentContext],
    path: str,
    view_range: list[int] | None = None,
) -> FunctionCallResult | ToolOutputImage:
    """Expose only the existing ``edit_file(command="view")`` backend."""
    requested_path = Path(path)
    if not requested_path.is_absolute():
        root_dir = getattr(context.context, "root_dir", None)
        if not root_dir:
            raise ValueError("read_file requires a workspace root in the run context.")
        path = str(Path(root_dir) / requested_path)
    return _edit_file(
        context=context,
        command="view",
        path=path,
        view_range=view_range,
    )


class NativeApplyPatchTool(ApplyPatchTool):
    """Native Responses apply-patch tool with Siada's shared contract.

    The Responses API accepts only ``{"type": "apply_patch"}``, so its
    protocol cannot carry a custom description. The class attribute is retained
    for introspection and is injected into native-patch model prompts from the
    same source constant.
    """

    description = APPLY_PATCH_DESCRIPTION


class SiadaNativeApplyPatchEditor(ApplyPatchEditor):
    """Apply native V4A patch operations within one Siada workspace.

    The SDK serializes operations and delegates their diff interpretation to
    ``agents.apply_diff.apply_diff``. This editor intentionally owns only
    policy that depends on Siada: context discovery, workspace containment,
    `.siadaignore` protection, UTF-8 file I/O, and readable operation results.
    """

    def __init__(self, recorder: PatchPresentationRecorder | None = None) -> None:
        self._recorder = recorder

    def create_file(self, operation: ApplyPatchOperation) -> ApplyPatchResult:
        try:
            _root, target, display_path = self._resolve_operation_path(operation)
            if target.exists() or target.is_symlink():
                raise ValueError(f"Cannot create '{display_path}': the path already exists.")
            content = self._apply_diff(operation, input_text="", mode="create")
            self._write_text(target, content)
            self._record_completed(operation, old_text="", new_text=content)
            return ApplyPatchResult(status="completed", output=f"Created {display_path}")
        except Exception as exc:
            return self._failure(operation, exc)

    def update_file(self, operation: ApplyPatchOperation) -> ApplyPatchResult:
        try:
            root, source, display_path = self._resolve_operation_path(operation)
            if not source.exists():
                raise FileNotFoundError(f"Cannot update '{display_path}': file does not exist.")
            if not source.is_file():
                raise ValueError(f"Cannot update '{display_path}': path is not a regular file.")

            original = self._read_text(source, display_path)
            updated = self._apply_diff(operation, input_text=original, mode="default")

            destination = source
            moved_display_path: str | None = None
            if operation.move_to is not None:
                destination, moved_display_path = self._resolve_path(
                    root,
                    operation.move_to,
                    operation=operation,
                    label="move_to",
                )

            self._write_text(destination, updated)
            if destination != source:
                source.unlink()

            self._record_completed(operation, old_text=original, new_text=updated)
            output = f"Updated {display_path}"
            if moved_display_path is not None:
                output += f"\nMoved {display_path} to {moved_display_path}"
            return ApplyPatchResult(status="completed", output=output)
        except Exception as exc:
            return self._failure(operation, exc)

    def delete_file(self, operation: ApplyPatchOperation) -> ApplyPatchResult:
        try:
            _root, target, display_path = self._resolve_operation_path(operation)
            if not target.exists() and not target.is_symlink():
                raise FileNotFoundError(f"Cannot delete '{display_path}': file does not exist.")
            if target.is_dir():
                raise ValueError(f"Cannot delete '{display_path}': path is a directory.")
            original = self._read_text(target, display_path, action="delete")
            target.unlink()
            self._record_completed(operation, old_text=original, new_text="")
            return ApplyPatchResult(status="completed", output=f"Deleted {display_path}")
        except Exception as exc:
            return self._failure(operation, exc)

    def _resolve_operation_path(
        self, operation: ApplyPatchOperation
    ) -> tuple[Path, Path, str]:
        root = self._workspace_root(operation)
        target, display_path = self._resolve_path(root, operation.path, operation=operation, label="path")
        return root, target, display_path

    @staticmethod
    def _workspace_root(operation: ApplyPatchOperation) -> Path:
        context_wrapper = operation.ctx_wrapper
        context = getattr(context_wrapper, "context", None)
        root_dir = getattr(context, "root_dir", None)
        if not root_dir:
            raise ValueError("apply_patch requires a workspace root in the run context.")
        return Path(root_dir).resolve()

    @staticmethod
    def _resolve_path(
        root: Path,
        raw_path: str,
        *,
        operation: ApplyPatchOperation,
        label: str,
    ) -> tuple[Path, str]:
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise ValueError(f"apply_patch {label} must be a non-empty relative path.")

        # A native path on this host may not recognize Windows drive or UNC
        # paths, so reject both path conventions before normalizing separators.
        windows_path = PureWindowsPath(raw_path)
        if Path(raw_path).is_absolute() or windows_path.is_absolute() or windows_path.drive:
            raise ValueError(f"apply_patch {label} must be relative to the workspace: {raw_path!r}")

        normalized = raw_path.replace("\\", "/")
        normalized_parts = Path(normalized).parts
        if ".." in normalized_parts:
            raise ValueError(
                f"apply_patch {label} cannot contain parent-directory traversal: {raw_path!r}"
            )
        try:
            target = (root / normalized).resolve(strict=False)
            relative = target.relative_to(root)
        except (OSError, ValueError) as exc:
            raise ValueError(
                f"apply_patch {label} escapes the workspace: {raw_path!r}"
            ) from exc

        context = getattr(getattr(operation, "ctx_wrapper", None), "context", None)
        siadaignore_controller = getattr(context, "siadaignore_controller", None)
        # Validate the logical, workspace-relative path rather than the
        # resolved physical path. On macOS ``/var`` may resolve beneath
        # ``/private/var`` while the controller is rooted at ``/var``.
        if siadaignore_controller and not siadaignore_controller.validate_access(normalized):
            raise PermissionError(f"Access to '{relative.as_posix()}' is denied by .siadaignore.")

        return target, relative.as_posix()

    @staticmethod
    def _apply_diff(
        operation: ApplyPatchOperation,
        *,
        input_text: str,
        mode: str,
    ) -> str:
        if operation.diff is None:
            raise ValueError(f"apply_patch {operation.type} is missing its diff payload.")
        return apply_diff(input_text, operation.diff, mode=mode)  # type: ignore[arg-type]

    @staticmethod
    def _read_text(path: Path, display_path: str, *, action: str = "update") -> str:
        try:
            with path.open("r", encoding="utf-8", newline="") as file:
                return file.read()
        except UnicodeDecodeError as exc:
            raise ValueError(
                f"Cannot {action} '{display_path}': file is not UTF-8 text."
            ) from exc

    @staticmethod
    def _write_text(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as file:
            file.write(content)

    def _record_completed(
        self, operation: ApplyPatchOperation, *, old_text: str, new_text: str
    ) -> None:
        if self._recorder is not None:
            self._recorder.record_completed(operation, old_text=old_text, new_text=new_text)

    def _failure(self, operation: ApplyPatchOperation, exc: Exception) -> ApplyPatchResult:
        if self._recorder is not None:
            self._recorder.record_failed(operation, exc)
        return ApplyPatchResult(
            status="failed",
            output=f"ERROR: apply_patch failed for {operation.path}: {exc}",
        )


def create_native_apply_patch_tool() -> NativeApplyPatchTool:
    """Create a fresh native tool; its editor is stateless across agent runs."""
    recorder = PatchPresentationRecorder()
    return NativeApplyPatchTool(
        editor=SiadaNativeApplyPatchEditor(recorder=recorder),
        custom_data_extractor=recorder.extract_custom_data,
    )
