#!/usr/bin/env python3
import argparse
import json
import os
import random
import subprocess
import sys
import time
from datetime import datetime

from PyQt5.QtCore import Qt, QIODevice, QRect, QTimer
from PyQt5.QtGui import QColor, QPainter, QImage, QPen, QIcon, QPixmap, QCursor
from PyQt5.QtNetwork import QLocalServer, QLocalSocket
from PyQt5.QtSvg import QSvgRenderer
from PyQt5.QtWidgets import (
    QApplication,
    QWidget,
    QSystemTrayIcon,
    QMenu,
    QAction,
    QLabel,
    QSlider,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QRadioButton,
    QGroupBox,
    QCheckBox,
    QMessageBox,
)


def send_quit_to_existing_instance(server_name):
    socket = QLocalSocket()
    socket.connectToServer(server_name, QIODevice.WriteOnly)
    if socket.waitForConnected(250):
        socket.write(b"quit")
        socket.flush()
        socket.waitForBytesWritten(250)
        socket.disconnectFromServer()
        socket.waitForDisconnected(250)
        socket.close()
        return True
    socket.close()
    return False


def remove_stale_local_server(server_name):
    try:
        QLocalServer.removeServer(server_name)
    except Exception:
        pass


CONFIG_DIR = os.path.join(os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")), "cinnapaper")
SETTINGS_PATH = os.path.join(CONFIG_DIR, "settings.json")
DEFAULT_SETTINGS = {
    "preset": "sepia",
    "opacity": 0.92,
    "grain": 0.22,
    "intensity": 0.65,
    "screen_mode": "all",
    "auto_schedule": False,
    "day_preset": "sepia",
    "schedule_hours": [19, 20, 21, 22, 23, 0, 1, 2, 3, 4, 5, 6],
}


def load_settings():
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as handle:
            data = json.load(handle)
            return {**DEFAULT_SETTINGS, **data}
    except Exception:
        return DEFAULT_SETTINGS.copy()


def save_settings(settings):
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(SETTINGS_PATH, "w", encoding="utf-8") as handle:
            json.dump(settings, handle, indent=2)
    except Exception:
        pass


def is_night_time():
    now = datetime.now().time()
    return now >= datetime.strptime("19:00", "%H:%M").time() or now <= datetime.strptime("07:00", "%H:%M").time()


class PaperOverlay(QWidget):
    def __init__(
        self,
        preset="sepia",
        opacity=0.92,
        grain=0.22,
        intensity=0.65,
        screen_mode="all",
        auto_schedule=False,
        day_preset="sepia",
        schedule_hours=None,
    ):
        super().__init__()
        self.setWindowTitle("Paper Overlay")
        self.preset_name = preset
        self.opacity = opacity
        self.grain = grain
        self.intensity = intensity
        self.screen_mode = screen_mode
        self.auto_schedule = auto_schedule
        self.day_preset = day_preset
        self.schedule_hours = schedule_hours if schedule_hours is not None else DEFAULT_SETTINGS["schedule_hours"]
        self.overlay_enabled = True
        self.seed = random.randint(1, 10_000)
        self.offset_x = 0
        self.offset_y = 0
        self.texture = self._build_texture(120, 120, 14, 30)
        self.texture2 = self._build_texture(180, 180, 8, 25)

        self.presets = {
            "sepia": {"base": QColor(243, 234, 217), "shadow": QColor(120, 84, 41), "accent": QColor(205, 168, 116), "tone": 0.14},
            "cool": {"base": QColor(232, 240, 245), "shadow": QColor(46, 79, 112), "accent": QColor(147, 182, 203), "tone": 0.10},
            "ink": {"base": QColor(248, 244, 238), "shadow": QColor(38, 35, 32), "accent": QColor(108, 88, 70), "tone": 0.16},
            "parchment": {"base": QColor(250, 235, 208), "shadow": QColor(96, 64, 34), "accent": QColor(181, 152, 110), "tone": 0.18},
            "mist": {"base": QColor(240, 240, 232), "shadow": QColor(79, 85, 102), "accent": QColor(151, 160, 173), "tone": 0.11},
            "night": {"base": QColor(30, 27, 24), "shadow": QColor(14, 11, 10), "accent": QColor(121, 92, 63), "tone": 0.14},
            "eyecomfort": {"base": QColor(245, 210, 145), "shadow": QColor(120, 80, 40), "accent": QColor(200, 135, 70), "tone": 0.16},
            "warm": {"base": QColor(255, 236, 188), "shadow": QColor(143, 101, 64), "accent": QColor(212, 136, 46), "tone": 0.14},
            "study": {"base": QColor(235, 226, 203), "shadow": QColor(90, 70, 40), "accent": QColor(185, 145, 80), "tone": 0.12},
            "darkcomfort": {"base": QColor(40, 36, 33), "shadow": QColor(12, 9, 8), "accent": QColor(125, 95, 58), "tone": 0.14},
        }

        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_X11NetWmWindowTypeDock, True)
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.BypassWindowManagerHint
            | Qt.X11BypassWindowManagerHint
        )

        self.setGeometry(self._get_screen_geometry())
        self.setWindowOpacity(0.0)
        self.show()
        self.raise_()
        self.update()

        self.settings_window = None
        self.local_server = None
        self._init_tray()
        self._update_tray_tooltip()
        self._start_local_server()

        self.schedule_timer = QTimer(self)
        self.schedule_timer.timeout.connect(self._apply_auto_schedule)
        self.schedule_timer.start(60 * 1000)
        self._apply_auto_schedule()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(120)
        self._tick()
        QTimer.singleShot(50, self._show_ready)

    def _build_texture(self, width, height, alpha_min, alpha_range):
        image = QImage(width, height, QImage.Format_ARGB32_Premultiplied)
        image.fill(Qt.transparent)
        rng = random.Random(self.seed)
        for y in range(height):
            for x in range(width):
                alpha = alpha_min + int(rng.random() * alpha_range)
                image.setPixelColor(x, y, QColor(0, 0, 0, alpha))
        return image

    def _get_active_screen(self):
        cursor_screen = QApplication.screenAt(QCursor.pos())
        return cursor_screen or QApplication.primaryScreen()

    def _get_screen_geometry(self):
        if self.screen_mode == "primary":
            screen = QApplication.primaryScreen()
            return screen.geometry() if screen else QRect(0, 0, 800, 600)

        if self.screen_mode == "active":
            screen = self._get_active_screen()
            return screen.geometry() if screen else QRect(0, 0, 800, 600)

        screens = QApplication.screens()
        if not screens:
            screen = QApplication.primaryScreen()
            return screen.geometry() if screen else QRect(0, 0, 800, 600)

        geometry = screens[0].geometry()
        for screen in screens[1:]:
            geometry = geometry.united(screen.geometry())
        return geometry

    def _is_scheduled_time(self):
        now = datetime.now().time()
        return now.hour in self.schedule_hours

    def _apply_auto_schedule(self):
        if not self.auto_schedule:
            return

        if self._is_scheduled_time():
            if self.preset_name != "eyecomfort":
                self.set_preset("eyecomfort", save=False)
        else:
            if self.preset_name == "eyecomfort":
                self.set_preset(self.day_preset or DEFAULT_SETTINGS["preset"], save=False)

    def _update_tray_tooltip(self):
        if not hasattr(self, "tray") or self.tray is None:
            return

        schedule_state = "On" if self.auto_schedule else "Off"
        overlay_state = "On" if getattr(self, "overlay_enabled", True) else "Off"
        self.tray.setToolTip(
            f"CinnaPaper — {self.preset_name.capitalize()} — Intensity {int(self.intensity * 100)}% — Schedule {schedule_state} — Overlay {overlay_state}"
        )

    def save_settings(self):
        settings = {
            "preset": self.preset_name,
            "opacity": self.opacity,
            "grain": self.grain,
            "intensity": self.intensity,
            "screen_mode": self.screen_mode,
            "auto_schedule": self.auto_schedule,
            "day_preset": self.day_preset,
            "schedule_hours": self.schedule_hours,
        }
        save_settings(settings)

    def _tick(self):
        self.offset_x = (self.offset_x + 1) % 220
        self.offset_y = (self.offset_y + 1) % 220
        self.update()

    def _start_local_server(self):
        server_name = "CinnaPaperOverlay"
        self.local_server = QLocalServer(self)
        if not self.local_server.listen(server_name):
            remove_stale_local_server(server_name)
            self.local_server.listen(server_name)
        self.local_server.newConnection.connect(self._handle_local_connection)

    def _handle_local_connection(self):
        socket = self.local_server.nextPendingConnection()
        if socket is None:
            return
        if socket.waitForReadyRead(250):
            message = socket.readAll().data().decode().strip()
            if message == "quit":
                self.close()
        socket.disconnectFromServer()
        socket.close()

    def _show_ready(self):
        self.setWindowOpacity(self.opacity * self.intensity)
        self.update()

    def cleanup(self):
        if self.timer.isActive():
            self.timer.stop()
        if hasattr(self, "schedule_timer") and self.schedule_timer.isActive():
            self.schedule_timer.stop()
        if hasattr(self, "tray") and self.tray:
            self.tray.hide()
            self.tray.setVisible(False)
            self.tray.deleteLater()
        if self.settings_window:
            self.settings_window.hide()
            self.settings_window.deleteLater()
            self.settings_window = None
        if self.local_server:
            self.local_server.close()
            remove_stale_local_server("CinnaPaperOverlay")
        self.hide()

    def set_preset(self, preset_name, save=True):
        if preset_name in self.presets:
            if self.auto_schedule and preset_name != "eyecomfort":
                self.day_preset = preset_name

            self.preset_name = preset_name
            self.update()
            for action in getattr(self, "preset_actions", []):
                action.setChecked(action.data() == preset_name)
            if save:
                self.save_settings()
            self._update_tray_tooltip()

    def set_intensity(self, intensity, save=True):
        self.intensity = intensity
        self.setWindowOpacity(self.opacity * self.intensity)
        self.update()
        if save:
            self.save_settings()
        self._update_tray_tooltip()

    def set_screen_mode(self, screen_mode, save=True):
        if screen_mode in {"all", "primary", "active"}:
            self.screen_mode = screen_mode
            self.setGeometry(self._get_screen_geometry())
            self.update()
            if save:
                self.save_settings()
            self._update_tray_tooltip()

    def set_auto_schedule(self, enabled, save=True):
        self.auto_schedule = enabled
        if self.auto_schedule:
            self._apply_auto_schedule()
        if save:
            self.save_settings()
        self._update_tray_tooltip()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        size = self.size()
        preset = self.presets[self.preset_name]

        width = size.width()
        height = size.height()
        base = preset["base"]
        shadow = preset["shadow"]
        accent = preset["accent"]

        global_alpha = self.opacity * self.intensity
        painter.fillRect(0, 0, width, height, QColor(base.red(), base.green(), base.blue(), max(28, min(160, int(100 * global_alpha)))))

        painter.setPen(Qt.NoPen)
        painter.setOpacity(min(1.0, (0.18 + self.grain * 0.3) * self.intensity))
        for y in range(0, height, self.texture.height()):
            for x in range(0, width, self.texture.width()):
                painter.drawImage(QRect(x, y, self.texture.width(), self.texture.height()), self.texture)

    def _init_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = None
            return

        self.tray = QSystemTrayIcon(self)
        self.tray.setIcon(self._build_tray_icon())
        self.tray.setToolTip("CinnaPaper overlay")

        menu = QMenu()
        preset_menu = menu.addMenu("Preset")
        self.preset_actions = []
        for preset_name in self.presets:
            label = "Eye Comfort" if preset_name == "eyecomfort" else preset_name.capitalize()
            action = QAction(label, self)
            action.setCheckable(True)
            action.setData(preset_name)
            action.setChecked(preset_name == self.preset_name)
            action.triggered.connect(lambda checked, name=preset_name: self.set_preset(name))
            preset_menu.addAction(action)
            self.preset_actions.append(action)

        settings_action = QAction("Intensity / Schedule...", self)
        settings_action.triggered.connect(self.open_settings)
        menu.addAction(settings_action)

        self.toggle_overlay_action = QAction("Disable overlay", self)
        self.toggle_overlay_action.setCheckable(True)
        self.toggle_overlay_action.setChecked(self.overlay_enabled)
        self.toggle_overlay_action.triggered.connect(self._toggle_overlay)
        menu.addAction(self.toggle_overlay_action)

        schedule_action = QAction("Toggle auto schedule", self)
        schedule_action.setCheckable(True)
        schedule_action.setChecked(self.auto_schedule)
        schedule_action.triggered.connect(lambda: self.set_auto_schedule(not self.auto_schedule))
        menu.addAction(schedule_action)

        uninstall_action = QAction("Uninstall", self)
        uninstall_action.triggered.connect(self._confirm_uninstall)
        menu.addAction(uninstall_action)

        menu.addSeparator()
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(QApplication.quit)
        menu.addAction(quit_action)

        self.tray.setContextMenu(menu)
        self.tray.show()

    def _build_tray_icon(self):
        base = os.path.dirname(__file__)
        png_path = os.path.join(base, "cinnapaper.png")
        svg_path = os.path.join(base, "cinnapaper.svg")

        # Prefer a bundled PNG if present
        if os.path.exists(png_path):
            icon = QIcon(png_path)
            if not icon.isNull():
                return icon

        # Fall back to rendering an SVG if available
        if os.path.exists(svg_path):
            renderer = QSvgRenderer(svg_path)
            if renderer.isValid():
                pixmap = QPixmap(24, 24)
                pixmap.fill(Qt.transparent)
                painter = QPainter(pixmap)
                renderer.render(painter)
                painter.end()
                return QIcon(pixmap)

            icon = QIcon(svg_path)
            if not icon.isNull():
                return icon

        # Fallback generated icon
        pixmap = QPixmap(16, 16)
        pixmap.fill(Qt.transparent)
        icon_painter = QPainter(pixmap)
        icon_painter.setRenderHint(QPainter.Antialiasing)
        icon_painter.setBrush(QColor(245, 242, 232))
        icon_painter.setPen(QColor(140, 130, 115))
        icon_painter.drawRoundedRect(2, 2, 12, 12, 2, 2)
        icon_painter.drawLine(8, 2, 14, 8)
        icon_painter.drawLine(8, 2, 8, 8)
        icon_painter.drawLine(14, 8, 8, 8)
        icon_painter.end()
        return QIcon(pixmap)

    def open_settings(self):
        if self.settings_window is None:
            self.settings_window = SettingsWindow(self)
        self.settings_window.show()
        self.settings_window.raise_()

    def _confirm_uninstall(self):
        reply = QMessageBox.question(
            self,
            "Uninstall CinnaPaper",
            "This will uninstall CinnaPaper and stop the overlay. Continue?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self._run_uninstall()

    def _run_uninstall(self):
        uninstall_script = os.path.join(os.path.dirname(__file__), "uninstall.sh")
        if os.path.exists(uninstall_script):
            subprocess.Popen(["bash", uninstall_script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        QApplication.quit()

    def _toggle_overlay(self, enabled):
        self._set_overlay_enabled(enabled)

    def _set_overlay_enabled(self, enabled):
        self.overlay_enabled = enabled
        if enabled:
            self.show()
            self.raise_()
        else:
            self.hide()

        if hasattr(self, "toggle_overlay_action"):
            self.toggle_overlay_action.setText("Disable overlay" if enabled else "Enable overlay")
            self.toggle_overlay_action.setChecked(enabled)

        self._update_tray_tooltip()

    def closeEvent(self, event):
        self.cleanup()
        event.accept()

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key_Escape:
            QApplication.quit()
        elif Qt.Key_1 <= key <= Qt.Key_9:
            names = list(self.presets.keys())
            index = key - Qt.Key_1
            if index < len(names):
                self.set_preset(names[index])
        elif key == Qt.Key_P:
            self.grain = 0.0 if self.grain > 0.0 else 0.22
            self.update()


class SettingsWindow(QWidget):
    def __init__(self, overlay):
        super().__init__(overlay, Qt.Window | Qt.WindowStaysOnTopHint)
        self.overlay = overlay
        self.setWindowTitle("CinnaPaper Settings")
        self.setWindowFlags(self.windowFlags() | Qt.Tool)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setFixedSize(520, 280)

        layout = QVBoxLayout(self)
        self.label = QLabel(f"Intensity: {int(self.overlay.intensity * 100)}%", self)
        self.slider = QSlider(Qt.Horizontal, self)
        self.slider.setRange(0, 100)
        self.slider.setValue(int(self.overlay.intensity * 100))
        self.slider.valueChanged.connect(self._on_slider)

        screen_mode_box = QGroupBox("Screen mode", self)
        screen_mode_layout = QHBoxLayout(screen_mode_box)
        self.screen_mode_buttons = {}
        for mode, label in [("all", "All"), ("primary", "Primary"), ("active", "Active")]:
            button = QRadioButton(label, self)
            button.setChecked(self.overlay.screen_mode == mode)
            button.toggled.connect(lambda checked, m=mode: self._on_screen_mode_changed(m, checked))
            self.screen_mode_buttons[mode] = button
            screen_mode_layout.addWidget(button)

        self.auto_schedule_checkbox = QCheckBox("Auto eye comfort scheduling", self)
        self.auto_schedule_checkbox.setChecked(self.overlay.auto_schedule)
        self.auto_schedule_checkbox.toggled.connect(self._on_schedule_toggled)

        layout.addWidget(self.label)
        layout.addWidget(self.slider)
        layout.addWidget(screen_mode_box)
        layout.addWidget(self.auto_schedule_checkbox)

        self.schedule_box = QGroupBox("Auto schedule hours", self)
        schedule_layout = QGridLayout(self.schedule_box)
        self.schedule_hours_checkboxes = {}
        for hour in range(24):
            checkbox = QCheckBox(f"{hour:02d}:00", self)
            checkbox.setChecked(hour in self.overlay.schedule_hours)
            checkbox.toggled.connect(lambda checked, h=hour: self._on_schedule_hour_toggled(h, checked))
            self.schedule_hours_checkboxes[hour] = checkbox
            row = hour // 6
            col = hour % 6
            schedule_layout.addWidget(checkbox, row, col)
        layout.addWidget(self.schedule_box)

        self._update_schedule_visibility()
        self._position_window()

    def _position_window(self):
        screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        if screen is None:
            return

        available = screen.availableGeometry()
        x = available.x() + (available.width() - self.width()) // 2
        y = available.y() + (available.height() - self.height()) // 2
        self.move(x, y)

    def _on_slider(self, value):
        self.label.setText(f"Intensity: {value}%")
        self.overlay.set_intensity(value / 100.0)

    def _on_screen_mode_changed(self, mode, checked):
        if checked:
            self.overlay.set_screen_mode(mode)

    def _on_schedule_toggled(self, enabled):
        self.overlay.set_auto_schedule(enabled)
        self._update_schedule_visibility()

    def _update_schedule_visibility(self):
        self.schedule_box.setVisible(self.auto_schedule_checkbox.isChecked())

    def _on_schedule_hour_toggled(self, hour, enabled):
        if enabled and hour not in self.overlay.schedule_hours:
            self.overlay.schedule_hours.append(hour)
        elif not enabled and hour in self.overlay.schedule_hours:
            self.overlay.schedule_hours.remove(hour)
        self.overlay.schedule_hours.sort()
        self.overlay.save_settings()
        if self.overlay.auto_schedule:
            self.overlay._apply_auto_schedule()
        self.overlay._update_tray_tooltip()


def main():
    parser = argparse.ArgumentParser(description="Fullscreen paper-like overlay for Linux")
    parser.add_argument("--preset", choices=list({"sepia", "cool", "ink", "parchment", "mist", "night", "eyecomfort", "warm", "study", "darkcomfort"}), default=None)
    parser.add_argument("--opacity", type=float, default=None)
    parser.add_argument("--grain", type=float, default=None)
    parser.add_argument("--intensity", type=float, default=None)
    parser.add_argument("--screen-mode", choices=["all", "primary", "active"], default=None)
    parser.add_argument("--auto-schedule", action="store_true")
    args = parser.parse_args()

    if not os.environ.get("DISPLAY") and os.environ.get("QT_QPA_PLATFORM", "") != "offscreen":
        print("No DISPLAY detected. Start an X11 session on Cinnamon/Linux Mint and run the launcher again.", file=sys.stderr)
        return 1

    settings = load_settings()
    preset = args.preset if args.preset is not None else settings["preset"]
    opacity = args.opacity if args.opacity is not None else settings["opacity"]
    grain = args.grain if args.grain is not None else settings["grain"]
    intensity = args.intensity if args.intensity is not None else settings["intensity"]
    screen_mode = args.screen_mode if args.screen_mode is not None else settings["screen_mode"]
    auto_schedule = args.auto_schedule or settings["auto_schedule"]
    schedule_hours = settings.get("schedule_hours", DEFAULT_SETTINGS["schedule_hours"])
    day_preset = settings.get("day_preset", settings["preset"])

    if auto_schedule and preset != "eyecomfort":
        day_preset = preset
    if auto_schedule and is_night_time():
        preset = "eyecomfort"

    server_name = "CinnaPaperOverlay"
    send_quit_to_existing_instance(server_name)
    time.sleep(0.15)

    app = QApplication(sys.argv)
    app.setApplicationName("Paper Overlay")
    app.setQuitOnLastWindowClosed(False)

    server_name = "CinnaPaperOverlay"
    if send_quit_to_existing_instance(server_name):
        timeout = time.time() + 1.0
        while time.time() < timeout:
            test_socket = QLocalSocket()
            test_socket.connectToServer(server_name, QIODevice.WriteOnly)
            if not test_socket.waitForConnected(150):
                break
            test_socket.close()
            time.sleep(0.1)

    window = PaperOverlay(
        preset=preset,
        opacity=opacity,
        grain=grain,
        intensity=intensity,
        screen_mode=screen_mode,
        auto_schedule=auto_schedule,
        day_preset=day_preset,
        schedule_hours=schedule_hours,
    )
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
