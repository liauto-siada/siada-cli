"""
Tests for RipgrepSearcher._parse_ripgrep_output context attribution.

Covers the bug where context lines appearing between two matches are
incorrectly added to the previous match's after_context instead of
being assigned to the next match's before_context.
"""

import json

import pytest

from siada.tools.coder.file_search.search import RipgrepSearcher


def _make_searcher() -> RipgrepSearcher:
    """Instantiate RipgrepSearcher without locating a real binary."""
    obj = object.__new__(RipgrepSearcher)
    return obj


def _context(line_number: int, text: str, path: str = "/project/file.py") -> str:
    return json.dumps({
        "type": "context",
        "data": {
            "line_number": line_number,
            "lines": {"text": text},
            "path": {"text": path},
        },
    })


def _match(line_number: int, text: str, path: str = "/project/file.py") -> str:
    return json.dumps({
        "type": "match",
        "data": {
            "line_number": line_number,
            "lines": {"text": text},
            "path": {"text": path},
            "submatches": [{"start": 0, "end": 3}],
        },
    })


class TestParseRipgrepOutputContextAttribution:
    """
    Verifies that context lines are attributed to the correct match.

    ripgrep --context 1 --json outputs events in file order:

        context @ N-1   <- before-context of match@N
        match   @ N
        context @ N+1   <- after-context of match@N
        context @ M-1   <- before-context of match@M  (M >> N)
        match   @ M
        context @ M+1   <- after-context of match@M
    """

    def test_first_match_before_context_is_not_lost(self):
        """
        Bug 1: context lines before the very first match should appear in
        that match's before_context, not be silently dropped.
        """
        output = "\n".join([
            _context(4, "line4\n"),   # before-context of match@5
            _match(5, "line5\n"),
            _context(6, "line6\n"),   # after-context of match@5
        ])

        searcher = _make_searcher()
        results = searcher._parse_ripgrep_output(output)

        assert len(results) == 1
        assert results[0].before_context == ["line4\n"], (
            "before_context of the first match should contain the leading context line"
        )
        assert results[0].after_context == ["line6\n"]

    def test_inter_match_context_goes_to_next_match_before_context(self):
        """
        Bug 2: a context line that appears between two matches (and whose
        line number is immediately before the second match) must be placed
        in the second match's before_context, not the first match's
        after_context.

        File layout (--context 1):
          line 4   context before match@5
          line 5   match
          line 6   context after match@5
          line 9   context before match@10
          line 10  match
          line 11  context after match@10
        """
        output = "\n".join([
            _context(4, "line4\n"),
            _match(5, "line5\n"),
            _context(6, "line6\n"),
            _context(9, "line9\n"),   # should become before_context of match@10
            _match(10, "line10\n"),
            _context(11, "line11\n"),
        ])

        searcher = _make_searcher()
        results = searcher._parse_ripgrep_output(output)

        assert len(results) == 2

        match5, match10 = results[0], results[1]

        # match@5
        assert match5.line == 5
        assert match5.before_context == ["line4\n"], (
            "match@5 before_context should be ['line4\\n']"
        )
        assert match5.after_context == ["line6\n"], (
            "match@5 after_context must NOT include line9 "
            "(that belongs to match@10's before_context)"
        )

        # match@10
        assert match10.line == 10
        assert match10.before_context == ["line9\n"], (
            "match@10 before_context should be ['line9\\n'], not empty"
        )
        assert match10.after_context == ["line11\n"]

    def test_adjacent_matches_shared_context_line(self):
        """
        When two matches are adjacent (e.g. lines 5 and 7 with --context 1),
        the shared context line (line 6) appears once in the output.
        It should be treated as after-context of match@5 AND/OR before-context
        of match@7 — the important thing is it is not duplicated or lost.

        File layout:
          line 4   context before match@5
          line 5   match
          line 6   shared context (after match@5 / before match@7)
          line 7   match
          line 8   context after match@7
        """
        output = "\n".join([
            _context(4, "line4\n"),
            _match(5, "line5\n"),
            _context(6, "line6\n"),   # shared
            _match(7, "line7\n"),
            _context(8, "line8\n"),
        ])

        searcher = _make_searcher()
        results = searcher._parse_ripgrep_output(output)

        assert len(results) == 2

        match5, match7 = results[0], results[1]

        # line 6 must appear exactly once across both results
        all_context_lines = (
            match5.before_context
            + match5.after_context
            + match7.before_context
            + match7.after_context
        )
        assert all_context_lines.count("line6\n") == 1, (
            "shared context line should appear exactly once across both matches"
        )

        # match@5 should have its before_context
        assert match5.before_context == ["line4\n"]
        # match@7 should have its after_context
        assert match7.after_context == ["line8\n"]

    def test_single_match_no_context(self):
        """Single match with no surrounding context lines."""
        output = _match(3, "target\n")

        searcher = _make_searcher()
        results = searcher._parse_ripgrep_output(output)

        assert len(results) == 1
        assert results[0].before_context == []
        assert results[0].after_context == []

    def test_empty_output_returns_empty_list(self):
        searcher = _make_searcher()
        results = searcher._parse_ripgrep_output("")
        assert results == []

    def test_three_matches_each_context_attributed_correctly(self):
        """
        Three matches spread across a file; each must carry the correct
        before_context and after_context.
        """
        output = "\n".join([
            _context(1, "c1\n"),
            _match(2, "m2\n"),
            _context(3, "c3\n"),
            _context(9, "c9\n"),
            _match(10, "m10\n"),
            _context(11, "c11\n"),
            _context(19, "c19\n"),
            _match(20, "m20\n"),
            _context(21, "c21\n"),
        ])

        searcher = _make_searcher()
        results = searcher._parse_ripgrep_output(output)

        assert len(results) == 3

        assert results[0].before_context == ["c1\n"]
        assert results[0].after_context  == ["c3\n"]

        assert results[1].before_context == ["c9\n"]
        assert results[1].after_context  == ["c11\n"]

        assert results[2].before_context == ["c19\n"]
        assert results[2].after_context  == ["c21\n"]
