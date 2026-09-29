"""Unit tests for ``siada.services.siada_memory``.

``load_siada_memory`` reads the recognised workspace context files
(SIADA.md / AGENTS.md / CLAUDE.md / .claude/CLAUDE.md) and combines their
bodies into a single string for the system prompt. The contract verified
here:

1. Every file body is prefixed with a ``# <relative path>`` heading so
   file boundaries stay visible in the combined output.
2. Files are concatenated in ``WORKSPACE_MEMORY_FILES`` priority order.
3. Deduplication by basename: a project-root ``CLAUDE.md`` shadows
   ``.claude/CLAUDE.md``.
4. ``.claude/CLAUDE.md`` is used when no root-level ``CLAUDE.md`` exists,
   and its heading reflects the real relative path.
5. Empty files are skipped; ``None`` is returned when nothing contributes.
6. A file whose body is >=90% similar to an already-loaded,
   higher-priority file is skipped (users often copy CLAUDE.md /
   AGENTS.md into SIADA.md), and ``refresh_siada_memory`` reports the
   skip instead of a spurious "loaded" checkmark.
"""

from siada.services.siada_memory import (
    _NEAR_DUPLICATE_THRESHOLD,
    _text_similarity,
    load_siada_memory,
    refresh_siada_memory,
)


def test_single_file_gets_heading(tmp_path):
    (tmp_path / "SIADA.md").write_text("prefer poetry for runs", encoding="utf-8")
    out = load_siada_memory(str(tmp_path))
    assert out == "# SIADA.md\n\nprefer poetry for runs"


def test_multiple_files_each_carry_heading_in_priority_order(tmp_path):
    # Written in reverse priority order on purpose: the output order must
    # follow WORKSPACE_MEMORY_FILES, not filesystem or creation order.
    (tmp_path / "CLAUDE.md").write_text("claude body", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("agents body", encoding="utf-8")
    (tmp_path / "SIADA.md").write_text("siada body", encoding="utf-8")
    out = load_siada_memory(str(tmp_path))
    assert out == (
        "# SIADA.md\n\nsiada body\n\n"
        "# AGENTS.md\n\nagents body\n\n"
        "# CLAUDE.md\n\nclaude body"
    )


def test_root_claude_md_shadows_dot_claude_dir(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("root body", encoding="utf-8")
    dot_claude = tmp_path / ".claude"
    dot_claude.mkdir()
    (dot_claude / "CLAUDE.md").write_text("nested body", encoding="utf-8")
    out = load_siada_memory(str(tmp_path))
    assert out == "# CLAUDE.md\n\nroot body"


def test_dot_claude_fallback_heading_shows_real_path(tmp_path):
    dot_claude = tmp_path / ".claude"
    dot_claude.mkdir()
    (dot_claude / "CLAUDE.md").write_text("nested body", encoding="utf-8")
    out = load_siada_memory(str(tmp_path))
    assert out == "# .claude/CLAUDE.md\n\nnested body"


def test_empty_files_are_skipped(tmp_path):
    (tmp_path / "SIADA.md").write_text("", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("   \n  ", encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text("claude body", encoding="utf-8")
    out = load_siada_memory(str(tmp_path))
    assert out == "# CLAUDE.md\n\nclaude body"


def test_returns_none_when_nothing_exists(tmp_path):
    assert load_siada_memory(str(tmp_path)) is None


def test_returns_none_when_all_files_empty(tmp_path):
    (tmp_path / "AGENTS.md").write_text("  \n", encoding="utf-8")
    assert load_siada_memory(str(tmp_path)) is None


# ---------------------------------------------------------------------------
# Near-duplicate dedup
# ---------------------------------------------------------------------------


def _near_identical_pair() -> tuple:
    """Two texts ~99% similar: a five-character edit in ~1000 chars of rules."""
    lines = [f"rule {i:02d}: keep the build green and the diffs small" for i in range(20)]
    tweaked = list(lines)
    tweaked[7] = "rule 07: keep the build green and the diffs tidy."
    return "\n".join(lines), "\n".join(tweaked)


def test_text_similarity_scores():
    assert _text_similarity("identical body", "identical body") == 1.0
    assert _text_similarity("", "non-empty") == 0.0
    assert (
        _text_similarity("completely different", "nothing alike here")
        < _NEAR_DUPLICATE_THRESHOLD
    )


def test_identical_claude_md_is_skipped(tmp_path):
    body = "# Rules\n\nprefer poetry for runs\nuse four-space indent\n"
    (tmp_path / "SIADA.md").write_text(body, encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text(body, encoding="utf-8")
    out = load_siada_memory(str(tmp_path))
    assert out == f"# SIADA.md\n\n{body.strip()}"


def test_near_identical_agents_md_is_skipped(tmp_path):
    base, tweaked = _near_identical_pair()
    (tmp_path / "SIADA.md").write_text(base, encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text(tweaked, encoding="utf-8")
    out = load_siada_memory(str(tmp_path))
    assert out == f"# SIADA.md\n\n{base}"


def test_partially_overlapping_file_is_still_loaded(tmp_path):
    # ~50% overlap — below the threshold, so both files must ship.
    shared = "\n".join(f"shared rule {i}" for i in range(10))
    siada_body = shared + "\n" + "\n".join(f"siada-only rule {i}" for i in range(10))
    claude_body = shared + "\n" + "\n".join(f"claude-only rule {i}" for i in range(10))
    (tmp_path / "SIADA.md").write_text(siada_body, encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text(claude_body, encoding="utf-8")
    out = load_siada_memory(str(tmp_path))
    assert f"# SIADA.md\n\n{siada_body}" in out
    assert f"# CLAUDE.md\n\n{claude_body}" in out


def test_claude_md_copy_of_agents_md_is_skipped(tmp_path):
    # The near-dup reference is any already-loaded file, not just SIADA.md:
    # with SIADA.md absent, a CLAUDE.md copied from AGENTS.md is dropped.
    body = "# Shared\n\nsame instructions everywhere\n"
    (tmp_path / "AGENTS.md").write_text(body, encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text(body, encoding="utf-8")
    out = load_siada_memory(str(tmp_path))
    assert out == f"# AGENTS.md\n\n{body.strip()}"


def test_skipped_root_claude_md_still_shadows_dot_claude(tmp_path):
    # A similarity-skipped file keeps its basename claim (same semantics
    # as empty files), so .claude/CLAUDE.md stays shadowed.
    body = "# Rules\n\nidentical content\n"
    (tmp_path / "SIADA.md").write_text(body, encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text(body, encoding="utf-8")
    dot_claude = tmp_path / ".claude"
    dot_claude.mkdir()
    (dot_claude / "CLAUDE.md").write_text("unique nested content", encoding="utf-8")
    out = load_siada_memory(str(tmp_path))
    assert out == f"# SIADA.md\n\n{body.strip()}"


def test_refresh_reports_near_duplicate_skip(tmp_path):
    body = "# Rules\n\nprefer poetry for runs\n"
    (tmp_path / "SIADA.md").write_text(body, encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text(body, encoding="utf-8")
    _, status = refresh_siada_memory(str(tmp_path))
    assert "✓ SIADA.md" in status
    assert "~ CLAUDE.md" in status
    assert "similar to SIADA.md" in status


def test_large_near_duplicate_is_skipped(tmp_path):
    # Bodies above _CHAR_COMPARE_LIMIT (~15KB here) force the line-level
    # comparison path; a one-line tweak in a copied file must still be
    # detected, and in milliseconds rather than seconds.
    lines = [f"rule {i:03d}: keep the build green and the diffs small" for i in range(300)]
    base = "\n".join(lines)
    tweaked_lines = list(lines)
    tweaked_lines[150] = "rule 150: keep the build green and the diffs tidy.."
    tweaked = "\n".join(tweaked_lines)
    (tmp_path / "SIADA.md").write_text(base, encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text(tweaked, encoding="utf-8")
    out = load_siada_memory(str(tmp_path))
    assert out == f"# SIADA.md\n\n{base}"


def test_large_dissimilar_files_are_all_loaded(tmp_path):
    # Same size and shape, disjoint line content — the line-level upper
    # bound must bail out fast and report "not a duplicate".
    siada_body = "\n".join(f"alpha rule {i:03d}: {'a' * 40}" for i in range(300))
    claude_body = "\n".join(f"beta rule {i:03d}: {'b' * 40}" for i in range(300))
    (tmp_path / "SIADA.md").write_text(siada_body, encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text(claude_body, encoding="utf-8")
    out = load_siada_memory(str(tmp_path))
    assert f"# SIADA.md\n\n{siada_body}" in out
    assert f"# CLAUDE.md\n\n{claude_body}" in out
