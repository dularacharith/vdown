#!/usr/bin/env bash
set -e

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="$HOME/.local/bin"
DESKTOP_DIR="$HOME/.local/share/applications"

echo "=== Installing VDown (CLI & Desktop GUI) ==="

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
echo "Installing dependencies (including PyQt6 for Desktop GUI)..."
"$REPO_DIR/.venv/bin/python" -m pip install -e "$REPO_DIR"

# Ensure launchers are executable
chmod +x "$REPO_DIR/vdown"
chmod +x "$REPO_DIR/vdown-gui"

# Create ~/.local/bin if not exists
mkdir -p "$BIN_DIR"

# Create symlinks in ~/.local/bin
ln -sf "$REPO_DIR/vdown" "$BIN_DIR/vdown"
ln -sf "$REPO_DIR/vdown-gui" "$BIN_DIR/vdown-gui"

# Install desktop shortcut
if [ -f "$REPO_DIR/vdown.desktop" ]; then
    mkdir -p "$DESKTOP_DIR"
    cp "$REPO_DIR/vdown.desktop" "$DESKTOP_DIR/vdown.desktop"
    sed -i "s|Exec=vdown-gui|Exec=$BIN_DIR/vdown-gui|g" "$DESKTOP_DIR/vdown.desktop"
fi

echo ""
echo "✔ Installation complete!"
echo "You can now run:"
echo "  - 'vdown' (Command Line Interface)"
echo "  - 'vdown-gui' (Modern Desktop GUI Application)"
echo "  - Or launch VDown from your desktop application launcher!"
