#!/usr/bin/env bash
set -euo pipefail

this_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
internal_dir="${this_dir}/.."
repo_root="${internal_dir}/.."

# 1) Clean root dist
echo "Cleaning root dist..."
rm -rf "${repo_root}/dist" || true

# 2) Build root package
poetry -C "${repo_root}" build | cat

# 3) Run pack & publish (point packer to root dist)
SIADA_DIST_DIR="${repo_root}/dist" \
  poetry -C "${internal_dir}" run \
  python -m pack_pipeline "$@"