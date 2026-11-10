#!/usr/bin/env bash
set -e

# Portable directory resolution
TARGET="${BASH_SOURCE[0]}"
while [ -L "$TARGET" ]; do
    DIR="$(cd -P "$(dirname "$TARGET")" && pwd)"
    TARGET="$(readlink "$TARGET")"
    [[ $TARGET != /* ]] && TARGET="$DIR/$TARGET"
done
REPO_DIR="$(cd -P "$(dirname "$TARGET")" && pwd)"
BIN_DIR="$HOME/.local/bin"
OS_TYPE="$(uname -s)"

echo "=== Installing VDown (CLI & Desktop GUI) on $OS_TYPE ==="

# Check Python 3
if ! command -v python3 >/dev/null 2>&1; then
    echo "Error: Python 3 is required." >&2
    exit 1
fi

PYTHON_VER="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
echo "Detected Python $PYTHON_VER"

# Ensure venv exists
if [ ! -d "$REPO_DIR/.venv" ]; then
    echo "Creating virtual environment at $REPO_DIR/.venv ..."
    python3 -m venv "$REPO_DIR/.venv"
fi

# Upgrade pip and install package
echo "Installing dependencies (including yt-dlp and PyQt6)..."
"$REPO_DIR/.venv/bin/python" -m pip install --upgrade pip
"$REPO_DIR/.venv/bin/python" -m pip install -e "$REPO_DIR"

# Ensure launchers are executable
chmod +x "$REPO_DIR/vdown"
chmod +x "$REPO_DIR/vdown-gui"

# Create ~/.local/bin if not exists
mkdir -p "$BIN_DIR"

# Create symlinks in ~/.local/bin
ln -sf "$REPO_DIR/vdown" "$BIN_DIR/vdown"
ln -sf "$REPO_DIR/vdown-gui" "$BIN_DIR/vdown-gui"

# Check if /usr/local/bin is writable and symlink there for convenience
if [ -w "/usr/local/bin" ] && [ "/usr/local/bin" != "$BIN_DIR" ]; then
    ln -sf "$REPO_DIR/vdown" "/usr/local/bin/vdown" 2>/dev/null || true
    ln -sf "$REPO_DIR/vdown-gui" "/usr/local/bin/vdown-gui" 2>/dev/null || true
fi

# Platform-specific desktop integration
if [ "$OS_TYPE" = "Darwin" ]; then
    echo "Configuring macOS application bundle..."

    # Check for ffmpeg
    if ! command -v ffmpeg >/dev/null 2>&1 && [ ! -f "/usr/local/bin/ffmpeg" ] && [ ! -f "/opt/homebrew/bin/ffmpeg" ]; then
        echo ""
        echo "ℹ Note: FFmpeg is recommended on macOS for high-quality audio extraction and video format merging."
        if command -v brew >/dev/null 2>&1; then
            echo "  To install FFmpeg via Homebrew, run: brew install ffmpeg"
        fi
        echo ""
    fi

    # Ensure assets/icon.icns exists
    if [ ! -f "$REPO_DIR/assets/icon.icns" ] && [ -f "$REPO_DIR/assets/icon.png" ] && command -v sips >/dev/null 2>&1 && command -v iconutil >/dev/null 2>&1; then
        ICONSET_DIR="$(mktemp -d /tmp/vdown_icon.iconset.XXXXXX)"
        sips -z 16 16 "$REPO_DIR/assets/icon.png" --out "$ICONSET_DIR/icon_16x16.png" >/dev/null 2>&1 || true
        sips -z 32 32 "$REPO_DIR/assets/icon.png" --out "$ICONSET_DIR/icon_16x16@2x.png" >/dev/null 2>&1 || true
        sips -z 32 32 "$REPO_DIR/assets/icon.png" --out "$ICONSET_DIR/icon_32x32.png" >/dev/null 2>&1 || true
        sips -z 64 64 "$REPO_DIR/assets/icon.png" --out "$ICONSET_DIR/icon_32x32@2x.png" >/dev/null 2>&1 || true
        sips -z 128 128 "$REPO_DIR/assets/icon.png" --out "$ICONSET_DIR/icon_128x128.png" >/dev/null 2>&1 || true
        sips -z 256 256 "$REPO_DIR/assets/icon.png" --out "$ICONSET_DIR/icon_128x128@2x.png" >/dev/null 2>&1 || true
        sips -z 256 256 "$REPO_DIR/assets/icon.png" --out "$ICONSET_DIR/icon_256x256.png" >/dev/null 2>&1 || true
        sips -z 512 512 "$REPO_DIR/assets/icon.png" --out "$ICONSET_DIR/icon_256x256@2x.png" >/dev/null 2>&1 || true
        sips -z 512 512 "$REPO_DIR/assets/icon.png" --out "$ICONSET_DIR/icon_512x512.png" >/dev/null 2>&1 || true
        iconutil -c icns "$ICONSET_DIR" -o "$REPO_DIR/assets/icon.icns" >/dev/null 2>&1 || true
        rm -rf "$ICONSET_DIR"
    fi

    # Create ~/Applications/VDown.app macOS Application
    MAC_APPS_DIR="$HOME/Applications"
    mkdir -p "$MAC_APPS_DIR"
    APP_BUNDLE="$MAC_APPS_DIR/VDown.app"
    CONTENTS_DIR="$APP_BUNDLE/Contents"
    MACOS_DIR="$CONTENTS_DIR/MacOS"
    RESOURCES_DIR="$CONTENTS_DIR/Resources"

    mkdir -p "$MACOS_DIR" "$RESOURCES_DIR"

    # Write launcher wrapper inside macOS app bundle
    cat << 'WRAPPER' > "$MACOS_DIR/VDown"
#!/usr/bin/env bash
for extra_path in "/opt/homebrew/bin" "/usr/local/bin" "/opt/local/bin" "$HOME/.local/bin"; do
    if [ -d "$extra_path" ] && [[ ":$PATH:" != *":$extra_path:"* ]]; then
        export PATH="$extra_path:$PATH"
    fi
done
REPO_DIR="$(cat "$HOME/Applications/VDown.app/Contents/Resources/repo_dir.txt" 2>/dev/null || echo "")"
if [ -n "$REPO_DIR" ] && [ -x "$REPO_DIR/vdown-gui" ]; then
    exec "$REPO_DIR/vdown-gui" "$@"
fi
exec vdown-gui "$@"
WRAPPER
    chmod +x "$MACOS_DIR/VDown"
    echo "$REPO_DIR" > "$RESOURCES_DIR/repo_dir.txt"

    # Write Info.plist
    cat << PLIST > "$CONTENTS_DIR/Info.plist"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>VDown</string>
    <key>CFBundleDisplayName</key>
    <string>VDown</string>
    <key>CFBundleIdentifier</key>
    <string>com.dularacharith.vdown</string>
    <key>CFBundleVersion</key>
    <string>2.0.0</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleSignature</key>
    <string>????</string>
    <key>CFBundleExecutable</key>
    <string>VDown</string>
    <key>CFBundleIconFile</key>
    <string>AppIcon</string>
    <key>LSMinimumSystemVersion</key>
    <string>10.13</string>
    <key>NSHighResolutionCapable</key>
    <true/>
</dict>
</plist>
PLIST

    # Copy macOS icon
    if [ -f "$REPO_DIR/assets/icon.icns" ]; then
        cp "$REPO_DIR/assets/icon.icns" "$RESOURCES_DIR/AppIcon.icns"
    fi
    touch "$APP_BUNDLE"

    echo "✔ Created macOS Application: $APP_BUNDLE"

else
    # Linux Desktop integration
    DESKTOP_DIR="$HOME/.local/share/applications"
    mkdir -p "$HOME/.local/share/icons/hicolor/512x512/apps"
    mkdir -p "$HOME/.local/share/pixmaps"

    if [ -f "$REPO_DIR/assets/icon.png" ]; then
        cp "$REPO_DIR/assets/icon.png" "$HOME/.local/share/icons/hicolor/512x512/apps/vdown.png"
        cp "$REPO_DIR/assets/icon.png" "$HOME/.local/share/pixmaps/vdown.png"
    fi

    if [ -f "$REPO_DIR/vdown.desktop" ]; then
        mkdir -p "$DESKTOP_DIR"
        cp "$REPO_DIR/vdown.desktop" "$DESKTOP_DIR/vdown.desktop"
        "$REPO_DIR/.venv/bin/python" -c "
with open('$DESKTOP_DIR/vdown.desktop', 'r') as f:
    content = f.read()
content = content.replace('Exec=vdown-gui', 'Exec=$BIN_DIR/vdown-gui')
content = content.replace('Icon=vdown', 'Icon=$HOME/.local/share/pixmaps/vdown.png')
with open('$DESKTOP_DIR/vdown.desktop', 'w') as f:
    f.write(content)
"
    fi
fi

# PATH notice
if [[ ":$PATH:" != *":$BIN_DIR:"* ]] && [[ ":$PATH:" != *":/usr/local/bin:"* ]]; then
    echo ""
    echo "⚠ Note: $BIN_DIR is not currently in your PATH."
    echo "  Add it to your shell configuration:"
    if [ "$OS_TYPE" = "Darwin" ]; then
        echo "  echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.zshrc"
    else
        echo "  echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.bashrc"
    fi
fi

echo ""
echo "✔ Installation complete!"
echo "You can now run:"
echo "  - 'vdown' (Command Line Interface)"
echo "  - 'vdown-gui' (Modern Desktop GUI Application)"
if [ "$OS_TYPE" = "Darwin" ]; then
    echo "  - Or open VDown from ~/Applications in Finder / Spotlight!"
else
    echo "  - Or launch VDown from your desktop application launcher!"
fi
