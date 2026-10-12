"""GLM version parsing and explicit model capability configuration.

Built-in models declare their capabilities; own-key models keep the fields
supplied by the provider list or models.json without name-based inference.
"""

from types import SimpleNamespace

import pytest

from siada.models import model_base_config
from siada.models.model_base_config import (
    MODEL_SETTING,
    get_glm_version,
    get_valid_reasoning_efforts,
    is_glm_5_2_or_newer,
    is_glm_5_3_or_newer,
)


@pytest.mark.parametrize(
    "model_name, expected",
    [
        ("glm-5.3", (5, 3)),
        ("GLM-5.3", (5, 3)),
        ("glm-5.3-flash", (5, 3)),
        ("openai/glm-5.4", (5, 4)),
        ("zhipuai/glm-5.30", (5, 30)),
        ("glm-6", (6, 0)),
        ("zhipuai/glm-5.2", (5, 2)),
        ("xglm-5.3", None),
        ("chatglm3-6b", None),
        ("claude-sonnet-5", None),
        ("", None),
        (None, None),
    ],
)
def test_glm_version_parsing_is_token_bounded(model_name, expected):
    assert get_glm_version(model_name) == expected


def test_existing_glm_generation_checks_keep_their_meaning():
    assert is_glm_5_2_or_newer("glm-5.2") is True
    assert is_glm_5_3_or_newer("glm-5.2") is False
    assert is_glm_5_3_or_newer("glm-5.3-flash") is True
    # Integer-only later generations count as newer than 5.3.
    assert is_glm_5_3_or_newer("glm-6") is True
    assert get_valid_reasoning_efforts("glm-6") == ["low", "high", "max"]
    assert get_valid_reasoning_efforts("glm-5.2") == ["high", "max"]


def test_builtin_glm_5_3_entries_declare_reasoning_capabilities():
    """Built-in entries keep their explicit reasoning configuration."""
    entries = [c for c in MODEL_SETTING if is_glm_5_3_or_newer(c.model_name)]
    assert entries
    for config in entries:
        assert config.supports_extra_params == ["reasoning_effort"]
        assert config.default_reasoning_effort == "max"


def test_models_dev_unknown_glm_keeps_unspecified_capabilities(monkeypatch):
    from siada.provider import models_dev

    monkeypatch.setattr(
        models_dev,
        "get_providers_for_ui",
        lambda: [{"id": "zhipuai", "models": [
            {"id": "glm-5.10", "context": 200},
            {"id": "zhipuai/glm-5.3", "context": 200},
            {"id": "glm-5.3-flash", "context": 200},
        ]}],
    )
    configs = {
        c.model_name: c
        for c in models_dev.get_provider_model_configs("zhipuai", "glm-5.10")
    }

    # "glm-5.10" parses as a GLM-5.3-or-newer generation but has no built-in
    # entry, so its capabilities must NOT be inferred from the name.
    assert get_glm_version("glm-5.10") == (5, 10)
    assert is_glm_5_3_or_newer("glm-5.10") is True
    bare = configs["glm-5.10"]
    assert bare.context_window == 200_000
    assert bare.supports_extra_params is None
    assert bare.default_reasoning_effort is None
    assert bare.supports_vision_bridge is False
    # Nor is a provider-qualified spelling, which is never a catalogue name.
    prefixed = configs["zhipuai/glm-5.3"]
    assert prefixed.context_window == 200_000
    assert prefixed.supports_extra_params is None
    assert prefixed.default_reasoning_effort is None
    assert prefixed.supports_vision_bridge is False
    # An exact built-in match still inherits its explicit capabilities.
    builtin = next(c for c in MODEL_SETTING if c.model_name == "glm-5.3-flash")
    assert builtin.supports_extra_params == ["reasoning_effort"]
    assert builtin.default_reasoning_effort == "max"
    inherited = configs["glm-5.3-flash"]
    assert inherited.supports_extra_params == builtin.supports_extra_params
    assert inherited.default_reasoning_effort == "max"
    assert inherited.supports_images is builtin.supports_images


def test_models_json_entries_keep_unspecified_and_explicit_fields(monkeypatch):
    from siada.config.model_config import UserModelConfig
    from siada.entrypoint.helpers import model_setup

    captured = {}
    # Synthetic endpoint so the default-provider validation passes offline.
    monkeypatch.setenv("BASE_URL", "http://127.0.0.1:9/v1")
    monkeypatch.setenv("API_KEY", "test-key")
    monkeypatch.setattr(model_base_config, "_user_model_settings", None)
    import siada.entrypoint as entrypoint
    # get_config records the resolved provider globally; restore it after.
    monkeypatch.setattr(entrypoint, "_CURRENT_PROVIDER", getattr(entrypoint, "_CURRENT_PROVIDER", ""))
    original_setter = model_base_config.set_user_model_settings

    def capture(models):
        captured["models"] = models
        original_setter(models)

    monkeypatch.setattr(model_base_config, "set_user_model_settings", capture)
    conf = SimpleNamespace(
        llm_config=SimpleNamespace(
            model="glm-5.3",
            provider="default",
            reasoning_effort=None,
            enable_thinking=None,
            thinking=None,
            parallel_tool_calls=None,
        ),
        model_config=SimpleNamespace(
            default_model=None,
            models=[
                UserModelConfig.from_dict({"model_name": "glm-5.3", "context_window": 200_000}),
                UserModelConfig.from_dict({
                    "model_name": "glm-5.4",
                    "context_window": 200_000,
                    "supports_extra_params": ["thinking_tokens"],
                    "default_reasoning_effort": "high",
                }),
            ],
        ),
    )
    args = SimpleNamespace(
        model=None,
        provider=None,
        verbose=False,
        reasoning_effort=None,
        thinking=None,
        parallel_tool_calls=None,
    )
    io = SimpleNamespace(print_info=lambda *_: None, print_error=lambda *_: None)

    run_config = model_setup.get_config(args, io, conf=conf)

    models = {m.model_name: m for m in captured["models"]}
    assert models["glm-5.3"].supports_extra_params is None
    assert models["glm-5.3"].default_reasoning_effort is None
    assert models["glm-5.4"].supports_extra_params == ["thinking_tokens"]
    assert models["glm-5.4"].default_reasoning_effort == "high"
    assert run_config.model_name == "glm-5.3"
    assert run_config.reasoning_effort is None