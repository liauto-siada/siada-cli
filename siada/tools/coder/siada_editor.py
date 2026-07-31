"""
Siada-customized file editor.

This module subclasses the upstream :class:`OHEditor` (from ``openhands_aci``)
to override the ``view`` command truncation strategy for regular text files.

Policy summary
--------------
The upstream ``OHEditor`` applies a single global 16000-character cap to
``view`` output. That is both too small for real source files and too
opaque for the model (cuts mid-line, no size info). The Siada policy
replaces it with a two-layer strategy inspired by another agent codebase:

1. **Byte-size truncation (file-level)**

   Before any line slicing, the raw file content is capped at
   ``MAX_CONTENT_SIZE_BYTES`` (100 KB, measured in UTF-8 bytes). Anything
   beyond that is dropped and a clearly-labeled ``[FILE TRUNCATED: ...]``
   suffix is appended telling the model the total file size, how much was
   shown, and how to continue reading (via ``regex_search_files`` or
   ``run_cmd`` with ``grep`` / ``head`` / ``tail``).

2. **Soft line-based pagination (display-level)**

   Within the (possibly byte-truncated) body, line slicing is applied:

   - Default window size is ``DEFAULT_MAX_LINES`` (1000 lines).
   - ``view_range = None``              -> lines ``[1, min(1000, N)]``.
   - ``view_range = [a, -1]``           -> lines ``[a, N]`` (explicit "to
     end"; honored as-is, no 1000-line cap).
   - ``view_range = [a, b]`` (b >= 1)   -> lines ``[a, b]`` (honored as-is).
   - Out-of-range inputs are clamped to ``[1, N]``; if ``start > end``
     after clamping, the two are swapped.

3. **Suffix message (three mutually exclusive forms)**

   - If byte truncation happened → the ``[FILE TRUNCATED: ...]`` marker
     produced in step 1.
   - Else if the shown slice ended before the last line
     (``end < total_lines``) → ``(Showing lines S-E of N total. ...)``
     with a hint to continue reading.
   - Else → ``(File has N lines total.)``.

Out of scope
------------
- Directory ``view`` and supported-binary ``view`` (PDF/DOCX → Markdown)
  keep the upstream behavior unchanged.
- ``str_replace`` / ``insert`` / ``undo_edit`` snippet previews keep the
  upstream behavior unchanged.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

# Suppress openhands_aci DEBUG noise (FileCache init, size updates, etc.)
# before the package is imported, so it takes effect regardless of which
# entrypoint is used.
logging.getLogger('openhands_aci').setLevel(logging.WARNING)

from openhands_aci.editor.editor import OHEditor
from openhands_aci.editor.results import CLIResult


# Maximum raw-content size (in UTF-8 bytes) before byte-level truncation
# kicks in. 100 KB matches the reference implementation.
MAX_CONTENT_SIZE_BYTES: int = 100 * 1024

# Default number of lines shown per ``view`` call when the caller does
# not provide ``view_range``.
DEFAULT_MAX_LINES: int = 1000

# Byte-truncation marker prefix. Used both to build the suffix and to
# re-detect it when splitting body vs. suffix.
_FILE_TRUNCATED_MARKER_PREFIX = "\n\n---\n\n[FILE TRUNCATED:"


def _format_bytes(n: int) -> str:
    """Format a byte count as a short human-readable string.

    Matches the conventions used in the reference implementation (e.g.
    ``100KB``, ``1.5MB``).
    """
    if n < 1024:
        return f"{n}B"
    if n < 1024 * 1024:
        # Show one decimal for sub-MB to give the model useful resolution.
        value = n / 1024
        return f"{value:.1f}KB" if value < 10 else f"{int(round(value))}KB"
    value = n / (1024 * 1024)
    return f"{value:.1f}MB" if value < 10 else f"{int(round(value))}MB"


class SiadaEditor(OHEditor):
    """OHEditor subclass with Siada-specific ``view`` truncation policy."""

    # ------------------------------------------------------------------
    # Public overrides
    # ------------------------------------------------------------------
    def view(self, path: Path, view_range: list[int] | None = None) -> CLIResult:
        # Non-text-file cases are delegated to the upstream implementation
        # (directory listing, PDF/DOCX-to-Markdown conversion, etc.).
        if path.is_dir():
            return super().view(path, view_range)

        self.validate_file(path)

        if self.is_supported_binary_file(path):
            return super().view(path, view_range)

        # ------------------------------------------------------------------
        # Step 1: read the full raw content and apply byte-level truncation.
        # ------------------------------------------------------------------
        full_content = self.read_file(path)
        body, truncation_suffix = self._apply_byte_truncation(full_content)

        # ------------------------------------------------------------------
        # Step 2: split into lines.
        # ``re.split(r'\r?\n', ...)`` mirrors the reference implementation
        # so Windows line endings are handled correctly.
        # ------------------------------------------------------------------
        # Empty body shortcuts to 0 lines. Without this guard,
        # ``re.split`` would return ``['']`` and we'd report 1 fake line.
        if body == "":
            lines: list[str] = []
        else:
            lines = re.split(r"\r?\n", body)
            # If the body ends with a newline, ``split`` leaves a trailing
            # empty string; drop it so line-count math is intuitive.
            if body.endswith("\n") and lines and lines[-1] == "":
                lines.pop()
        total_lines = len(lines)

        # Edge case: empty file. Render a minimal, unambiguous output.
        if total_lines == 0:
            return self._build_result(
                path=str(path),
                numbered_body="",
                suffix=truncation_suffix or "\n\n(File has 0 lines total.)",
            )

        # ------------------------------------------------------------------
        # Step 3: resolve the requested slice, clamp, and possibly swap.
        # ------------------------------------------------------------------
        start, end = self._resolve_range(view_range, total_lines)

        # ------------------------------------------------------------------
        # Step 4: build the numbered output.
        # ------------------------------------------------------------------
        slice_lines = lines[start - 1 : end]
        numbered_body = "\n".join(
            f"{i + start:6}\t{line}" for i, line in enumerate(slice_lines)
        )

        # ------------------------------------------------------------------
        # Step 5: choose the suffix. Byte truncation has priority; then the
        # "continue reading" hint; then the plain total-line footer.
        # ------------------------------------------------------------------
        if truncation_suffix:
            suffix = truncation_suffix
        elif end < total_lines:
            # Recommend the NEXT ``DEFAULT_MAX_LINES``-sized window so the
            # model keeps reading in stable 1000-line pages instead of
            # pulling thousands of lines at once with ``[next, -1]``.
            # If the remaining tail fits inside one window, fold it into
            # ``-1`` so the final page is a single ``(File has N lines total.)``.
            next_start = end + 1
            remaining = total_lines - next_start + 1
            if remaining <= DEFAULT_MAX_LINES:
                next_range = f"[{next_start}, -1]"
            else:
                next_end = next_start + DEFAULT_MAX_LINES - 1
                next_range = f"[{next_start}, {next_end}]"
            suffix = (
                f"\n\n(Showing lines {start}-{end} of {total_lines} total. "
                f"Use `view_range={next_range}` with the same `edit_file view` "
                f"call to continue reading from line {next_start}. "
                f"File has {total_lines} lines total.)"
            )
        else:
            suffix = f"\n\n(File has {total_lines} lines total.)"

        return self._build_result(
            path=str(path),
            numbered_body=numbered_body,
            suffix=suffix,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _apply_byte_truncation(content: str) -> tuple[str, str | None]:
        """Cap ``content`` at ``MAX_CONTENT_SIZE_BYTES``.

        Returns a tuple ``(body, suffix)`` where ``suffix`` is ``None``
        when no truncation was applied, or the full ``[FILE TRUNCATED: ...]``
        marker string (already starting with ``\\n\\n---\\n\\n``) when it
        was. The returned ``body`` is guaranteed to be valid UTF-8 / a
        well-formed Python string even when the raw byte cut would have
        landed inside a multi-byte character (we back off to the last
        safe boundary).
        """
        raw = content.encode("utf-8")
        total_bytes = len(raw)
        if total_bytes <= MAX_CONTENT_SIZE_BYTES:
            return content, None

        # Back off to the last valid UTF-8 boundary so we never produce a
        # broken string. ``errors='ignore'`` handles any remaining
        # partial code unit conservatively.
        truncated_bytes = raw[:MAX_CONTENT_SIZE_BYTES]
        body = truncated_bytes.decode("utf-8", errors="ignore")

        truncated_amount = total_bytes - MAX_CONTENT_SIZE_BYTES
        suffix = (
            f"\n\n---\n\n[FILE TRUNCATED: This content is "
            f"{_format_bytes(total_bytes)} but only the first "
            f"{_format_bytes(MAX_CONTENT_SIZE_BYTES)} is shown "
            f"({_format_bytes(truncated_amount)} truncated). Use "
            f"`regex_search_files` to find specific patterns, or `run_cmd` "
            f"with `grep`/`head`/`tail` for targeted reading.]"
        )
        return body, suffix

    @staticmethod
    def _resolve_range(
        view_range: list[int] | None, total_lines: int
    ) -> tuple[int, int]:
        """Compute the effective ``[start, end]`` 1-based line range.

        Follows the reference semantics:

        * No range → ``[1, min(DEFAULT_MAX_LINES, total_lines)]``.
        * Range with ``end == -1`` → ``[start, total_lines]`` (explicit
          "to end of file"; honored without the 1000-line cap).
        * Explicit ``[start, end]`` → honored, but each bound is clamped
          to ``[1, total_lines]`` and swapped if ``start > end``.
        * Malformed inputs (wrong length or non-integers) fall back to
          the "no range" default; they are not raised as errors here
          because the upstream ``view`` would have already returned
          earlier on such inputs in most call sites, and downgrading is
          friendlier to the agent.
        """
        default_start = 1
        default_end = min(DEFAULT_MAX_LINES, total_lines)

        if (
            view_range is None
            or len(view_range) != 2
            or not all(isinstance(v, int) for v in view_range)
        ):
            return default_start, default_end

        start, end = view_range[0], view_range[1]

        # "-1" is the long-standing sentinel meaning "to the last line".
        if end == -1:
            end = total_lines

        # Clamp both bounds into the valid range.
        start = max(1, min(start, total_lines))
        end = max(1, min(end, total_lines))
        if start > end:
            start, end = end, start
        return start, end

    @staticmethod
    def _build_result(path: str, numbered_body: str, suffix: str) -> CLIResult:
        """Assemble the final CLIResult with the standard ``cat -n`` header."""
        output = (
            f"Here's the result of running `cat -n` on {path}:\n"
            f"{numbered_body}"
            f"{suffix}\n"
        )
        return CLIResult(output=output, path=path, prev_exist=True)
