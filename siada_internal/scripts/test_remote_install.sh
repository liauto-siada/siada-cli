#!/bin/sh
set -eu

# Ensure ~/.local/bin is on PATH for this session
export PATH="$HOME/.local/bin:$PATH"

# Install uv if missing (minimal approach)
if ! command -v uv >/dev/null 2>&1; then
  echo "Installing uv..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi

# Ensure Python 3.12 is available to uv
uv python install 3.12

# Create or reuse a dedicated venv
VENV_DIR="$HOME/.local/share/siada_cli_venv_3.12"
if [ ! -d "$VENV_DIR" ]; then
  echo "Creating virtual environment at: $VENV_DIR"
  uv venv --python 3.12 "$VENV_DIR"
else
  echo "Using existing virtual environment at: $VENV_DIR"
fi

# Optional: custom index mirror (using variables instead of arrays)
if [ -n "${SIADA_PYPI_INDEX:-}" ]; then
  INDEX_URL="$SIADA_PYPI_INDEX"
else
  INDEX_URL="https://pypi.tuna.tsinghua.edu.cn/simple"
fi

# Upgrade pip in the target venv via uv
uv pip install --python "$VENV_DIR/bin/python" --upgrade pip
# Install the wheel into the target venv via uv
uv pip install --python "$VENV_DIR/bin/python" --no-cache-dir --force-reinstall \
  "https://bj.bcebos.com/prod-cnhb01-siada/cli-install/test/siada_cli-1.1.0-py3-none-any.whl" \
  -i "$INDEX_URL"

# Enforce executable name
BIN_NAME="siada-cli"

# Create symlink into ~/.local/bin (works for macOS and Linux)
LINK_DIR="$HOME/.local/bin"
mkdir -p "$LINK_DIR"
ln -sf "$VENV_DIR/bin/$BIN_NAME" "$LINK_DIR/$BIN_NAME"

echo "**************************************"
echo "siada-cli installed in venv: \$HOME/.local/share/siada_cli_venv_3.12"
echo "Symlink created: \$HOME/.local/bin/$BIN_NAME"
echo "Next Steps"
echo "1. Add ~/.local/bin to your PATH:"
echo "   For bash:"
echo "   echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.bashrc"
echo "   source ~/.bashrc"
echo "   For zsh:"
echo "   echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.zshrc"
echo "   source ~/.zshrc"
