import os
from pathlib import Path

from siada.tools.coder.file_search.search import RipgrepSearchResult, SearchResult
from siada.utils import DirectoryUtils


def test_ripgrep_search_result_content_truncates_and_persists(tmp_path, monkeypatch):
    # Arrange
    cwd = str(tmp_path)

    # Make truncation deterministic & easy to trigger
    monkeypatch.setenv("SIADA_TRUNCATE_TOOL_OUTPUT_THRESHOLD", "200")
    monkeypatch.setenv("SIADA_TRUNCATE_TOOL_OUTPUT_LINES", "10")

    # Force project temp dir to a deterministic location under tmp_path
    project_temp_dir = tmp_path / "project_tmp"
    project_temp_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(DirectoryUtils, "get_project_temp_dir", lambda _cwd: str(project_temp_dir))

    # Create enough results to generate long formatted output
    results = []
    for i in range(50):
        results.append(
            SearchResult(
                file_path=str(tmp_path / f"file_{i}.py"),
                line=1,
                column=1,
                match=f"match line {i}: " + ("x" * 50) + "\n",
                before_context=["before\n"],
                after_context=["after\n"],
            )
        )

    r = RipgrepSearchResult(search_results=results, cwd=cwd)

    # Act
    content = r.content

    # Assert: truncation marker exists
    assert "Tool output was too large and has been truncated." in content
    assert "... [CONTENT TRUNCATED] ..." in content

    # Assert: persisted file exists and contains full output (not truncated)
    output_files = list(Path(project_temp_dir).glob("*.output"))
    assert output_files, "Expected a persisted .output file"
    persisted = output_files[0].read_text(encoding="utf-8", errors="replace")
    assert "Tool output was too large" not in persisted
    assert "match line" in persisted

