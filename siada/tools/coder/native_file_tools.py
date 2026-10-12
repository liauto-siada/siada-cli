"""Native patch file tools for GPT-5-or-newer models and the Astra alias.

``read_file`` deliberately exposes only the ``view`` branch of ``edit_file``.
``apply_patch`` uses the OpenAI Agents SDK's native Responses tool and V4A
patch parser, while this module supplies the workspace-specific editor policy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path, PureWindowsPath

from agents import ApplyPatchTool, RunContextWrapper, ToolOutputImage, function_tool
from agents.editor import ApplyPatchEditor, ApplyPatchOperation, ApplyPatchResult

from siada.foundation.code_agent_context import CodeAgentContext
from siada.tools.coder.native_file_contract import (
    APPLY_PATCH_DESCRIPTION,
    READ_FILE_DESCRIPTION,
)
from siada.tools.coder.apply_patch_presentation import PatchPresentationRecorder
from siada.tools.coder.native_patch_diff import apply_native_diff
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


@dataclass(frozen=True)
class _PreparedOperation:
    source: Path
    destination: Path
    display_path: str
    moved_display_path: str | None
    old_text: str | None
    new_text: str | None
    destination_old_text: str | None = None


@dataclass
class _PatchFileState:
    files: dict[Path, str | None] = field(default_factory=dict)
    directories: set[Path] = field(default_factory=set)


class SiadaNativeApplyPatchEditor(ApplyPatchEditor):
    """Apply native V4A patch operations from one Siada workspace.

    The SDK dispatches operations, while Siada adds bounded matching tolerance
    and per-operation verification around its V4A parser. The editor owns context
    discovery and codex-aligned path resolution (absolute or workspace-relative,
    symlinks followed, outside targets granted by default), `.siadaignore` protection,
    UTF-8 file I/O, and readable operation results.
    """

    def __init__(self, recorder: PatchPresentationRecorder | None = None) -> None:
        self._recorder = recorder

    def create_file(self, operation: ApplyPatchOperation) -> ApplyPatchResult:
        return self._execute_operation(operation)

    def update_file(self, operation: ApplyPatchOperation) -> ApplyPatchResult:
        return self._execute_operation(operation)

    def delete_file(self, operation: ApplyPatchOperation) -> ApplyPatchResult:
        return self._execute_operation(operation)

    def _execute_operation(self, operation: ApplyPatchOperation) -> ApplyPatchResult:
        try:
            prepared = self._prepare_operation(operation, _PatchFileState())
            return self._commit_operation(operation, prepared)
        except Exception as exc:
            return self._failure(operation, exc)

    def _prepare_operation(
        self, operation: ApplyPatchOperation, state: _PatchFileState
    ) -> _PreparedOperation:
        root, source, display_path = self._resolve_operation_path(operation)
        original = self._batch_text(source, display_path, state)
        destination = source
        moved_display_path = None
        destination_old_text = None
        if operation.type == "create_file":
            if original is not None:
                raise ValueError(f"Cannot create '{display_path}': the path already exists.")
            updated = self._apply_diff(operation, input_text="", mode="create")
        else:
            if original is None:
                raise FileNotFoundError(f"Cannot {operation.type} '{display_path}': file does not exist.")
            updated = None
            if operation.type == "update_file":
                updated = self._apply_diff(operation, input_text=original, mode="default")
                if operation.move_to is not None:
                    destination, moved_display_path = self._resolve_path(
                        root, operation.move_to, operation=operation, label="move_to"
                    )
                    if destination != source:
                        destination_old_text = self._batch_text(destination, moved_display_path, state)
        if updated is not None:
            self._validate_parents(destination, state)
            state.directories.update(destination.parents)
        prepared = _PreparedOperation(
            source=source,
            destination=destination,
            display_path=display_path,
            moved_display_path=moved_display_path,
            old_text=original,
            new_text=updated,
            destination_old_text=destination_old_text,
        )
        state.files[source] = None if destination != source else updated
        if destination != source:
            state.files[destination] = updated
        return prepared

    def _batch_text(
        self, path: Path, display_path: str, state: _PatchFileState
    ) -> str | None:
        if path in state.directories:
            raise ValueError(f"Cannot patch '{display_path}': path is a directory in this batch.")
        if path not in state.files:
            if path.exists() or path.is_symlink():
                if not path.is_file():
                    raise ValueError(f"Cannot patch '{display_path}': path is not a regular file.")
                state.files[path] = self._read_text(path, display_path)
            else:
                state.files[path] = None
        return state.files[path]

    @staticmethod
    def _validate_parents(path: Path, state: _PatchFileState) -> None:
        for parent in path.parents:
            if parent in state.files:
                invalid = state.files[parent] is not None
            else:
                invalid = parent.exists() and not parent.is_dir()
            if invalid:
                raise ValueError(f"Cannot patch '{path}': parent '{parent}' is not a directory.")

    def _commit_operation(
        self, operation: ApplyPatchOperation, prepared: _PreparedOperation
    ) -> ApplyPatchResult:
        root, source, _display_path = self._resolve_operation_path(operation)
        destination = source
        if operation.move_to is not None and operation.type == "update_file":
            destination, _moved = self._resolve_path(
                root, operation.move_to, operation=operation, label="move_to"
            )
        if source != prepared.source or destination != prepared.destination:
            raise ValueError("Patch path changed after verification; read the current file again.")
        if self._batch_text(source, prepared.display_path, _PatchFileState()) != prepared.old_text:
            raise ValueError("File changed after patch verification; read the current file again.")
        if destination != source:
            destination_text = self._batch_text(destination, str(destination), _PatchFileState())
            if destination_text != prepared.destination_old_text:
                raise ValueError("Move destination changed after patch verification; read the current file again.")
        if prepared.new_text is None:
            source.unlink()
        else:
            self._write_text(destination, prepared.new_text)
            if destination != source:
                source.unlink()
        self._record_completed(
            operation, old_text=prepared.old_text or "", new_text=prepared.new_text or ""
        )
        action = {
            "create_file": "Created", "update_file": "Updated", "delete_file": "Deleted"
        }[operation.type]
        output = f"{action} {prepared.display_path}"
        if prepared.moved_display_path is not None:
            output += f"\nMoved {prepared.display_path} to {prepared.moved_display_path}"
        return ApplyPatchResult(status="completed", output=output)

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
            raise ValueError(f"apply_patch {label} must be a non-empty path.")

        # Codex-native path semantics: an absolute native path targets its
        # spelled location, a relative path resolves against the workspace
        # root, and ``..`` segments normalize during resolution. Only Windows
        # drive/UNC spellings are rejected because a host that does not
        # recognize them would reinterpret them as relative names.
        windows_path = PureWindowsPath(raw_path)
        if not Path(raw_path).is_absolute() and (
            windows_path.is_absolute() or windows_path.drive
        ):
            raise ValueError(
                f"apply_patch {label} uses Windows path syntax that this host "
                f"cannot interpret: {raw_path!r}"
            )

        normalized = raw_path.replace("\\", "/")
        logical = Path(normalized)
        if not logical.is_absolute():
            logical = root / logical
        try:
            target = logical.resolve(strict=False)
        except OSError as exc:
            raise ValueError(
                f"apply_patch {label} could not be resolved: {raw_path!r}"
            ) from exc

        try:
            display_path = target.relative_to(root).as_posix()
        except ValueError:
            # Outside the workspace: report where the patch actually landed
            # so the model can follow up on the physical location.
            display_path = str(target)

        context = getattr(getattr(operation, "ctx_wrapper", None), "context", None)
        siadaignore_controller = getattr(context, "siadaignore_controller", None)
        # Validate the spelling as given rather than the resolved physical
        # path: the root here is symlink-resolved while the controller keeps
        # its own workspace spelling (on macOS ``/var`` resolves beneath
        # ``/private/var``). Relative spellings anchor to the controller's
        # workspace; absolute spellings are matched as spelled.
        if siadaignore_controller and not siadaignore_controller.validate_access(normalized):
            raise PermissionError(f"Access to '{display_path}' is denied by .siadaignore.")

        return target, display_path

    @staticmethod
    def _apply_diff(
        operation: ApplyPatchOperation,
        *,
        input_text: str,
        mode: str,
    ) -> str:
        if operation.diff is None:
            raise ValueError(f"apply_patch {operation.type} is missing its diff payload.")
        return apply_native_diff(input_text, operation.diff, mode=mode)

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
        message = str(exc)
        if any(label in message for label in ("Invalid Context", "Invalid EOF Context", "Invalid Anchor")):
            message += (
                "\nContext matching requires complete current source lines, not JSON fields "
                "or substrings. Read the target region again with read_file (or a targeted "
                "read-only search), omit reader line numbers and truncation markers, and "
                "generate a new patch. Do not retry the unchanged patch."
            )
        if self._recorder is not None:
            self._recorder.record_failed(operation, message)
        return ApplyPatchResult(
            status="failed",
            output=f"ERROR: apply_patch failed for {operation.path}: {message}",
        )


def create_native_apply_patch_tool() -> NativeApplyPatchTool:
    """Create a fresh native tool; its editor is stateless across agent runs."""
    recorder = PatchPresentationRecorder()
    return NativeApplyPatchTool(
        editor=SiadaNativeApplyPatchEditor(recorder=recorder),
        custom_data_extractor=recorder.extract_custom_data,
    )
