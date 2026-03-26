#!/usr/bin/env bash
set -euo pipefail

# One-click launcher for siada_cli_ui in module mode.
#
# Usage:
#   ./run-ui-module-mode.sh [-- extra siada-ui args...]
#
# Examples:
#   ./run-ui-module-mode.sh -- --debug
#   ./run-ui-module-mode.sh -- --alternate-buffer

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

UI_DIR="${SCRIPT_DIR}"
# Default python interpreter for module mode.
#
# Historically some environments used "venv/", but this repo uses Poetry and
# typically creates ".venv/" at the repo root. When the path is wrong, the UI
# launcher will fail with: spawn ... ENOENT.
PYTHON_PATH_DEFAULT=""
if [[ -x "${REPO_ROOT}/siada-agenthub/.venv/bin/python" ]]; then
  PYTHON_PATH_DEFAULT="${REPO_ROOT}/siada-agenthub/.venv/bin/python"
elif [[ -x "${REPO_ROOT}/siada-agenthub/venv/bin/python" ]]; then
  PYTHON_PATH_DEFAULT="${REPO_ROOT}/siada-agenthub/venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_PATH_DEFAULT="$(command -v python3)"
elif command -v python >/dev/null 2>&1; then
  PYTHON_PATH_DEFAULT="$(command -v python)"
else
  echo "[siada_cli_ui] ERROR: Python interpreter not found. Please set SIADA_PYTHON_PATH." >&2
  exit 1
fi
SIADA_MODULE_DEFAULT="${REPO_ROOT}/siada-agenthub"

# Allow override via env vars (keeps behavior consistent with src/cli.ts)
export SIADA_PYTHON_PATH="${SIADA_PYTHON_PATH:-${PYTHON_PATH_DEFAULT}}"
export SIADA_MODULE_PATH="${SIADA_MODULE_PATH:-${SIADA_MODULE_DEFAULT}}"

cd "${UI_DIR}"

# If deps not installed, npm scripts won't find tsx (devDependency).
if [[ ! -d node_modules ]]; then
  echo "[siada_cli_ui] node_modules not found, running: npm install" >&2
  npm install
fi

# Forward any extra args after an optional "--".
EXTRA_ARGS=()
if [[ "${#}" -gt 0 ]]; then
  if [[ "${1}" == "--" ]]; then
    shift
  fi
  EXTRA_ARGS=("$@")
fi

# In `set -u` (nounset) mode, expanding an empty array via "${arr[@]}" can
# trigger "unbound variable" on bash 3.2 (macOS default). Only append the
# extra args when the array is non-empty.
CMD=(
  npm start --
  --use-module-mode
  --python-path "${SIADA_PYTHON_PATH}"
  --siada-module "${SIADA_MODULE_PATH}"
)
if (( ${#EXTRA_ARGS[@]} > 0 )); then
  CMD+=("${EXTRA_ARGS[@]}")
fi
echo "${CMD[@]}"
exec "${CMD[@]}"
