"""Tri-state image-input capability of a model.

``supports_images`` mirrors ``supports_extra_params``: the catalogue may
declare support (True), declare a denial (False), or leave the capability
undeclared (None). Only an explicit False may be treated as a denial, so a
provider-synthesized model that no catalogue resolves still gets its images
through to the gateway.
"""

from siada.models.model_base_config import ModelBaseConfig, supports_image_input


def test_explicit_true_declares_image_support():
    assert supports_image_input(True) is True


def test_explicit_false_is_a_denial():
    assert supports_image_input(False) is False


def test_none_stays_undeclared_not_denied():
    assert supports_image_input(None) is None


def test_builtin_field_default_declares_no_images():
    """A built-in entry that omits the field keeps its "no images" meaning."""
    config = ModelBaseConfig(model_name="some-model", context_window=1)
    assert config.supports_images is False
    assert supports_image_input(config.supports_images) is False


def test_provider_fallback_can_undeclare_image_support():
    config = ModelBaseConfig(
        model_name="some-model", context_window=1, supports_images=None
    )
    assert config.supports_images is None
    assert supports_image_input(config.supports_images) is None