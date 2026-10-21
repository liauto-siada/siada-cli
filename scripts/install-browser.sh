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
uv tool install --force --python python3.12 --compile --with pip \
  --default-index https://pypi.org/simple siada-cli@latest
uv tool update-shell
siada_tool_bin="$(uv tool dir --bin)"
export PATH="$siada_tool_bin:$PATH"
"$siada_tool_bin/siada-browser" setup --no-wait --host 127.0.0.1
"$siada_tool_bin/siada-browser" start
printf '%s\n' "Siada browser service is ready. Return to Chrome to complete login."