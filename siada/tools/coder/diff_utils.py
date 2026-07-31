"""
Diff utility for code generation telemetry.

Computes added-line hunks from old/new file content pairs,
mirroring the calculateDiffLines() logic in siada-plugin.
"""

import difflib
from typing import Optional


def calculate_diff_lines(
    new_content: str,
    old_content: str,
    hunk_interval: int = 6,
) -> list[dict]:
    """
    Compare old and new file content, returning a list of added-line hunks.

    Only tracks added lines (not deletions). Adjacent hunks separated by
    <= hunk_interval lines are merged. Trivially short single-line hunks
    (stripped length < 3) are filtered out.

    Returns:
        List of dicts: [{ start_line, end_line, line_count, content }, ...]
        Line numbers are 1-based.
    """
    if not new_content and not old_content:
        return []

    # Mirror siada-plugin: trim both inputs before diffing
    old_trimmed = (old_content or "").strip()
    new_trimmed = (new_content or "").strip()

    old_lines = old_trimmed.splitlines(keepends=True)
    new_lines = new_trimmed.splitlines(keepends=True)

    # Collect added hunks: each contiguous block of added lines becomes one raw hunk.
    # Track current_line as position in the new file (1-based), matching plugin's currentLine.
    raw_hunks: list[dict] = []
    current_line = 1

    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(
        None, old_lines, new_lines, autojunk=False
    ).get_opcodes():
        added_count = j2 - j1
        removed_count = i2 - i1

        if tag == "equal":
            current_line += added_count
        elif tag == "insert":
            # Pure addition
            start_line = current_line
            content = "".join(new_lines[j1:j2])
            line_count = added_count
            end_line = start_line + line_count - 1
            # Mirror plugin filter: keep if multi-line OR raw content length >= 3
            if start_line != end_line or len(content) >= 3:
                raw_hunks.append({
                    "start_line": start_line,
                    "end_line": end_line,
                    "line_count": line_count,
                    "content": content,
                })
            current_line += line_count
        elif tag == "replace":
            # Lines replaced: old lines removed, new lines added
            start_line = current_line
            content = "".join(new_lines[j1:j2])
            line_count = added_count
            end_line = start_line + line_count - 1
            if start_line != end_line or len(content) >= 3:
                raw_hunks.append({
                    "start_line": start_line,
                    "end_line": end_line,
                    "line_count": line_count,
                    "content": content,
                })
            current_line += line_count
        elif tag == "delete":
            # Removed lines don't advance current_line (they don't exist in new file)
            pass

    if not raw_hunks:
        return []

    # Merge adjacent hunks whose distance <= hunk_interval.
    # Mirror plugin: next.start_line - current.end_line <= hunkInterval
    # Gap fill uses new_lines (0-based): lines between end_line and start_line of next hunk.
    new_content_lines = new_trimmed.split("\n")  # match plugin's split("\n") for gap fill
    merged = [dict(raw_hunks[0])]
    for hunk in raw_hunks[1:]:
        prev = merged[-1]
        if hunk["start_line"] - prev["end_line"] <= hunk_interval:
            # Fill gap: lines between the two hunks (exclusive of both endpoints).
            # end_line is 1-based → 0-based index is end_line-1, so next line is index end_line.
            # start_line is 1-based → lines up to start_line-1 are at index start_line-2.
            # Slice: new_content_lines[end_line : start_line-1]
            gap = new_content_lines[prev["end_line"]: hunk["start_line"] - 1]
            if gap:
                prev["content"] += "\n".join(gap) + "\n" + hunk["content"]
            else:
                prev["content"] += hunk["content"]
            prev["end_line"] = hunk["end_line"]
            prev["line_count"] = prev["end_line"] - prev["start_line"] + 1
        else:
            merged.append(dict(hunk))

    return merged
