"""Durable response anchors must remain bound to usage and authoritative context."""

import copy
import logging
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from agents import Agent, ModelSettings, function_tool, handoff
from agents.agent_output import AgentOutputSchema
from agents.tool import ComputerTool, FileSearchTool
from agents.usage import InputTokensDetails, OutputTokensDetails, Usage
from pydantic import BaseModel, create_model

from siada.agent_hub.context_filter import request_token_estimator as estimator
from siada.provider.reasoning_replay import should_replay_reasoning_content
from siada.provider.responses import ResponsesModel
from siada.provider import token_counting
from siada.provider.token_counting import token_counting_info_from_model
from siada.services.input_processor import process_input
from siada.services.model_wrapper import ModelWrapper
from siada.session.session_models import SessionState


@pytest.fixture(autouse=True)
def budget_logs(monkeypatch, caplog):
    logger = logging.getLogger(__name__)
    caplog.set_level(logging.DEBUG, logger=logger.name)
    monkeypatch.setattr(estimator, "logger", logger)


@pytest.fixture
def token_request():
    state = SessionState()
    state.openai_session = SimpleNamespace(session_id="synthetic-session")
    context = SimpleNamespace(
        session=SimpleNamespace(state=state, session_id="synthetic-session"),
        session_id="synthetic-session", bound_session_id="synthetic-session", provider="default",
        runtime_session=SimpleNamespace(_restore_generation=0, token_counting_info=None, token_budget_model_settings=None),
        model_run_config=SimpleNamespace(model_name="glm-test", provider=None, enable_thinking=None,
                                        reasoning_effort=None, thinking_tokens=None, extra_params=None),
    )
    agent = Agent(name="synthetic", model="glm-test", instructions="# Test")
    items = [{"role": "user", "content": "old request"}, {"role": "assistant", "content": "old reply"}]
    signature = estimator.request_token_signature(context, agent, "# Test")
    state.context_token_baseline = estimator.RequestTokenBaseline.from_response(
        signature, items, Usage(requests=1, input_tokens=900, output_tokens=100, total_tokens=1000),
        session_id=context.session_id,
    )
    return context, agent, items


@pytest.mark.parametrize("source", ["runtime_session", "agent_model"])
@pytest.mark.parametrize("native", [False, True])
def test_signature_logs_counting_info_source_and_protocol(token_request, caplog, source, native):
    context, agent, _ = token_request
    model = SimpleNamespace(model="glm-test", supports_native_responses_items=native)
    info = token_counting_info_from_model(model)
    if source == "runtime_session":
        context.runtime_session.token_counting_info = info
    else:
        agent.model = model
    context.runtime_session.request_identity = "synthetic-request:request:0"
    caplog.clear()

    assert estimator.request_token_signature(context, agent, "# Synthetic sensitive instructions") is not None

    records = [record for record in caplog.records if "status=route_selected" in record.getMessage()]
    assert len(records) == 1
    record = records[0]
    assert record.levelno == logging.DEBUG
    message = record.getMessage()
    assert "session=synthetic-session request=synthetic-request:request:0" in message
    assert f"provider=default source={source} protocol={info.protocol} native={native}" in message
    assert f"info={info}" in message
    assert "Synthetic sensitive instructions" not in caplog.text


def test_unavailable_signature_still_logs_selected_counting_info(token_request, caplog):
    context, agent, _ = token_request
    info = token_counting.TokenCountingInfo("glm-test", unavailable_reason="opaque_processor")
    context.runtime_session.token_counting_info = info
    caplog.clear()

    assert estimator.request_token_signature(context, agent, "# Synthetic sensitive instructions") is None

    assert "status=route_selected" in caplog.text
    assert f"info={info}" in caplog.text
    assert "status=unavailable reason=opaque_processor" in caplog.text
    assert "Synthetic sensitive instructions" not in caplog.text


def test_incremental_counts_only_post_response_additions_without_tools_or_instructions(token_request, monkeypatch, caplog):
    context, agent, items = token_request
    delta = [{"role": "user", "content": "continue"}]
    counter = Mock(return_value=25)
    monkeypatch.setattr(estimator, "calculate_tokens", counter)
    assert estimator.estimate_request_tokens(context, agent, items + delta, "# Test") == 1025
    counter.assert_called_once_with("glm-test", delta, diagnostics={})
    assert context.session.state.usage is None
    assert context.session.state.context_token_baseline.input_tokens == 900
    assert context.session.state.context_token_baseline.response_tokens == 100
    assert "token_mode=delta_only" in caplog.text
    assert "baseline_source=server_usage" in caplog.text
    assert "baseline_count=2 input_tokens=900 response_tokens=100 baseline_tokens=1000" in caplog.text
    assert "delta_count=1 delta_tokens=25 total=1025" in caplog.text
    assert "old request" not in caplog.text and "continue" not in caplog.text


def test_unchanged_input_and_retry_do_not_recount_or_accumulate(token_request, monkeypatch):
    context, agent, items = token_request
    counter = Mock(return_value=25)
    monkeypatch.setattr(estimator, "calculate_tokens", counter)
    assert estimator.estimate_request_tokens(context, agent, items, "# Test") == 1000
    counter.assert_not_called()
    extended = items + [{"role": "user", "content": "retry"}]
    assert estimator.estimate_request_tokens(context, agent, extended, "# Test") == 1025
    assert estimator.estimate_request_tokens(context, agent, extended, "# Test") == 1025


@pytest.mark.parametrize("change", ["no_baseline", "restore", "storage", "session", "bound_session", "owner",
                                  "model", "provider", "instructions", "tools", "run_model", "prefix", "shorter"])
def test_invalid_anchor_falls_back_to_full_count(token_request, monkeypatch, caplog, change):
    context, agent, items = token_request
    signature = context.session.state.context_token_baseline.signature
    items = copy.deepcopy(items)
    instructions = "# Test"
    if change == "no_baseline":
        context.session.state.context_token_baseline = None
    elif change == "restore":
        context.runtime_session._restore_generation += 1
    elif change == "storage":
        context.session.state.openai_session = SimpleNamespace(session_id="replaced-session")
    elif change == "session":
        context.session.session_id = "replaced-session"
    elif change == "bound_session":
        context.bound_session_id = "replaced-session"
    elif change == "owner":
        context.session_id = "replaced-session"
    elif change == "model":
        agent.model = "kimi-test"
    elif change == "provider":
        context.provider = "li"
    elif change == "instructions":
        instructions = "# Changed"
    elif change == "tools":
        @function_tool
        def synthetic_tool() -> str:
            """Return a deterministic result."""
            return "ok"
        agent.tools = [synthetic_tool]
    elif change == "run_model":
        context.runtime_session.token_counting_info = token_counting_info_from_model("different-model")
    elif change == "prefix":
        items[0]["content"] = "rewritten prefix with unchanged last item"
    elif change == "shorter":
        items = items[-1:]
    if change in ("restore", "storage", "session", "bound_session", "owner"):
        assert estimator.request_token_signature(context, agent, instructions) == signature
    counter = Mock(side_effect=[300, 10])
    monkeypatch.setattr(estimator, "calculate_tokens", counter)
    assert estimator.estimate_request_tokens(context, agent, items, instructions) == 310
    model_name = estimator.request_token_model_name(context, agent)
    assert counter.call_args_list[0].args == (model_name, items)
    assert counter.call_args_list[0].kwargs == {"tools": agent.tools, "diagnostics": {}}
    assert counter.call_args_list[1].args == (model_name, instructions)
    assert context.session.state.context_token_baseline is None
    reasons = {
        "no_baseline": "no_baseline", "restore": "restore_generation_mismatch",
        "storage": "session_owner_mismatch", "session": "session_owner_mismatch",
        "bound_session": "session_owner_mismatch", "owner": "session_owner_mismatch",
        "prefix": "prefix_rewritten", "shorter": "prefix_shortened",
    }
    assert f"token_mode=recount_all reason={reasons.get(change, 'signature_mismatch')}" in caplog.text


@pytest.mark.parametrize("input_tokens", [600, 900])
@pytest.mark.parametrize("output_tokens", [0, 100])
def test_cache_is_included_once_for_li_and_default_chat(input_tokens, output_tokens):
    usage = Usage(requests=1, input_tokens=input_tokens, output_tokens=output_tokens, total_tokens=900 + output_tokens,
                  input_tokens_details=InputTokensDetails(cached_tokens=300, cache_write_tokens=0))
    baseline = estimator.RequestTokenBaseline.from_response("signature", [], usage, session_id="synthetic-session")
    assert baseline.input_tokens == 900
    assert baseline.response_tokens == output_tokens
    assert baseline.context_tokens == usage.total_tokens


@pytest.mark.parametrize("usage", [None, Usage(requests=1), Usage(requests=2, input_tokens=20),
                                  Usage(requests=1, input_tokens=-1), Usage(requests=1, output_tokens=-1)])
def test_absent_or_invalid_usage_cannot_seed_anchor(usage):
    assert estimator.RequestTokenBaseline.from_response("signature", [], usage, session_id="synthetic-session") is None


def test_baseline_owns_an_immutable_request_snapshot(token_request):
    context, _, items = token_request
    items[0]["content"] = "mutated by caller"
    assert context.session.state.context_token_baseline.items[0]["content"] == "old request"


def test_compact_anchor_round_trip_uses_authoritative_prefix(token_request):
    import json

    context, _, items = token_request
    baseline = context.session.state.context_token_baseline
    data = json.loads(json.dumps(baseline.to_dict()))
    usage = Usage(requests=1, input_tokens=900, output_tokens=100, total_tokens=1000)
    snapshot = {"items": items + [{"role": "user", "content": "new input"}], "restore_generation": 0}
    restored = estimator.RequestTokenBaseline.from_dict(data, snapshot, usage, session_id=context.session_id)
    assert restored == baseline
    assert restored.items is not items
    assert "items" not in data
    assert "old request" not in json.dumps(data)
    assert data["format_version"] == 4
    assert data["session_id"] == context.session_id


@pytest.mark.parametrize("damage", ["version", "old_version", "old_response_version", "old_estimated_response_version",
                                  "count", "tokens", "response_tokens", "response_usage_mismatch",
                                  "missing_response_tokens", "signature", "digest", "generation", "prefix", "usage",
                                  "owner", "missing_owner", "snapshot_owner"])
def test_invalid_durable_anchor_is_not_recovered(token_request, damage):
    context, _, items = token_request
    data = context.session.state.context_token_baseline.to_dict()
    snapshot = {"items": copy.deepcopy(items), "restore_generation": 0}
    usage = Usage(requests=1, input_tokens=900, output_tokens=100, total_tokens=1000)
    if damage == "version":
        data["format_version"] = True
    elif damage == "old_version":
        data["format_version"] = 1
    elif damage == "old_response_version":
        data["format_version"] = 2
    elif damage == "old_estimated_response_version":
        data["format_version"] = 3
    elif damage == "count":
        data["item_count"] = len(items) + 1
    elif damage == "tokens":
        data["input_tokens"] = 901
    elif damage == "response_tokens":
        data["response_tokens"] = -1
    elif damage == "response_usage_mismatch":
        data["response_tokens"] = 25
    elif damage == "missing_response_tokens":
        data.pop("response_tokens")
    elif damage == "signature":
        data["signature"] = "malformed"
    elif damage == "digest":
        data["prefix_signature"] = "0" * 32
    elif damage == "generation":
        snapshot["restore_generation"] = 1
    elif damage == "prefix":
        snapshot["items"][0]["content"] = "rewritten"
    elif damage == "usage":
        usage = None
    elif damage == "owner":
        data["session_id"] = "another-session"
    elif damage == "missing_owner":
        data.pop("session_id")
    elif damage == "snapshot_owner":
        snapshot["session_id"] = "another-session"
    assert estimator.RequestTokenBaseline.from_dict(data, snapshot, usage, session_id=context.session_id) is None


@pytest.mark.parametrize("native", [False, True])
def test_server_total_includes_reasoning_and_only_new_input_is_estimated(token_request, monkeypatch, native):
    context, agent, items = token_request
    context.runtime_session.token_counting_info = token_counting_info_from_model(
        SimpleNamespace(model="glm-test", supports_native_responses_items=native),
    )
    signature = estimator.request_token_signature(context, agent, "# Test")
    usage = Usage(requests=1, input_tokens=900, output_tokens=6000, total_tokens=6900,
                  output_tokens_details=OutputTokensDetails(reasoning_tokens=5900))
    context.session.state.context_token_baseline = estimator.RequestTokenBaseline.from_response(
        signature, items, usage, session_id=context.session_id,
    )
    counter = Mock()
    monkeypatch.setattr(estimator, "calculate_tokens", counter)
    assert estimator.estimate_request_tokens(context, agent, items, "# Test") == 6900
    counter.assert_not_called()
    delta = [{"role": "user", "content": "continue"}]
    counter.return_value = 25
    assert estimator.estimate_request_tokens(context, agent, items + delta, "# Test") == 6925
    counter.assert_called_once_with("glm-test", delta, diagnostics={})


@pytest.mark.parametrize("field", ["input_tokens", "output_tokens", "total_tokens"])
@pytest.mark.parametrize("tokens", [None, True, -1, 1.5])
def test_invalid_server_token_counts_cannot_seed_anchor(field, tokens):
    usage = SimpleNamespace(requests=1, input_tokens=900, output_tokens=100, total_tokens=1000)
    setattr(usage, field, tokens)
    assert estimator.RequestTokenBaseline.from_response(
        "signature", [], usage, session_id="synthetic-session",
    ) is None


@pytest.mark.parametrize("total_tokens", [100, 999])
def test_inconsistent_server_total_cannot_seed_anchor(total_tokens):
    usage = Usage(requests=1, input_tokens=900, output_tokens=100, total_tokens=total_tokens)
    assert estimator.RequestTokenBaseline.from_response(
        "signature", [], usage, session_id="synthetic-session",
    ) is None


def test_signature_survives_fresh_storage_model_and_processor_objects(token_request):
    from tests.session.baseline.conftest import ScriptedModel

    context, agent, _ = token_request

    def create_model():
        return ModelWrapper(ScriptedModel(context.session.state.openai_session, []), input_processor=process_input)

    agent.model = create_model()
    original = estimator.request_token_signature(context, agent, "# Test")
    assert original is not None
    context.session.state.openai_session = SimpleNamespace(session_id="synthetic-session")
    agent.model = create_model()
    assert estimator.request_token_signature(context, agent, "# Test") == original


@pytest.mark.parametrize("location", ["agent", "run"])
@pytest.mark.parametrize("settings", [
    {"temperature": 0.5}, {"top_p": 0.8}, {"max_tokens": 2048},
    {"frequency_penalty": 0.2}, {"presence_penalty": 0.3},
    {"extra_args": {"seed": 42}},
    {"extra_body": {"reasoning": {"effort": "high"}, "enable_thinking": True, "preserve_thinking": True}},
])
def test_output_only_settings_keep_delta_estimation(token_request, monkeypatch, location, settings):
    context, agent, items = token_request
    baseline = context.session.state.context_token_baseline
    if location == "agent":
        agent.model_settings = ModelSettings(**settings)
    else:
        context.runtime_session.token_budget_model_settings = ModelSettings(**settings)
    assert estimator.request_token_signature(context, agent, "# Test") == baseline.signature
    counter = Mock(return_value=25)
    monkeypatch.setattr(estimator, "calculate_tokens", counter)
    delta = [{"role": "user", "content": "continue"}]
    assert estimator.estimate_request_tokens(context, agent, items + delta, "# Test") == 1025
    counter.assert_called_once_with("glm-test", delta, diagnostics={})
    assert context.session.state.context_token_baseline is baseline


def test_overridden_configuration_is_not_the_effective_counting_domain(token_request, monkeypatch):
    context, agent, items = token_request
    context.model_run_config.model_name = "unused-model"
    context.model_run_config.reasoning_effort = "high"
    context.model_run_config.thinking_tokens = 4096
    context.model_run_config.extra_params = {"temperature": 0.5}
    counter = Mock()
    monkeypatch.setattr(estimator, "calculate_tokens", counter)
    assert estimator.estimate_request_tokens(context, agent, items, "# Test") == 1000
    counter.assert_not_called()


@pytest.mark.parametrize("location", ["agent", "run"])
@pytest.mark.parametrize("settings", [
    {"extra_body": {"tools": [{"type": "function", "name": "synthetic"}]}},
    {"extra_args": {"input": []}},
    {"extra_args": {"extra_body": {"model": "different-wire-model"}}},
    {"extra_body": {"instructions": "untracked instructions"}},
    {"extra_body": {"text": {"format": {"type": "json_object"}}}},
    {"context_management": [{"type": "compaction", "compact_threshold": 1000}]},
    {"truncation": "auto"},
])
def test_untracked_request_overrides_do_not_reuse_anchor(token_request, monkeypatch, caplog, location, settings):
    context, agent, items = token_request
    if location == "agent":
        agent.model_settings = ModelSettings(**settings)
    else:
        context.runtime_session.token_budget_model_settings = ModelSettings(**settings)
    assert estimator.request_token_signature(context, agent, "# Test") is None
    counter = Mock(return_value=10)
    monkeypatch.setattr(estimator, "calculate_tokens", counter)
    assert estimator.estimate_request_tokens(context, agent, items, "# Test") == 20
    assert counter.call_count == 2
    assert context.session.state.context_token_baseline is None
    assert "status=unavailable reason=request_override" in caplog.text
    assert "token_mode=recount_all reason=signature_unavailable" in caplog.text
    assert "untracked instructions" not in caplog.text


@pytest.mark.parametrize("processor", [None, process_input])
def test_fresh_noop_wrappers_keep_delta_estimation(token_request, monkeypatch, processor):
    context, agent, items = token_request
    original = context.session.state.context_token_baseline
    agent.model = ModelWrapper(ModelWrapper(SimpleNamespace(model="glm-test")), input_processor=processor)
    context.session.state.openai_session = SimpleNamespace(session_id=context.session_id)
    counter = Mock()
    monkeypatch.setattr(estimator, "calculate_tokens", counter)
    assert estimator.estimate_request_tokens(context, agent, items, "# Test") == 1000
    counter.assert_not_called()
    assert context.session.state.context_token_baseline is original


@pytest.mark.parametrize("change", ["protocol", "replay"])
def test_counting_semantics_invalidate_anchor(token_request, monkeypatch, change):
    context, agent, items = token_request
    baseline = context.session.state.context_token_baseline
    if change == "protocol":
        context.runtime_session.token_counting_info = token_counting_info_from_model(
            SimpleNamespace(model="glm-test", supports_native_responses_items=True),
        )
    else:
        monkeypatch.setattr(estimator, "_REQUEST_TOKEN_DOMAIN_VERSION", 2)
    assert estimator.request_token_signature(context, agent, "# Test") != baseline.signature
    counter = Mock(return_value=10)
    monkeypatch.setattr(estimator, "calculate_tokens", counter)
    assert estimator.estimate_request_tokens(context, agent, items, "# Test") == 20
    assert counter.call_count == 2


def synthetic_tool():
    @function_tool
    def echo(value: str) -> str:
        """Return a deterministic synthetic result."""
        return value
    return echo


@pytest.mark.parametrize("native", [False, True])
@pytest.mark.parametrize("change", ["tool_description", "tool_parameters", "tool_strict", "tool_enabled",
                                  "handoff_description", "handoff_parameters", "handoff_strict", "handoff_enabled",
                                  "output", "output_strict"])
def test_effective_wire_schema_changes_invalidate_anchor(token_request, monkeypatch, native, change):
    context, agent, items = token_request
    context.runtime_session.token_counting_info = token_counting_info_from_model(
        SimpleNamespace(model="glm-test", supports_native_responses_items=native),
    )
    tool = synthetic_tool()
    transfer = handoff(Agent(name="synthetic-target", model="glm-test"))

    class Output(BaseModel):
        value: str

    agent.tools = [tool]
    agent.handoffs = [transfer]
    agent.output_type = Output
    signature = estimator.request_token_signature(context, agent, "# Test")
    assert signature is not None
    context.session.state.context_token_baseline = estimator.RequestTokenBaseline.from_response(
        signature, items, Usage(requests=1, input_tokens=900, output_tokens=100, total_tokens=1000),
        session_id=context.session_id,
    )
    if change == "tool_description":
        tool.description = "Changed tool description"
    elif change == "tool_parameters":
        tool.params_json_schema["properties"]["value"]["description"] = "Changed parameter schema"
    elif change == "tool_strict":
        tool.strict_json_schema = False
    elif change == "tool_enabled":
        tool.is_enabled = False
    elif change == "handoff_description":
        transfer.tool_description = "Changed handoff description"
    elif change == "handoff_parameters":
        transfer.input_json_schema["description"] = "Changed handoff schema"
    elif change == "handoff_strict":
        transfer.strict_json_schema = False
    elif change == "handoff_enabled":
        transfer.is_enabled = False
    elif change == "output":
        agent.output_type = create_model("Output", value=(int, ...))
    elif change == "output_strict":
        agent.output_type = AgentOutputSchema(Output, strict_json_schema=False)
    assert estimator.request_token_signature(context, agent, "# Test") != signature
    counter = Mock(return_value=10)
    monkeypatch.setattr(estimator, "calculate_tokens", counter)
    assert estimator.estimate_request_tokens(context, agent, items, "# Test") == 20
    assert counter.call_count == 2
    assert context.session.state.context_token_baseline is None


@pytest.mark.parametrize("native", [False, True])
def test_fresh_equivalent_schemas_and_callables_have_stable_signature(token_request, native):
    context, agent, _ = token_request
    context.runtime_session.token_counting_info = token_counting_info_from_model(
        SimpleNamespace(model="glm-test", supports_native_responses_items=native),
    )

    def signature():
        agent.tools = [synthetic_tool()]
        agent.handoffs = [Agent(name="synthetic-target", model="glm-test")]
        agent.output_type = create_model("SyntheticOutput", value=(str, ...))
        return estimator.request_token_signature(context, agent, "# Test")

    original = signature()
    assert original is not None
    assert signature() == original
    agent.tools[0].on_invoke_tool = Mock()
    assert estimator.request_token_signature(context, agent, "# Test") == original


def test_disabled_schema_is_not_part_of_effective_request(token_request):
    context, agent, _ = token_request
    original = estimator.request_token_signature(context, agent, "# Test")
    tool = synthetic_tool()
    tool.is_enabled = False
    transfer = handoff(Agent(name="synthetic-target", model="glm-test"), is_enabled=False)
    agent.tools = [tool]
    agent.handoffs = [transfer]
    assert estimator.request_token_signature(context, agent, "# Test") == original
    tool.params_json_schema["properties"]["value"]["description"] = "Disabled tool changed"
    transfer.tool_description = "Disabled handoff changed"
    assert estimator.request_token_signature(context, agent, "# Test") == original


def test_hosted_responses_tool_and_function_output_schemas_are_signed(token_request):
    context, agent, _ = token_request
    context.runtime_session.token_counting_info = token_counting_info_from_model(
        SimpleNamespace(model="synthetic-responses", supports_native_responses_items=True),
    )
    tool = FileSearchTool(vector_store_ids=["synthetic-store"], max_num_results=2)
    agent.tools = [tool]
    original = estimator.request_token_signature(context, agent, "# Test")
    assert original is not None
    tool.max_num_results = 3
    assert estimator.request_token_signature(context, agent, "# Test") != original
    function = synthetic_tool()
    agent.tools = [function]
    original = estimator.request_token_signature(context, agent, "# Test")
    function.output_json_schema = {"type": "string"}
    assert estimator.request_token_signature(context, agent, "# Test") != original


def test_responses_provider_signs_sanitized_wire_schema_not_dropped_fields(token_request):
    context, agent, _ = token_request
    context.runtime_session.token_counting_info = token_counting_info_from_model(
        ResponsesModel("gpt-6", transport=SimpleNamespace()),
    )
    tool = synthetic_tool()
    tool.params_json_schema["additionalProperties"] = {}
    transfer = handoff(Agent(name="synthetic-target"))
    agent.tools = [tool]
    agent.handoffs = [transfer]
    original = estimator.request_token_signature(context, agent, "# Test")
    assert original is not None
    tool.strict_json_schema = False
    transfer.strict_json_schema = False
    tool.params_json_schema.pop("additionalProperties")
    assert estimator.request_token_signature(context, agent, "# Test") == original
    tool.params_json_schema["properties"]["value"]["description"] = "Changed wire schema"
    assert estimator.request_token_signature(context, agent, "# Test") != original


@pytest.mark.parametrize("policy", [None, lambda context: False])
def test_untracked_reasoning_replay_policy_cannot_reuse_anchor(token_request, caplog, policy):
    context, agent, _ = token_request
    model = SimpleNamespace(model="glm-test", should_replay_reasoning_content=should_replay_reasoning_content)
    context.runtime_session.token_counting_info = token_counting_info_from_model(model)
    assert estimator.request_token_signature(context, agent, "# Test") is not None
    model.should_replay_reasoning_content = policy
    context.runtime_session.token_counting_info = token_counting_info_from_model(model)
    assert estimator.request_token_signature(context, agent, "# Test") is None
    assert "status=unavailable reason=unknown_replay_policy" in caplog.text


@pytest.mark.parametrize("unsupported", ["processor", "registered_processor", "dynamic_tool", "dynamic_handoff",
                                       "mcp", "prompt", "computer", "duplicate_tool", "duplicate_handoff",
                                       "hosted_chat_tool", "schema"])
def test_opaque_or_unresolved_inputs_fall_back_safely(token_request, monkeypatch, caplog, unsupported):
    context, agent, items = token_request
    tool = synthetic_tool()
    if unsupported == "processor":
        agent.model = ModelWrapper(SimpleNamespace(model="glm-test"), input_processor=lambda value: value)
    elif unsupported == "registered_processor":
        monkeypatch.setattr(token_counting, "PROCESSING_FUNCTIONS", [lambda value: value])
        agent.model = ModelWrapper(SimpleNamespace(model="glm-test"), input_processor=process_input)
    elif unsupported == "dynamic_tool":
        tool.is_enabled = lambda context, agent: True
        agent.tools = [tool]
    elif unsupported == "dynamic_handoff":
        agent.handoffs = [handoff(Agent(name="synthetic-target"), is_enabled=lambda context, agent: True)]
    elif unsupported == "mcp":
        agent.mcp_servers = [object()]
    elif unsupported == "prompt":
        agent.prompt = {"id": "synthetic-prompt"}
    elif unsupported == "computer":
        agent.tools = [ComputerTool(computer=Mock())]
    elif unsupported == "duplicate_tool":
        agent.tools = [tool, tool]
    elif unsupported == "duplicate_handoff":
        agent.tools = [tool]
        agent.handoffs = [handoff(Agent(name="synthetic-target"), tool_name_override=tool.name)]
    elif unsupported == "hosted_chat_tool":
        agent.tools = [FileSearchTool(vector_store_ids=["synthetic-store"])]
    elif unsupported == "schema":
        tool.params_json_schema["unsupported"] = object()
        agent.tools = [tool]
    assert estimator.request_token_signature(context, agent, "# Test") is None
    counter = Mock(return_value=10)
    monkeypatch.setattr(estimator, "calculate_tokens", counter)
    assert estimator.estimate_request_tokens(context, agent, items, "# Test") == 20
    assert counter.call_count == 2
    assert context.session.state.context_token_baseline is None
    reasons = {
        "processor": "opaque_processor", "registered_processor": "opaque_processor",
        "dynamic_tool": "dynamic_tool", "dynamic_handoff": "dynamic_handoff",
        "mcp": "mcp_tools", "prompt": "remote_prompt", "computer": "unresolved_computer_schema",
        "duplicate_tool": "duplicate_tool_name", "duplicate_handoff": "duplicate_tool_name",
        "hosted_chat_tool": "unsupported_schema", "schema": "unsupported_schema",
    }
    assert f"status=unavailable reason={reasons[unsupported]}" in caplog.text
    assert "token_mode=recount_all reason=signature_unavailable" in caplog.text


@pytest.mark.parametrize("session_id", [None, "", True])
def test_response_anchor_requires_session_owner(session_id):
    usage = Usage(requests=1, input_tokens=900, output_tokens=100, total_tokens=1000)
    assert estimator.RequestTokenBaseline.from_response("signature", [], usage, session_id=session_id) is None


def test_request_signature_matches_in_independent_processes(tmp_path):
    import os
    import subprocess
    import sys

    program = """
from types import SimpleNamespace
from agents import Agent
from siada.agent_hub.context_filter.request_token_estimator import request_token_signature
from siada.services.input_processor import process_input
from siada.provider.token_counting import token_counting_info_from_model

storage = SimpleNamespace(session_id="synthetic-session")
model = SimpleNamespace(wrapped_model=SimpleNamespace(model="glm-test"), input_processor=process_input)
context = SimpleNamespace(
    session_id="synthetic-session", session=SimpleNamespace(state=SimpleNamespace(openai_session=storage)),
    provider="default", runtime_session=SimpleNamespace(_restore_generation=0, token_counting_info=token_counting_info_from_model(model)),
    model_run_config=SimpleNamespace(model_name="glm-test", provider=None, enable_thinking=None,
                                    reasoning_effort=None, thinking_tokens=None, extra_params=None),
)
print(request_token_signature(context, Agent(name="synthetic", model="glm-test"), "# Test"))
"""
    environment = {
        **os.environ, "SIADA_REMOTE_MODEL_CONFIG": "0", "LITELLM_LOCAL_MODEL_COST_MAP": "True",
        "HOME": str(tmp_path), "USERPROFILE": str(tmp_path), "SIADA_CLI_LOG_DIR": str(tmp_path / "logs"),
        "XDG_CACHE_HOME": str(tmp_path / "cache"),
    }
    results = [
        subprocess.run(
            [sys.executable, "-c", program], check=False, capture_output=True, text=True,
            env=environment, timeout=30,
        )
        for _ in range(2)
    ]
    assert all(result.returncode == 0 for result in results), "\n".join(result.stderr for result in results)
    signatures = [result.stdout.strip() for result in results]
    assert len(signatures[0]) == 32
    assert signatures[0] == signatures[1]