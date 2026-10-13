"""Capability resolution for provider models in the models.dev catalogue.

Covers the provider-catalogue fallback used when a login provider's model is
missing from models.json (the "custom"/own-key path):

- ``_catalogue_name_candidates`` unwraps gateway ids such as
  "azure-gpt-6_1-sol" and returns candidates in match order, so an exact
  catalogue name always wins over a stripped variant;
- ``_find_builtin_model`` resolves those ids against the built-in
  ``MODEL_SETTING`` capabilities;
- ``supports_images`` stays tri-state: a resolved model inherits the
  catalogue declaration, a models.dev entry may declare it, and an id that
  nothing resolves stays UNDECLARED (None) so the image guard lets the
  gateway judge instead of denying outright.
"""

import pytest

from siada.models.model_base_config import MODEL_SETTING
from siada.provider import models_dev


def _builtin_index():
    return {m.model_name: m for m in MODEL_SETTING}


def _image_capable_builtin():
    """Any built-in entry that declares native image support.

    The catalogue differs between builds (the internal list is
    vendor-prefixed, the open-source one is not), so the tests derive the
    model under test instead of pinning an id that one build may not ship.
    """
    for model in MODEL_SETTING:
        if model.supports_images is True:
            return model
    pytest.skip("this catalogue build declares no image-capable model")


def _vendor_prefixed_builtin():
    """Any built-in whose name already starts with a gateway vendor prefix."""
    for model in MODEL_SETTING:
        if model.model_name.startswith(models_dev._GATEWAY_NAME_PREFIXES):
            return model
    return None


# ── Gateway id → catalogue name candidates ───────────────────────────


class TestCatalogueNameCandidates:
    def test_exact_name_is_tried_first(self):
        assert models_dev._catalogue_name_candidates("gpt-6.1-sol")[0] == "gpt-6.1-sol"

    def test_unwraps_vendor_prefix_and_underscore_separator(self):
        candidates = models_dev._catalogue_name_candidates("azure-gpt-6_1-sol")

        assert candidates[0] == "azure-gpt-6_1-sol"
        assert "gpt-6.1-sol" in candidates
        # The id itself must be tried before any stripped variant.
        assert candidates.index("azure-gpt-6_1-sol") < candidates.index("gpt-6.1-sol")

    def test_vendor_qualified_name_is_left_alone(self):
        """A "vendor/name" spelling is a user namespace, not a catalogue id.

        Stripping the segment would let a user-defined id silently inherit an
        unrelated built-in model's capabilities (see the contract in
        tests/models/test_glm_capability_defaults.py).
        """
        assert models_dev._catalogue_name_candidates("zhipuai/glm-5.3") == [
            "zhipuai/glm-5.3"
        ]

    def test_unknown_name_yields_only_itself(self):
        assert models_dev._catalogue_name_candidates("my-local-llm") == ["my-local-llm"]

    @pytest.mark.parametrize("name", ["", "   ", None])
    def test_blank_names_yield_no_candidates(self, name):
        assert models_dev._catalogue_name_candidates(name) == []


# ── Built-in lookup tolerates gateway ids ────────────────────────────


class TestBuiltinLookupToleratesGatewayIds:
    def test_resolves_vendor_prefixed_id(self):
        builtin = _image_capable_builtin()

        resolved = models_dev._find_builtin_model(
            "azure-" + builtin.model_name, _builtin_index()
        )

        assert resolved is not None
        assert resolved.model_name == builtin.model_name

    def test_exact_catalogue_name_wins_over_stripped_variant(self):
        """A name that is itself a catalogue entry is never rewritten."""
        builtin = _vendor_prefixed_builtin()
        if builtin is None:
            pytest.skip("this catalogue build has no vendor-prefixed name")

        resolved = models_dev._find_builtin_model(builtin.model_name, _builtin_index())

        assert resolved is not None
        assert resolved.model_name == builtin.model_name

    def test_real_world_gateway_id(self):
        """The id seen in the field: the gateway's ``azure-gpt-6_1-sol``."""
        if "gpt-6.1-sol" not in _builtin_index():
            pytest.skip("this catalogue build does not ship gpt-6.1-sol")

        resolved = models_dev._find_builtin_model("azure-gpt-6_1-sol", _builtin_index())

        assert resolved is not None
        assert resolved.model_name == "gpt-6.1-sol"

    def test_unknown_id_resolves_to_nothing(self):
        assert models_dev._find_builtin_model("my-local-llm", _builtin_index()) is None


# ── models.dev image declarations ────────────────────────────────────


class TestImageCapability:
    def test_modalities_win_over_attachment(self):
        """`attachment` also covers non-image files, so modalities is preferred."""
        assert models_dev._image_capability(
            {"attachment": False, "modalities": {"input": ["text", "image"]}}
        ) is True

    @pytest.mark.parametrize("attachment", [True, False])
    def test_attachment_used_when_modalities_absent(self, attachment):
        assert models_dev._image_capability({"attachment": attachment}) is attachment

    def test_undeclared_entry_stays_none(self):
        assert models_dev._image_capability({}) is None

    def test_curate_carries_the_image_flag(self):
        raw = {
            "openai": {
                "models": {
                    "gpt-vision": {
                        "name": "GPT Vision",
                        "tool_call": True,
                        "release_date": "2026-01-02",
                        "limit": {"context": 128_000},
                        "modalities": {"input": ["text", "image"]},
                    },
                    "gpt-declared-plain": {
                        "name": "GPT Plain",
                        "tool_call": True,
                        "release_date": "2026-01-01",
                        "limit": {"context": 128_000},
                        "attachment": False,
                    },
                }
            }
        }

        providers = {p["id"]: p for p in models_dev._curate(raw)}
        by_id = {m["id"]: m for m in providers["openai"]["models"]}

        assert by_id["gpt-vision"]["image"] is True
        assert by_id["gpt-declared-plain"]["image"] is False


# ── get_provider_model_configs fallback ──────────────────────────────


def _stub_custom_provider(monkeypatch):
    """No catalogue entry for the 'custom' provider — the id fallback runs."""
    monkeypatch.setattr(
        models_dev,
        "get_providers_for_ui",
        lambda: [{"id": "custom", "models": []}],
    )


class TestUnresolvedModelKeepsImageSupportUndeclared:
    def test_synthesized_unknown_model_is_not_denied(self, monkeypatch):
        _stub_custom_provider(monkeypatch)

        (config,) = models_dev.get_provider_model_configs("custom", "my-local-llm")

        # Undeclared, NOT False: the gateway decides.
        assert config.supports_images is None
        assert config.supports_extra_params is None
        # The vision bridge stays opt-in and must never be inferred.
        assert config.supports_vision_bridge is False


class TestGatewayIdInheritsBuiltinCapabilities:
    def test_vendor_prefixed_id_inherits_the_builtin_declaration(self, monkeypatch):
        builtin = _image_capable_builtin()
        gateway_id = "azure-" + builtin.model_name
        _stub_custom_provider(monkeypatch)

        (config,) = models_dev.get_provider_model_configs("custom", gateway_id)

        # The caller's id is preserved; only capabilities are inherited.
        assert config.model_name == gateway_id
        assert config.supports_images is True
        assert config.supports_extra_params == builtin.supports_extra_params


class TestVendorQualifiedNameIsNotACatalogueName:
    """A "vendor/name" id must never inherit a built-in entry's capabilities.

    Mirrors the contract asserted by
    tests/models/test_glm_capability_defaults.py.
    """

    def test_vendor_qualified_id_stays_undeclared(self, monkeypatch):
        monkeypatch.setattr(
            models_dev,
            "get_providers_for_ui",
            lambda: [{"id": "somevendor", "models": [
                {"id": "zhipuai/glm-5.3", "context": 200},
            ]}],
        )

        (config,) = models_dev.get_provider_model_configs("somevendor", "")

        assert config.supports_extra_params is None
        assert config.default_reasoning_effort is None
        assert config.supports_images is None
        assert config.supports_vision_bridge is False


class TestCatalogueImageDeclarationFlowsThrough:
    def _config_for(self, monkeypatch, model_entry):
        monkeypatch.setattr(
            models_dev,
            "get_providers_for_ui",
            lambda: [{"id": "somevendor", "models": [model_entry]}],
        )
        (config,) = models_dev.get_provider_model_configs("somevendor", "")
        return config

    @pytest.mark.parametrize("declared", [True, False])
    def test_declared_capability_is_used(self, monkeypatch, declared):
        config = self._config_for(
            monkeypatch,
            {"id": "unknown-vendor-model", "context": 128, "image": declared},
        )

        assert config.supports_images is declared

    def test_missing_declaration_stays_undeclared(self, monkeypatch):
        config = self._config_for(
            monkeypatch, {"id": "unknown-vendor-model", "context": 128}
        )

        assert config.supports_images is None

    def test_builtin_declaration_wins_when_it_resolves(self, monkeypatch):
        """A resolvable id keeps the built-in answer, not the cache's."""
        builtin = _image_capable_builtin()
        config = self._config_for(
            monkeypatch,
            {"id": "azure-" + builtin.model_name, "context": 128, "image": False},
        )

        assert config.supports_images is True