#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_NAME="cinnapaper"
INSTALL_DIR="${HOME}/.local/share/${APP_NAME}"
LAUNCHER_DIR="${HOME}/.local/share/applications"
ICON_DIR="${HOME}/.local/share/icons/hicolor/scalable/apps"
AUTOSTART_DIR="${HOME}/.config/autostart"

echo "Installing CinnaPaper..."

# Create directories
mkdir -p "${INSTALL_DIR}"
mkdir -p "${LAUNCHER_DIR}"
mkdir -p "${ICON_DIR}"
mkdir -p "${AUTOSTART_DIR}"

# Copy application files
echo "Copying application files..."
cp "${SCRIPT_DIR}/paper_overlay.py" "${INSTALL_DIR}/"
cp "${SCRIPT_DIR}/run_paper_overlay.sh" "${INSTALL_DIR}/"
cp "${SCRIPT_DIR}/requirements.txt" "${INSTALL_DIR}/"
cp "${SCRIPT_DIR}/cinnapaper.png" "${ICON_DIR}/cinnapaper.png"

# Install icons: put a copy in the app dir and into the icon theme
if [[ -f "${SCRIPT_DIR}/cinnapaper.png" ]]; then
    cp "${SCRIPT_DIR}/cinnapaper.png" "${INSTALL_DIR}/cinnapaper.png"
    cp "${SCRIPT_DIR}/cinnapaper.png" "${ICON_DIR}/cinnapaper.png"
fi
if [[ -f "${SCRIPT_DIR}/cinnapaper.svg" ]]; then
    cp "${SCRIPT_DIR}/cinnapaper.svg" "${ICON_DIR}/cinnapaper.svg"
fi
# Make scripts executable
chmod +x "${INSTALL_DIR}/run_paper_overlay.sh"
chmod +x "${INSTALL_DIR}/paper_overlay.py"

# Create desktop launcher from template
cp "${SCRIPT_DIR}/cinnapaper.desktop" "${LAUNCHER_DIR}/cinnapaper.desktop"
sed -i "s|%INSTALL_DIR%|${INSTALL_DIR}|g" "${LAUNCHER_DIR}/cinnapaper.desktop"

# Create autostart entry so the app starts on login
cp "${LAUNCHER_DIR}/cinnapaper.desktop" "${AUTOSTART_DIR}/cinnapaper.desktop"
if grep -q '^X-GNOME-Autostart-enabled=' "${AUTOSTART_DIR}/cinnapaper.desktop"; then
    sed -i 's/^X-GNOME-Autostart-enabled=.*/X-GNOME-Autostart-enabled=true/' "${AUTOSTART_DIR}/cinnapaper.desktop"
else
    echo 'X-GNOME-Autostart-enabled=true' >> "${AUTOSTART_DIR}/cinnapaper.desktop"
fi

# Update MIME type database and icon cache
if command -v update-desktop-database &> /dev/null; then
    update-desktop-database "${LAUNCHER_DIR}" || true
fi

if command -v gtk-update-icon-cache &> /dev/null; then
    gtk-update-icon-cache "${ICON_DIR%/*}" || true
fi

# Optional: Install dependencies
echo ""
echo "Checking Python dependencies..."
if ! python3 -c "import PyQt5" 2>/dev/null; then
    echo "Installing PyQt5..."
    python3 -m pip install --user -r "${INSTALL_DIR}/requirements.txt" || {
        echo "Failed to auto-install PyQt5. Install manually with:"
        echo "  python3 -m pip install -r ${INSTALL_DIR}/requirements.txt"
    }
fi

echo ""
echo "✓ CinnaPaper installed successfully!"
echo ""
echo "Starting CinnaPaper now..."
nohup "${INSTALL_DIR}/run_paper_overlay.sh" >/dev/null 2>&1 &
echo ""
echo "Launch it from your application menu or run:"
echo "  ${INSTALL_DIR}/run_paper_overlay.sh"
echo ""
echo "CinnaPaper will also auto-start on login."
echo ""
echo "To uninstall, run:"
echo "  bash ${SCRIPT_DIR}/uninstall.sh"
