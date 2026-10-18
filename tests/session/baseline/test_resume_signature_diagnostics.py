"""Stable prompt rebuilds and content-free, response-calibrated diagnostics."""

import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from agents import Agent

from siada.agent_hub.context_filter import request_token_estimator as estimator
from siada.agent_hub.context_filter import utils
from siada.services.rule_memory import bfs_search, discovery


def test_rule_reads_keep_hierarchical_order_even_when_completion_is_reversed(tmp_path, monkeypatch):
    paths = [str(tmp_path / name) for name in ("global.md", "project.md", "child.md")]
    for path in paths:
        Path(path).write_text(Path(path).stem, encoding="utf-8")
    loader = discovery.ContextDiscovery(str(tmp_path))
    monkeypatch.setattr(loader, "discover_all_files", lambda: ([paths[0]], [paths[1]], [paths[1], paths[2]]))
    monkeypatch.setattr(discovery, "as_completed", lambda futures: reversed(list(futures)))

    assert loader._read_files_concurrent(paths) == [(path, Path(path).stem) for path in paths]
    combined, count, actual = loader.load_and_process_files(process_imports=False)
    assert actual == paths and count == 3
    assert combined.index("global") < combined.index("project") < combined.index("child")


def test_rule_read_failure_keeps_its_original_slot(tmp_path, monkeypatch):
    loader = discovery.ContextDiscovery(str(tmp_path))
    paths = ["first", "failed", "last"]

    def read(path):
        if path == "failed":
            raise OSError("synthetic read failure")
        return path, path

    monkeypatch.setattr(loader, "_read_file_content", read)
    monkeypatch.setattr(discovery, "as_completed", lambda futures: reversed(list(futures)))
    assert loader._read_files_concurrent(paths) == [("first", "first"), ("failed", ""), ("last", "last")]


@pytest.mark.parametrize("multi", [False, True])
def test_rule_bfs_has_stable_directory_and_filename_priority(tmp_path, monkeypatch, multi):
    names = ["z-rule.md", "a-rule.md", "z-rule.md"]
    for directory in ("z-child", "a-child"):
        child = tmp_path / directory
        child.mkdir()
        for name in set(names):
            (child / name).write_text("synthetic", encoding="utf-8")
    listdir = os.listdir
    monkeypatch.setattr(bfs_search.os, "listdir", lambda path: list(reversed(sorted(listdir(path)))))
    search = bfs_search.BFSFileSearch(respect_gitignore=False, respect_siadaignore=False, max_dirs=2)
    actual = search.search_multiple_names(str(tmp_path), names) if multi else search.search(str(tmp_path), names[0])
    expected_names = names[:2] if multi else names[:1]
    assert actual == [str(tmp_path / "a-child" / name) for name in expected_names]


def _request():
    context = SimpleNamespace(
        session_id="synthetic", provider="default", bound_session_id="synthetic",
        runtime_session=SimpleNamespace(_restore_generation=0, request_identity="synthetic:request:0"),
        model_run_config=SimpleNamespace(model_name="glm-test"),
        session=SimpleNamespace(session_id="synthetic", state=SimpleNamespace(
            openai_session=SimpleNamespace(session_id="synthetic"), context_token_baseline=None,
        )),
    )
    return context, Agent(name="synthetic", model="glm-test")


@pytest.mark.parametrize("block", ["core", "skills", "agents", "memory", "tools", "domain", "output"])
def test_saved_components_identify_real_changes_without_allowing_reuse(monkeypatch, caplog, block):
    from agents import function_tool
    from pydantic import BaseModel
    from agents.usage import Usage

    context, agent = _request()
    logger = logging.getLogger(__name__)
    monkeypatch.setattr(estimator, "logger", logger)
    caplog.set_level(logging.DEBUG, logger=logger.name)
    instructions = "# Intro\nprivate core\n# Skills\nprivate skills\n# AGENT TYPES\nprivate agents\n# Combined Memory\nprivate memory"
    components = {}
    signature = estimator.request_token_signature(context, agent, instructions, components=components)
    items = [{"role": "user", "content": "private history"}]
    usage = Usage(requests=1, input_tokens=900, output_tokens=100, total_tokens=1000)
    anchor = estimator.RequestTokenBaseline.from_response(
        signature, items, usage, session_id="synthetic", signature_components=components,
    )
    payload = anchor.to_dict()
    snapshot = {"items": items, "restore_generation": 0}
    context.session.state.context_token_baseline = estimator.RequestTokenBaseline.from_dict(
        payload, snapshot, usage, session_id="synthetic",
    )
    assert context.session.state.context_token_baseline.signature_components == components
    assert "private" not in json.dumps(payload)
    if block in ("core", "skills", "agents", "memory"):
        instructions = instructions.replace(f"private {block}", f"changed private {block}")
    elif block == "tools":
        @function_tool
        def synthetic_tool() -> str:
            """Return synthetic data."""
            return "ok"
        agent.tools = [synthetic_tool]
    elif block == "domain":
        context.provider = "changed-provider"
    else:
        class Output(BaseModel):
            value: str
        agent.output_type = Output
    monkeypatch.setattr(estimator, "calculate_tokens", Mock(return_value=10))
    caplog.clear()
    assert estimator.estimate_request_tokens(context, agent, items, instructions) == 20
    assert context.session.state.context_token_baseline is None
    changed = next(record.getMessage() for record in caplog.records if "status=mismatch" in record.getMessage())
    expected = f"instructions_{block}" if block in ("core", "skills", "agents", "memory") else block
    assert expected in changed.split("changed_components=")[1].split(",")
    assert "reason=signature_mismatch" in caplog.text and "private" not in caplog.text

    # Old v4 anchors still restore without the new optional diagnostic field.
    payload.pop("signature_components")
    restored = estimator.RequestTokenBaseline.from_dict(payload, snapshot, usage, session_id="synthetic")
    assert restored is not None and restored.signature_components is None
    payload["signature_components"] = {"instructions": "private invalid digest"}
    restored = estimator.RequestTokenBaseline.from_dict(payload, snapshot, usage, session_id="synthetic")
    assert restored is not None and restored.signature_components is None


def test_budget_logs_split_raw_headroom_and_provenance(monkeypatch, caplog):
    from agents.usage import Usage

    context, agent = _request()
    logger = logging.getLogger(__name__)
    monkeypatch.setattr(estimator, "logger", logger)
    caplog.set_level(logging.INFO, logger=logger.name)
    counter = Mock(side_effect=[200, 10, 25])
    monkeypatch.setattr(utils, "_calculate_tokens", counter)
    items = [{"role": "user", "content": "private history"}]
    assert estimator.estimate_request_tokens(context, agent, items, "# private instructions") == 231
    assert "raw_tokens=210 safety_tokens=21 budget_tokens=231" in caplog.text
    assert "tokenizer_source=litellm:openai/glm-test:tiktoken:cl100k_base" in caplog.text
    context.session.state.context_token_baseline = estimator.RequestTokenBaseline.from_response(
        estimator.request_token_signature(context, agent, "# private instructions"), items,
        Usage(requests=1, input_tokens=900, output_tokens=100, total_tokens=1000), session_id="synthetic",
    )
    caplog.clear()
    delta = [{"role": "user", "content": "private delta"}]
    assert estimator.estimate_request_tokens(context, agent, items + delta, "# private instructions") == 1027
    assert "raw_tokens=1025 safety_tokens=2 budget_tokens=1027" in caplog.text
    assert "tokenizer_source=server_usage+litellm:openai/glm-test:tiktoken:cl100k_base" in caplog.text
    assert counter.call_count == 3 and counter.call_args.args == ("glm-test", delta)
    caplog.clear()
    assert estimator.estimate_request_tokens(context, agent, items, "# private instructions") == 1000
    assert "raw_tokens=1000 safety_tokens=0 budget_tokens=1000 tokenizer_source=server_usage+none" in caplog.text
    assert "private" not in caplog.text


@pytest.mark.parametrize("value", ["synthetic text" * 10, [{"role": "user", "content": "synthetic" * 10}]])
def test_char_fallback_keeps_existing_margin_and_reports_source(monkeypatch, value):
    monkeypatch.setattr(utils, "_calculate_tokens", Mock(side_effect=RuntimeError("private failure")))
    diagnostics = {}
    expected = int((len(value) // 4) * 1.1) if isinstance(value, str) else utils.estimate_tokens(value)
    assert utils.calculate_tokens("glm-test", value, diagnostics=diagnostics) == expected
    assert diagnostics["raw_tokens"] + diagnostics["safety_tokens"] == expected
    assert diagnostics["tokenizer_source"].startswith("char_fallback:")


def test_encoding_diagnostic_failure_does_not_change_budget(monkeypatch):
    from litellm.litellm_core_utils import token_counter

    monkeypatch.setattr(utils, "_calculate_tokens", Mock(return_value=100))
    monkeypatch.setattr(token_counter, "_get_count_function", Mock(side_effect=RuntimeError("private failure")))
    diagnostics = {}
    assert utils.calculate_tokens("glm-test", "synthetic", diagnostics=diagnostics) == 110
    assert diagnostics == {"raw_tokens": 100, "safety_tokens": 10, "budget_tokens": 110,
                           "tokenizer_source": "litellm:openai/glm-test:encoding_unavailable"}


@pytest.mark.parametrize("model_name", ["glm-5.1", "bailian-glm-5.3"])
def test_real_glm_prompt_rebuild_reuses_persisted_anchor_across_processes(tmp_path, model_name):
    program = r'''
import json, socket, sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from agents import Agent
from agents.usage import Usage
from siada.services.rule_memory import discovery
from siada.services.memory.combined_memory import build_combined_memory
from siada.agent_hub.coder.prompt import code_gen_prompt
from siada.agent_hub.context_filter import request_token_estimator as estimator, utils

def deny(*args, **kwargs):
    raise AssertionError("Network is prohibited")
socket.socket.connect = socket.socket.connect_ex = socket.create_connection = deny
root = Path(sys.argv[1])
model_name = sys.argv[3]
effective_model = model_name.removeprefix("bailian-")
workspace = root / "workspace"
workspace.mkdir(exist_ok=True)
global_rules = root / "global"
global_rules.mkdir(exist_ok=True)
for directory, text in ((global_rules, "# Global\nsynthetic global rule"), (workspace, "# Project\nsynthetic project rule")):
    (directory / "siada_rule.md").write_text(text, encoding="utf-8")
discovery.get_rule_config = lambda: SimpleNamespace(
    config_dir=str(global_rules), get_file_names=lambda: ["siada_rule.md"], get_enable_subdirectories=lambda: False,
    get_import_format=lambda: "flat",
)
# Force the two independent builds to finish reads in opposite orders.
if sys.argv[2] == "resume":
    discovery.as_completed = lambda futures: reversed(list(futures))
code_gen_prompt.get_username = lambda: None
code_gen_prompt.get_skills_section = lambda *args, **kwargs: "## Skills\nsynthetic stable catalog"
code_gen_prompt.get_agents_section = lambda *args: "# AGENT TYPES\nsynthetic stable agents"
instructions = code_gen_prompt.get_system_prompt(
    str(workspace), model_name=model_name, preferred_language="zh-CN",
    user_memory=build_combined_memory(str(workspace), None, None),
)
context = SimpleNamespace(
    session_id="synthetic", bound_session_id="synthetic", provider="default",
    runtime_session=SimpleNamespace(_restore_generation=0), model_run_config=SimpleNamespace(model_name=model_name),
    session=SimpleNamespace(session_id="synthetic", state=SimpleNamespace(
        openai_session=SimpleNamespace(session_id="synthetic"), context_token_baseline=None)),
)
agent = Agent(name="synthetic", model=effective_model)
components = {}
signature = estimator.request_token_signature(context, agent, instructions, components=components)
items = [{"role": "user", "content": "synthetic history"}, {"role": "assistant", "content": "synthetic answer"}]
usage = Usage(requests=1, input_tokens=503531, output_tokens=1682, total_tokens=505213)
path = root / "anchor.json"
if sys.argv[2] == "save":
    anchor = estimator.RequestTokenBaseline.from_response(signature, items, usage, session_id="synthetic", signature_components=components)
    path.write_text(json.dumps(anchor.to_dict()), encoding="utf-8")
    print(json.dumps({"signature": signature}))
else:
    context.session.state.context_token_baseline = estimator.RequestTokenBaseline.from_dict(
        json.loads(path.read_text()), {"items": items, "restore_generation": 0}, usage, session_id="synthetic")
    assert context.session.state.context_token_baseline is not None
    delta = [{"role": "user", "content": "continue"}]
    counter = Mock(return_value=100)
    utils._calculate_tokens = counter
    budget = estimator.estimate_request_tokens(context, agent, items + delta, instructions)
    assert counter.call_count == 1 and counter.call_args.args[1] == delta
    print(json.dumps({"signature": signature, "budget_tokens": budget}))
'''
    environment = {**os.environ, "HOME": str(tmp_path), "USERPROFILE": str(tmp_path),
                   "SIADA_CLI_LOG_DIR": str(tmp_path / "logs"), "SIADA_REMOTE_MODEL_CONFIG": "0",
                   "LITELLM_LOCAL_MODEL_COST_MAP": "True", "XDG_CACHE_HOME": str(tmp_path / "cache")}
    results = []
    for mode, seed in (("save", "1"), ("resume", "2")):
        result = subprocess.run([sys.executable, "-c", program, str(tmp_path), mode, model_name],
                                env={**environment, "PYTHONHASHSEED": seed}, capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stderr
        results.append(json.loads(result.stdout))
    assert results[0]["signature"] == results[1]["signature"]
    assert results[1]["budget_tokens"] == 505_323