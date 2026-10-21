#!/bin/sh
# Public browser-first installation; safe to invoke with curl ... | sh.
set -eu
case "$(uname -s)" in
  Darwin|Linux) ;;
  *) printf '%s\n' "This script supports Linux and macOS." >&2; exit 1 ;;
esac
if ! command -v uv >/dev/null 2>&1; then
  if [ -x "$HOME/.local/bin/uv" ]; then
    PATH="$HOME/.local/bin:$PATH"
  else
    siada_uv_script="$(mktemp)"
    trap 'rm -f "$siada_uv_script"' EXIT HUP INT TERM
    curl -fsSL https://astral.sh/uv/install.sh -o "$siada_uv_script"
    sh "$siada_uv_script"
    PATH="$HOME/.local/bin:$PATH"
  fi
fi
export PATH
siada_version="${SIADA_VERSION:-latest}"
case "$siada_version" in
  latest) siada_package="siada-cli@latest" ;;
  *[!0-9.abrc]*|'') printf '%s\n' "Invalid Siada version." >&2; exit 1 ;;
  *b*|*a*|*rc*)
    siada_package="$(uv run --no-project --python 3.12 python -c '
import json, sys, urllib.request
with urllib.request.urlopen("https://test.pypi.org/pypi/siada-cli/" + sys.argv[1] + "/json", timeout=30) as response:
    release = json.load(response)
print(next(item["url"] for item in release["urls"] if item["filename"].endswith(".whl")))
' "$siada_version")" ;;
  *) siada_package="siada-cli==$siada_version" ;;
esac
uv tool install --force --python python3.12 --compile --with pip \
  --default-index https://pypi.org/simple "$siada_package"
uv tool update-shell
siada_tool_bin="$(uv tool dir --bin)"
export PATH="$siada_tool_bin:$PATH"
if [ "$siada_version" = latest ]; then
  "$siada_tool_bin/siada-browser" setup --no-wait --host 127.0.0.1
else
  "$siada_tool_bin/siada-browser" setup --no-wait --host 127.0.0.1 \
    --base-url "https://github.com/liauto-siada/siada-cli/releases/download/v$siada_version"
fi
"$siada_tool_bin/siada-browser" start
printf '%s\n' "Siada browser service is ready. Return to Chrome to complete login."