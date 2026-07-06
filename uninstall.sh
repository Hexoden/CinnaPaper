#!/usr/bin/env bash
set -euo pipefail

APP_NAME="cinnapaper"
INSTALL_DIR="${HOME}/.local/share/${APP_NAME}"
LAUNCHER_DIR="${HOME}/.local/share/applications"
AUTOSTART_DIR="${HOME}/.config/autostart"
ICON_DIR="${HOME}/.local/share/icons/hicolor/scalable/apps"

echo "Uninstalling CinnaPaper..."

echo "Stopping any running CinnaPaper instance..."
if command -v python3 &> /dev/null; then
    python3 <<'PY' || true
import sys
try:
    from PyQt5.QtNetwork import QLocalSocket, QIODevice
except Exception:
    sys.exit(1)

s = QLocalSocket()
s.connectToServer('CinnaPaperOverlay', QIODevice.WriteOnly)
if s.waitForConnected(250):
    s.write(b'quit')
    s.flush()
    s.waitForBytesWritten(250)
    s.disconnectFromServer()
    s.waitForDisconnected(250)
    s.close()
    sys.exit(0)
sys.exit(1)
PY
fi

if pgrep -u "${USER}" -f 'paper_overlay.py' >/dev/null 2>&1; then
    echo "Fallback: killing any remaining paper_overlay.py process..."
    pkill -u "${USER}" -f 'paper_overlay.py' || true
fi

# Remove application files
if [[ -d "${INSTALL_DIR}" ]]; then
    echo "Removing application files..."
    rm -rf "${INSTALL_DIR}"
fi

# Remove desktop launcher
if [[ -f "${LAUNCHER_DIR}/cinnapaper.desktop" ]]; then
    echo "Removing launcher..."
    rm -f "${LAUNCHER_DIR}/cinnapaper.desktop"
fi

# Remove autostart entry
if [[ -f "${AUTOSTART_DIR}/cinnapaper.desktop" ]]; then
    echo "Removing autostart entry..."
    rm -f "${AUTOSTART_DIR}/cinnapaper.desktop"
fi

# Remove icon (png, svg or ico)
for ext in png svg ico; do
    if [[ -f "${ICON_DIR}/cinnapaper.${ext}" ]]; then
        echo "Removing icon ${ext}..."
        rm -f "${ICON_DIR}/cinnapaper.${ext}"
    fi
done

# Update MIME type database and icon cache
if command -v update-desktop-database &> /dev/null; then
    update-desktop-database "${LAUNCHER_DIR}" || true
fi

if command -v gtk-update-icon-cache &> /dev/null; then
    gtk-update-icon-cache "${ICON_DIR%/*}" || true
fi

echo "✓ CinnaPaper uninstalled successfully!"
