"""Compatibility imports for the original Astra-named file tools."""

from .native_file_tools import (
    APPLY_PATCH_DESCRIPTION,
    READ_FILE_DESCRIPTION,
    NativeApplyPatchTool,
    SiadaNativeApplyPatchEditor,
    create_native_apply_patch_tool,
    read_file,
)

AstraApplyPatchTool = NativeApplyPatchTool
SiadaAstraApplyPatchEditor = SiadaNativeApplyPatchEditor

__all__ = [
    "NativeApplyPatchTool",
    "AstraApplyPatchTool",
    "READ_FILE_DESCRIPTION",
    "APPLY_PATCH_DESCRIPTION",
    "SiadaNativeApplyPatchEditor",
    "SiadaAstraApplyPatchEditor",
    "create_native_apply_patch_tool",
    "create_astra_apply_patch_tool",
    "read_file",
]


def create_astra_apply_patch_tool() -> NativeApplyPatchTool:
    """Keep the old factory available for existing callers."""
    return create_native_apply_patch_tool()
