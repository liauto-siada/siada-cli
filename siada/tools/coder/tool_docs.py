EDIT_DOCS= """Custom editing tool for viewing, creating and editing files in plain-text format
* State is persistent across command calls and discussions with the user
* If `path` is a text file, `view` displays the result of applying `cat -n`. If `path` is a directory, `view` lists non-hidden files and directories up to 2 levels deep
* The following binary file extensions can be viewed in Markdown format: [".xlsx", ".pptx", ".wav", ".mp3", ".m4a", ".flac", ".pdf", ".docx"]. 
* Image files ([".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"]) are automatically returned as base64-encoded data URIs optimized for AI vision models.
* The `create` command cannot be used if the specified `path` already exists as a file
* Truncation for `view` on text files (two layers; lines are never character-truncated):
  1. Byte cap: files > 100 KB are cut to the first 100 KB; output ends with `[FILE TRUNCATED: ...]`. Then switch to `regex_search_files` or `run_cmd` (grep/head/tail) — `view_range` cannot reach the dropped bytes.
  2. Line pagination (default 1000 lines): no `view_range` → `[1, min(1000, N)]`; `[a, -1]` → `[a, N]`; `[a, b]` → as given (auto-clamped/swapped).
* Each `view` output ends with exactly ONE suffix — act on it:
  - `[FILE TRUNCATED: ...]` → use search/grep, stop paging.
  - `(Showing lines S-E of N total. Use view_range=<suggested> ...)` → more lines left; `<suggested>` is the next 1000-line window (or `[E+1, -1]` when ≤1000 remain). Follow it verbatim, don't widen it yourself.
  - `(File has N lines total.)` → EOF reached, no follow-up needed.
* The `undo_edit` command will revert the last edit made to the file at `path`
* This tool can be used for creating and editing files in plain-text format.


Before using this tool:
1. Use the view tool to understand the file's contents and context
2. Verify the directory path is correct (only applicable when creating new files):
   - Use the view tool to verify the parent directory exists and is the correct location

When making edits:
   - Ensure the edit results in idiomatic, correct code
   - Do not leave the code in a broken state
   - Always use absolute file paths (starting with /)
   - ALWAYS prefer editing existing files in the codebase. NEVER write new files unless explicitly required.
   - NEVER proactively create documentation files (*.md) or README files. Only create documentation files if explicitly requested by the User.

CRITICAL REQUIREMENTS FOR USING THIS TOOL:

1. EXACT MATCHING: The `old_str` parameter must match EXACTLY one or more consecutive lines from the file, including all whitespace and indentation. The tool will fail if `old_str` matches multiple locations or doesn't match exactly with the file content.

2. UNIQUENESS: The `old_str` must uniquely identify a single instance in the file:
   - Include sufficient context before and after the change point (3-5 lines recommended)
   - If not unique, the replacement will not be performed

3. REPLACEMENT: The `new_str` parameter should contain the edited lines that replace the `old_str`. Both strings must be different.

Remember: when making multiple file edits in a row to the same file, you should prefer to send all edits in a single message with multiple calls to this tool, rather than multiple messages with a single call each.
Note: When a parameter value is not provided, use null (in JSON) instead of an empty string “”.

Args:
    command: The commands to run. Allowed options are: `view`, `create`, `str_replace`, `insert`, `undo_edit`.
    path: Absolute path to file or directory, e.g. `/workspace/file.py` or `/workspace`.
    file_text: Required parameter of `create` command, with the content of the file to be created.
    old_str: Required parameter of `str_replace` command containing the string in `path` to replace.
    new_str: Optional parameter of `str_replace` command containing the new string (if not given, no string will be added). Required parameter of `insert` command containing the string to insert.
    insert_line: Required parameter of `insert` command. The `new_str` will be inserted AFTER the line `insert_line` of `path`.
    view_range: Optional parameter of `view` command when `path` points to a file. If none is given, the full file is shown. If provided, the file will be shown in the indicated line number range, e.g. [11, 12] will show lines 11 and 12. Indexing at 1 to start. Setting `[start_line, -1]` shows all lines from `start_line` to the end of the file.



"""

