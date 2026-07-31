"""Tests for the image-support guard in PendingUserInputInjector.

Covers the TUI mid-turn injection path: when the bound model does not
support images, image-only messages (no text) are rejected with an error
printed to the frontend, and text+image messages have their images stripped.
"""

import asyncio
from unittest.mock import MagicMock, patch
from types import SimpleNamespace

import pytest

from siada.agent_hub.context_filter.pending_user_input_filter import (
    PendingUserInputInjector,
    _print_image_not_supported_error,
)


# ── Helpers ──────────────────────────────────────────────────────────


def _make_context(supports_images: bool):
    """Build a minimal CodeAgentContext-like mock for the filter."""
    llm_config = SimpleNamespace(supports_images=supports_images)
    siada_config = SimpleNamespace(llm_config=llm_config)
    session = SimpleNamespace(
        siada_config=siada_config,
        openai_session=None,
    )
    context = SimpleNamespace(session=session)
    return context


def _make_model_data():
    """Build a minimal ModelInputData-like mock."""
    return SimpleNamespace(input=[])


def _drain_side_effect(items):
    """Return a side-effect function for drain_pending_injections."""
    def _fn():
        return list(items)
    return _fn


# ── Tests: model does NOT support images ─────────────────────────────


class TestImageNotSupportedGuard:
    """When the model cannot process images."""

    @pytest.mark.asyncio
    async def test_image_only_no_text_rejected(self):
        """Image-only mid-turn message (no text) is rejected, not injected."""
        context = _make_context(supports_images=False)
        model_data = _make_model_data()

        pending = [(None, "", ["/tmp/img1.png"])]
        with patch(
            "siada.io.stdin_interrupt_monitor.drain_pending_injections",
            side_effect=_drain_side_effect(pending),
        ), patch(
            "siada.io.stdin_interrupt_monitor._send_queue_notification"
        ), patch(
            "siada.agent_hub.context_filter.pending_user_input_filter._print_image_not_supported_error"
        ) as mock_print_err:
            injector = PendingUserInputInjector()
            await injector.filter(model_data, MagicMock(), context)

        # Error was printed
        mock_print_err.assert_called_once()
        # Nothing was injected into model_data.input
        assert model_data.input == []

    @pytest.mark.asyncio
    async def test_text_plus_images_images_stripped(self):
        """Text+image message has images stripped, text is kept."""
        context = _make_context(supports_images=False)
        model_data = _make_model_data()

        pending = [("id1", "hello world", ["/tmp/img1.png", "/tmp/img2.jpg"])]
        with patch(
            "siada.io.stdin_interrupt_monitor.drain_pending_injections",
            side_effect=_drain_side_effect(pending),
        ), patch(
            "siada.io.stdin_interrupt_monitor._send_queue_notification"
        ), patch(
            "siada.agent_hub.context_filter.pending_user_input_filter._print_image_not_supported_error"
        ) as mock_print_err:
            injector = PendingUserInputInjector()
            await injector.filter(model_data, MagicMock(), context)

        # Error was NOT printed (there is text)
        mock_print_err.assert_not_called()
        # Text was injected as a plain user message (no image content)
        assert len(model_data.input) == 1
        assert model_data.input[0]["role"] == "user"
        assert model_data.input[0]["content"] == "hello world"

    @pytest.mark.asyncio
    async def test_whitespace_only_text_with_images_rejected(self):
        """Whitespace-only text + images is treated as image-only and rejected."""
        context = _make_context(supports_images=False)
        model_data = _make_model_data()

        pending = [("id1", "   \n  ", ["/tmp/img1.png"])]
        with patch(
            "siada.io.stdin_interrupt_monitor.drain_pending_injections",
            side_effect=_drain_side_effect(pending),
        ), patch(
            "siada.io.stdin_interrupt_monitor._send_queue_notification"
        ), patch(
            "siada.agent_hub.context_filter.pending_user_input_filter._print_image_not_supported_error"
        ) as mock_print_err:
            injector = PendingUserInputInjector()
            await injector.filter(model_data, MagicMock(), context)

        # Error was printed (whitespace-only is not meaningful text)
        mock_print_err.assert_called_once()
        # Nothing was injected
        assert model_data.input == []

    @pytest.mark.asyncio
    async def test_image_placeholder_only_rejected(self):
        """Frontend placeholder '[Image #1]' + images is treated as image-only."""
        context = _make_context(supports_images=False)
        model_data = _make_model_data()

        pending = [("id1", "[Image #1]", ["/tmp/img1.png"])]
        with patch(
            "siada.io.stdin_interrupt_monitor.drain_pending_injections",
            side_effect=_drain_side_effect(pending),
        ), patch(
            "siada.io.stdin_interrupt_monitor._send_queue_notification"
        ), patch(
            "siada.agent_hub.context_filter.pending_user_input_filter._print_image_not_supported_error"
        ) as mock_print_err:
            injector = PendingUserInputInjector()
            await injector.filter(model_data, MagicMock(), context)

        # Error was printed ([Image #1] is a placeholder, not real text)
        mock_print_err.assert_called_once()
        # Nothing was injected
        assert model_data.input == []

    @pytest.mark.asyncio
    async def test_real_text_with_image_placeholder_images_stripped(self):
        """Real text + '[Image #1]' placeholder + images → images stripped, text kept."""
        context = _make_context(supports_images=False)
        model_data = _make_model_data()

        pending = [("id1", "What is this? [Image #1]", ["/tmp/img1.png"])]
        with patch(
            "siada.io.stdin_interrupt_monitor.drain_pending_injections",
            side_effect=_drain_side_effect(pending),
        ), patch(
            "siada.io.stdin_interrupt_monitor._send_queue_notification"
        ), patch(
            "siada.agent_hub.context_filter.pending_user_input_filter._print_image_not_supported_error"
        ) as mock_print_err:
            injector = PendingUserInputInjector()
            await injector.filter(model_data, MagicMock(), context)

        # Error was NOT printed (there is real text)
        mock_print_err.assert_not_called()
        # Text was injected as a plain user message (no image content)
        assert len(model_data.input) == 1
        assert model_data.input[0]["role"] == "user"
        assert model_data.input[0]["content"] == "What is this? [Image #1]"


# ── Tests: model DOES support images ─────────────────────────────────


class TestImageSupported:
    """When the model can process images — normal multimodal path."""

    @pytest.mark.asyncio
    async def test_text_plus_images_multimodal(self):
        """Text+image message is built as multimodal input."""
        context = _make_context(supports_images=True)
        model_data = _make_model_data()

        pending = [("id1", "describe this", ["/tmp/img1.png"])]
        with patch(
            "siada.io.stdin_interrupt_monitor.drain_pending_injections",
            side_effect=_drain_side_effect(pending),
        ), patch(
            "siada.io.stdin_interrupt_monitor._send_queue_notification"
        ), patch(
            "siada.agent_hub.context_filter.pending_user_input_filter._print_image_not_supported_error"
        ) as mock_print_err, patch(
            "siada.entrypoint.interaction.turn.conversation_turn._build_multimodal_input"
        ) as mock_build:
            # Return a recognizable structure
            mock_build.return_value = [{"role": "user", "content": [{"type": "input_text", "text": "describe this"}, {"type": "input_image", "image_url": "data:image/png;base64,xxx"}]}]
            injector = PendingUserInputInjector()
            await injector.filter(model_data, MagicMock(), context)

        # Error was NOT printed
        mock_print_err.assert_not_called()
        # Multimodal builder was called
        mock_build.assert_called_once_with("describe this", ["/tmp/img1.png"])
        # Injected
        assert len(model_data.input) == 1

    @pytest.mark.asyncio
    async def test_image_only_no_text_still_injected(self):
        """When model supports images, image-only (no text) is still injected."""
        context = _make_context(supports_images=True)
        model_data = _make_model_data()

        pending = [("id1", "", ["/tmp/img1.png"])]
        with patch(
            "siada.io.stdin_interrupt_monitor.drain_pending_injections",
            side_effect=_drain_side_effect(pending),
        ), patch(
            "siada.io.stdin_interrupt_monitor._send_queue_notification"
        ), patch(
            "siada.agent_hub.context_filter.pending_user_input_filter._print_image_not_supported_error"
        ) as mock_print_err, patch(
            "siada.entrypoint.interaction.turn.conversation_turn._build_multimodal_input"
        ) as mock_build:
            mock_build.return_value = [{"role": "user", "content": [{"type": "input_image", "image_url": "data:image/png;base64,xxx"}]}]
            injector = PendingUserInputInjector()
            await injector.filter(model_data, MagicMock(), context)

        # Error was NOT printed
        mock_print_err.assert_not_called()
        # Multimodal builder was called with empty text
        mock_build.assert_called_once_with("", ["/tmp/img1.png"])
        assert len(model_data.input) == 1


# ── Tests: error helper ──────────────────────────────────────────────


class TestPrintImageNotSupportedError:
    """Test the _print_image_not_supported_error helper."""

    def test_prints_when_io_available(self):
        """Error is printed via the IO singleton when available."""
        mock_io = MagicMock()
        with patch("siada.io.io.InputOutput.get_instance", return_value=mock_io):
            _print_image_not_supported_error()

        mock_io.print_error.assert_called_once()
        call_args = mock_io.print_error.call_args[0][0]
        assert "does not support image input" in call_args

    def test_no_error_when_io_unavailable(self):
        """No exception when IO singleton is None."""
        with patch("siada.io.io.InputOutput.get_instance", return_value=None):
            # Should not raise
            _print_image_not_supported_error()

    def test_swallows_unexpected_exception(self):
        """Unexpected exceptions are swallowed (best-effort)."""
        with patch(
            "siada.io.io.InputOutput.get_instance",
            side_effect=RuntimeError("boom"),
        ):
            # Should not raise
            _print_image_not_supported_error()
