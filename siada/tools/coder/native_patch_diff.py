"""SDK V4A parsing with bounded Codex-style context matching."""

from __future__ import annotations

import importlib
import re

sdk_diff = importlib.import_module("agents.apply_diff")


class PatchContextError(ValueError):
    """The submitted old lines do not match the current source."""


_UNICODE_TRANSLATION = str.maketrans(
    {
        **dict.fromkeys("\u2010\u2011\u2012\u2013\u2014\u2015\u2212", "-"),
        **dict.fromkeys("\u2018\u2019\u201a\u201b", "'"),
        **dict.fromkeys("\u201c\u201d\u201e\u201f", '"'),
        **dict.fromkeys(
            "\u00a0\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u202f\u205f\u3000",
            " ",
        ),
    }
)


def _normalize_context(line: str) -> str:
    return line.strip().translate(_UNICODE_TRANSLATION)


def _find_context_core(
    lines: list[str], context: list[str], start: int
) -> sdk_diff.ContextMatch:
    match = sdk_diff._find_context_core(lines, context, start)
    if match.new_index != -1:
        return match
    normalized = [_normalize_context(line) for line in context]
    for index in range(start, len(lines) - len(context) + 1):
        if all(
            _normalize_context(lines[index + offset]) == expected
            for offset, expected in enumerate(normalized)
        ):
            return sdk_diff.ContextMatch(new_index=index, fuzz=1000)
    return match


def _find_context(
    lines: list[str], context: list[str], start: int, eof: bool
) -> sdk_diff.ContextMatch:
    if not eof:
        return _find_context_core(lines, context, start)
    search_lines = sdk_diff._eof_search_lines(lines)
    end_start = max(start, len(search_lines) - len(context))
    match = _find_context_core(search_lines, context, end_start)
    if match.new_index != -1:
        return match
    return _find_context_core(search_lines, context, min(start, len(search_lines)))


def _advance_anchor(
    anchor: str,
    lines: list[str],
    cursor: int,
    *,
    required: bool,
    force_forward: bool,
) -> int:
    for normalize in (lambda line: line, str.strip, _normalize_context):
        expected = normalize(anchor)
        if not force_forward and any(normalize(line) == expected for line in lines[:cursor]):
            return cursor
        for index in range(cursor, len(lines)):
            if normalize(lines[index]) == expected:
                return index + 1
    if required:
        raise PatchContextError(f"Invalid Anchor {cursor}:\n{anchor}")
    return cursor


def _parse_update(diff: str, input_text: str) -> list[sdk_diff.Chunk]:
    parser = sdk_diff.ParserState(lines=[*sdk_diff._normalize_diff_lines(diff), sdk_diff.END_PATCH])
    lines = re.split(r"\r\n|\r|\n", input_text)
    chunks: list[sdk_diff.Chunk] = []
    cursor = 0
    while not sdk_diff._is_done(parser, sdk_diff.END_SECTION_MARKERS):
        anchors, anchor_count = sdk_diff._read_anchors(parser)
        if not (anchor_count > 0 or cursor == 0):
            raise ValueError(f"Invalid Line:\n{parser.lines[parser.index]}")
        for index, anchor in enumerate(anchors):
            cursor = _advance_anchor(
                anchor,
                lines,
                cursor,
                required=anchor_count > 1,
                force_forward=index > 0,
            )
        section = sdk_diff._read_section(parser.lines, parser.index)
        context = section.next_context
        match = _find_context(lines, context, cursor, section.eof)
        trimmed = False
        if match.new_index == -1 and len(context) > 1 and context[-1] == "":
            candidate = _find_context(lines, context[:-1], cursor, section.eof)
            real_lines = sdk_diff._eof_search_lines(lines)
            if candidate.new_index != -1 and candidate.new_index + len(context) - 1 == len(real_lines):
                context = context[:-1]
                match = candidate
                trimmed = True
        if match.new_index == -1:
            label = "Invalid EOF Context" if section.eof else "Invalid Context"
            raise PatchContextError(f"{label} {cursor}:\n" + "\n".join(section.next_context))
        for chunk in section.section_chunks:
            deleted = chunk.del_lines
            inserted = chunk.ins_lines
            if trimmed and chunk.orig_index + len(deleted) > len(context):
                deleted = deleted[: max(0, len(context) - chunk.orig_index)]
                if inserted and inserted[-1] == "":
                    inserted = inserted[:-1]
            chunks.append(
                sdk_diff.Chunk(
                    orig_index=match.new_index + (min(chunk.orig_index, len(context)) if trimmed else chunk.orig_index),
                    del_lines=deleted,
                    ins_lines=inserted,
                )
            )
        cursor = match.new_index + len(context)
        parser.index = section.end_index
    return chunks


def apply_native_diff(input_text: str, diff: str, *, mode: str) -> str:
    """Normalize only matching text, preserving untouched source and inserted text."""
    if mode == "create":
        return sdk_diff.apply_diff(input_text, diff, mode="create")
    chunks = _parse_update(diff, input_text)
    parts = re.split(r"(\r\n|\r|\n)", input_text)
    source = [
        (parts[index], parts[index + 1] if index + 1 < len(parts) else "")
        for index in range(0, len(parts), 2)
    ]
    newline = next((ending for _, ending in source if ending), "\n")
    result: list[tuple[str, str]] = []
    cursor = 0
    for chunk in chunks:
        if chunk.orig_index < cursor or chunk.orig_index + len(chunk.del_lines) > len(source):
            raise ValueError(f"Invalid or overlapping patch chunk at {chunk.orig_index}")
        result.extend(source[cursor : chunk.orig_index])
        result.extend((line, newline) for line in chunk.ins_lines)
        cursor = chunk.orig_index + len(chunk.del_lines)
    result.extend(source[cursor:])
    return "".join(
        line + ((ending or newline) if index < len(result) - 1 else "")
        for index, (line, ending) in enumerate(result)
    )
