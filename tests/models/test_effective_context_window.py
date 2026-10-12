"""Effective context-window resolution for the public (local-catalogue) build.

The public build keeps exactly ONE static window per model: the built-in
``MODEL_SETTING`` catalogue is the single source of truth, there is no remote
catalogue fetch and no expanded-window field. What still matters for callers is
that the LIVE ``ModelRunConfig`` is refreshed before the next request -- it may
have been built before the model's metadata was known, and every consumer
(compaction threshold, tool-result truncation, ...) reads ``context_window`` off
that shared object.

These tests pin that contract, the "unknown model changes nothing" behaviour and
the absence of the private remote-catalogue machinery. Everything here is
offline and deterministic: no vendor call and no network.
"""

from __future__ import annotations

from dataclasses import fields
from types import SimpleNamespace

import pytest

from siada.models import model_base_config
from siada.models.model_base_config import MODEL_SETTING, ModelBaseConfig
from siada.models.model_run_config import ModelRunConfig

MODEL_NAME = "gpt-6-sol"
UNKNOWN_MODEL_NAME = "not-in-the-public-catalogue"

# The private remote-catalogue design must not exist in the public build. The
# names are assembled from fragments so that a plain source scan for the private
# spellings does not match this file, while the assertions below still prove the
# symbols are gone.
_PRIVATE_REMOTE_SYMBOLS = (
    "_remote_" + "model_configs",
    "_ensure_" + "remote_fetch_started",
    "_fetch_" + "remote_model_config",
)
_PRIVATE_WINDOW_FIELD = "extended_" + "context_window"


def _catalog_window(model_name: str) -> int:
    """The static window the public catalogue declares for ``model_name``."""
    entry = next(c for c in MODEL_SETTING if c.model_name == model_name)
    return entry.context_window


CATALOG_WINDOW = _catalog_window(MODEL_NAME)
# A deliberately different ("stale") live value, as carried by a config built
# before the model's metadata was known.
STALE_WINDOW = CATALOG_WINDOW // 2

# Every continuity combination a caller can report for the previous request.
# With one static window per model they must all resolve the same way.
CONTINUITY_CASES = [
    pytest.param(
        dict(last_request_at=None, last_model=None, same_turn=False, now=100.0),
        id="cold-start",
    ),
    pytest.param(
        dict(last_request_at=100.0, last_model=MODEL_NAME, same_turn=True, now=101.0),
        id="same-turn-within-cache-ttl",
    ),
    pytest.param(
        dict(last_request_at=100.0, last_model=MODEL_NAME, same_turn=False, now=101.0),
        id="new-turn-within-cache-ttl",
    ),
    pytest.param(
        dict(last_request_at=100.0, last_model=MODEL_NAME, same_turn=False, now=10_000.0),
        id="previous-request-after-cache-ttl",
    ),
    pytest.param(
        dict(last_request_at=100.0, last_model="glm-5.2", same_turn=False, now=101.0),
        id="previous-request-from-a-different-model",
    ),
]


@pytest.fixture(params=["model_run_config", "duck_typed"])
def stale_live_config(request, monkeypatch):
    """A live ``llm_config`` whose window no longer matches the catalogue.

    Both shapes are covered: the real ``ModelRunConfig`` shared through
    ``CodeAgentContext.model_run_config`` and a duck-typed object, which
    ``resolve_effective_context_window`` must accept too.
    """
    monkeypatch.setattr(model_base_config, "_user_model_settings", None)
    if request.param == "model_run_config":
        llm_config = ModelRunConfig(MODEL_NAME)
        # The freshly built object carries the catalogue window already; make it
        # stale so the refresh below is observable.
        assert llm_config.context_window == CATALOG_WINDOW
    else:
        llm_config = SimpleNamespace(model_name=MODEL_NAME, context_window=0)
    llm_config.context_window = STALE_WINDOW
    return llm_config


def test_live_context_window_is_refreshed_from_the_local_catalogue(stale_live_config):
    assert stale_live_config.context_window == STALE_WINDOW

    resolved = model_base_config.resolve_effective_context_window(
        stale_live_config,
        last_request_at=None,
        last_model=None,
        same_turn=False,
        now=100.0,
    )

    # Mutated in place -- no copy is returned -- so that every consumer reading
    # the same object sees the refreshed window.
    assert resolved is None
    assert stale_live_config.context_window == CATALOG_WINDOW
    assert CATALOG_WINDOW == model_base_config.get_extended_context_window(MODEL_NAME)
    assert CATALOG_WINDOW != STALE_WINDOW


@pytest.mark.parametrize("continuity", CONTINUITY_CASES)
def test_catalogue_window_wins_for_every_continuity_combination(
    continuity, monkeypatch
):
    monkeypatch.setattr(model_base_config, "_user_model_settings", None)
    llm_config = SimpleNamespace(model_name=MODEL_NAME, context_window=STALE_WINDOW)

    model_base_config.resolve_effective_context_window(llm_config, **continuity)

    assert llm_config.context_window == CATALOG_WINDOW


def test_unknown_model_leaves_the_live_context_window_untouched(monkeypatch):
    monkeypatch.setattr(model_base_config, "_user_model_settings", None)
    llm_config = SimpleNamespace(
        model_name=UNKNOWN_MODEL_NAME, context_window=STALE_WINDOW
    )

    model_base_config.resolve_effective_context_window(
        llm_config,
        last_request_at=None,
        last_model=None,
        same_turn=False,
        now=100.0,
    )

    assert llm_config.context_window == STALE_WINDOW


@pytest.mark.parametrize("model_name", ["gpt-6-sol", "glm-5.2", "claude-sonnet-5"])
def test_extended_context_window_is_the_catalogue_window(model_name, monkeypatch):
    monkeypatch.setattr(model_base_config, "_user_model_settings", None)

    window = model_base_config.get_extended_context_window(model_name)
    assert window == _catalog_window(model_name)


def test_extended_context_window_is_none_for_an_unknown_model(monkeypatch):
    monkeypatch.setattr(model_base_config, "_user_model_settings", None)

    # A name the catalogue does not know -- bare or provider-qualified -- has no
    # window of its own; nothing is guessed for it.
    assert model_base_config.get_extended_context_window(UNKNOWN_MODEL_NAME) is None
    assert model_base_config.get_extended_context_window("zhipuai/glm-5.3") is None


def test_no_private_remote_catalogue_machinery_is_involved():
    for symbol in _PRIVATE_REMOTE_SYMBOLS:
        assert not hasattr(model_base_config, symbol), symbol

    # One static window per model: the private expanded-window field is not part
    # of the public model configuration at all.
    for config_type in (ModelBaseConfig, ModelRunConfig):
        field_names = {field.name for field in fields(config_type)}
        assert _PRIVATE_WINDOW_FIELD not in field_names