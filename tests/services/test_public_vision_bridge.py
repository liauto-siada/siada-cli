"""Vision engine resolution without private providers or model aliases."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from siada.services import vision_bridge


@pytest.mark.parametrize(
    "settings, expected",
    [
        ({}, None),
        ({"model": "text-model"}, None),
        ({"model": "image-model"}, ("image-model", "default")),
        (
            {"model": "text-model", "vision_model": "image-model", "provider": "custom"},
            ("image-model", "custom"),
        ),
        (
            {
                "model": "text-model",
                "vision_model": "image-model",
                "provider": "default",
                "vision_provider": "custom",
            },
            ("image-model", "custom"),
        ),
        ({"vision_model": "text-model"}, None),
        ({"vision_model": "unknown", "model": "image-model"}, ("image-model", "default")),
    ],
)
def test_configured_vision_engine(settings, expected):
    def model_config(name):
        if name == "unknown":
            return None
        return SimpleNamespace(supports_images=name == "image-model")

    with (
        patch.object(vision_bridge, "_read_user_llm_section", return_value=settings),
        patch.object(vision_bridge, "get_model_config", side_effect=model_config),
    ):
        assert vision_bridge._get_vision_engine() == expected