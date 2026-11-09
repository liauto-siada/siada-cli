"""Side-question budgets follow the admitted protocol without changing replay items."""

import copy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from siada.agent_hub.context_filter import utils
from siada.provider.gemini import counting
from siada.provider.token_counting import TokenCountingInfo
from siada.services.side_question import _prepare_btw_snapshot


@pytest.mark.parametrize("protocol", ["chat", "responses", "gemini"])
@pytest.mark.parametrize("oversized", [False, True])
def test_snapshot_budget_and_trim_use_runtime_protocol(monkeypatch, protocol, oversized):
    info = TokenCountingInfo("opaque-wire-alias", protocol)
    context = SimpleNamespace(
        model_run_config=SimpleNamespace(model_name="google/gemini-3.5-flash", context_window=100),
        runtime_session=SimpleNamespace(token_counting_info=info),
    )
    items = [
        {"role": "user", "content": "old task"},
        {"id": "old-answer", "type": "message", "role": "assistant", "status": "completed",
         "content": [{"type": "output_text", "text": "old answer", "annotations": []}]},
        {"role": "user", "content": "latest task"},
        {"id": "latest-answer", "type": "message", "role": "assistant", "status": "completed",
         "content": [{"type": "output_text", "text": "latest answer", "annotations": []}],
         "provider_data": {"synthetic": {"signature": "text-signature"}}},
        {"type": "function_call", "call_id": "latest-call", "name": "lookup", "arguments": "{}",
         "provider_data": {"synthetic": {"signature": "tool-signature"}}},
        {"type": "function_call_output", "call_id": "latest-call", "output": "result"},
    ]
    original = copy.deepcopy(items)
    counts = [100, 100, 20] if oversized else [20]
    chat_counter = Mock(side_effect=counts)
    native_counter = Mock(side_effect=counts)
    monkeypatch.setattr(utils, "_calculate_tokens", chat_counter)
    monkeypatch.setattr(counting, "estimate_input_tokens", native_counter)

    result = _prepare_btw_snapshot(items, context)

    assert items == original
    assert result == (original[2:] if oversized else original)
    if protocol == "gemini":
        chat_counter.assert_not_called()
        assert native_counter.call_count == len(counts)
    else:
        native_counter.assert_not_called()
        assert chat_counter.call_count == len(counts)
        assert all(call.args[0] == info.model_name for call in chat_counter.call_args_list)
