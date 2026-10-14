from pathlib import Path

import pytest
from openhands_aci.editor.exceptions import ToolError

from siada.tools.coder.siada_editor import SiadaEditor


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
@pytest.mark.parametrize("argument_newline", ["\n", "\r\n"])
@pytest.mark.parametrize("trailing_newline", [False, True])
def test_replace_preserves_file_newlines(
    tmp_path: Path, newline: str, argument_newline: str, trailing_newline: bool
):
    path = tmp_path / "sample.txt"
    original = newline.join(["header", "first", "second", "footer"])
    if trailing_newline:
        original += newline
    path.write_bytes(original.encode())
    editor = SiadaEditor()

    result = editor(
        command="str_replace",
        path=str(path),
        old_str=argument_newline.join(["first", "second"]),
        new_str=argument_newline.join(["changed", "added", "line"]),
    )

    expected = original.replace(
        newline.join(["first", "second"]), newline.join(["changed", "added", "line"])
    )
    assert path.read_bytes() == expected.encode()
    assert result.old_content == original
    assert result.new_content == expected
    assert "\r" not in result.output
    editor(command="undo_edit", path=str(path))
    assert path.read_bytes() == original.encode()


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
@pytest.mark.parametrize("argument_newline", ["\n", "\r\n"])
@pytest.mark.parametrize("insert_line", [0, 1, 2])
def test_insert_preserves_newlines_and_file_identity(
    tmp_path: Path, newline: str, argument_newline: str, insert_line: int
):
    path = tmp_path / "sample.txt"
    original = f"first{newline}last{newline}"
    path.write_bytes(original.encode())
    inode = path.stat().st_ino
    path.chmod(0o640)
    editor = SiadaEditor()

    result = editor(
        command="insert",
        path=str(path),
        insert_line=insert_line,
        new_str=f"added{argument_newline}line",
    )

    lines = original.splitlines(keepends=True)
    lines.insert(insert_line, f"added{newline}line{newline}")
    expected = "".join(lines)
    assert path.read_bytes() == expected.encode()
    assert path.stat().st_ino == inode
    assert path.stat().st_mode & 0o777 == 0o640
    assert result.old_content == original
    assert result.new_content == expected
    editor(command="undo_edit", path=str(path))
    assert path.read_bytes() == original.encode()


def test_insert_after_unterminated_line(tmp_path: Path):
    path = tmp_path / "sample.txt"
    path.write_bytes(b"first\r\nlast")
    editor = SiadaEditor()
    editor(command="insert", path=str(path), insert_line=2, new_str="added")
    assert path.read_bytes() == b"first\r\nlast\r\nadded\r\n"
    editor(command="undo_edit", path=str(path))
    assert path.read_bytes() == b"first\r\nlast"


@pytest.mark.parametrize("command", ["str_replace", "insert"])
def test_edit_preserves_unaffected_mixed_newlines(tmp_path: Path, command: str):
    path = tmp_path / "sample.txt"
    path.write_bytes(b"first\r\ntarget\nlast\r\n")
    editor = SiadaEditor()
    if command == "str_replace":
        editor(command=command, path=str(path), old_str="target", new_str="new\nline")
        expected = b"first\r\nnew\r\nline\nlast\r\n"
    else:
        editor(command=command, path=str(path), insert_line=1, new_str="new\nline")
        expected = b"first\r\nnew\r\nline\r\ntarget\nlast\r\n"
    assert path.read_bytes() == expected


@pytest.mark.parametrize("command", ["str_replace", "insert"])
def test_failed_edit_does_not_rewrite_crlf_file(tmp_path: Path, command: str):
    path = tmp_path / "sample.txt"
    original = b"same\r\nsame\r\n"
    path.write_bytes(original)
    editor = SiadaEditor()
    with pytest.raises(ToolError):
        if command == "str_replace":
            editor(command=command, path=str(path), old_str="same", new_str="new")
        else:
            editor(command=command, path=str(path), insert_line=3, new_str="new")
    assert path.read_bytes() == original


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_create_keeps_supplied_newlines(tmp_path: Path, newline: str):
    path = tmp_path / "new.txt"
    content = f"first{newline}last{newline}"
    SiadaEditor()(command="create", path=str(path), file_text=content)
    assert path.read_bytes() == content.encode()


@pytest.mark.parametrize("command", ["str_replace", "insert"])
def test_edit_retains_detected_encoding(tmp_path: Path, monkeypatch, command: str):
    path = tmp_path / "encoded.txt"
    original = "café\r\nlast\r\n"
    path.write_bytes(original.encode("cp1252"))
    editor = SiadaEditor()
    monkeypatch.setattr(editor._encoding_manager, "get_encoding", lambda path: "cp1252")
    if command == "str_replace":
        editor(command=command, path=str(path), old_str="last", new_str="déjà\nvu")
        expected = "café\r\ndéjà\r\nvu\r\n"
    else:
        editor(command=command, path=str(path), insert_line=1, new_str="déjà\nvu")
        expected = "café\r\ndéjà\r\nvu\r\nlast\r\n"
    assert path.read_bytes() == expected.encode("cp1252")
    editor(command="undo_edit", path=str(path))
    assert path.read_bytes() == original.encode("cp1252")


def test_insert_through_symlink_preserves_link(tmp_path: Path):
    target = tmp_path / "target.txt"
    target.write_bytes(b"first\r\nlast\r\n")
    link = tmp_path / "link.txt"
    link.symlink_to(target)
    SiadaEditor()(command="insert", path=str(link), insert_line=1, new_str="added")
    assert link.is_symlink()
    assert target.read_bytes() == b"first\r\nadded\r\nlast\r\n"


def test_insert_into_empty_file_defaults_to_lf(tmp_path: Path):
    path = tmp_path / "empty.txt"
    path.touch()
    SiadaEditor()(command="insert", path=str(path), insert_line=0, new_str="first\r\nlast")
    assert path.read_bytes() == b"first\nlast\n"


def test_read_range_and_view_leave_crlf_file_untouched(tmp_path: Path):
    path = tmp_path / "sample.txt"
    original = b"first\r\nsecond\r\nlast"
    path.write_bytes(original)
    editor = SiadaEditor()
    assert editor.read_file(path, start_line=2, end_line=3) == "second\r\nlast"
    result = editor(command="view", path=str(path), view_range=[2, -1])
    assert "second" in result.output
    assert "File has 3 lines total." in result.output
    assert "\r" not in result.output
    assert path.read_bytes() == original