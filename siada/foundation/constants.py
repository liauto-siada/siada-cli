from pathlib import Path

# Siada directory name constant
SIADA_DIR_NAME = ".siada-cli"

# Siada home directory - the default configuration and data directory
SIADA_HOME = Path.home() / SIADA_DIR_NAME

CHECKPOINT_INIT_TIMEOUT = 60  # timeout for checkpoint initialization (seconds)

# Timeout for a single POST attempt to the LLM backend (seconds).
# This value is explicitly passed to `litellm.acompletion(timeout=...)` so it
# lands on the aiohttp socket-read layer and prevents half-open TCP
# connections from hanging the caller for dozens of minutes. It governs
# ONE attempt only — siada/entrypoint/__init__.py sets a process-wide
# `litellm.num_retries=3`, so on Anthropic Timeout the wrapper will retry
# up to 3 more times. Worst-case wall clock for a single chat_complete is
# therefore ~ 4 × LLM_API_POST_TIMEOUT (1 original + 3 wrapper retries).
LLM_API_POST_TIMEOUT = 600 * 2  # 20 minutes (single litellm attempt)
