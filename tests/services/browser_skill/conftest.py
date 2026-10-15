"""Browser learning tests never call real models or use personal skill data."""

import pytest

from siada.services.browser_skill import distiller, llm_utils, matcher, paths


@pytest.fixture(autouse=True)
def browser_test_boundaries(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "SIADA_HOME", tmp_path)

    async def forbidden_model(*args, **kwargs):
        pytest.fail("A browser-skill test attempted an unmocked model call")

    for module in (distiller, llm_utils, matcher):
        monkeypatch.setattr(module, "call_fast_llm", forbidden_model)
