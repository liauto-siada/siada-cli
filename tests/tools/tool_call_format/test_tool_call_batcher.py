from siada.tools.tool_call_format.tool_call_batcher import classify_tool


def test_read_file_is_classified_as_file_read():
    assert classify_tool("read_file", '{"path":"src"}') == "file_read"


def test_edit_file_view_remains_classified_as_file_read():
    assert classify_tool("edit_file", '{"command":"view","path":"src"}') == "file_read"


def test_edit_file_write_remains_classified_as_file_write():
    assert classify_tool("edit_file", '{"command":"create","path":"src/new.py"}') == "file_write"