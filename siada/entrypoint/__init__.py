"""
Siada Hub 命令行工具入口点
"""
from siada.foundation.logging import logger


def _configure_litellm_logging():
    """Configure LiteLLM global logging settings to suppress debug logs"""
    try:
        import litellm

        # Configure litellm global properties
        litellm.set_verbose = False
        litellm.turn_off_message_logging = True
        litellm.suppress_debug_info = True
        litellm.drop_params = True

        # Try to disable internal debug logging
        try:
            litellm._logging._disable_debugging()
        except Exception:
            pass  # Ignore if method doesn't exist

        # Disable message logging and tracing
        litellm.turn_off_message_logging = True
        litellm.success_callback = []
        litellm.failure_callback = []

        logger.debug("LiteLLM logging configuration completed")

    except ImportError:
        logger.debug("LiteLLM not installed, skipping logging configuration")
    except Exception as e:
        logger.debug(f"Error configuring LiteLLM logging: {e}")


