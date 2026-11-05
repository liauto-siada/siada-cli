"""Image-input gating in ConversationTurn._resolve_image_input.

``supports_images`` is tri-state (see
``siada.models.model_base_config.supports_image_input``): only an explicit
``False`` strips or rejects attached images. An undeclared ``None`` — what the
provider-catalogue fallback synthesizes for an id no catalogue resolves — sends
them and lets the gateway judge, instead of denying outright.
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from siada.entrypoint.interaction.turn.conversation_turn import ConversationTurn
from siada.entrypoint.interaction.turn.interface import ImageNotSupportedError
from siada.services import vision_bridge


def _make_turn(supports_images, supports_bridge=False):
    turn = ConversationTurn.__new__(ConversationTurn)
    turn.config = SimpleNamespace(
        io=SimpleNamespace(_pending_image_paths=None),
        llm_config=SimpleNamespace(
            supports_images=supports_images,
            supports_vision_bridge=supports_bridge,
        ),
    )
    return turn


def _png(tmp_path, name="probe.png"):
    path = tmp_path / name
    path.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    return str(path)


def test_declared_support_sends_the_image(tmp_path):
    turn = _make_turn(supports_images=True)

    result = turn._resolve_image_input("hello", [_png(tmp_path)])

    assert isinstance(result, list)
    assert result[0]["content"][1]["type"] == "input_image"


def test_undeclared_support_sends_the_image(tmp_path):
    """None = undeclared, so the image reaches the model instead of being stripped."""
    turn = _make_turn(supports_images=None)

    result = turn._resolve_image_input("hello [Image #1]", [_png(tmp_path)])

    assert isinstance(result, list)
    content = result[0]["content"]
    assert content[0] == {"type": "input_text", "text": "hello [Image #1]"}
    assert content[1]["type"] == "input_image"
    assert content[1]["image_url"].startswith("data:image/png;base64,")


def test_undeclared_support_never_calls_the_bridge(tmp_path):
    """Only an explicit denial is routed through the vision bridge."""
    turn = _make_turn(supports_images=None)

    with patch.object(vision_bridge, "transcribe_images_sync") as mock_sync:
        turn._resolve_image_input("hello [Image #1]", [_png(tmp_path)])

    mock_sync.assert_not_called()


def test_explicitly_unsupported_strips_the_image():
    """False stays a denial: the images go, the text survives."""
    turn = _make_turn(supports_images=False)

    result = turn._resolve_image_input("hello [Image #1]", ["/tmp/does-not-exist.png"])

    assert result == "hello [Image #1]"


def test_explicitly_unsupported_image_only_raises():
    turn = _make_turn(supports_images=False)

    with pytest.raises(ImageNotSupportedError):
        turn._resolve_image_input("[Image #1]", ["/tmp/does-not-exist.png"])


def test_bridge_model_transcribes_instead_of_sending(tmp_path):
    """A bridge model (text-only + engine) gets text evidence, not the image."""
    turn = _make_turn(supports_images=False, supports_bridge=True)
    transcriptions = [("/tmp/img.png", "the image shows a red square")]

    with patch.object(
        vision_bridge, "transcribe_images_sync", return_value=transcriptions
    ):
        result = turn._resolve_image_input("what color? [Image #1]", [_png(tmp_path)])

    assert isinstance(result, str)
    assert "what color?" in result
    assert "the image shows a red square" in result