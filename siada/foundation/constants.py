from pathlib import Path

# Siada directory name constant
SIADA_DIR_NAME = ".siada-cli"

# Siada home directory - the default configuration and data directory
SIADA_HOME = Path.home() / SIADA_DIR_NAME

LLM_API_CONNECT_TIMEOUT = 30  # timeout for connecting to the API and sending the request (seconds)
LLM_API_READ_TIMEOUT = 600  # timeout for receiving the response (seconds)
CHECKPOINT_INIT_TIMEOUT = 60  # timeout for checkpoint initialization (seconds)
