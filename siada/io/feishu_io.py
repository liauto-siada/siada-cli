"""LarkIO - InputOutput implementation that redirects output to relay transport.

Extends the base InputOutput to send agent responses back through the
WebSocket relay transport instead of printing to the terminal.
"""

import asyncio
import logging
import time
from typing import Optional

from siada.im.models import IMResponse
from siada.im.transport.base import Transport
from siada.io.io import InputOutput

logger = logging.getLogger("siada.io.lark")
logger.setLevel(logging.DEBUG)


class LarkIO(InputOutput):
    """IO adapter that sends output to Lark via relay transport.

    This class overrides output methods to route agent responses through
    the relay WebSocket connection back to the Lark user, while keeping
    logging and error output local.

    Usage:
        transport = RelayTransport(config)
        lark_io = LarkIO(transport=transport)
        # Use lark_io as the IO instance for SiadaRunner
    """

    def __init__(
        self,
        transport: Transport,
        request_id: str = "",
        chat_id: str = "",
        **kwargs,
    ):
        # Initialize base InputOutput in non-interactive, non-pretty mode
        super().__init__(
            pretty=False,
            yes=True,  # auto-confirm all prompts
            fancy_input=False,
            **kwargs,
        )
        self._transport = transport
        self._request_id = request_id
        self._chat_id = chat_id
        self._buffer: list[str] = []
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        logger.debug(f"LarkIO initialized with request_id={request_id}, chat_id={chat_id}")

    def set_context(self, request_id: str, chat_id: str) -> None:
        """Set the current message context for routing responses."""
        logger.debug(f"set_context called: request_id={request_id}, chat_id={chat_id}")
        self._request_id = request_id
        self._chat_id = chat_id
        self._buffer.clear()

    def _get_loop(self) -> asyncio.AbstractEventLoop:
        """Get or cache the running event loop."""
        if self._loop is None or self._loop.is_closed():
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                self._loop = asyncio.get_event_loop()
        return self._loop

    def _send_response(self, content: str, content_type: str = "text", is_streaming: bool = False) -> None:
        """Send a response through the relay transport (fire-and-forget)."""
        logger.debug(f"_send_response called: content_type={content_type}, is_streaming={is_streaming}, content={content[:200] if content else ''}")
        if not content or not self._request_id:
            logger.debug(f"_send_response skipped: content={'empty' if not content else 'present'}, request_id={self._request_id}")
            return
        response = IMResponse(
            request_id=self._request_id,
            content_type=content_type,
            content=content,
            chat_id=self._chat_id,
            is_streaming=is_streaming,
        )
        try:
            loop = self._get_loop()
            if loop.is_running():
                asyncio.ensure_future(self._transport.send(response), loop=loop)
            else:
                loop.run_until_complete(self._transport.send(response))
        except Exception as e:
            logger.error(f"Failed to send response via relay: {e}")

    # ========== Override output methods ==========

    def assistant_output(self, message, pretty=None, stream_end=False, stream_start_id=None):
        """Send assistant output to Lark via relay."""
        logger.debug(f"assistant_output called: stream_end={stream_end}, stream_start_id={stream_start_id}, message={str(message)[:200] if message else ''}")
        if not message:
            return
        self._send_response(message, content_type="markdown", is_streaming=not stream_end)

    def tool_output(self, message="", bold=False):
        """Buffer tool output; will be flushed with assistant response."""
        if message:
            self._buffer.append(str(message))
            logger.debug(f"Tool output buffered: {str(message)[:100]}")

    def print_info(self, *messages, bold=False):
        """Log info locally, don't send to Lark."""
        message = " ".join(str(m) for m in messages)
        logger.info(f"[LarkIO] {message}")

    def print_error(self, message="", strip=True):
        """Send errors to Lark and log locally."""
        error_str = str(message) if message else ""
        logger.error(f"[LarkIO] Error: {error_str}")
        if error_str:
            self._send_response(f"❌ {error_str}", content_type="text")

    def print_warning(self, message="", strip=True):
        """Log warnings locally."""
        logger.warning(f"[LarkIO] Warning: {message}")

    def print_tool_result(self, message="", strip=True):
        """Buffer tool results."""
        logger.debug(f"print_tool_result: {str(message)[:100]}")
        if message:
            self._buffer.append(str(message))

    def print_tool_call(self, message="", strip=True):
        """Log tool calls locally."""
        logger.info(f"[LarkIO] Tool call: {str(message)[:200]}")

    def print_tool_call_all_stages(self, message="", final=False, append=True):
        """Buffer tool call stage output."""
        logger.debug(f"print_tool_call_all_stages: final={final}, append={append}, message={str(message)[:100]}")
        if message:
            self._buffer.append(str(message))

    def get_input(self, completer=None, display_rule=False, color=None):
        """LarkIO does not support interactive input.

        This should never be called in relay mode; messages come
        from the transport queue instead.
        """
        raise NotImplementedError(
            "LarkIO does not support interactive input. "
            "Messages are received via relay transport."
        )

    def confirm_ask(self, question, default="y", subject=None,
                     explicit_yes_required=False, group=None, allow_never=False):
        """Auto-confirm all prompts in Lark mode."""
        logger.debug(f"confirm_ask: question={question}, default={default}, explicit_yes_required={explicit_yes_required}")
        return not explicit_yes_required

    def prompt_ask(self, question, default="", subject=None):
        """Return default for all prompts in Lark mode."""
        return default

    def flush_buffer(self) -> str:
        """Flush buffered output and return as single string."""
        logger.debug(f"flush_buffer called: buffer_size={len(self._buffer)}")
        if not self._buffer:
            return ""
        content = "\n".join(self._buffer)
        self._buffer.clear()
        logger.debug(f"flush_buffer returning: {content[:200]}")
        return content
