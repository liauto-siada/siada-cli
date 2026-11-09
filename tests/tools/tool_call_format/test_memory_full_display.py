"""Terminal tool details retain full arguments for expanded views."""

import json

import pytest

from siada.tools.tool_call_format.formatters import (
    FactFeedbackFormatter,
    FactStoreFormatter,
    MemoryWriteFormatter,
    SearchMemoryFormatter,
    SmartSearchMemoryFormatter,
)


@pytest.mark.parametrize(
    ("formatter", "function", "args", "prefix"),
    [
        (MemoryWriteFormatter, "memory", {"action": "add", "target": "memory"}, "Save to memory [add/memory]: "),
        (SearchMemoryFormatter, "search_memory", {}, "Searching memory: "),
        (SmartSearchMemoryFormatter, "smart_search_memory", {}, "Searching memory: "),
        (FactStoreFormatter, "fact_store", {"action": "search"}, "Fact memory [search] "),
        (FactStoreFormatter, "fact_store", {"action": "add"}, "Fact memory [add] "),
        (FactStoreFormatter, "fact_store", {"action": "update", "fact_id": 7}, "Fact memory [update] #7 "),
        (FactFeedbackFormatter, "fact_feedback", {"action": "correct", "fact_id": 7}, "Fact feedback #7 correct: "),
    ],
)
def test_full_multiline_terminal_arguments(formatter, function, args, prefix):
    text = "first line\n" + "中文长内容" * 30 + "\nFINAL_ARGUMENT_TAIL"
    field = "comment" if function == "fact_feedback" else (
        "content" if function == "memory" or args.get("action") in ("add", "update")
        else "query"
    )
    content, complete = formatter().format_input(
        "synthetic", function, json.dumps({**args, field: text})
    )
    assert complete
    assert content == prefix + text