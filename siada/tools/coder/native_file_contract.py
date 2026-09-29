"""Native patch file-tool contract shared by tool registration and prompting.

The OpenAI Responses ``apply_patch`` tool has no per-tool description field:
its wire representation is simply ``{"type": "apply_patch"}``.  Keeping
the model-facing contract here gives the native tool and GPT-5/6 prompts one
source of truth without changing the legacy ``edit_file`` contract for
non-native model families.
"""

READ_FILE_DESCRIPTION = """Read a file or directory without modifying it.

This is the native-patch models' only file-reading wrapper. It uses the existing workspace
reader, so it preserves directory listings, supported document/image handling,
`.siadaignore` filtering, and text-file pagination. It accepts only:

- `path`: a file or directory path. Workspace-relative paths are resolved
  from the current workspace; absolute paths keep the existing reader's
  behavior.
- `view_range`: optional `[start_line, end_line]` for text files; `-1` means
  the end of the file.

For large text files, follow the continuation range reported by the tool. This
tool is read-only: it never creates, replaces, inserts, deletes, or reverts
content."""


APPLY_PATCH_DESCRIPTION = """Create, update, delete, or move text files with
focused patches. Read the current file before updating it. All referenced
paths, including `move_to`, must be workspace-relative."""
