#!/usr/bin/env bash
set -e

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="$HOME/.local/bin"

echo "=== Installing Simple Downloader (vdown) ==="

# Check Python 3
if ! command -v python3 >/dev/null 2>&1; then
    echo "Error: Python 3 is required."
    exit 1
fi

# Ensure venv exists
if [ ! -d "$REPO_DIR/.venv" ]; then
    echo "Creating virtual environment at $REPO_DIR/.venv ..."
    python3 -m venv "$REPO_DIR/.venv"
fi

# Install dependencies in venv
echo "Installing dependencies..."
"$REPO_DIR/.venv/bin/python" -m pip install -e "$REPO_DIR"

# Ensure vdown is executable
chmod +x "$REPO_DIR/vdown"

# Create ~/.local/bin if not exists
mkdir -p "$BIN_DIR"

# Create symlink in ~/.local/bin
ln -sf "$REPO_DIR/vdown" "$BIN_DIR/vdown"

echo ""
echo "✔ Installation complete!"
echo "You can now run 'vdown' from anywhere in your terminal."
echo "Try: vdown --help"
