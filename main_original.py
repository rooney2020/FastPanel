import sys
import os
import re
import json
import signal
import subprocess
import uuid
import pty
import select
import errno
import fcntl
import calendar
import datetime
import urllib.request
import urllib.parse
import threading
import configparser
import glob as glob_mod
import ctypes
import ctypes.util
import argparse

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFrame, QScrollArea, QLineEdit, QComboBox,
    QCheckBox, QTextEdit, QDialog, QFormLayout, QSpinBox,
    QGraphicsDropShadowEffect, QGraphicsOpacityEffect, QSizePolicy, QFileDialog, QMenu,
    QStackedWidget, QStackedLayout, QSystemTrayIcon, QAction
)
from PyQt5.QtCore import Qt, QPoint, QRect, QThread, QObject, pyqtSignal, QTimer, QPropertyAnimation, QEasingCurve
from PyQt5.QtGui import QFont, QPainter, QColor, QPixmap, QIcon, QFontMetrics, QPen, QPolygon, QIntValidator, QCursor

GRID_SIZE = 20
MIN_W = 260
MIN_H = 140
PANEL_PADDING = 60
PARAM_PATTERN = re.compile(r'\(\$\)')
import html as _html_mod

_CSI_RE_B = re.compile(rb'\x1b\[([0-9;?]*)([A-Za-z@`])')
_NON_CSI_B = re.compile(
    rb'\x1b(?:'
    rb'\][^\x07\x1b]*(?:\x07|\x1b\\)'   # OSC
    rb'|[()][A-Z0-9]'                   # charset
    rb'|[>=<]'                           # keypad/cursor
    rb'|[^[\]])'                         # other single-char
    rb'|\x07|\r'
)
_CTRL_RE = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')
_SGR_RE = re.compile(r'\x1b\[([0-9;]*)m')

def _filter_csi(m):
    return m.group(0) if m.group(2) == b'm' else b""

def _clean_pty(raw: bytes, keep_color=False) -> str:
    if keep_color:
        clean = _CSI_RE_B.sub(_filter_csi, raw)
    else:
        clean = _CSI_RE_B.sub(b"", raw)
    clean = _NON_CSI_B.sub(b"", clean)
    text = clean.decode("utf-8", errors="replace")
    return _CTRL_RE.sub("", text)

_TC16 = {
    0: '#45475a', 1: '#f38ba8', 2: '#a6e3a1', 3: '#f9e2af',
    4: '#89b4fa', 5: '#cba6f7', 6: '#94e2d5', 7: '#bac2de',
    8: '#585b70', 9: '#f38ba8', 10: '#a6e3a1', 11: '#f9e2af',
    12: '#89b4fa', 13: '#cba6f7', 14: '#94e2d5', 15: '#a6adc8',
}

def _c256(n):
    if n < 16: return _TC16.get(n, '')
    if n < 232:
        n -= 16; return f'#{(n//36)*51:02x}{((n%36)//6)*51:02x}{(n%6)*51:02x}'
    v = 8 + (n - 232) * 10; return f'#{v:02x}{v:02x}{v:02x}'

def _ansi_to_html(text: str) -> str:
    parts = []; spans = 0; pos = 0
    for m in _SGR_RE.finditer(text):
        parts.append(_html_mod.escape(text[pos:m.start()]))
        pos = m.end()
        codes = [int(c) for c in m.group(1).split(';') if c] if m.group(1) else [0]
        styles = []; i = 0
        while i < len(codes):
            c = codes[i]
            if c == 0:
                parts.append('</span>' * spans); spans = 0
            elif c == 1: styles.append('font-weight:bold')
            elif c == 3: styles.append('font-style:italic')
            elif c == 4: styles.append('text-decoration:underline')
            elif 30 <= c <= 37:
                cl = _TC16.get(c - 30, ''); cl and styles.append(f'color:{cl}')
            elif 40 <= c <= 47:
                cl = _TC16.get(c - 40, ''); cl and styles.append(f'background-color:{cl}')
            elif 90 <= c <= 97:
                cl = _TC16.get(c - 90 + 8, ''); cl and styles.append(f'color:{cl}')
            elif c == 38 and i + 2 < len(codes) and codes[i+1] == 5:
                cl = _c256(codes[i+2]); cl and styles.append(f'color:{cl}'); i += 2
            elif c == 48 and i + 2 < len(codes) and codes[i+1] == 5:
                cl = _c256(codes[i+2]); cl and styles.append(f'background-color:{cl}'); i += 2
            elif c == 38 and i + 4 < len(codes) and codes[i+1] == 2:
                styles.append(f'color:#{codes[i+2]:02x}{codes[i+3]:02x}{codes[i+4]:02x}'); i += 4
            elif c == 48 and i + 4 < len(codes) and codes[i+1] == 2:
                styles.append(f'background-color:#{codes[i+2]:02x}{codes[i+3]:02x}{codes[i+4]:02x}'); i += 4
            i += 1
        if styles:
            parts.append(f'<span style="{";".join(styles)}">'); spans += 1
    parts.append(_html_mod.escape(text[pos:]))
    parts.append('</span>' * spans)
    return ''.join(parts)

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(_BASE_DIR, "data.json")
ARROW_PATH = os.path.join(_BASE_DIR, "arrow_down.png")
CHECK_PATH = os.path.join(_BASE_DIR, "check.svg")

TYPE_CMD = "cmd"
TYPE_CMD_WINDOW = "cmd_window"
TYPE_SHORTCUT = "shortcut"
TYPE_CALENDAR = "calendar"
TYPE_WEATHER = "weather"
TYPE_DOCK = "dock"
TYPE_TODO = "todo"
TYPE_CLOCK = "clock"
TYPE_MONITOR = "monitor"
TYPE_LAUNCHER = "launcher"
TYPE_NOTE = "note"
TYPE_QUICKACTION = "quickaction"
TYPE_MEDIA = "media"
TYPE_CLIPBOARD = "clipboard"
TYPE_TIMER = "timer"
TYPE_GALLERY = "gallery"
TYPE_SYSINFO = "sysinfo"
TYPE_BOOKMARK = "bookmark"
TYPE_CALC = "calc"
TYPE_TRASH = "trash"
TYPE_RSS = "rss"
TYPE_LABELS = {TYPE_CMD: "CMD", TYPE_CMD_WINDOW: "CMD窗口", TYPE_SHORTCUT: "快捷方式",
               TYPE_CALENDAR: "日历", TYPE_WEATHER: "天气", TYPE_DOCK: "Dock栏", TYPE_TODO: "待办",
               TYPE_CLOCK: "时钟", TYPE_MONITOR: "系统监控", TYPE_LAUNCHER: "应用启动器",
               TYPE_NOTE: "便签", TYPE_QUICKACTION: "快捷操作",
               TYPE_MEDIA: "媒体控制", TYPE_CLIPBOARD: "剪贴板", TYPE_TIMER: "计时器",
               TYPE_GALLERY: "相册", TYPE_SYSINFO: "系统信息",
               TYPE_BOOKMARK: "书签", TYPE_CALC: "计算器", TYPE_TRASH: "回收站",
               TYPE_RSS: "RSS"}

MONITOR_SUB_CPU = "cpu"
MONITOR_SUB_MEM = "memory"
MONITOR_SUB_DISK = "disk"
MONITOR_SUB_NET = "network"
MONITOR_SUB_ALL = "all"
MONITOR_SUB_LABELS = {
    MONITOR_SUB_CPU: "CPU", MONITOR_SUB_MEM: "内存",
    MONITOR_SUB_DISK: "磁盘", MONITOR_SUB_NET: "网络",
    MONITOR_SUB_ALL: "综合概览",
}

CLOCK_SUB_CLOCK = "clock"
CLOCK_SUB_WORLD = "world"
CLOCK_SUB_STOPWATCH = "stopwatch"
CLOCK_SUB_TIMER = "timer"
CLOCK_SUB_ALARM = "alarm"
CLOCK_SUB_LABELS = {CLOCK_SUB_CLOCK: "时钟", CLOCK_SUB_WORLD: "世界时钟",
                    CLOCK_SUB_STOPWATCH: "秒表", CLOCK_SUB_TIMER: "计时器",
                    CLOCK_SUB_ALARM: "闹钟"}

SUB_APP = "application"
SUB_FILE = "file"
SUB_SCRIPT = "script"
SUB_LABELS = {SUB_APP: "应用程序", SUB_FILE: "文件", SUB_SCRIPT: "脚本"}

THEMES = {
    "Catppuccin Mocha": {
        "base": "#1e1e2e", "mantle": "#181825", "crust": "#11111b",
        "surface0": "#313244", "surface1": "#45475a", "surface2": "#585b70",
        "overlay0": "#6c7086", "text": "#cdd6f4", "subtext0": "#a6adc8",
        "blue": "#89b4fa", "sky": "#89dceb", "teal": "#94e2d5",
        "green": "#a6e3a1", "red": "#f38ba8", "peach": "#fab387",
        "lavender": "#b4befe", "yellow": "#f9e2af", "mauve": "#cba6f7",
    },
    "Catppuccin Latte": {
        "base": "#eff1f5", "mantle": "#e6e9ef", "crust": "#dce0e8",
        "surface0": "#ccd0da", "surface1": "#bcc0cc", "surface2": "#acb0be",
        "overlay0": "#9ca0b0", "text": "#4c4f69", "subtext0": "#6c6f85",
        "blue": "#1e66f5", "sky": "#04a5e5", "teal": "#179299",
        "green": "#40a02b", "red": "#d20f39", "peach": "#fe640b",
        "lavender": "#7287fd", "yellow": "#df8e1d", "mauve": "#8839ef",
    },
    "Nord": {
        "base": "#2e3440", "mantle": "#242933", "crust": "#1d2128",
        "surface0": "#3b4252", "surface1": "#434c5e", "surface2": "#4c566a",
        "overlay0": "#616e88", "text": "#eceff4", "subtext0": "#d8dee9",
        "blue": "#81a1c1", "sky": "#88c0d0", "teal": "#8fbcbb",
        "green": "#a3be8c", "red": "#bf616a", "peach": "#d08770",
        "lavender": "#b48ead", "yellow": "#ebcb8b", "mauve": "#b48ead",
    },
    "Dracula": {
        "base": "#282a36", "mantle": "#21222c", "crust": "#191a21",
        "surface0": "#343746", "surface1": "#44475a", "surface2": "#585b6e",
        "overlay0": "#6272a4", "text": "#f8f8f2", "subtext0": "#bfbfbf",
        "blue": "#8be9fd", "sky": "#8be9fd", "teal": "#8be9fd",
        "green": "#50fa7b", "red": "#ff5555", "peach": "#ffb86c",
        "lavender": "#bd93f9", "yellow": "#f1fa8c", "mauve": "#bd93f9",
    },
    "One Dark": {
        "base": "#282c34", "mantle": "#21252b", "crust": "#1b1f27",
        "surface0": "#31353f", "surface1": "#3e4451", "surface2": "#4b5263",
        "overlay0": "#636d83", "text": "#abb2bf", "subtext0": "#828997",
        "blue": "#61afef", "sky": "#56b6c2", "teal": "#56b6c2",
        "green": "#98c379", "red": "#e06c75", "peach": "#d19a66",
        "lavender": "#c678dd", "yellow": "#e5c07b", "mauve": "#c678dd",
    },
}

SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.json")

def _load_settings():
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _save_settings(s):
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(s, ensure_ascii=False, indent=2, fp=f)
    except Exception:
        pass

_settings = _load_settings()
C = dict(THEMES.get(_settings.get("theme", "Catppuccin Mocha"), THEMES["Catppuccin Mocha"]))

_DESKTOP_MODE = False


# ---------------------------------------------------------------------------
# Platform Abstraction Layer for Desktop Mode
# ---------------------------------------------------------------------------
class DesktopBackend:
    @staticmethod
    def create():
        if sys.platform == 'linux':
            session = os.environ.get('XDG_SESSION_TYPE', 'x11')
            if session == 'wayland':
                return _WaylandDesktopBackend()
            return _X11DesktopBackend()
        elif sys.platform == 'win32':
            return _WindowsDesktopBackend()
        elif sys.platform == 'darwin':
            return _MacDesktopBackend()
        return _FallbackDesktopBackend()

    def setup_window(self, window):
        raise NotImplementedError

    def get_available_geometry(self):
        wa = self._read_net_workarea()
        if wa:
            return wa
        screens = QApplication.screens()
        if len(screens) <= 1:
            return QApplication.primaryScreen().availableGeometry()
        union = QRect()
        for s in screens:
            union = union.united(s.availableGeometry())
        return union

    def get_full_geometry(self):
        return QApplication.primaryScreen().virtualGeometry()

    def get_screens_info(self):
        return [(s.name(), s.geometry(), s.availableGeometry()) for s in QApplication.screens()]

    def _read_net_workarea(self):
        if sys.platform != 'linux':
            return None
        try:
            out = subprocess.check_output(
                ["xprop", "-root", "_NET_WORKAREA"],
                timeout=2, stderr=subprocess.DEVNULL
            ).decode().strip()
            parts = out.split("=", 1)
            if len(parts) < 2:
                return None
            vals = [int(v.strip()) for v in parts[1].split(",")[:4]]
            if len(vals) == 4:
                return QRect(vals[0], vals[1], vals[2], vals[3])
        except Exception:
            pass
        return None

    @property
    def name(self):
        return "Unknown"


class _X11DesktopBackend(DesktopBackend):
    _ding_was_enabled = False

    @property
    def name(self):
        return "X11"

    def setup_window(self, window):
        self._suppress_gnome_desktop()
        window.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnBottomHint
            | Qt.Tool
        )
        window.setAttribute(Qt.WA_X11NetWmWindowTypeDesktop, True)
        window.setAttribute(Qt.WA_ShowWithoutActivating, True)
        geo = self.get_full_geometry()
        window.setGeometry(geo)
        QTimer.singleShot(100, lambda: self._set_x11_hints(window))
        self._window = window
        self._restack_timer = QTimer()
        self._restack_timer.timeout.connect(lambda: self._restack_window(window))
        self._restack_timer.start(3000)

    def _suppress_gnome_desktop(self):
        try:
            r = subprocess.run(
                ["gnome-extensions", "info", "ding@rastersoft.com"],
                capture_output=True, text=True, timeout=3)
            if "ENABLED" in r.stdout.upper():
                _X11DesktopBackend._ding_was_enabled = True
                subprocess.run(
                    ["gnome-extensions", "disable", "ding@rastersoft.com"],
                    capture_output=True, timeout=3)
                print("[Desktop] Disabled ding extension", flush=True)
        except Exception:
            pass

    @staticmethod
    def restore_gnome_desktop():
        if _X11DesktopBackend._ding_was_enabled:
            try:
                subprocess.run(
                    ["gnome-extensions", "enable", "ding@rastersoft.com"],
                    capture_output=True, timeout=3)
                print("[Desktop] Restored ding extension", flush=True)
            except Exception:
                pass

    def _restack_window(self, window):
        try:
            wid = int(window.winId())
            subprocess.run(
                ["xprop", "-id", str(wid),
                 "-f", "_NET_WM_WINDOW_TYPE", "32a",
                 "-set", "_NET_WM_WINDOW_TYPE", "_NET_WM_WINDOW_TYPE_DESKTOP"],
                capture_output=True, timeout=2)
        except Exception:
            pass

    def _set_x11_hints(self, window):
        try:
            result = subprocess.run(
                ["xprop", "-id", str(int(window.winId())),
                 "-f", "_NET_WM_WINDOW_TYPE", "32a",
                 "-set", "_NET_WM_WINDOW_TYPE", "_NET_WM_WINDOW_TYPE_DESKTOP"],
                capture_output=True, timeout=3
            )
        except Exception:
            pass


class _WaylandDesktopBackend(DesktopBackend):
    @property
    def name(self):
        return "Wayland"

    def setup_window(self, window):
        window.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnBottomHint
        )
        window.setAttribute(Qt.WA_ShowWithoutActivating, True)
        geo = self.get_full_geometry()
        window.setGeometry(geo)


class _WindowsDesktopBackend(DesktopBackend):
    @property
    def name(self):
        return "Windows"

    def setup_window(self, window):
        window.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnBottomHint
            | Qt.Tool
        )
        window.setAttribute(Qt.WA_ShowWithoutActivating, True)
        geo = self.get_full_geometry()
        window.setGeometry(geo)
        QTimer.singleShot(200, lambda: self._embed_in_desktop(window))

    def _embed_in_desktop(self, window):
        try:
            user32 = ctypes.windll.user32
            progman = user32.FindWindowW("Progman", None)
            user32.SendMessageTimeoutW(progman, 0x052C, 0, 0, 0x0, 1000, ctypes.byref(ctypes.c_ulong()))
            workerw = 0

            @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
            def enum_cb(hwnd, lparam):
                nonlocal workerw
                p = ctypes.c_void_p()
                user32.FindWindowExW(hwnd, 0, "SHELLDLL_DefView", None)
                if user32.FindWindowExW(hwnd, 0, "SHELLDLL_DefView", None):
                    workerw = user32.FindWindowExW(0, hwnd, "WorkerW", None)
                return True

            user32.EnumWindows(enum_cb, 0)
            if workerw:
                user32.SetParent(int(window.winId()), workerw)
        except Exception:
            pass


class _MacDesktopBackend(DesktopBackend):
    @property
    def name(self):
        return "macOS"

    def setup_window(self, window):
        window.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnBottomHint
            | Qt.Tool
        )
        window.setAttribute(Qt.WA_ShowWithoutActivating, True)
        geo = self.get_full_geometry()
        window.setGeometry(geo)
        try:
            import objc
            ns_view = int(window.winId())
            ns_window = objc.objc_msgSend(ns_view, objc.sel_registerName("window"))
            kCGDesktopWindowLevel = -2147483623
            objc.objc_msgSend(ns_window, objc.sel_registerName("setLevel:"), kCGDesktopWindowLevel)
        except Exception:
            pass


class _FallbackDesktopBackend(DesktopBackend):
    @property
    def name(self):
        return "Fallback"

    def setup_window(self, window):
        window.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnBottomHint
        )
        geo = self.get_full_geometry()
        window.setGeometry(geo)


# ---------------------------------------------------------------------------
# Autostart management
# ---------------------------------------------------------------------------
_AUTOSTART_DIR = os.path.expanduser("~/.config/autostart")
_AUTOSTART_FILE = os.path.join(_AUTOSTART_DIR, "fastpanel.desktop")
_APP_DESKTOP_DIR = os.path.expanduser("~/.local/share/applications")
_APP_DESKTOP_FILE = os.path.join(_APP_DESKTOP_DIR, "fastpanel.desktop")

def _desktop_entry_content(autostart=False):
    main_py = os.path.abspath(__file__)
    icon = os.path.join(os.path.dirname(main_py), "fastpanel.svg")
    entry = f"""[Desktop Entry]
Type=Application
Name=FastPanel
Comment=Desktop widget engine
Exec=python3 {main_py} --desktop
Icon={icon}
Terminal=false
Categories=Utility;
StartupNotify=false
"""
    if autostart:
        entry += "X-GNOME-Autostart-enabled=true\n"
    return entry

def _is_autostart_enabled():
    return os.path.isfile(_AUTOSTART_FILE)

def _set_autostart(enabled: bool):
    if enabled:
        os.makedirs(_AUTOSTART_DIR, exist_ok=True)
        with open(_AUTOSTART_FILE, "w") as f:
            f.write(_desktop_entry_content(autostart=True))
    else:
        if os.path.isfile(_AUTOSTART_FILE):
            os.remove(_AUTOSTART_FILE)

def _install_desktop_entry():
    os.makedirs(_APP_DESKTOP_DIR, exist_ok=True)
    with open(_APP_DESKTOP_FILE, "w") as f:
        f.write(_desktop_entry_content())

# ---------------------------------------------------------------------------
# Global Hotkey Manager (X11 via python-xlib, fallback: noop)
# ---------------------------------------------------------------------------
class _HotkeySignalBridge(QObject):
    triggered = pyqtSignal(str)

class _HotkeyManager:
    _instance = None

    def __init__(self):
        self._bindings: dict[str, callable] = {}
        self._running = False
        self._bridge = _HotkeySignalBridge()
        self._bridge.triggered.connect(self._fire)

    @classmethod
    def create(cls):
        if cls._instance:
            return cls._instance
        if sys.platform == "linux":
            try:
                inst = _X11HotkeyManager()
                cls._instance = inst
                return inst
            except Exception:
                pass
        inst = _HotkeyManager()
        cls._instance = inst
        return inst

    def register(self, key_str: str, callback: callable):
        self._bindings[key_str] = callback

    def unregister(self, key_str: str):
        self._bindings.pop(key_str, None)

    def start(self):
        pass

    def stop(self):
        self._running = False

    def _fire(self, key_str):
        cb = self._bindings.get(key_str)
        if cb:
            print(f"[Hotkey] Executing callback for: {key_str}", flush=True)
            cb()


class _X11HotkeyManager(_HotkeyManager):
    _MOD_MAP = {
        "ctrl": "control", "control": "control",
        "alt": "mod1", "mod1": "mod1",
        "shift": "shift",
        "super": "mod4", "win": "mod4", "mod4": "mod4",
    }

    def __init__(self):
        super().__init__()
        from Xlib import X, display as xdisplay, XK
        self._X = X
        self._XK = XK
        self._display = xdisplay.Display()
        self._display.set_error_handler(self._x_error_handler)
        self._root = self._display.screen().root
        self._grabbed_keys: list[tuple] = []
        self._thread = None
        self._grab_failures: list[str] = []

    @staticmethod
    def _x_error_handler(err, *args):
        pass

    def _parse_hotkey(self, key_str: str):
        from Xlib import X, XK
        parts = [p.strip().lower() for p in key_str.split("+")]
        mod_mask = 0
        keycode = 0
        mod_bits = {"control": X.ControlMask, "shift": X.ShiftMask,
                     "mod1": X.Mod1Mask, "mod4": X.Mod4Mask}
        for p in parts:
            mapped = self._MOD_MAP.get(p)
            if mapped and mapped in mod_bits:
                mod_mask |= mod_bits[mapped]
            else:
                keysym = XK.string_to_keysym(p.capitalize() if len(p) == 1 else p)
                if keysym == 0:
                    keysym = XK.string_to_keysym(p)
                if keysym == 0:
                    _sym_map = {
                        "f1": "F1", "f2": "F2", "f3": "F3", "f4": "F4",
                        "f5": "F5", "f6": "F6", "f7": "F7", "f8": "F8",
                        "f9": "F9", "f10": "F10", "f11": "F11", "f12": "F12",
                        "space": "space", "return": "Return", "enter": "Return",
                        "escape": "Escape", "esc": "Escape", "tab": "Tab",
                        "backspace": "BackSpace", "delete": "Delete",
                        "up": "Up", "down": "Down", "left": "Left", "right": "Right",
                        "home": "Home", "end": "End", "pageup": "Prior", "pagedown": "Next",
                    }
                    mapped_name = _sym_map.get(p, p)
                    keysym = XK.string_to_keysym(mapped_name)
                if keysym != 0:
                    keycode = self._display.keysym_to_keycode(keysym)
        return keycode, mod_mask

    def register(self, key_str: str, callback: callable):
        super().register(key_str, callback)
        keycode, mod_mask = self._parse_hotkey(key_str)
        if keycode == 0:
            self._grab_failures.append(key_str)
            print(f"[Hotkey] Failed to parse: {key_str}", flush=True)
            return
        from Xlib import X
        try:
            for extra in [0, X.Mod2Mask, X.LockMask, X.Mod2Mask | X.LockMask]:
                self._root.grab_key(keycode, mod_mask | extra, True,
                                    X.GrabModeAsync, X.GrabModeAsync)
            self._grabbed_keys.append((keycode, mod_mask, key_str))
            self._display.sync()
            print(f"[Hotkey] Registered: {key_str} (keycode={keycode}, mask={mod_mask})", flush=True)
        except Exception as e:
            self._grab_failures.append(key_str)
            print(f"[Hotkey] Grab failed for {key_str}: {e}", flush=True)

    def unregister(self, key_str: str):
        super().unregister(key_str)
        to_remove = [(kc, mm, ks) for kc, mm, ks in self._grabbed_keys if ks == key_str]
        from Xlib import X
        for kc, mm, _ks in to_remove:
            for extra in [0, X.Mod2Mask, X.LockMask, X.Mod2Mask | X.LockMask]:
                try:
                    self._root.ungrab_key(kc, mm | extra)
                except Exception:
                    pass
        self._grabbed_keys = [(kc, mm, ks) for kc, mm, ks in self._grabbed_keys if ks != key_str]
        self._display.flush()

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._event_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        from Xlib import X
        for kc, mm, _ks in self._grabbed_keys:
            for extra in [0, X.Mod2Mask, X.LockMask, X.Mod2Mask | X.LockMask]:
                try:
                    self._root.ungrab_key(kc, mm | extra)
                except Exception:
                    pass
        self._grabbed_keys.clear()
        self._display.flush()

    def _event_loop(self):
        from Xlib import X
        self._root.change_attributes(event_mask=X.KeyPressMask)
        while self._running:
            try:
                count = self._display.pending_events()
                if count == 0:
                    import time
                    time.sleep(0.05)
                    continue
                ev = self._display.next_event()
                if ev.type == X.KeyPress:
                    clean_mask = ev.state & ~(X.Mod2Mask | X.LockMask)
                    matched = False
                    for kc, mm, ks in self._grabbed_keys:
                        if ev.detail == kc and clean_mask == mm:
                            print(f"[Hotkey] Fired: {ks}", flush=True)
                            self._bridge.triggered.emit(ks)
                            matched = True
                            break
                    if not matched:
                        print(f"[Hotkey] Unmatched key event: detail={ev.detail} state={ev.state} clean={clean_mask}", flush=True)
            except Exception:
                if not self._running:
                    break
                import time
                time.sleep(0.1)


_HOLIDAY_CACHE = {}
_HOLIDAY_CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".holiday_cache")

def _load_holidays_for_year(year):
    if year in _HOLIDAY_CACHE:
        return _HOLIDAY_CACHE[year]
    os.makedirs(_HOLIDAY_CACHE_DIR, exist_ok=True)
    cache_file = os.path.join(_HOLIDAY_CACHE_DIR, f"{year}.json")
    data = None
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            pass
    if data is None:
        try:
            url = f"https://cdn.jsdelivr.net/npm/chinese-days/dist/years/{year}.json"
            req = urllib.request.Request(url, headers={"User-Agent": "FastPanel/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(data, ensure_ascii=False, indent=2, fp=f)
        except Exception:
            data = {}
    parsed = {"holidays": {}, "workdays": set()}
    for k, v in data.get("holidays", {}).items():
        parts = v.split(",")
        parsed["holidays"][k] = parts[1] if len(parts) >= 2 else parts[0]
    for k in data.get("workdays", {}):
        parsed["workdays"].add(k)
    _HOLIDAY_CACHE[year] = parsed
    return parsed


def snap(val, grid=GRID_SIZE):
    return round(val / grid) * grid


def count_params(cmd):
    return len(PARAM_PATTERN.findall(cmd))


def _confirm_dialog(parent, title, text):
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    dlg.setFixedWidth(340)
    dlg.setStyleSheet(_dialog_style())
    lay = QVBoxLayout(dlg)
    lay.setSpacing(16)
    lay.setContentsMargins(24, 20, 24, 20)
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    lbl.setStyleSheet(f"color: {C['text']}; font-size: 14px;")
    lay.addWidget(lbl)
    btn_row = QHBoxLayout()
    btn_row.addStretch()
    cancel_btn = QPushButton("取消")
    cancel_btn.setObjectName("cancelBtn")
    cancel_btn.clicked.connect(dlg.reject)
    btn_row.addWidget(cancel_btn)
    ok_btn = QPushButton("确认")
    ok_btn.setObjectName("okBtn")
    ok_btn.clicked.connect(dlg.accept)
    btn_row.addWidget(ok_btn)
    lay.addLayout(btn_row)
    return dlg.exec_() == QDialog.Accepted


def _input_dialog(parent, title, label, default_text=""):
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    dlg.setFixedWidth(360)
    dlg.setStyleSheet(_dialog_style())
    lay = QVBoxLayout(dlg)
    lay.setSpacing(12)
    lay.setContentsMargins(24, 20, 24, 20)
    lbl = QLabel(label)
    lbl.setStyleSheet(f"color: {C['text']}; font-size: 14px;")
    lay.addWidget(lbl)
    edit = QLineEdit(default_text)
    lay.addWidget(edit)
    btn_row = QHBoxLayout()
    btn_row.addStretch()
    cancel_btn = QPushButton("取消")
    cancel_btn.setObjectName("cancelBtn")
    cancel_btn.clicked.connect(dlg.reject)
    btn_row.addWidget(cancel_btn)
    ok_btn = QPushButton("确定")
    ok_btn.setObjectName("okBtn")
    ok_btn.clicked.connect(dlg.accept)
    btn_row.addWidget(ok_btn)
    lay.addLayout(btn_row)
    if dlg.exec_() == QDialog.Accepted:
        return True, edit.text()
    return False, ""


def _dialog_style():
    return f"""
        QDialog {{ background: {C['base']}; }}
        #heading {{ color: {C['lavender']}; font-size: 18px; font-weight: bold; }}
        QLabel {{ color: {C['subtext0']}; font-size: 13px; }}
        QLineEdit {{
            background: {C['surface0']}; color: {C['text']};
            border: 1px solid {C['surface1']}; border-radius: 8px;
            padding: 8px 14px; font-size: 13px;
            selection-background-color: {C['blue']};
        }}
        QLineEdit:focus {{ border: 1px solid {C['blue']}; }}
        QComboBox {{
            background: {C['surface0']}; color: {C['text']};
            border: 1px solid {C['surface1']}; border-radius: 8px;
            padding: 8px 14px; font-size: 13px;
        }}
        QComboBox::drop-down {{
            subcontrol-origin: padding; subcontrol-position: center right;
            width: 28px; border: none; background: transparent;
        }}
        QComboBox::down-arrow {{ image: url({ARROW_PATH}); width: 12px; height: 8px; }}
        QComboBox QAbstractItemView {{
            background: {C['surface0']}; color: {C['text']};
            selection-background-color: {C['surface1']};
            border: 1px solid {C['surface1']}; outline: none;
        }}
        QCheckBox {{ color: {C['subtext0']}; font-size: 13px; spacing: 8px; }}
        QCheckBox::indicator {{
            width: 18px; height: 18px; border-radius: 4px;
            border: 2px solid {C['surface2']}; background: transparent;
        }}
        QCheckBox::indicator:hover {{ border-color: {C['blue']}; }}
        QCheckBox::indicator:checked {{
            border: 2px solid {C['blue']}; background: transparent;
            image: url({CHECK_PATH});
        }}
        #cancelBtn {{
            background: {C['surface1']}; color: {C['text']};
            border: none; border-radius: 8px; padding: 8px 24px; font-size: 13px;
        }}
        #cancelBtn:hover {{ background: {C['surface2']}; }}
        #okBtn {{
            background: {C['blue']}; color: {C['crust']};
            border: none; border-radius: 8px; padding: 8px 28px;
            font-size: 13px; font-weight: bold;
        }}
        #okBtn:hover {{ background: {C['lavender']}; }}
    """


def _scrollbar_style(width=6):
    return f"""
        QScrollBar:vertical {{
            width: {width}px; background: transparent; border: none; margin: 0;
        }}
        QScrollBar::handle:vertical {{
            background: {C['surface1']}; border-radius: {width // 2}px; min-height: 20px;
        }}
        QScrollBar::handle:vertical:hover {{ background: {C['surface2']}; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
        QScrollBar:horizontal {{
            height: {width}px; background: transparent; border: none; margin: 0;
        }}
        QScrollBar::handle:horizontal {{
            background: {C['surface1']}; border-radius: {width // 2}px; min-width: 20px;
        }}
        QScrollBar::handle:horizontal:hover {{ background: {C['surface2']}; }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
        QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: transparent; }}
    """


def _hex_to_rgba(hex_color, alpha):
    h = hex_color.lstrip('#')
    return f"rgba({int(h[:2],16)},{int(h[2:4],16)},{int(h[4:6],16)},{alpha})"

def _bg(color_key):
    """Get a background color with component opacity applied."""
    opa = _settings.get("comp_opacity", 90) / 100.0
    a = int(opa * 255)
    return _hex_to_rgba(C[color_key], a)

def _comp_style():
    opa = _settings.get("comp_opacity", 90) / 100.0
    a = int(opa * 255)
    bg = _hex_to_rgba(C['base'], a)
    crust_bg = _hex_to_rgba(C['crust'], a)
    s0_bg = _hex_to_rgba(C['surface0'], a)
    s1_bg = _hex_to_rgba(C['surface1'], a)
    border = _hex_to_rgba(C['surface0'], min(a + 30, 255))
    hover = _hex_to_rgba(C['surface2'], min(a + 50, 255))
    return f"""
    QFrame[compWidget="true"] {{
        background: {bg}; border: 1px solid {border}; border-radius: 12px;
    }}
    QFrame[compWidget="true"]:hover {{ border: 1px solid {hover}; }}
    #badge {{
        background: {C['blue']}; color: {C['crust']};
        border-radius: 4px; font-size: 10px; font-weight: bold; padding: 0 8px;
    }}
    #badgeCmdWin {{
        background: {C['mauve']}; color: {C['crust']};
        border-radius: 4px; font-size: 9px; font-weight: bold; padding: 0 6px;
    }}
    #badgeShortcut {{
        background: {C['peach']}; color: {C['crust']};
        border-radius: 4px; font-size: 9px; font-weight: bold; padding: 0 6px;
    }}
    #title {{ color: {C['text']}; font-size: 14px; font-weight: bold; }}
    #runBtn {{
        background: {C['green']}; color: {C['crust']};
        border: none; border-radius: 6px; padding: 0 14px;
        font-weight: bold; font-size: 12px;
    }}
    #runBtn:hover {{ background: {C['teal']}; }}
    #runBtn[running="true"] {{ background: {C['red']}; }}
    #runBtn[running="true"]:hover {{ background: {C['peach']}; }}
    #cmdFrame {{
        background: {crust_bg}; border-radius: 8px;
    }}
    #prompt {{
        color: {C['green']};
        font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace;
        font-size: 12px; font-weight: bold;
    }}
    #cmdText {{
        color: {C['subtext0']};
        font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace;
        font-size: 12px;
    }}
    #paramInput {{
        background: {crust_bg}; color: {C['yellow']};
        border: 1px solid {border}; border-radius: 6px;
        padding: 5px 10px;
        font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace;
        font-size: 12px;
    }}
    #paramInput:focus {{ border: 1px solid {C['yellow']}; }}
    #output {{
        background: {crust_bg}; color: {C['green']};
        border: 1px solid {border}; border-radius: 8px;
        font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace;
        font-size: 11px; padding: 8px;
    }}
    #stdinInput {{
        background: {crust_bg}; color: {C['text']};
        border: 1px solid {border}; border-radius: 6px;
        padding: 4px 8px;
        font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace;
        font-size: 11px;
    }}
    #stdinInput:focus {{ border: 1px solid {C['sky']}; }}
    #stdinInput:disabled {{ color: {C['overlay0']}; }}
    #sendBtn {{
        background: {C['sky']}; color: {C['crust']};
        border: none; border-radius: 6px; font-size: 11px;
        font-weight: bold; padding: 4px;
    }}
    #sendBtn:hover {{ background: {C['teal']}; }}
    #sendBtn:disabled {{ background: {s1_bg}; color: {C['overlay0']}; }}
    #launchBtn {{
        background: {C['peach']}; color: {C['crust']};
        border: none; border-radius: 8px; padding: 10px 24px;
        font-size: 14px; font-weight: bold;
    }}
    #launchBtn:hover {{ background: {C['yellow']}; }}
    #iconLabel {{ background: transparent; }}
    #pathLabel {{
        color: {C['subtext0']};
        font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace;
        font-size: 11px;
    }}
    """


# ---------------------------------------------------------------------------
# Process runner (pty-based)
# ---------------------------------------------------------------------------
class PtyRunner(QThread):
    line_ready = pyqtSignal(str)
    done = pyqtSignal(int)

    def __init__(self, cmd):
        super().__init__()
        self.cmd = cmd
        self._master_fd = -1
        self._proc = None
        self._stopped = False

    def write_stdin(self, text):
        if self._master_fd >= 0:
            try:
                os.write(self._master_fd, (text + "\n").encode())
            except OSError:
                pass

    def stop(self):
        self._stopped = True
        if self._proc and self._proc.poll() is None:
            try:
                pgid = os.getpgid(self._proc.pid)
                os.killpg(pgid, signal.SIGTERM)
                try:
                    self._proc.wait(timeout=0.5)
                except subprocess.TimeoutExpired:
                    os.killpg(pgid, signal.SIGKILL)
            except (OSError, ProcessLookupError):
                try:
                    self._proc.kill()
                except OSError:
                    pass

    def run(self):
        master_fd = -1
        try:
            master_fd, slave_fd = pty.openpty()
            self._master_fd = master_fd
            flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
            fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

            env = os.environ.copy()
            env.setdefault("TERM", "xterm-256color")
            self._proc = subprocess.Popen(
                self.cmd, shell=True,
                stdin=slave_fd, stdout=slave_fd, stderr=slave_fd,
                preexec_fn=os.setsid, close_fds=True, env=env
            )
            os.close(slave_fd)

            buf = b""
            idle = 0
            while not self._stopped:
                try:
                    ready, _, _ = select.select([master_fd], [], [], 0.05)
                except (ValueError, OSError):
                    break
                if ready:
                    try:
                        chunk = os.read(master_fd, 4096)
                    except OSError as ex:
                        if ex.errno == errno.EIO:
                            break
                        if ex.errno == errno.EAGAIN:
                            continue
                        break
                    if not chunk:
                        break
                    buf += chunk
                    idle = 0
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        self.line_ready.emit(_clean_pty(line, keep_color=True))
                else:
                    idle += 1
                    if buf and idle >= 2:
                        self.line_ready.emit(_clean_pty(buf, keep_color=True))
                        buf = b""
                        idle = 0
                if self._proc.poll() is not None:
                    try:
                        while True:
                            rest = os.read(master_fd, 4096)
                            if not rest:
                                break
                            buf += rest
                    except OSError:
                        pass
                    break
            if buf:
                self.line_ready.emit(_clean_pty(buf, keep_color=True))
            code = self._proc.wait() if self._proc else -1
            if self._stopped:
                code = -15
        except Exception as e:
            self.line_ready.emit(f"错误: {e}")
            code = -1
        finally:
            if master_fd >= 0:
                try:
                    os.close(master_fd)
                except OSError:
                    pass
                self._master_fd = -1
        self.done.emit(code)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------
class ComponentData:
    def __init__(self, name="", comp_type=TYPE_CMD, sub_type=SUB_APP, cmd="", show_output=False,
                 icon="", path="", x=0, y=0, w=300, h=200, uid=None,
                 param_hints=None, param_defaults=None, group_id=None, pre_cmd="",
                 refresh_interval=300):
        self.id = uid or str(uuid.uuid4())
        self.comp_type = comp_type
        self.sub_type = sub_type
        self.name = name
        self.cmd = cmd
        self.show_output = show_output
        self.icon = icon
        self.path = path
        self.x = x
        self.y = y
        self.w = w
        self.h = h
        self.param_hints = param_hints or []
        self.param_defaults = param_defaults or []
        self._group_id = group_id
        self.pre_cmd = pre_cmd
        self.refresh_interval = refresh_interval

    def to_dict(self):
        d = {
            "id": self.id, "type": self.comp_type, "sub_type": self.sub_type,
            "name": self.name, "cmd": self.cmd, "show_output": self.show_output,
            "icon": self.icon, "path": self.path,
            "x": self.x, "y": self.y, "w": self.w, "h": self.h,
        }
        if self.param_hints:
            d["param_hints"] = self.param_hints
        if self.param_defaults:
            d["param_defaults"] = self.param_defaults
        if self._group_id:
            d["group_id"] = self._group_id
        if self.pre_cmd:
            d["pre_cmd"] = self.pre_cmd
        if self.refresh_interval != 300:
            d["refresh_interval"] = self.refresh_interval
        return d

    @staticmethod
    def from_dict(d):
        return ComponentData(
            name=d.get("name", ""), comp_type=d.get("type", TYPE_CMD),
            sub_type=d.get("sub_type", SUB_APP),
            cmd=d.get("cmd", ""), show_output=d.get("show_output", False),
            icon=d.get("icon", ""), path=d.get("path", ""),
            x=d.get("x", 0), y=d.get("y", 0),
            w=d.get("w", 300), h=d.get("h", 200), uid=d.get("id"),
            param_hints=d.get("param_hints", []),
            param_defaults=d.get("param_defaults", []),
            group_id=d.get("group_id"),
            pre_cmd=d.get("pre_cmd", ""),
            refresh_interval=d.get("refresh_interval", 300),
        )


class PanelData:
    def __init__(self, name="默认", uid=None, components=None):
        self.id = uid or str(uuid.uuid4())
        self.name = name
        self.components: list[ComponentData] = components or []

    def to_dict(self):
        return {"id": self.id, "name": self.name,
                "components": [c.to_dict() for c in self.components]}

    @staticmethod
    def from_dict(d):
        comps = [ComponentData.from_dict(c) for c in d.get("components", [])]
        return PanelData(name=d["name"], uid=d.get("id"), components=comps)


# ---------------------------------------------------------------------------
# Drag/Resize mixin
# ---------------------------------------------------------------------------
class DragResizeMixin:
    EDGE_MARGIN = 8

    def init_drag(self):
        self._dragging = False
        self._resizing = False
        self._drag_offset = QPoint()
        self._resize_origin = QPoint()
        self._resize_geo = QRect()
        self._edges = []

    def _detect_edges(self, pos):
        m = self.EDGE_MARGIN
        edges = []
        if pos.x() >= self.width() - m: edges.append("r")
        if pos.y() >= self.height() - m: edges.append("b")
        if pos.x() <= m: edges.append("l")
        if pos.y() <= m: edges.append("t")
        return edges

    def _edge_cursor(self, edges):
        s = set(edges)
        if s == {"r","b"} or s == {"l","t"}: return Qt.SizeFDiagCursor
        if s == {"r","t"} or s == {"l","b"}: return Qt.SizeBDiagCursor
        if s & {"r","l"}: return Qt.SizeHorCursor
        if s & {"t","b"}: return Qt.SizeVerCursor
        return None

    def handle_press(self, e):
        if e.button() != Qt.LeftButton: return False
        if self.property("locked"):
            return False
        edges = self._detect_edges(e.pos())
        if edges:
            self._resizing = True
            self._edges = edges
            self._resize_origin = e.globalPos()
            self._resize_geo = self.geometry()
            return True
        if e.pos().y() < 44:
            self._dragging = True
            self._drag_offset = e.globalPos() - self.pos()
            self._drag_origin = QPoint(self.x(), self.y())
            return True
        return False

    def handle_move(self, e):
        if self._resizing:
            d = e.globalPos() - self._resize_origin
            g = QRect(self._resize_geo)
            pw = self.parent().width() if self.parent() else 9999
            mw, mh = self.minimumWidth(), self.minimumHeight()
            if "r" in self._edges: g.setWidth(min(max(mw, g.width()+d.x()), pw-g.x()))
            if "b" in self._edges: g.setHeight(max(mh, g.height()+d.y()))
            if "l" in self._edges:
                nw = g.width()-d.x()
                if nw >= mw: g.setLeft(max(0, self._resize_geo.left()+d.x()))
            if "t" in self._edges:
                nh = g.height()-d.y()
                if nh >= mh: g.setTop(self._resize_geo.top()+d.y())
            self.setGeometry(g)
            return True
        if self._dragging:
            p = e.globalPos() - self._drag_offset
            par = self.parent()
            pw = par.width() if par else 9999
            safe_top = getattr(par, '_safe_margin_top', 0) if par else 0
            safe_bottom = getattr(par, '_safe_margin_bottom', 0) if par else 0
            ph = par.height() if par else 9999
            p.setX(max(0, min(p.x(), pw-self.width())))
            p.setY(max(safe_top, min(p.y(), ph - safe_bottom - self.height())))
            self.move(p)
            return True
        edges = self._detect_edges(e.pos())
        cur = self._edge_cursor(edges)
        if cur: self.setCursor(cur)
        elif e.pos().y() < 44: self.setCursor(Qt.OpenHandCursor)
        else: self.setCursor(Qt.ArrowCursor)
        return False

    def handle_release(self, e, data):
        if self._dragging:
            x, y = snap(self.x()), snap(self.y())
            par = self.parent()
            pw = par.width() if par else 9999
            safe_top = getattr(par, '_safe_margin_top', 0) if par else 0
            safe_bottom = getattr(par, '_safe_margin_bottom', 0) if par else 0
            ph = par.height() if par else 9999
            x = max(0, min(x, pw-self.width()))
            y = max(safe_top, min(y, ph - safe_bottom - self.height()))
            self.move(x, y)
            data.x, data.y = x, y
            self._dragging = False
            return True
        if self._resizing:
            g = self.geometry()
            mw, mh = self.minimumWidth(), self.minimumHeight()
            g = QRect(snap(g.x()), snap(g.y()), max(mw, snap(g.width())), max(mh, snap(g.height())))
            self.setGeometry(g)
            data.x, data.y = g.x(), g.y()
            data.w, data.h = g.width(), g.height()
            self._resizing = False
            self._edges = []
            return True
        return False


# ---------------------------------------------------------------------------
# Component base
# ---------------------------------------------------------------------------
class CompBase(QFrame, DragResizeMixin):
    delete_requested = pyqtSignal(object)
    edit_requested = pyqtSignal(object)
    copy_requested = pyqtSignal(object)
    geometry_changed = pyqtSignal()

    def __init__(self, data: ComponentData, parent=None):
        super().__init__(parent)
        self.data = data
        self.init_drag()
        self.setProperty("compWidget", "true")
        self.setGeometry(data.x, data.y, data.w, data.h)
        if data.comp_type == TYPE_SHORTCUT:
            self.setMinimumSize(GRID_SIZE * 4, GRID_SIZE * 4)
        elif data.comp_type == TYPE_CALENDAR:
            self.setMinimumSize(GRID_SIZE * 14, GRID_SIZE * 14)
        elif data.comp_type == TYPE_WEATHER:
            self.setMinimumSize(GRID_SIZE * 12, GRID_SIZE * 10)
        elif data.comp_type == TYPE_DOCK:
            self.setMinimumSize(GRID_SIZE * 6, GRID_SIZE * 4)
        elif data.comp_type == TYPE_TODO:
            self.setMinimumSize(GRID_SIZE * 10, GRID_SIZE * 8)
        elif data.comp_type == TYPE_CLOCK:
            self.setMinimumSize(GRID_SIZE * 8, GRID_SIZE * 6)
        elif data.comp_type == TYPE_MONITOR:
            sub = data.cmd.strip() if data.cmd else MONITOR_SUB_ALL
            if sub == MONITOR_SUB_ALL:
                self.setMinimumSize(GRID_SIZE * 20, GRID_SIZE * 16)
            elif sub == MONITOR_SUB_DISK:
                self.setMinimumSize(GRID_SIZE * 16, GRID_SIZE * 8)
            else:
                self.setMinimumSize(GRID_SIZE * 12, GRID_SIZE * 8)
        elif data.comp_type == TYPE_LAUNCHER:
            self.setMinimumSize(GRID_SIZE * 14, GRID_SIZE * 16)
        elif data.comp_type == TYPE_NOTE:
            self.setMinimumSize(GRID_SIZE * 10, GRID_SIZE * 8)
        elif data.comp_type == TYPE_QUICKACTION:
            self.setMinimumSize(GRID_SIZE * 16, GRID_SIZE * 10)
        elif data.comp_type == TYPE_MEDIA:
            self.setMinimumSize(GRID_SIZE * 14, GRID_SIZE * 6)
        elif data.comp_type == TYPE_CLIPBOARD:
            self.setMinimumSize(GRID_SIZE * 12, GRID_SIZE * 10)
        elif data.comp_type == TYPE_TIMER:
            self.setMinimumSize(GRID_SIZE * 10, GRID_SIZE * 8)
        elif data.comp_type == TYPE_GALLERY:
            self.setMinimumSize(GRID_SIZE * 12, GRID_SIZE * 10)
        elif data.comp_type == TYPE_SYSINFO:
            self.setMinimumSize(GRID_SIZE * 14, GRID_SIZE * 10)
        elif data.comp_type == TYPE_BOOKMARK:
            self.setMinimumSize(GRID_SIZE * 12, GRID_SIZE * 10)
        elif data.comp_type == TYPE_CALC:
            self.setMinimumSize(GRID_SIZE * 12, GRID_SIZE * 14)
        elif data.comp_type == TYPE_TRASH:
            self.setMinimumSize(GRID_SIZE * 10, GRID_SIZE * 6)
        elif data.comp_type == TYPE_RSS:
            self.setMinimumSize(GRID_SIZE * 14, GRID_SIZE * 14)
        elif data.comp_type == TYPE_CMD and not data.show_output:
            np = count_params(data.cmd)
            mh = GRID_SIZE * (2 + np * 2) if np > 0 else GRID_SIZE * 2
            self.setMinimumSize(GRID_SIZE * 13, mh)
        else:
            self.setMinimumSize(MIN_W, MIN_H)
        self.setMouseTracking(True)
        self.setStyleSheet(_comp_style())
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._ctx_menu)
        self._apply_opacity_effect()

    def _apply_opacity_effect(self):
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24); shadow.setOffset(0, 4); shadow.setColor(QColor(0, 0, 0, 100))
        self.setGraphicsEffect(shadow)

    def refresh_theme(self):
        for timer in self.findChildren(QTimer):
            timer.stop()
        old_layout = self.layout()
        if old_layout:
            self._clear_layout_recursive(old_layout)
            QWidget().setLayout(old_layout)
        build_fn = getattr(self, '_build_ui', None) or getattr(self, '_build', None)
        if build_fn:
            build_fn()

    @staticmethod
    def _clear_layout_recursive(layout):
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
            elif item.layout():
                CompBase._clear_layout_recursive(item.layout())

    def _get_grid(self):
        p = self.parent()
        return p if isinstance(p, GridPanel) else None

    def _get_batch(self):
        """Return the set of widgets that should move together (selection or group)."""
        grid = self._get_grid()
        if not grid:
            return [self]
        if self in grid._selected and len(grid._selected) > 1:
            return list(grid._selected)
        gid = getattr(self.data, '_group_id', None)
        if gid:
            return [w for w in grid._components if getattr(w.data, '_group_id', None) == gid]
        return [self]

    def _ctx_menu(self, pos):
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{ background:{C['base']}; border:1px solid {C['surface0']}; border-radius:8px; padding:6px 0; }}
            QMenu::item {{ color:{C['text']}; padding:8px 28px 8px 16px; font-size:12px; }}
            QMenu::item:selected {{ background:{_bg('surface1')}; }}
            QMenu::separator {{ height:1px; background:{_bg('surface0')}; margin:4px 8px; }}
        """)

        grid = self._get_grid()
        in_selection = grid and self in grid._selected and len(grid._selected) > 1
        gid = getattr(self.data, '_group_id', None)

        ea = ca = ga = ua = da = None
        if in_selection:
            ga = menu.addAction("🔗  组合")
            menu.addSeparator()
        ea = menu.addAction("✏  修改"); ca = menu.addAction("📋  复制")
        if gid:
            menu.addSeparator()
            ua = menu.addAction("🔓  解除组合")
        menu.addSeparator(); da = menu.addAction("🗑  删除")
        a = menu.exec_(self.mapToGlobal(pos))
        if a is None: return
        if a == ea: self.edit_requested.emit(self)
        elif a == ca: self.copy_requested.emit(self)
        elif a == da: self.delete_requested.emit(self)
        elif ga and a == ga and grid:
            grid._group_selected()
        elif ua and a == ua and grid:
            grid._ungroup(gid)

    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton:
            super().mousePressEvent(e); return
        grid = self._get_grid()
        batch = self._get_batch()
        if len(batch) > 1 and not self._detect_edges(e.pos()):
            self._batch_dragging = True
            self._batch_drag_origin = e.globalPos()
            self._batch_offsets = [(w, QPoint(w.x(), w.y())) for w in batch]
            for w in batch:
                w.raise_()
            grid = self._get_grid()
            if grid:
                grid._overlay.raise_()
            return
        if grid and grid._selected and self not in grid._selected:
            grid._clear_selection()
        self._batch_dragging = False
        self.handle_press(e); self.raise_()

    def mouseMoveEvent(self, e):
        if getattr(self, '_batch_dragging', False):
            delta = e.globalPos() - self._batch_drag_origin
            par = self.parent()
            pw = par.width() if par else 9999
            ph = par.height() if par else 9999
            safe_top = getattr(par, '_safe_margin_top', 0) if par else 0
            safe_bottom = getattr(par, '_safe_margin_bottom', 0) if par else 0
            min_x = min(orig.x() for _, orig in self._batch_offsets)
            min_y = min(orig.y() for _, orig in self._batch_offsets)
            max_r = max(orig.x() + w.width() for w, orig in self._batch_offsets)
            max_b = max(orig.y() + w.height() for w, orig in self._batch_offsets)
            dx, dy = delta.x(), delta.y()
            if min_x + dx < 0: dx = -min_x
            if min_y + dy < safe_top: dy = safe_top - min_y
            if max_r + dx > pw: dx = pw - max_r
            if max_b + dy > ph - safe_bottom: dy = ph - safe_bottom - max_b
            for w, orig in self._batch_offsets:
                w.move(orig.x() + dx, orig.y() + dy)
            grid = self._get_grid()
            if grid:
                grid._update_overlay()
            return
        self.handle_move(e)

    def mouseReleaseEvent(self, e):
        if getattr(self, '_batch_dragging', False):
            self._batch_dragging = False
            par = self.parent()
            pw = par.width() if par else 9999
            ph = par.height() if par else 9999
            safe_top = getattr(par, '_safe_margin_top', 0) if par else 0
            safe_bottom = getattr(par, '_safe_margin_bottom', 0) if par else 0
            grid = self._get_grid()
            all_snapshot = [(w, w.data.x, w.data.y) for w in grid._components] if grid else []
            batch_origins = list(self._batch_offsets)
            for w, _ in self._batch_offsets:
                x, y = snap(w.x()), snap(w.y())
                x = max(0, min(x, pw - w.width()))
                y = max(safe_top, min(y, ph - safe_bottom - w.height()))
                w.move(x, y); w.data.x, w.data.y = x, y
            if grid:
                for w, _ in self._batch_offsets:
                    grid._resolve_overlaps(w)
                if grid._layout_overflow():
                    for w, ox, oy in all_snapshot:
                        w.move(ox, oy)
                        w.data.x, w.data.y = ox, oy
                    grid._show_toast("⚠ 布局空间不足，组件已回到原位")
                grid._update_overlay()
            self.geometry_changed.emit()
            return
        if self.handle_release(e, self.data): self.geometry_changed.emit()


# ---------------------------------------------------------------------------
# Fullscreen Output Dialog
# ---------------------------------------------------------------------------
class _ExpandBtn(QPushButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(28, 28)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("全屏查看输出")

    def paintEvent(self, e):
        from PyQt5.QtGui import QPen
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        bg = QColor(C['surface1'])
        p.setBrush(bg); p.setPen(Qt.NoPen)
        p.drawRoundedRect(0, 0, self.width(), self.height(), 6, 6)
        pen = QPen(QColor(C['subtext0']), 2)
        p.setPen(pen); p.setBrush(Qt.NoBrush)
        m = 7; w, h = self.width(), self.height()
        p.drawLine(w - m, m, w - m - 5, m)
        p.drawLine(w - m, m, w - m, m + 5)
        p.drawLine(w - m, m, w - m - 4, m + 4)
        p.drawLine(m, h - m, m + 5, h - m)
        p.drawLine(m, h - m, m, h - m - 5)
        p.drawLine(m, h - m, m + 4, h - m - 4)
        p.end()


class FullscreenOutputOverlay(QWidget):
    run_toggled = pyqtSignal()
    closed = pyqtSignal()

    def __init__(self, title, comp_type=TYPE_CMD, parent=None):
        super().__init__(parent)
        self._start_label = "启动" if comp_type == TYPE_CMD_WINDOW else "执行"
        self._stop_label = "停止"
        self.setAutoFillBackground(True)
        lay = QVBoxLayout(self); lay.setContentsMargins(16, 12, 16, 12); lay.setSpacing(8)
        h = QHBoxLayout(); h.setSpacing(8)
        lbl = QLabel(title)
        lbl.setStyleSheet(f"color:{C['text']}; font-size:16px; font-weight:bold;")
        h.addWidget(lbl)
        h.addStretch()
        self._run_btn = QPushButton(f"▶  {self._start_label}")
        self._run_btn.setStyleSheet(f"background:{C['green']}; color:{C['crust']}; border:none; border-radius:6px; padding:6px 16px; font-weight:bold; font-size:12px;")
        self._run_btn.setCursor(Qt.PointingHandCursor); self._run_btn.clicked.connect(self.run_toggled.emit)
        h.addWidget(self._run_btn)
        close_btn = QPushButton("↙↗ 退出全屏")
        close_btn.setStyleSheet(f"background:{C['surface1']}; color:{C['text']}; border:none; border-radius:6px; padding:6px 16px; font-size:12px;")
        close_btn.setCursor(Qt.PointingHandCursor); close_btn.clicked.connect(self._close)
        h.addWidget(close_btn)
        lay.addLayout(h)
        self._output = QTextEdit(); self._output.setReadOnly(True)
        self._output.setStyleSheet(f"background:{C['crust']}; color:{C['green']}; border:1px solid {C['surface0']}; border-radius:8px; font-family:'JetBrains Mono','Consolas',monospace; font-size:12px; padding:8px;")
        lay.addWidget(self._output, 1)
        ir = QHBoxLayout(); ir.setSpacing(6)
        self._stdin = QLineEdit(); self._stdin.setPlaceholderText("输入内容（回车发送）…")
        self._stdin.setStyleSheet(f"background:{C['crust']}; color:{C['text']}; border:1px solid {C['surface0']}; border-radius:6px; padding:6px 10px; font-family:'JetBrains Mono','Consolas',monospace; font-size:12px;")
        ir.addWidget(self._stdin)
        self._send_btn = QPushButton("发送")
        self._send_btn.setStyleSheet(f"background:{C['sky']}; color:{C['crust']}; border:none; border-radius:6px; font-size:12px; font-weight:bold; padding:6px 16px;")
        self._send_btn.setCursor(Qt.PointingHandCursor)
        ir.addWidget(self._send_btn)
        lay.addLayout(ir)
        self._write_fn = None
        self._connected = False

    def set_write_fn(self, fn):
        self._write_fn = fn
        if not self._connected:
            self._stdin.returnPressed.connect(self._do_send)
            self._send_btn.clicked.connect(self._do_send)
            self._connected = True

    def set_running(self, running):
        if running:
            self._run_btn.setText(f"■  {self._stop_label}")
            self._run_btn.setStyleSheet(f"background:{C['red']}; color:{C['crust']}; border:none; border-radius:6px; padding:6px 16px; font-weight:bold; font-size:12px;")
        else:
            self._run_btn.setText(f"▶  {self._start_label}")
            self._run_btn.setStyleSheet(f"background:{C['green']}; color:{C['crust']}; border:none; border-radius:6px; padding:6px 16px; font-weight:bold; font-size:12px;")

    def set_input_enabled(self, enabled):
        self._stdin.setEnabled(enabled)
        self._send_btn.setEnabled(enabled)

    def _do_send(self):
        if self._write_fn:
            self._write_fn(self._stdin.text())
            self._stdin.clear()

    def append_line(self, html):
        self._output.append(html)

    def sync_content(self, source: QTextEdit):
        self._output.setHtml(source.toHtml())

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(C['base']))
        p.end()

    def _close(self):
        self.hide()
        self.closed.emit()

    def sync_content(self, source: QTextEdit):
        self._output.setHtml(source.toHtml())
        sb = self._output.verticalScrollBar()
        sb.setValue(sb.maximum())


# ---------------------------------------------------------------------------
# CMD Component
# ---------------------------------------------------------------------------
class CmdWidget(CompBase):
    def __init__(self, data, parent=None):
        super().__init__(data, parent)
        self._runner = None
        self._param_inputs = []
        self._fs_dlg = None
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 6, 10, 6); root.setSpacing(4)

        h = QHBoxLayout(); h.setSpacing(6)
        badge = QLabel("CMD"); badge.setObjectName("badge"); badge.setFixedHeight(22); badge.setAlignment(Qt.AlignCenter)
        h.addWidget(badge)
        self._title = QLabel(self.data.name); self._title.setObjectName("title")
        self._title.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._title.setToolTip(self.data.name)
        self._title.setMinimumWidth(0)
        h.addWidget(self._title)
        cmd_q = QLabel("?"); cmd_q.setFixedSize(18, 18); cmd_q.setAlignment(Qt.AlignCenter)
        cmd_q.setStyleSheet(f"background:{_bg('surface1')}; color:{C['subtext0']}; border-radius:9px; font-size:11px; font-weight:bold;")
        cmd_q.setToolTip(self.data.cmd)
        h.addWidget(cmd_q)
        if self.data.show_output:
            fs = _ExpandBtn()
            fs.clicked.connect(self._open_fullscreen); h.addWidget(fs)
        self._run_btn = QPushButton("▶  执行"); self._run_btn.setObjectName("runBtn")
        self._run_btn.setCursor(Qt.PointingHandCursor); self._run_btn.setFixedHeight(28)
        self._run_btn.clicked.connect(self._toggle); h.addWidget(self._run_btn)
        root.addLayout(h)

        for i in range(count_params(self.data.cmd)):
            row = QHBoxLayout(); row.setSpacing(4)
            inp = QLineEdit(); inp.setObjectName("paramInput")
            hint = self.data.param_hints[i] if i < len(self.data.param_hints) and self.data.param_hints[i] else ""
            inp.setPlaceholderText(hint or f"参数 {i+1}")
            default = self.data.param_defaults[i] if i < len(self.data.param_defaults) and self.data.param_defaults[i] else ""
            if default:
                inp.setText(default)
            row.addWidget(inp); self._param_inputs.append(inp)
            if hint:
                q = QLabel("?"); q.setFixedSize(18, 18); q.setAlignment(Qt.AlignCenter)
                q.setStyleSheet(f"background:{_bg('surface1')}; color:{C['subtext0']}; border-radius:9px; font-size:11px; font-weight:bold;")
                q.setToolTip(hint)
                row.addWidget(q)
            root.addLayout(row)

        if self.data.show_output:
            self._output = QTextEdit(); self._output.setObjectName("output")
            self._output.setReadOnly(True); self._output.setPlaceholderText("点击「执行」查看输出…")
            root.addWidget(self._output, 1)
            ir = QHBoxLayout(); ir.setSpacing(6)
            self._stdin = QLineEdit(); self._stdin.setObjectName("stdinInput")
            self._stdin.setPlaceholderText("输入内容（回车发送）…"); self._stdin.setEnabled(False)
            self._stdin.returnPressed.connect(self._send); ir.addWidget(self._stdin)
            self._send_btn = QPushButton("发送"); self._send_btn.setObjectName("sendBtn")
            self._send_btn.setFixedWidth(52); self._send_btn.setEnabled(False)
            self._send_btn.setCursor(Qt.PointingHandCursor); self._send_btn.clicked.connect(self._send)
            ir.addWidget(self._send_btn); root.addLayout(ir)
        else:
            self._output = None; self._stdin = None; self._send_btn = None
            root.addStretch()

    def _build_cmd(self):
        cmd = self.data.cmd
        for inp in self._param_inputs:
            cmd = PARAM_PATTERN.sub(inp.text(), cmd, count=1)
        return cmd

    def _send(self):
        if self._runner and self._stdin:
            self._runner.write_stdin(self._stdin.text()); self._stdin.clear()

    def _toggle(self):
        if self._runner and self._runner.isRunning(): self._runner.stop()
        else: self._execute()

    def _execute(self):
        self._run_btn.setText("■  停止"); self._run_btn.setProperty("running", True)
        self._run_btn.style().unpolish(self._run_btn); self._run_btn.style().polish(self._run_btn)
        if self._output: self._output.clear()
        if self._stdin: self._stdin.setEnabled(True)
        if self._send_btn: self._send_btn.setEnabled(True)
        self._runner = PtyRunner(self._build_cmd())
        self._runner.line_ready.connect(self._on_line); self._runner.done.connect(self._on_done)
        self._runner.start()
        if self._fs_dlg:
            self._fs_dlg.set_write_fn(self._runner.write_stdin)
            self._fs_dlg.set_input_enabled(True)
            self._fs_dlg.set_running(True)

    def _open_fullscreen(self):
        grid = self.parentWidget()
        if not grid:
            return
        if not self._fs_dlg:
            self._fs_dlg = FullscreenOutputOverlay(self.data.name, TYPE_CMD, grid)
            self._fs_dlg.run_toggled.connect(self._toggle)
            self._fs_dlg.closed.connect(self._on_fs_closed)
        running = self._runner and self._runner.isRunning()
        if running:
            self._fs_dlg.set_write_fn(self._runner.write_stdin)
            self._fs_dlg.set_input_enabled(True)
        else:
            self._fs_dlg.set_write_fn(None)
            self._fs_dlg.set_input_enabled(False)
        self._fs_dlg.set_running(running)
        if self._output:
            self._fs_dlg.sync_content(self._output)
        self._fs_dlg.setGeometry(0, 0, grid.width(), grid.height())
        self._fs_dlg.raise_()
        self._fs_dlg.show()

    def _on_fs_closed(self):
        self._fs_dlg = None

    def _on_line(self, t):
        plain = _SGR_RE.sub("", t)
        if self._output: self._output.append(plain)
        if self._fs_dlg: self._fs_dlg.append_line(plain)

    def _on_done(self, code):
        self._run_btn.setProperty("running", False)
        self._run_btn.style().unpolish(self._run_btn)
        self._run_btn.style().polish(self._run_btn)
        if self._stdin:
            self._stdin.setEnabled(False)
        if self._send_btn:
            self._send_btn.setEnabled(False)
        if self._fs_dlg:
            self._fs_dlg.set_input_enabled(False)
            self._fs_dlg.set_running(False)
        if self._output:
            if code == -15:
                msg, c = "--- 已停止 ---", C['peach']
            else:
                msg, c = f"--- 退出码 {code} ---", C['green'] if code == 0 else C['red']
            html = f'<span style="color:{c}; font-weight:bold;">{msg}</span>'
            self._output.append(html)
            if self._fs_dlg: self._fs_dlg.append_line(html)
            self._run_btn.setText("▶  执行")
        else:
            if code == -15:
                self._run_btn.setText("⏹ 已停止")
                self._run_btn.setStyleSheet(f"background:{_bg('surface1')}; color:{C['text']}; border:none; border-radius:6px; padding:0 14px; font-weight:bold; font-size:12px;")
            elif code == 0:
                self._run_btn.setText("✓ 完成")
                self._run_btn.setStyleSheet(f"background:{_bg('surface0')}; color:{C['green']}; border:none; border-radius:6px; padding:0 14px; font-weight:bold; font-size:12px;")
            else:
                self._run_btn.setText(f"✗ 失败({code})")
                self._run_btn.setStyleSheet(f"background:{_bg('surface0')}; color:{C['red']}; border:none; border-radius:6px; padding:0 14px; font-weight:bold; font-size:12px;")
            QTimer.singleShot(2000, self._reset_btn)

    def _reset_btn(self):
        self._run_btn.setText("▶  执行")
        self._run_btn.setStyleSheet("")
        self._run_btn.style().unpolish(self._run_btn)
        self._run_btn.style().polish(self._run_btn)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        fm = self._title.fontMetrics()
        elided = fm.elidedText(self.data.name, Qt.ElideRight, self._title.width())
        self._title.setText(elided)

    def update_from_data(self):
        self._title.setText(self.data.name)
        self._title.setToolTip(self.data.name)


# ---------------------------------------------------------------------------
# CMD Window Component
# ---------------------------------------------------------------------------
class CmdWindowWidget(CompBase):
    def __init__(self, data, parent=None):
        super().__init__(data, parent)
        self._runner = None
        self._fs_dlg = None
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14,10,14,14); root.setSpacing(8)

        h = QHBoxLayout(); h.setSpacing(8)
        badge = QLabel("CMD窗口"); badge.setObjectName("badgeCmdWin"); badge.setFixedHeight(22); badge.setAlignment(Qt.AlignCenter)
        h.addWidget(badge)
        self._title = QLabel(self.data.name); self._title.setObjectName("title")
        self._title.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred); h.addWidget(self._title)
        exp_btn = QPushButton("📋"); exp_btn.setFixedSize(28, 28); exp_btn.setCursor(Qt.PointingHandCursor)
        exp_btn.setToolTip("导出日志"); exp_btn.setStyleSheet(f"background:{_bg('surface1')}; color:{C['text']}; border:none; border-radius:6px; font-size:14px;")
        exp_btn.clicked.connect(self._export_log); h.addWidget(exp_btn)
        fs = _ExpandBtn()
        fs.clicked.connect(self._open_fullscreen); h.addWidget(fs)
        self._run_btn = QPushButton("▶  启动"); self._run_btn.setObjectName("runBtn")
        self._run_btn.setCursor(Qt.PointingHandCursor); self._run_btn.setFixedHeight(28)
        self._run_btn.clicked.connect(self._toggle); h.addWidget(self._run_btn)
        root.addLayout(h)

        self._output = QTextEdit(); self._output.setObjectName("output")
        self._output.setReadOnly(True); self._output.setPlaceholderText("启动后可在下方输入命令…")
        root.addWidget(self._output, 1)

        ir = QHBoxLayout(); ir.setSpacing(6)
        self._stdin = QLineEdit(); self._stdin.setObjectName("stdinInput")
        self._stdin.setPlaceholderText("输入命令（回车执行）…"); self._stdin.setEnabled(False)
        self._stdin.returnPressed.connect(self._send); ir.addWidget(self._stdin)
        self._send_btn = QPushButton("发送"); self._send_btn.setObjectName("sendBtn")
        self._send_btn.setFixedWidth(52); self._send_btn.setEnabled(False)
        self._send_btn.setCursor(Qt.PointingHandCursor); self._send_btn.clicked.connect(self._send)
        ir.addWidget(self._send_btn); root.addLayout(ir)

    def _send(self):
        if self._runner:
            self._runner.write_stdin(self._stdin.text()); self._stdin.clear()

    def _toggle(self):
        if self._runner and self._runner.isRunning(): self._runner.stop()
        else: self._start()

    def _start(self):
        self._run_btn.setText("■  停止"); self._run_btn.setProperty("running", True)
        self._run_btn.style().unpolish(self._run_btn); self._run_btn.style().polish(self._run_btn)
        self._output.clear(); self._stdin.setEnabled(True); self._send_btn.setEnabled(True)
        self._runner = PtyRunner("/bin/bash")
        self._runner.line_ready.connect(self._on_line); self._runner.done.connect(self._on_done)
        self._runner.start()
        if self._fs_dlg:
            self._fs_dlg.set_write_fn(self._runner.write_stdin)
            self._fs_dlg.set_input_enabled(True)
            self._fs_dlg.set_running(True)
        if self.data.pre_cmd:
            lines = [l for l in self.data.pre_cmd.splitlines() if l.strip()]
            if lines:
                QTimer.singleShot(200, lambda: self._send_pre_cmds(lines, 0))

    def _send_pre_cmds(self, lines, idx):
        if idx < len(lines) and self._runner and self._runner.isRunning():
            self._runner.write_stdin(lines[idx])
            QTimer.singleShot(100, lambda: self._send_pre_cmds(lines, idx + 1))

    def _open_fullscreen(self):
        grid = self.parentWidget()
        if not grid:
            return
        if not self._fs_dlg:
            self._fs_dlg = FullscreenOutputOverlay(self.data.name, TYPE_CMD_WINDOW, grid)
            self._fs_dlg.run_toggled.connect(self._toggle)
            self._fs_dlg.closed.connect(self._on_fs_closed)
        running = self._runner and self._runner.isRunning()
        if running:
            self._fs_dlg.set_write_fn(self._runner.write_stdin)
            self._fs_dlg.set_input_enabled(True)
        else:
            self._fs_dlg.set_write_fn(None)
            self._fs_dlg.set_input_enabled(False)
        self._fs_dlg.set_running(running)
        self._fs_dlg.sync_content(self._output)
        self._fs_dlg.setGeometry(0, 0, grid.width(), grid.height())
        self._fs_dlg.raise_()
        self._fs_dlg.show()

    def _on_fs_closed(self):
        self._fs_dlg = None

    def _on_line(self, t):
        html = _ansi_to_html(t)
        self._output.append(html)
        if self._fs_dlg: self._fs_dlg.append_line(html)

    def _on_done(self, code):
        self._run_btn.setText("▶  启动"); self._run_btn.setProperty("running", False)
        self._run_btn.style().unpolish(self._run_btn); self._run_btn.style().polish(self._run_btn)
        self._stdin.setEnabled(False); self._send_btn.setEnabled(False)
        if self._fs_dlg:
            self._fs_dlg.set_input_enabled(False)
            self._fs_dlg.set_running(False)
        c = C['peach'] if code == -15 else C['overlay0']
        html = f'<span style="color:{c}; font-weight:bold;">--- 会话结束 ---</span>'
        self._output.append(html)
        if self._fs_dlg: self._fs_dlg.append_line(html)

    def _export_log(self):
        text = self._output.toPlainText()
        if not text.strip():
            return
        f, _ = QFileDialog.getSaveFileName(self, "导出日志", f"{self.data.name}_log.txt", "文本文件 (*.txt);;所有文件 (*)")
        if f:
            try:
                with open(f, "w", encoding="utf-8") as fp:
                    fp.write(text)
            except Exception:
                pass

    def update_from_data(self):
        self._title.setText(self.data.name)


# ---------------------------------------------------------------------------
# Shortcut Component
# ---------------------------------------------------------------------------
class _LaunchThread(QThread):
    finished = pyqtSignal(bool, str)

    def __init__(self, path, sub_type):
        super().__init__()
        self._path = path
        self._sub_type = sub_type

    def run(self):
        try:
            if self._sub_type == SUB_SCRIPT:
                sh = "bash" if self._path.endswith(".sh") else "python3" if self._path.endswith(".py") else "bash"
                proc = subprocess.Popen([sh, self._path], start_new_session=True,
                                        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
                _, err = proc.communicate(timeout=30)
                ok = proc.returncode == 0
                msg = "" if ok else err.decode("utf-8", errors="replace")[:200]
            elif self._sub_type == SUB_APP:
                subprocess.Popen([self._path], start_new_session=True,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                ok, msg = True, ""
            else:
                subprocess.Popen(["xdg-open", self._path], start_new_session=True,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                ok, msg = True, ""
            self.finished.emit(ok, msg)
        except Exception as e:
            self.finished.emit(False, str(e))


class ShortcutWidget(CompBase):
    def __init__(self, data, parent=None):
        super().__init__(data, parent)
        self._thread = None
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 2)
        root.setSpacing(2)

        self._icon_lbl = QLabel()
        self._icon_lbl.setAlignment(Qt.AlignCenter)
        self._icon_lbl.setStyleSheet("background: transparent; border: none;")
        self._icon_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._has_pixmap = False
        if self.data.icon and os.path.isfile(self.data.icon):
            self._orig_pm = QPixmap(self.data.icon)
            self._has_pixmap = True
        else:
            sub_icons = {SUB_APP: "🖥️", SUB_SCRIPT: "📜", SUB_FILE: "📄"}
            self._icon_lbl.setText(sub_icons.get(self.data.sub_type, "🔗"))
            self._icon_lbl.setStyleSheet("font-size: 32px; background: transparent; border: none;")
            self._orig_pm = None
        root.addWidget(self._icon_lbl, 1)

        self._title = QLabel(self.data.name)
        self._title.setAlignment(Qt.AlignCenter)
        self._title.setWordWrap(True)
        self._title.setFixedHeight(18)
        self._title.setStyleSheet(f"color:{C['text']}; font-size:11px; background:transparent; border:none;")
        root.addWidget(self._title)

        self._hover_overlay = QWidget(self)
        self._hover_overlay.setStyleSheet("background: rgba(0,0,0,120); border-radius: 12px;")
        hover_lay = QVBoxLayout(self._hover_overlay)
        hover_lay.setAlignment(Qt.AlignCenter)
        btn_text = "▶ 打开" if self.data.sub_type == SUB_FILE else "▶ 启动"
        self._launch_btn = QPushButton(btn_text)
        self._launch_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C['green']}; color: {C['crust']};
                border: none; border-radius: 6px;
                font-size: 11px; font-weight: bold; padding: 4px 8px;
            }}
            QPushButton:hover {{ background: #b5e8b0; }}
        """)
        self._launch_btn.setCursor(Qt.PointingHandCursor)
        hover_lay.addWidget(self._launch_btn)
        self._launch_btn.clicked.connect(self._launch)
        self._hover_overlay.hide()

        self._result_overlay = QLabel(self)
        self._result_overlay.setAlignment(Qt.AlignCenter)
        self._result_overlay.hide()

        self._result_effect = QGraphicsOpacityEffect(self._result_overlay)
        self._result_overlay.setGraphicsEffect(self._result_effect)
        self._result_effect.setOpacity(1.0)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self._has_pixmap and self._orig_pm:
            avail = self._icon_lbl.size()
            s = min(avail.width(), avail.height(), 64)
            if s > 4:
                self._icon_lbl.setPixmap(
                    self._orig_pm.scaled(s, s, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self._hover_overlay.setGeometry(0, 0, self.width(), self.height())
        self._result_overlay.setGeometry(0, 0, self.width(), self.height())

    def enterEvent(self, e):
        super().enterEvent(e)
        if not (self._thread and self._thread.isRunning()):
            self._hover_overlay.show()
            self._hover_overlay.raise_()

    def leaveEvent(self, e):
        super().leaveEvent(e)
        self._hover_overlay.hide()

    def _launch(self):
        path = self.data.path
        if not path or (self._thread and self._thread.isRunning()):
            return
        self._hover_overlay.hide()
        self._thread = _LaunchThread(path, self.data.sub_type)
        self._thread.finished.connect(self._on_launch_done)
        self._thread.start()

    def _on_launch_done(self, ok, msg):
        if ok:
            self._show_result("✓ 已启动", C['green'])
        else:
            tip = msg[:30] if msg else "启动失败"
            self._show_result(f"✗ {tip}", C['red'])

    def _show_result(self, text, color):
        self._result_overlay.setText(text)
        self._result_overlay.setStyleSheet(
            f"background: rgba(0,0,0,140); color: {color}; font-size: 12px; "
            f"font-weight: bold; border-radius: 12px;")
        self._result_overlay.setGeometry(0, 0, self.width(), self.height())
        self._result_overlay.show()
        self._result_overlay.raise_()
        self._result_effect.setOpacity(1.0)

        anim = QPropertyAnimation(self._result_effect, b"opacity", self)
        anim.setDuration(1500)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.setEasingCurve(QEasingCurve.InQuad)
        anim.finished.connect(self._result_overlay.hide)
        anim.start()
        self._anim = anim

    def update_from_data(self):
        self._title.setText(self.data.name)


# ---------------------------------------------------------------------------
# Calendar Component
# ---------------------------------------------------------------------------
_LUNAR_INFO = [
    0x04bd8, 0x04ae0, 0x0a570, 0x054d5, 0x0d260, 0x0d950, 0x16554, 0x056a0, 0x09ad0, 0x055d2,
    0x04ae0, 0x0a5b6, 0x0a4d0, 0x0d250, 0x1d255, 0x0b540, 0x0d6a0, 0x0ada2, 0x095b0, 0x14977,
    0x04970, 0x0a4b0, 0x0b4b5, 0x06a50, 0x06d40, 0x1ab54, 0x02b60, 0x09570, 0x052f2, 0x04970,
    0x06566, 0x0d4a0, 0x0ea50, 0x06e95, 0x05ad0, 0x02b60, 0x186e3, 0x092e0, 0x1c8d7, 0x0c950,
    0x0d4a0, 0x1d8a6, 0x0b550, 0x056a0, 0x1a5b4, 0x025d0, 0x092d0, 0x0d2b2, 0x0a950, 0x0b557,
    0x06ca0, 0x0b550, 0x15355, 0x04da0, 0x0a5b0, 0x14573, 0x052b0, 0x0a9a8, 0x0e950, 0x06aa0,
    0x0aea6, 0x0ab50, 0x04b60, 0x0aae4, 0x0a570, 0x05260, 0x0f263, 0x0d950, 0x05b57, 0x056a0,
    0x096d0, 0x04dd5, 0x04ad0, 0x0a4d0, 0x0d4d4, 0x0d250, 0x0d558, 0x0b540, 0x0b6a0, 0x195a6,
    0x095b0, 0x049b0, 0x0a974, 0x0a4b0, 0x0b27a, 0x06a50, 0x06d40, 0x0af46, 0x0ab60, 0x09570,
    0x04af5, 0x04970, 0x064b0, 0x074a3, 0x0ea50, 0x06b58, 0x05ac0, 0x0ab60, 0x096d5, 0x092e0,
    0x0c960, 0x0d954, 0x0d4a0, 0x0da50, 0x07552, 0x056a0, 0x0abb7, 0x025d0, 0x092d0, 0x0cab5,
    0x0a950, 0x0b4a0, 0x0baa4, 0x0ad50, 0x055d9, 0x04ba0, 0x0a5b0, 0x15176, 0x052b0, 0x0a930,
    0x07954, 0x06aa0, 0x0ad50, 0x05b52, 0x04b60, 0x0a6e6, 0x0a4e0, 0x0d260, 0x0ea65, 0x0d530,
    0x05aa0, 0x076a3, 0x096d0, 0x04afb, 0x04ad0, 0x0a4d0, 0x1d0b6, 0x0d250, 0x0d520, 0x0dd45,
    0x0b5a0, 0x056d0, 0x055b2, 0x049b0, 0x0a577, 0x0a4b0, 0x0aa50, 0x1b255, 0x06d20, 0x0ada0,
    0x14b63, 0x09370, 0x049f8, 0x04970, 0x064b0, 0x168a6, 0x0ea50, 0x06b20, 0x1a6c4, 0x0aae0,
    0x092e0, 0x0d2e3, 0x0c960, 0x0d557, 0x0d4a0, 0x0da50, 0x05d55, 0x056a0, 0x0a6d0, 0x055d4,
    0x052d0, 0x0a9b8, 0x0a950, 0x0b4a0, 0x0b6a6, 0x0ad50, 0x055a0, 0x0aba4, 0x0a5b0, 0x052b0,
    0x0b273, 0x06930, 0x07337, 0x06aa0, 0x0ad50, 0x14b55, 0x04b60, 0x0a570, 0x054e4, 0x0d160,
    0x0e968, 0x0d520, 0x0daa0, 0x16aa6, 0x056d0, 0x04ae0, 0x0a9d4, 0x0a4d0, 0x0d150, 0x0f252,
    0x0d520,
]
_TIAN_GAN = "甲乙丙丁戊己庚辛壬癸"
_DI_ZHI = "子丑寅卯辰巳午未申酉戌亥"
_SHENG_XIAO = "鼠牛虎兔龙蛇马羊猴鸡狗猪"
_LUNAR_MON = ["正", "二", "三", "四", "五", "六", "七", "八", "九", "十", "冬", "腊"]
_LUNAR_DAY_STR = [
    "", "初一", "初二", "初三", "初四", "初五", "初六", "初七", "初八", "初九", "初十",
    "十一", "十二", "十三", "十四", "十五", "十六", "十七", "十八", "十九", "二十",
    "廿一", "廿二", "廿三", "廿四", "廿五", "廿六", "廿七", "廿八", "廿九", "三十",
]

def _lunar_year_days(y):
    idx = y - 1900
    if idx < 0 or idx >= len(_LUNAR_INFO): return 348
    s = 348
    for i in range(12):
        s += 30 if _LUNAR_INFO[idx] & (0x10000 >> i) else 29
    return s + _lunar_leap_days(y)

def _lunar_leap_month(y):
    idx = y - 1900
    if idx < 0 or idx >= len(_LUNAR_INFO): return 0
    return _LUNAR_INFO[idx] & 0xf

def _lunar_leap_days(y):
    lm = _lunar_leap_month(y)
    if not lm: return 0
    idx = y - 1900
    return 30 if _LUNAR_INFO[idx] & 0x10000 else 29

def _lunar_month_days(y, m):
    idx = y - 1900
    if idx < 0 or idx >= len(_LUNAR_INFO): return 29
    return 30 if _LUNAR_INFO[idx] & (0x10000 >> m) else 29

def _solar_to_lunar(year, month, day):
    base = datetime.date(1900, 1, 31)
    offset = (datetime.date(year, month, day) - base).days
    ly = 1900; lm = 1; ld = 1; leap = False
    while ly < 2101:
        ydays = _lunar_year_days(ly)
        if offset < ydays: break
        offset -= ydays; ly += 1
    lp = _lunar_leap_month(ly)
    for i in range(1, 14):
        if lp and i == lp + 1:
            mdays = _lunar_leap_days(ly); is_leap = True
        else:
            mi = i - (1 if i > lp and lp else 0)
            mdays = _lunar_month_days(ly, mi); is_leap = False
        if offset < mdays:
            lm = i - (1 if i > lp and lp else 0); ld = offset + 1; leap = is_leap; break
        offset -= mdays
    gan = _TIAN_GAN[(ly - 4) % 10]
    zhi = _DI_ZHI[(ly - 4) % 12]
    sx = _SHENG_XIAO[(ly - 4) % 12]
    return ly, lm, ld, leap, gan, zhi, sx


class _DayCell(QWidget):
    clicked = pyqtSignal(object)

    def __init__(self, date_obj, is_other, parent=None):
        super().__init__(parent)
        self.date_obj = date_obj
        self.is_other = is_other
        self.setCursor(Qt.PointingHandCursor)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit(self.date_obj)
        super().mousePressEvent(e)


class CalendarWidget(CompBase):
    def __init__(self, data, parent=None):
        super().__init__(data, parent)
        today = datetime.date.today()
        self._year = today.year
        self._month = today.month
        self._selected = None
        self._build()
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._auto_refresh)
        interval = max(data.refresh_interval, 10) * 1000
        self._refresh_timer.start(interval)

    def _auto_refresh(self):
        today = datetime.date.today()
        if today.year != self._year or today.month != self._month:
            pass
        self._refresh()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 8); root.setSpacing(4)

        nav = QHBoxLayout(); nav.setSpacing(4)
        pb = QPushButton("◀"); pb.setFixedSize(28, 28); pb.setCursor(Qt.PointingHandCursor)
        pb.setStyleSheet(f"background:{_bg('surface1')}; color:{C['text']}; border:none; border-radius:6px; font-size:12px;")
        pb.clicked.connect(self._prev_month); nav.addWidget(pb)
        self._month_lbl = QLabel(); self._month_lbl.setAlignment(Qt.AlignCenter)
        self._month_lbl.setStyleSheet(f"color:{C['text']}; font-size:14px; font-weight:bold;")
        nav.addWidget(self._month_lbl, 1)
        nb = QPushButton("▶"); nb.setFixedSize(28, 28); nb.setCursor(Qt.PointingHandCursor)
        nb.setStyleSheet(f"background:{_bg('surface1')}; color:{C['text']}; border:none; border-radius:6px; font-size:12px;")
        nb.clicked.connect(self._next_month); nav.addWidget(nb)
        tb = QPushButton("今天"); tb.setFixedHeight(28); tb.setCursor(Qt.PointingHandCursor)
        tb.setStyleSheet(f"background:{C['blue']}; color:{C['crust']}; border:none; border-radius:6px; font-size:11px; font-weight:bold; padding:0 10px;")
        tb.clicked.connect(self._go_today); nav.addWidget(tb)
        root.addLayout(nav)

        from PyQt5.QtWidgets import QGridLayout
        hdr = QHBoxLayout(); hdr.setSpacing(0)
        for i, d in enumerate(["一", "二", "三", "四", "五", "六", "日"]):
            l = QLabel(d); l.setAlignment(Qt.AlignCenter); l.setFixedHeight(20)
            clr = C['red'] if i >= 5 else C['subtext0']
            l.setStyleSheet(f"color:{clr}; font-size:11px; font-weight:bold;")
            hdr.addWidget(l, 1)
        root.addLayout(hdr)

        self._grid = QGridLayout(); self._grid.setSpacing(1)
        root.addLayout(self._grid, 1)

        self._lunar_lbl = QLabel(); self._lunar_lbl.setAlignment(Qt.AlignCenter)
        self._lunar_lbl.setStyleSheet(f"color:{C['subtext0']}; font-size:11px;")
        root.addWidget(self._lunar_lbl)

        self._refresh()

    def _prev_month(self):
        if self._month == 1: self._month = 12; self._year -= 1
        else: self._month -= 1
        self._refresh()

    def _next_month(self):
        if self._month == 12: self._month = 1; self._year += 1
        else: self._month += 1
        self._refresh()

    def _go_today(self):
        today = datetime.date.today()
        self._year = today.year; self._month = today.month
        self._selected = None
        self._refresh()

    def _refresh(self):
        self._month_lbl.setText(f"{self._year}年 {self._month}月")
        while self._grid.count():
            w = self._grid.takeAt(0).widget()
            if w: w.deleteLater()
        today = datetime.date.today()
        cal = calendar.monthcalendar(self._year, self._month)

        if self._month == 1:
            prev_y, prev_m = self._year - 1, 12
        else:
            prev_y, prev_m = self._year, self._month - 1
        prev_last = calendar.monthrange(prev_y, prev_m)[1]

        if self._month == 12:
            next_y, next_m = self._year + 1, 1
        else:
            next_y, next_m = self._year, self._month + 1

        years_needed = {self._year, prev_y, next_y}
        hol_data = {}
        for y in years_needed:
            hol_data[y] = _load_holidays_for_year(y)

        for r, week in enumerate(cal):
            for c, day in enumerate(week):
                is_other = False
                sy, sm, sd = self._year, self._month, day
                if day == 0:
                    is_other = True
                    if r == 0:
                        first_week = cal[0]
                        zeros = sum(1 for d in first_week if d == 0)
                        sd = prev_last - zeros + c + 1
                        sy, sm = prev_y, prev_m
                    else:
                        filled_before = sum(1 for d in week[:c] if d == 0)
                        sd = filled_before + 1
                        sy, sm = next_y, next_m
                try:
                    _, lm, ld, leap, _, _, _ = _solar_to_lunar(sy, sm, sd)
                    ltxt = _LUNAR_DAY_STR[ld] if ld <= 30 else ""
                except Exception:
                    ltxt = ""
                date_obj = datetime.date(sy, sm, sd)
                date_key = date_obj.strftime("%Y-%m-%d")
                yh = hol_data.get(sy, {"holidays": {}, "workdays": set()})
                holiday_name = yh["holidays"].get(date_key)
                is_workday = date_key in yh["workdays"]
                if holiday_name:
                    ltxt = holiday_name
                elif is_workday:
                    ltxt = "班"

                is_today = (date_obj == today)
                is_selected = (self._selected is not None and date_obj == self._selected)
                is_weekend = c >= 5
                w = _DayCell(date_obj, is_other); w.setFixedHeight(40)
                w.clicked.connect(self._on_day_click)
                vl = QVBoxLayout(w); vl.setContentsMargins(2, 1, 2, 1); vl.setSpacing(0)
                dl = QLabel(str(sd)); dl.setAlignment(Qt.AlignCenter)
                ll = QLabel(ltxt); ll.setAlignment(Qt.AlignCenter)
                if is_selected and is_today:
                    w.setStyleSheet(f"background:{C['blue']}; border-radius:6px; border:2px solid {C['lavender']};")
                    dl.setStyleSheet(f"color:{C['crust']}; font-size:13px; font-weight:bold;")
                    ll.setStyleSheet(f"color:{C['crust']}; font-size:8px;")
                elif is_today:
                    w.setStyleSheet(f"background:{C['blue']}; border-radius:6px;")
                    dl.setStyleSheet(f"color:{C['crust']}; font-size:13px; font-weight:bold;")
                    ll.setStyleSheet(f"color:{C['crust']}; font-size:8px;")
                elif is_selected:
                    w.setStyleSheet(f"background:{_bg('surface1')}; border-radius:6px; border:2px solid {C['blue']};")
                    dl.setStyleSheet(f"color:{C['text']}; font-size:13px; font-weight:bold;")
                    if holiday_name:
                        ll.setStyleSheet(f"color:{C['green']}; font-size:8px; font-weight:bold;")
                    elif is_workday:
                        ll.setStyleSheet(f"color:{C['peach']}; font-size:8px; font-weight:bold;")
                    else:
                        ll.setStyleSheet(f"color:{C['overlay0']}; font-size:8px;")
                elif is_other and holiday_name:
                    dl.setStyleSheet(f"color:{C['green']}; font-size:13px; opacity:0.7;")
                    ll.setStyleSheet(f"color:{C['green']}; font-size:8px; font-weight:bold;")
                elif is_other and is_workday:
                    dl.setStyleSheet(f"color:{C['peach']}; font-size:13px; opacity:0.7;")
                    ll.setStyleSheet(f"color:{C['peach']}; font-size:8px; font-weight:bold;")
                elif is_other:
                    dl.setStyleSheet(f"color:{C['surface2']}; font-size:13px;")
                    ll.setStyleSheet(f"color:{C['surface2']}; font-size:8px;")
                elif holiday_name:
                    dl.setStyleSheet(f"color:{C['green']}; font-size:13px; font-weight:bold;")
                    ll.setStyleSheet(f"color:{C['green']}; font-size:8px; font-weight:bold;")
                elif is_workday:
                    dl.setStyleSheet(f"color:{C['peach']}; font-size:13px; font-weight:bold;")
                    ll.setStyleSheet(f"color:{C['peach']}; font-size:8px; font-weight:bold;")
                elif is_weekend:
                    dl.setStyleSheet(f"color:{C['red']}; font-size:13px; font-weight:bold;")
                    ll.setStyleSheet(f"color:{C['overlay0']}; font-size:8px;")
                else:
                    dl.setStyleSheet(f"color:{C['text']}; font-size:13px; font-weight:bold;")
                    ll.setStyleSheet(f"color:{C['overlay0']}; font-size:8px;")
                vl.addWidget(dl); vl.addWidget(ll)
                self._grid.addWidget(w, r, c)

        ref_date = self._selected if self._selected else today
        try:
            _, lm, ld, leap, gan, zhi, sx = _solar_to_lunar(ref_date.year, ref_date.month, ref_date.day)
            lp = "闰" if leap else ""
            self._lunar_lbl.setText(f"{gan}{zhi}年（{sx}） {lp}{_LUNAR_MON[lm-1]}月{_LUNAR_DAY_STR[ld]}")
        except Exception:
            self._lunar_lbl.setText("")

    def _on_day_click(self, date_obj):
        if self._selected == date_obj:
            self._selected = None
        else:
            self._selected = date_obj
            if date_obj.year != self._year or date_obj.month != self._month:
                self._year = date_obj.year
                self._month = date_obj.month
        self._refresh()

    def update_from_data(self):
        pass


# ---------------------------------------------------------------------------
# Weather Component
# ---------------------------------------------------------------------------
_WMO_DESC = {
    0: "晴", 1: "少云", 2: "多云", 3: "阴", 45: "雾", 48: "霜雾",
    51: "小毛毛雨", 53: "毛毛雨", 55: "大毛毛雨",
    61: "小雨", 63: "中雨", 65: "大雨", 66: "冻雨", 67: "大冻雨",
    71: "小雪", 73: "中雪", 75: "大雪", 77: "雪粒",
    80: "小阵雨", 81: "阵雨", 82: "大阵雨",
    85: "小阵雪", 86: "大阵雪", 95: "雷暴", 96: "冰雹雷暴", 99: "大冰雹雷暴",
}
_WMO_ICON = {
    0: ("☀", "#FFB300"), 1: ("⛅", "#FFB300"), 2: ("⛅", "#90A4AE"), 3: ("☁", "#78909C"),
    45: ("≋", "#B0BEC5"), 48: ("≋", "#B0BEC5"),
    51: ("🌧", "#90CAF9"), 53: ("🌧", "#64B5F6"), 55: ("🌧", "#42A5F5"),
    61: ("🌧", "#42A5F5"), 63: ("🌧", "#1E88E5"), 65: ("🌧", "#1565C0"),
    66: ("🌧", "#80DEEA"), 67: ("🌧", "#4DD0E1"),
    71: ("❆", "#B3E5FC"), 73: ("❆", "#81D4FA"), 75: ("❆", "#4FC3F7"), 77: ("❆", "#E0F7FA"),
    80: ("🌧", "#42A5F5"), 81: ("🌧", "#1E88E5"), 82: ("🌧", "#0D47A1"),
    85: ("❆", "#81D4FA"), 86: ("❆", "#4FC3F7"),
    95: ("⛈", "#6A1B9A"), 96: ("⛈", "#4A148C"), 99: ("⛈", "#311B92"),
}
def _wmo_icon(code): return _WMO_ICON.get(code, ("☁", "#90A4AE"))
def _wmo_desc(code): return _WMO_DESC.get(code, "未知")

def _wind_dir_from_deg(deg):
    dirs = ["北", "北偏东", "东北", "东偏北", "东", "东偏南", "东南", "南偏东",
            "南", "南偏西", "西南", "西偏南", "西", "西偏北", "西北", "北偏西"]
    return dirs[round(deg / 22.5) % 16]

_CN_WEATHER_ICON = {
    "晴": ("☀", "#FFA726"), "多云": ("⛅", "#78909C"), "阴": ("☁", "#90A4AE"),
    "雾": ("🌫", "#B0BEC5"), "霾": ("🌫", "#8D6E63"),
    "小雨": ("🌧", "#42A5F5"), "中雨": ("🌧", "#1E88E5"), "大雨": ("🌧", "#1565C0"),
    "暴雨": ("⛈", "#0D47A1"), "大暴雨": ("⛈", "#0D47A1"), "特大暴雨": ("⛈", "#0D47A1"),
    "阵雨": ("🌦", "#42A5F5"), "雷阵雨": ("⛈", "#7E57C2"),
    "小雪": ("❄", "#90CAF9"), "中雪": ("❄", "#64B5F6"), "大雪": ("❄", "#42A5F5"),
    "暴雪": ("❄", "#1E88E5"), "阵雪": ("❄", "#90CAF9"),
    "雨夹雪": ("🌨", "#78909C"), "冻雨": ("🌧", "#4FC3F7"),
    "浮尘": ("💨", "#BCAAA4"), "扬沙": ("💨", "#A1887F"), "沙尘暴": ("💨", "#795548"),
}

def _cn_weather_icon(text):
    for key, val in _CN_WEATHER_ICON.items():
        if key in text:
            return val
    return ("☁", "#90A4AE")

class _WeatherFetcher(QThread):
    result_ready = pyqtSignal(dict)

    def __init__(self, city_code, city_name=""):
        super().__init__()
        self._code = city_code
        self._name = city_name

    def run(self):
        try:
            url = f"http://t.weather.sojson.com/api/weather/city/{self._code}"
            req = urllib.request.Request(url, headers={"User-Agent": "FastPanel/1.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if data.get("status") != 200:
                self.result_ready.emit({"_error": data.get("message", "API返回错误")})
                return
            data["_city_name"] = self._name or data.get("cityInfo", {}).get("city", "")
            self.result_ready.emit(data)
        except Exception as e:
            self.result_ready.emit({"_error": str(e)})


class _TempChartWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._data = []
        self._hover_idx = -1
        self.setMinimumHeight(140)
        self.setMouseTracking(True)

    def set_data(self, data):
        self._data = data
        self._hover_idx = -1
        self.update()

    def _layout_params(self):
        w, h = self.width(), self.height()
        n = len(self._data)
        pad_l, pad_r = 20, 20
        pad_b = 52
        pad_t = max(22, (h - pad_b) // 3)
        cw = (w - pad_l - pad_r) / (n - 1) if n > 1 else 0
        all_temps = [d["max"] for d in self._data] + [d["min"] for d in self._data]
        t_min, t_max = min(all_temps) - 2, max(all_temps) + 2
        t_range = t_max - t_min if t_max != t_min else 1
        def tx(i): return pad_l + i * cw
        def ty(t): return pad_t + (1 - (t - t_min) / t_range) * (h - pad_t - pad_b)
        return n, w, h, cw, tx, ty

    def mouseMoveEvent(self, e):
        if len(self._data) < 2:
            self._hover_idx = -1; self.update(); return
        n, w, h, cw, tx, ty = self._layout_params()
        mx = e.x()
        best = -1; best_dist = 999999
        for i in range(n):
            d = abs(mx - tx(i))
            if d < best_dist and d < max(cw * 0.6, 20):
                best_dist = d; best = i
        if best != self._hover_idx:
            self._hover_idx = best
            self.update()

    def leaveEvent(self, e):
        self._hover_idx = -1; self.update()

    def paintEvent(self, e):
        if not self._data:
            return
        from PyQt5.QtGui import QPen, QFontMetrics
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        n, w, h, cw, tx, ty = self._layout_params()
        if n < 2:
            p.end(); return

        pen_max = QPen(QColor("#FF7043"), 2)
        p.setPen(pen_max)
        for i in range(n - 1):
            p.drawLine(int(tx(i)), int(ty(self._data[i]["max"])),
                       int(tx(i+1)), int(ty(self._data[i+1]["max"])))
        for i in range(n):
            p.setBrush(QColor("#FF7043")); p.setPen(Qt.NoPen)
            p.drawEllipse(int(tx(i))-3, int(ty(self._data[i]["max"]))-3, 6, 6)
            p.setPen(QColor("#FF7043"))
            f = p.font(); f.setPixelSize(10); p.setFont(f)
            p.drawText(int(tx(i))-10, int(ty(self._data[i]["max"]))-8, f'{self._data[i]["max"]}°')

        pen_min = QPen(QColor("#42A5F5"), 2)
        p.setPen(pen_min)
        for i in range(n - 1):
            p.drawLine(int(tx(i)), int(ty(self._data[i]["min"])),
                       int(tx(i+1)), int(ty(self._data[i+1]["min"])))
        for i in range(n):
            p.setBrush(QColor("#42A5F5")); p.setPen(Qt.NoPen)
            p.drawEllipse(int(tx(i))-3, int(ty(self._data[i]["min"]))-3, 6, 6)
            p.setPen(QColor("#42A5F5"))
            f = p.font(); f.setPixelSize(10); p.setFont(f)
            p.drawText(int(tx(i))-10, int(ty(self._data[i]["min"]))+16, f'{self._data[i]["min"]}°')

        today = datetime.date.today()
        for i, d in enumerate(self._data):
            dt = d.get("date"); wtype = d.get("type", "")
            if not dt:
                continue
            ic, ic_clr = _cn_weather_icon(wtype)
            if dt == today:
                date_str = "今天"
            else:
                date_str = f"{dt.month}/{dt.day}"
            f = p.font(); f.setPixelSize(13); p.setFont(f)
            p.setPen(QColor(ic_clr))
            p.drawText(int(tx(i)) - 8, h - 22, ic)
            f.setPixelSize(11); p.setFont(f)
            p.setPen(QColor(C['subtext0']))
            fm = QFontMetrics(f)
            tw = fm.horizontalAdvance(date_str)
            p.drawText(int(tx(i)) - tw // 2, h - 6, date_str)

        if 0 <= self._hover_idx < n:
            hi = self._hover_idx
            cx = int(tx(hi))
            p.setPen(QPen(QColor(C['overlay0']), 1, Qt.DashLine))
            p.drawLine(cx, 0, cx, h - 52)

            d = self._data[hi]
            dt = d.get("date")
            wtype = d.get("type", "")
            ic, ic_clr = _cn_weather_icon(wtype)
            weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
            if dt:
                if dt == today:
                    title = f"今天 ({dt.month}/{dt.day} {weekdays[dt.weekday()]})"
                else:
                    title = f"{dt.month}/{dt.day} {weekdays[dt.weekday()]}"
            else:
                title = "?"
            lines = [title, f"{ic} {wtype}"]
            lines.append(f"最高 {d['max']}°  最低 {d['min']}°")
            if d.get("fx"): lines.append(f"{d['fx']} {d.get('fl','')}")
            if d.get("aqi"): lines.append(f"AQI {d['aqi']}")
            if d.get("notice"): lines.append(d["notice"][:20])

            card_f = p.font(); card_f.setPixelSize(12); p.setFont(card_f)
            fm = QFontMetrics(card_f)
            line_h = fm.height() + 4
            card_w = max(fm.horizontalAdvance(l) for l in lines) + 20
            card_h = line_h * len(lines) + 16
            card_x = cx + 10
            if card_x + card_w > w - 5:
                card_x = cx - card_w - 10
            card_y = 8

            p.setPen(Qt.NoPen)
            p.setBrush(QColor(C['surface0']))
            p.drawRoundedRect(card_x, card_y, card_w, card_h, 6, 6)
            p.setPen(QPen(QColor(C['overlay0']), 1))
            p.drawRoundedRect(card_x, card_y, card_w, card_h, 6, 6)

            y_off = card_y + 14
            for j, line in enumerate(lines):
                if j == 0:
                    card_f.setBold(True); p.setFont(card_f)
                    p.setPen(QColor(C['text']))
                elif j == 1:
                    card_f.setBold(False); p.setFont(card_f)
                    p.setPen(QColor(ic_clr))
                else:
                    p.setPen(QColor(C['subtext0']))
                p.drawText(card_x + 10, y_off, line)
                y_off += line_h

        p.end()

    def refresh_theme(self):
        saved_year = self._year
        saved_month = self._month
        saved_selected = self._selected
        super().refresh_theme()
        self._year = saved_year
        self._month = saved_month
        self._selected = saved_selected
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._auto_refresh)
        self._refresh_timer.start(max(self.data.refresh_interval, 10) * 1000)
        self._refresh()


class WeatherWidget(CompBase):
    def __init__(self, data, parent=None):
        super().__init__(data, parent)
        self._fetcher = None
        self._has_data = False
        self._retry_count = 0
        self._max_retries = 3
        self._retry_delays = [5000, 15000, 30000]
        self._build()
        self._fetch_weather()
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._fetch_weather)
        interval = max(data.refresh_interval, 10) * 1000
        self._refresh_timer.start(interval)

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 10, 14, 8); root.setSpacing(2)

        top = QHBoxLayout(); top.setSpacing(6)
        self._city_lbl = QLabel(self.data.cmd.strip() or "大连")
        self._city_lbl.setStyleSheet(f"color:{C['text']}; font-size:13px; font-weight:bold;")
        top.addWidget(self._city_lbl)
        self._err_icon = QLabel("⚠")
        self._err_icon.setStyleSheet(f"color:{C['red']}; font-size:12px; background:transparent;")
        self._err_icon.setCursor(Qt.WhatsThisCursor)
        self._err_icon.hide()
        top.addWidget(self._err_icon)
        top.addStretch()
        rb = QPushButton("↻"); rb.setFixedSize(24, 24); rb.setCursor(Qt.PointingHandCursor)
        rb.setToolTip("刷新"); rb.setStyleSheet(f"background:transparent; color:{C['subtext0']}; border:none; font-size:16px; font-weight:bold;")
        rb.clicked.connect(self._fetch_weather); top.addWidget(rb)
        root.addLayout(top)

        cur_row = QHBoxLayout(); cur_row.setSpacing(8)
        self._temp_lbl = QLabel("--")
        self._temp_lbl.setStyleSheet(f"color:{C['text']}; font-size:36px; font-weight:bold;")
        cur_row.addWidget(self._temp_lbl)
        cur_info = QVBoxLayout(); cur_info.setSpacing(2)
        self._desc_lbl = QLabel("加载中…")
        self._desc_lbl.setStyleSheet(f"color:{C['text']}; font-size:13px;")
        cur_info.addWidget(self._desc_lbl)
        self._detail_lbl = QLabel("")
        self._detail_lbl.setStyleSheet(f"color:{C['subtext0']}; font-size:11px;")
        cur_info.addWidget(self._detail_lbl)
        cur_row.addLayout(cur_info, 1)
        self._icon_lbl = QLabel("")
        self._icon_lbl.setStyleSheet(f"font-size:36px;")
        self._icon_lbl.setAlignment(Qt.AlignCenter)
        cur_row.addWidget(self._icon_lbl)
        root.addLayout(cur_row)

        sep = QFrame(); sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"color:{C['surface1']};"); sep.setFixedHeight(1)
        root.addWidget(sep)

        fc_title = QLabel("未来15天预报")
        fc_title.setStyleSheet(f"color:{C['subtext0']}; font-size:10px; margin-top:2px;")
        root.addWidget(fc_title)

        self._chart = _TempChartWidget()
        root.addWidget(self._chart, 1)



    def _parse_city_cmd(self):
        raw = self.data.cmd.strip()
        if "|" in raw:
            code, name = raw.split("|", 1)
            return code.strip(), name.strip()
        for c in _CITY_DB:
            if c["name"] == raw or c["city"] == raw:
                return c["code"], c["name"]
        return "", raw or "大连"

    def _fetch_weather(self):
        code, name = self._parse_city_cmd()
        self._city_lbl.setText(name)
        if not code:
            if not self._has_data:
                self._desc_lbl.setText("请选择城市")
                self._desc_lbl.setStyleSheet(f"color:{C['peach']}; font-size:13px;")
            return
        if not self._has_data:
            self._desc_lbl.setText("加载中…")
            self._temp_lbl.setText("--")
            self._detail_lbl.setText("")
            self._icon_lbl.setText("")
            self._chart.set_data([])
        self._fetcher = _WeatherFetcher(code, name)
        self._fetcher.result_ready.connect(self._on_result)
        self._fetcher.start()

    def _on_result(self, data):
        if "_error" in data:
            err_msg = str(data["_error"])
            if self._has_data:
                self._err_icon.setToolTip(f"刷新失败: {err_msg}")
                self._err_icon.show()
            else:
                if self._retry_count < self._max_retries:
                    delay = self._retry_delays[min(self._retry_count, len(self._retry_delays)-1)]
                    self._retry_count += 1
                    self._desc_lbl.setText(f"加载失败，{delay//1000}秒后重试({self._retry_count}/{self._max_retries})…")
                    self._desc_lbl.setStyleSheet(f"color:{C['peach']}; font-size:13px;")
                    QTimer.singleShot(delay, self._fetch_weather)
                else:
                    self._desc_lbl.setText("获取失败")
                    self._detail_lbl.setText(err_msg)
                    self._desc_lbl.setStyleSheet(f"color:{C['red']}; font-size:13px;")
            return
        self._has_data = True
        self._retry_count = 0
        self._err_icon.hide()
        city_name = data.get("_city_name", "")
        if city_name:
            self._city_lbl.setText(city_name)

        d = data.get("data", {})
        temp = d.get("wendu", "?")
        humidity = d.get("shidu", "?")
        quality = d.get("quality", "")
        pm25 = d.get("pm25", "")
        ganmao = d.get("ganmao", "")

        forecast = d.get("forecast", [])
        today = forecast[0] if forecast else {}
        today_type = today.get("type", "")
        today_high = today.get("high", "").replace("高温 ", "").replace("℃", "")
        today_low = today.get("low", "").replace("低温 ", "").replace("℃", "")
        today_fx = today.get("fx", "")
        today_fl = today.get("fl", "")

        ic, ic_clr = _cn_weather_icon(today_type)
        today_range = f"  {today_low}~{today_high}°C" if today_high and today_low else ""

        self._temp_lbl.setText(f"{temp}°")
        self._temp_lbl.setStyleSheet(f"color:{C['text']}; font-size:36px; font-weight:bold;")
        self._desc_lbl.setText(f"{today_type}{today_range}")
        self._desc_lbl.setStyleSheet(f"color:{C['text']}; font-size:13px;")
        detail_parts = [f"湿度 {humidity}"]
        if today_fx: detail_parts.append(f"{today_fx}{today_fl}")
        if quality: detail_parts.append(f"空气{quality}")
        if pm25: detail_parts.append(f"PM2.5 {pm25}")
        self._detail_lbl.setText("  ".join(detail_parts))
        self._detail_lbl.setStyleSheet(f"color:{C['subtext0']}; font-size:11px;")
        self._icon_lbl.setText(ic)
        self._icon_lbl.setStyleSheet(f"font-size:36px; color:{ic_clr};")

        chart_data = []
        for item in forecast[:15]:
            try:
                dt = datetime.datetime.strptime(item.get("ymd", ""), "%Y-%m-%d").date()
            except Exception:
                dt = None
            hi = item.get("high", "").replace("高温 ", "").replace("℃", "")
            lo = item.get("low", "").replace("低温 ", "").replace("℃", "")
            try: hi_val = float(hi)
            except: hi_val = 0
            try: lo_val = float(lo)
            except: lo_val = 0
            chart_data.append({
                "date": dt, "max": hi_val, "min": lo_val,
                "type": item.get("type", ""), "fx": item.get("fx", ""),
                "fl": item.get("fl", ""), "aqi": item.get("aqi", ""),
                "notice": item.get("notice", "")
            })
        self._chart.set_data(chart_data)

    def update_from_data(self):
        _, name = self._parse_city_cmd()
        self._city_lbl.setText(name)
        self._has_data = False
        self._fetch_weather()

    def refresh_theme(self):
        super().refresh_theme()
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._fetch_weather)
        self._refresh_timer.start(max(self.data.refresh_interval, 10) * 1000)
        self._fetch_weather()


def _scan_desktop_apps():
    dirs = ["/usr/share/applications", os.path.expanduser("~/.local/share/applications")]
    apps = []
    for d in dirs:
        for fp in glob_mod.glob(os.path.join(d, "*.desktop")):
            try:
                cp = configparser.ConfigParser(interpolation=None)
                cp.read(fp, encoding="utf-8")
                sec = "Desktop Entry"
                if not cp.has_section(sec):
                    continue
                if cp.get(sec, "Type", fallback="") != "Application":
                    continue
                if cp.getboolean(sec, "NoDisplay", fallback=False):
                    continue
                name = cp.get(sec, "Name[zh_CN]", fallback="") or cp.get(sec, "Name", fallback="")
                exe = cp.get(sec, "Exec", fallback="")
                icon = cp.get(sec, "Icon", fallback="")
                if not name or not exe:
                    continue
                exe = re.sub(r'\s+%[fFuUdDnNickvm]', '', exe).strip()
                icon_path = ""
                if icon:
                    if os.path.isabs(icon) and os.path.isfile(icon):
                        icon_path = icon
                    else:
                        for base in ["/usr/share/icons/hicolor", "/usr/share/pixmaps"]:
                            for ext in [".png", ".svg", ".xpm"]:
                                for sz in ["128x128", "96x96", "64x64", "48x48", "scalable", "256x256"]:
                                    cand = os.path.join(base, sz, "apps", icon + ext)
                                    if os.path.isfile(cand):
                                        icon_path = cand; break
                                if icon_path: break
                            if icon_path: break
                        if not icon_path:
                            cand = os.path.join("/usr/share/pixmaps", icon + ".png")
                            if os.path.isfile(cand):
                                icon_path = cand
                            cand2 = os.path.join("/usr/share/pixmaps", icon + ".xpm")
                            if not icon_path and os.path.isfile(cand2):
                                icon_path = cand2
                apps.append({"name": name, "exec": exe, "icon": icon_path, "desktop": fp})
            except Exception:
                continue
    apps.sort(key=lambda a: a["name"].lower())
    return apps


class _SystemAppDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("选择系统应用")
        self.setFixedSize(520, 480)
        self.setStyleSheet(f"""
            QDialog {{ background: {C['base']}; color: {C['text']}; }}
            QLabel {{ color: {C['text']}; background: transparent; }}
            QLineEdit {{ background: {C['surface0']}; color: {C['text']}; border: 1px solid {C['surface2']};
                         border-radius: 6px; padding: 6px; font-size: 12px; }}
            QScrollArea {{ border: none; background: {C['base']}; }}
            QScrollBar:vertical {{ background: {C['surface0']}; width: 8px; border-radius: 4px; }}
            QScrollBar::handle:vertical {{ background: {C['surface2']}; border-radius: 4px; min-height: 20px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)
        self._selected = None
        lay = QVBoxLayout(self)
        self._search = QLineEdit()
        self._search.setPlaceholderText("搜索应用…")
        self._search.textChanged.connect(self._filter)
        lay.addWidget(self._search)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._container = QWidget()
        self._container.setStyleSheet(f"background: {C['base']};")
        self._grid = QVBoxLayout(self._container)
        self._grid.setSpacing(2)
        self._grid.setContentsMargins(4, 4, 4, 4)
        self._scroll.setWidget(self._container)
        lay.addWidget(self._scroll, 1)

        self._apps = _scan_desktop_apps()
        self._buttons = []
        self._build_list(self._apps)

    def _build_list(self, apps):
        while self._grid.count():
            item = self._grid.takeAt(0)
            w = item.widget()
            if w: w.deleteLater()
        self._buttons.clear()
        for app in apps:
            btn = QPushButton()
            btn.setCursor(Qt.PointingHandCursor)
            hl = QHBoxLayout(btn)
            hl.setContentsMargins(8, 4, 8, 4)
            hl.setSpacing(10)
            icon_lbl = QLabel()
            icon_lbl.setFixedSize(28, 28)
            icon_lbl.setStyleSheet("background:transparent; border:none;")
            if app["icon"] and os.path.isfile(app["icon"]):
                pm = QPixmap(app["icon"]).scaled(28, 28, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                icon_lbl.setPixmap(pm)
            else:
                icon_lbl.setText("🖥️")
                icon_lbl.setStyleSheet("font-size:18px; background:transparent; border:none;")
            icon_lbl.setAlignment(Qt.AlignCenter)
            hl.addWidget(icon_lbl)
            name_lbl = QLabel(app["name"])
            name_lbl.setStyleSheet(f"color:{C['text']}; font-size:13px;")
            hl.addWidget(name_lbl, 1)
            btn.setStyleSheet(f"""
                QPushButton {{ background: transparent; border: none; border-radius: 6px; text-align: left; padding: 4px; }}
                QPushButton:hover {{ background: {C['surface1']}; }}
            """)
            btn.clicked.connect(lambda _, a=app: self._select(a))
            self._grid.addWidget(btn)
            self._buttons.append((btn, app))
        self._grid.addStretch()

    def _filter(self, text):
        ft = text.strip().lower()
        for btn, app in self._buttons:
            btn.setVisible(not ft or ft in app["name"].lower())

    def _select(self, app):
        self._selected = app
        self.accept()

    def selected_app(self):
        return self._selected


class _DockItemDialog(QDialog):
    def __init__(self, item=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("编辑Dock项" if item else "添加Dock项")
        self.setFixedWidth(380)
        self.setStyleSheet(f"""
            QDialog {{ background: {C['base']}; color: {C['text']}; }}
            QLabel {{ color: {C['text']}; font-size: 13px; }}
            QLineEdit {{ background: {C['surface0']}; color: {C['text']}; border: 1px solid {C['surface2']};
                         border-radius: 6px; padding: 6px; font-size: 12px; }}
            QComboBox {{ background: {C['surface0']}; color: {C['text']}; border: 1px solid {C['surface2']};
                         border-radius: 6px; padding: 6px; font-size: 12px; }}
        """)
        lay = QVBoxLayout(self)

        imp_btn = QPushButton("📦 从系统导入应用")
        imp_btn.setCursor(Qt.PointingHandCursor)
        imp_btn.setStyleSheet(f"""
            QPushButton {{ background:{C['surface1']}; color:{C['text']}; border:none; border-radius:8px; padding:8px; font-size:12px; }}
            QPushButton:hover {{ background:{C['surface2']}; }}
        """)
        imp_btn.clicked.connect(self._import_sys_app)
        lay.addWidget(imp_btn)

        form = QFormLayout(); form.setSpacing(10)

        self._name_edit = QLineEdit(item.get("name", "") if item else "")
        self._name_edit.setPlaceholderText("显示名称")
        form.addRow("名称", self._name_edit)

        self._type_combo = QComboBox()
        for k, v in SUB_LABELS.items():
            self._type_combo.addItem(v, k)
        if item:
            idx = list(SUB_LABELS.keys()).index(item.get("sub_type", SUB_APP))
            self._type_combo.setCurrentIndex(idx)
        form.addRow("类型", self._type_combo)

        icon_w = QWidget()
        icon_lay = QHBoxLayout(icon_w); icon_lay.setContentsMargins(0, 0, 0, 0); icon_lay.setSpacing(6)
        self._icon_edit = QLineEdit(item.get("icon", "") if item else "")
        self._icon_edit.setPlaceholderText("图标路径（可选）")
        icon_lay.addWidget(self._icon_edit)
        ib = QPushButton("…"); ib.setFixedWidth(36)
        ib.setStyleSheet(f"background:{C['surface1']}; color:{C['text']}; border:none; border-radius:6px;")
        ib.clicked.connect(self._browse_icon)
        icon_lay.addWidget(ib)
        form.addRow("图标", icon_w)

        path_w = QWidget()
        path_lay = QHBoxLayout(path_w); path_lay.setContentsMargins(0, 0, 0, 0); path_lay.setSpacing(6)
        self._path_edit = QLineEdit(item.get("path", "") if item else "")
        self._path_edit.setPlaceholderText("程序/文件/脚本路径")
        path_lay.addWidget(self._path_edit)
        pb = QPushButton("…"); pb.setFixedWidth(36)
        pb.setStyleSheet(f"background:{C['surface1']}; color:{C['text']}; border:none; border-radius:6px;")
        pb.clicked.connect(self._browse_path)
        path_lay.addWidget(pb)
        form.addRow("路径", path_w)

        lay.addLayout(form)
        lay.addStretch()

        btns = QHBoxLayout(); btns.addStretch()
        cancel = QPushButton("取消")
        cancel.setStyleSheet(f"background:{C['surface1']}; color:{C['text']}; border:none; border-radius:8px; padding:8px 20px; font-size:13px;")
        cancel.setCursor(Qt.PointingHandCursor)
        cancel.clicked.connect(self.reject); btns.addWidget(cancel)
        ok = QPushButton("确定")
        ok.setStyleSheet(f"background:{C['blue']}; color:{C['crust']}; border:none; border-radius:8px; padding:8px 20px; font-size:13px; font-weight:bold;")
        ok.setCursor(Qt.PointingHandCursor)
        ok.clicked.connect(self._validate); btns.addWidget(ok)
        lay.addLayout(btns)

    def _browse_icon(self):
        p, _ = QFileDialog.getOpenFileName(self, "选择图标", "", "图片 (*.png *.svg *.ico *.jpg)")
        if p: self._icon_edit.setText(p)

    def _browse_path(self):
        p, _ = QFileDialog.getOpenFileName(self, "选择文件", "", "所有文件 (*)")
        if p: self._path_edit.setText(p)

    def _import_sys_app(self):
        dlg = _SystemAppDialog(self)
        if dlg.exec_() == QDialog.Accepted:
            app = dlg.selected_app()
            if app:
                self._name_edit.setText(app["name"])
                self._icon_edit.setText(app.get("icon", ""))
                self._path_edit.setText(app.get("exec", ""))
                self._type_combo.setCurrentIndex(0)

    def _validate(self):
        if not self._name_edit.text().strip():
            return
        if not self._path_edit.text().strip():
            return
        self.accept()

    def get_item(self):
        return {
            "name": self._name_edit.text().strip(),
            "sub_type": self._type_combo.currentData(),
            "icon": self._icon_edit.text().strip(),
            "path": self._path_edit.text().strip(),
        }


class DockWidget(CompBase):
    def __init__(self, data, parent=None):
        super().__init__(data, parent)
        self._items = []
        self._load_items()
        self._threads = {}
        self._build()

    def _load_items(self):
        try:
            self._items = json.loads(self.data.cmd) if self.data.cmd else []
        except Exception:
            self._items = []

    def _save_items(self):
        self.data.cmd = json.dumps(self._items, ensure_ascii=False)

    def _build(self):
        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(6, 4, 6, 6)
        self._root.setSpacing(2)

        self._title_lbl = None

        self._dock_area = QWidget()
        self._dock_area.setStyleSheet("background:transparent; border:none;")
        self._dock_layout = QHBoxLayout(self._dock_area)
        self._dock_layout.setContentsMargins(4, 0, 4, 0)
        self._dock_layout.setSpacing(0)
        self._dock_layout.setAlignment(Qt.AlignCenter)
        self._root.addWidget(self._dock_area, 1)

        self._rebuild_icons()

    def _rebuild_icons(self):
        while self._dock_layout.count():
            item = self._dock_layout.takeAt(0)
            w = item.widget()
            if w: w.deleteLater()

        for i, it in enumerate(self._items):
            icon_w = _DockIcon(it, i, self)
            icon_w.launched.connect(self._launch_item)
            icon_w.edit_requested.connect(self._edit_item)
            icon_w.remove_requested.connect(self._remove_item)
            self._dock_layout.addWidget(icon_w, alignment=Qt.AlignVCenter)

        add_btn = QPushButton("+")
        add_btn.setFixedSize(48, 48)
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.setStyleSheet(f"""
            QPushButton {{
                background: {_bg('surface0')}; color: {C['overlay0']}; border: 2px dashed {C['surface2']};
                border-radius: 12px; font-size: 22px; font-weight: bold;
            }}
            QPushButton:hover {{ background: {_bg('surface1')}; color: {C['text']}; border-color: {C['overlay0']}; }}
        """)
        add_btn.setToolTip("添加项目")
        add_btn.clicked.connect(self._add_item)
        self._dock_layout.addWidget(add_btn, alignment=Qt.AlignVCenter)

    def _add_item(self):
        dlg = _DockItemDialog(parent=self)
        if dlg.exec_() == QDialog.Accepted:
            self._items.append(dlg.get_item())
            self._save_items()
            self._rebuild_icons()
            self._save_to_parent()

    def _edit_item(self, idx):
        if 0 <= idx < len(self._items):
            dlg = _DockItemDialog(self._items[idx], self)
            if dlg.exec_() == QDialog.Accepted:
                self._items[idx] = dlg.get_item()
                self._save_items()
                self._rebuild_icons()
                self._save_to_parent()

    def _remove_item(self, idx):
        if 0 <= idx < len(self._items):
            self._items.pop(idx)
            self._save_items()
            self._rebuild_icons()
            self._save_to_parent()

    def _launch_item(self, idx):
        if idx in self._threads and self._threads[idx].isRunning():
            return
        if 0 <= idx < len(self._items):
            it = self._items[idx]
            t = _LaunchThread(it.get("path", ""), it.get("sub_type", SUB_APP))
            t.finished.connect(lambda ok, msg, i=idx: self._on_launch_done(i, ok, msg))
            self._threads[idx] = t
            t.start()

    def _on_launch_done(self, idx, ok, msg):
        pass

    def _save_to_parent(self):
        w = self.window()
        if w and hasattr(w, '_save_data'):
            w._save_data()

    def update_from_data(self):
        self._load_items()
        self._rebuild_icons()

    def contextMenuEvent(self, e):
        from PyQt5.QtWidgets import QMenu
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{ background: {_bg('surface0')}; color: {C['text']}; border: 1px solid {C['surface2']}; border-radius: 6px; padding: 4px; }}
            QMenu::item {{ padding: 6px 20px; border-radius: 4px; }}
            QMenu::item:selected {{ background: {_bg('surface1')}; }}
        """)
        add_act = menu.addAction("➕ 添加项目")
        menu.addSeparator()
        edit_act = menu.addAction("✏️ 修改")
        del_act = menu.addAction("🗑️ 删除")
        if self._group_id:
            menu.addSeparator()
            ungrp_act = menu.addAction("📤 解除组合")
        else:
            ungrp_act = None
        act = menu.exec_(e.globalPos())
        if act == add_act:
            self._add_item()
        elif act == edit_act:
            grid = self.parent()
            if grid and hasattr(grid, '_edit'):
                grid._edit(self)
        elif act == del_act:
            grid = self.parent()
            if grid and hasattr(grid, '_delete'):
                grid._delete(self)
        elif ungrp_act and act == ungrp_act:
            grid = self.parent()
            if grid and hasattr(grid, '_ungroup'):
                grid._ungroup(self._group_id)


class _DockIcon(QWidget):
    launched = pyqtSignal(int)
    edit_requested = pyqtSignal(int)
    remove_requested = pyqtSignal(int)

    def __init__(self, item_data, idx, parent=None):
        super().__init__(parent)
        self._item = item_data
        self._idx = idx
        self._scale = 1.0
        self._target_scale = 1.0
        self._base_size = 48
        self.setFixedSize(self._base_size + 16, self._base_size + 16)
        self.setCursor(Qt.PointingHandCursor)
        self.setMouseTracking(True)

        self.setToolTip(item_data.get("name", ""))

        self._pm = None
        icon_path = item_data.get("icon", "")
        if icon_path and os.path.isfile(icon_path):
            self._pm = QPixmap(icon_path)

        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(16)
        self._anim_timer.timeout.connect(self._animate_step)

    def _animate_step(self):
        diff = self._target_scale - self._scale
        if abs(diff) < 0.02:
            self._scale = self._target_scale
            self._anim_timer.stop()
        else:
            self._scale += diff * 0.3
        self.update()

    def enterEvent(self, e):
        self._target_scale = 1.35
        if not self._anim_timer.isActive():
            self._anim_timer.start()

    def leaveEvent(self, e):
        self._target_scale = 1.0
        if not self._anim_timer.isActive():
            self._anim_timer.start()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.launched.emit(self._idx)

    def contextMenuEvent(self, e):
        from PyQt5.QtWidgets import QMenu
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{ background: {C['surface0']}; color: {C['text']}; border: 1px solid {C['surface2']}; border-radius: 6px; padding: 4px; }}
            QMenu::item {{ padding: 6px 16px; border-radius: 4px; }}
            QMenu::item:selected {{ background: {C['surface1']}; }}
        """)
        edit_act = menu.addAction("✏️ 编辑")
        del_act = menu.addAction("🗑️ 移除")
        act = menu.exec_(e.globalPos())
        if act == edit_act:
            self.edit_requested.emit(self._idx)
        elif act == del_act:
            self.remove_requested.emit(self._idx)
        e.accept()

    def paintEvent(self, e):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        s = int(self._base_size * self._scale)
        cx, cy = w // 2, h // 2

        if self._pm:
            scaled = self._pm.scaled(s, s, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            p.drawPixmap(cx - scaled.width() // 2, cy - scaled.height() // 2, scaled)
        else:
            sub_icons = {SUB_APP: "🖥️", SUB_SCRIPT: "📜", SUB_FILE: "📄"}
            icon_ch = sub_icons.get(self._item.get("sub_type", SUB_APP), "🔗")
            f = p.font()
            f.setPixelSize(int(24 * self._scale))
            p.setFont(f)
            p.setPen(QColor(C['text']))
            p.drawText(QRect(0, cy - s // 2, w, s), Qt.AlignCenter, icon_ch)

        pass  # name shown via tooltip

        p.end()


class _TodoEditDialog(QDialog):
    def __init__(self, text="", deadline="", parent=None):
        super().__init__(parent)
        self.setWindowTitle("编辑待办")
        self.setFixedWidth(380)
        self.setStyleSheet(f"""
            QDialog {{ background: {C['base']}; color: {C['text']}; }}
            QLabel {{ color: {C['text']}; font-size: 13px; }}
            QLineEdit {{ background: {C['surface0']}; color: {C['text']}; border: 1px solid {C['surface2']};
                         border-radius: 6px; padding: 6px; font-size: 12px; }}
        """)
        lay = QVBoxLayout(self)
        form = QFormLayout(); form.setSpacing(10)
        self._text_edit = QLineEdit(text)
        self._text_edit.setPlaceholderText("待办内容")
        form.addRow("内容", self._text_edit)
        self._deadline_edit = QLineEdit(deadline)
        self._deadline_edit.setPlaceholderText("截止日期 (YYYY-MM-DD)，可选")
        form.addRow("截止", self._deadline_edit)
        lay.addLayout(form)
        lay.addStretch()
        btns = QHBoxLayout(); btns.addStretch()
        cancel = QPushButton("取消")
        cancel.setStyleSheet(f"background:{C['surface1']}; color:{C['text']}; border:none; border-radius:8px; padding:8px 20px; font-size:13px;")
        cancel.setCursor(Qt.PointingHandCursor)
        cancel.clicked.connect(self.reject); btns.addWidget(cancel)
        ok = QPushButton("确定")
        ok.setStyleSheet(f"background:{C['blue']}; color:{C['crust']}; border:none; border-radius:8px; padding:8px 20px; font-size:13px; font-weight:bold;")
        ok.setCursor(Qt.PointingHandCursor)
        ok.clicked.connect(self._validate); btns.addWidget(ok)
        lay.addLayout(btns)

    def _validate(self):
        if self._text_edit.text().strip():
            self.accept()

    def get_data(self):
        return self._text_edit.text().strip(), self._deadline_edit.text().strip()


class TodoWidget(CompBase):
    def __init__(self, data, parent=None):
        super().__init__(data, parent)
        self._todos = []
        self._load_todos()
        self._build()

    def _load_todos(self):
        try:
            self._todos = json.loads(self.data.cmd) if self.data.cmd else []
        except Exception:
            self._todos = []

    def _save_todos(self):
        self.data.cmd = json.dumps(self._todos, ensure_ascii=False)
        w = self.window()
        if w and hasattr(w, '_save_data'):
            w._save_data()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 8); root.setSpacing(6)

        header = QHBoxLayout(); header.setSpacing(4)
        title = QLabel("📋 待办事项")
        title.setStyleSheet(f"color:{C['text']}; font-size:13px; font-weight:bold; background:transparent; border:none;")
        header.addWidget(title)
        header.addStretch()
        count_lbl = QLabel()
        count_lbl.setStyleSheet(f"color:{C['subtext0']}; font-size:11px; background:transparent; border:none;")
        header.addWidget(count_lbl)
        self._count_lbl = count_lbl
        root.addLayout(header)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet(f"QScrollArea {{ border:none; background:transparent; }}")
        self._list_w = QWidget()
        self._list_w.setStyleSheet("background:transparent;")
        self._list_lay = QVBoxLayout(self._list_w)
        self._list_lay.setContentsMargins(0, 0, 0, 0)
        self._list_lay.setSpacing(2)
        self._scroll.setWidget(self._list_w)
        root.addWidget(self._scroll, 1)

        add_row = QHBoxLayout(); add_row.setSpacing(4)
        self._add_edit = QLineEdit()
        self._add_edit.setPlaceholderText("添加新待办…")
        self._add_edit.setStyleSheet(f"background:{_bg('surface0')}; color:{C['text']}; border:1px solid {C['surface2']}; border-radius:6px; padding:4px 8px; font-size:12px;")
        self._add_edit.returnPressed.connect(self._add_todo)
        add_row.addWidget(self._add_edit, 1)
        add_btn = QPushButton("+")
        add_btn.setFixedSize(28, 28)
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.setStyleSheet(f"""
            QPushButton {{ background:{C['blue']}; color:{C['crust']}; border:none; border-radius:6px; font-size:16px; font-weight:bold; }}
            QPushButton:hover {{ background:{C['blue']}; }}
        """)
        add_btn.clicked.connect(self._add_todo)
        add_row.addWidget(add_btn)
        root.addLayout(add_row)

        self._rebuild_list()

    def _add_todo(self):
        text = self._add_edit.text().strip()
        if not text:
            return
        self._todos.append({"text": text, "done": False, "id": str(uuid.uuid4()), "deadline": ""})
        self._add_edit.clear()
        self._save_todos()
        self._rebuild_list()

    def _toggle_todo(self, tid):
        for t in self._todos:
            if t["id"] == tid:
                t["done"] = not t["done"]
                break
        self._save_todos()
        self._rebuild_list()

    def _edit_todo(self, tid):
        for t in self._todos:
            if t["id"] == tid:
                dlg = _TodoEditDialog(t["text"], t.get("deadline", ""), self)
                if dlg.exec_() == QDialog.Accepted:
                    text, deadline = dlg.get_data()
                    t["text"] = text
                    t["deadline"] = deadline
                    self._save_todos()
                    self._rebuild_list()
                break

    def _delete_todo(self, tid):
        self._todos = [t for t in self._todos if t["id"] != tid]
        self._save_todos()
        self._rebuild_list()

    def _make_row(self, t):
        row = QWidget()
        row.setStyleSheet(f"background:{_bg('surface0')}; border-radius:6px;")
        rl = QHBoxLayout(row); rl.setContentsMargins(8, 6, 8, 6); rl.setSpacing(8)

        chk = QCheckBox()
        chk.setChecked(t.get("done", False))
        chk.setStyleSheet(f"""
            QCheckBox::indicator {{ width:16px; height:16px; border-radius:4px; border:2px solid {C['overlay0']}; background:transparent; }}
            QCheckBox::indicator:checked {{ border:2px solid {C['green']}; background:transparent; image: url({CHECK_PATH}); }}
        """)
        chk.toggled.connect(lambda _, tid=t["id"]: self._toggle_todo(tid))
        rl.addWidget(chk)

        info_lay = QVBoxLayout(); info_lay.setSpacing(1)
        lbl = QLabel(t["text"])
        is_overdue = False
        deadline = t.get("deadline", "")
        if deadline:
            try:
                dl = datetime.datetime.strptime(deadline, "%Y-%m-%d").date()
                if dl < datetime.date.today() and not t.get("done"):
                    is_overdue = True
            except Exception:
                pass

        if t.get("done"):
            lbl.setStyleSheet(f"color:{C['overlay0']}; font-size:12px; text-decoration:line-through; background:transparent; border:none;")
        elif is_overdue:
            lbl.setStyleSheet(f"color:{C['red']}; font-size:12px; font-weight:bold; background:transparent; border:none;")
        else:
            lbl.setStyleSheet(f"color:{C['text']}; font-size:12px; background:transparent; border:none;")
        lbl.setWordWrap(True)
        info_lay.addWidget(lbl)

        if deadline:
            dl_lbl = QLabel(f"截止: {deadline}")
            dl_color = C['red'] if is_overdue else C['subtext0']
            dl_lbl.setStyleSheet(f"color:{dl_color}; font-size:10px; background:transparent; border:none;")
            info_lay.addWidget(dl_lbl)

        rl.addLayout(info_lay, 1)

        edit_btn = QPushButton("编辑")
        edit_btn.setFixedHeight(24)
        edit_btn.setCursor(Qt.PointingHandCursor)
        edit_btn.setStyleSheet(f"""
            QPushButton {{ background:{_bg('surface1')}; color:{C['subtext0']}; border:none; border-radius:4px; font-size:10px; padding:2px 8px; }}
            QPushButton:hover {{ background:{C['surface2']}; color:{C['text']}; }}
        """)
        edit_btn.clicked.connect(lambda _, tid=t["id"]: self._edit_todo(tid))
        rl.addWidget(edit_btn)

        del_btn = QPushButton("删除")
        del_btn.setFixedHeight(24)
        del_btn.setCursor(Qt.PointingHandCursor)
        del_btn.setStyleSheet(f"""
            QPushButton {{ background:transparent; color:{C['subtext0']}; border:none; border-radius:4px; font-size:10px; padding:2px 8px; }}
            QPushButton:hover {{ background:{C['red']}; color:{C['crust']}; }}
        """)
        del_btn.clicked.connect(lambda _, tid=t["id"]: self._delete_todo(tid))
        rl.addWidget(del_btn)

        return row

    def _rebuild_list(self):
        while self._list_lay.count():
            item = self._list_lay.takeAt(0)
            w = item.widget()
            if w: w.deleteLater()

        pending = [t for t in self._todos if not t.get("done")]
        done = [t for t in self._todos if t.get("done")]
        done_count = len(done)
        total = len(self._todos)
        self._count_lbl.setText(f"{done_count}/{total}")

        for t in pending:
            self._list_lay.addWidget(self._make_row(t))

        if done:
            collapse_btn = QPushButton(f"{'▾' if getattr(self, '_done_expanded', True) else '▸'} 已完成 ({len(done)})")
            collapse_btn.setCursor(Qt.PointingHandCursor)
            collapse_btn.setStyleSheet(f"""
                QPushButton {{ color:{C['overlay0']}; font-size:11px; background:transparent; border:none; text-align:left; padding:4px 0; }}
                QPushButton:hover {{ color:{C['subtext0']}; }}
            """)
            collapse_btn.clicked.connect(self._toggle_done_section)
            self._list_lay.addWidget(collapse_btn)
            if getattr(self, '_done_expanded', True):
                for t in done:
                    self._list_lay.addWidget(self._make_row(t))

        self._list_lay.addStretch()

    def _toggle_done_section(self):
        self._done_expanded = not getattr(self, '_done_expanded', True)
        self._rebuild_list()

    def update_from_data(self):
        self._load_todos()
        self._rebuild_list()


# ---------------------------------------------------------------------------
# Circle Icon Buttons for Stopwatch / Timer
# ---------------------------------------------------------------------------
class _CircleBtn(QPushButton):
    """Circular button with custom-painted icon."""
    PLAY, PAUSE, LAP, RESET = range(4)

    def __init__(self, icon_type, size=40, parent=None):
        super().__init__(parent)
        self._icon_type = icon_type
        self._size = size
        self.setFixedSize(size, size)
        self.setCursor(Qt.PointingHandCursor)
        self._bg = C['green']
        self._fg = C['crust']

    def set_colors(self, bg, fg):
        self._bg = bg; self._fg = fg; self.update()

    def set_icon_type(self, icon_type):
        self._icon_type = icon_type; self.update()

    def paintEvent(self, e):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        s = self._size
        p.setBrush(QColor(self._bg)); p.setPen(Qt.NoPen)
        p.drawEllipse(0, 0, s, s)
        p.setPen(Qt.NoPen); p.setBrush(QColor(self._fg))
        cx, cy = s // 2, s // 2
        if self._icon_type == self.PLAY:
            tri_h = int(s * 0.38); tri_w = int(s * 0.32)
            pts = [QPoint(cx - tri_w // 3, cy - tri_h // 2),
                   QPoint(cx - tri_w // 3, cy + tri_h // 2),
                   QPoint(cx + tri_w * 2 // 3, cy)]
            p.drawPolygon(QPolygon(pts))
        elif self._icon_type == self.PAUSE:
            bw = max(3, int(s * 0.09)); bh = int(s * 0.36)
            gap = int(s * 0.10)
            p.drawRoundedRect(cx - gap - bw, cy - bh // 2, bw, bh, 1, 1)
            p.drawRoundedRect(cx + gap, cy - bh // 2, bw, bh, 1, 1)
        elif self._icon_type == self.LAP:
            pen = QPen(QColor(self._fg), max(2, int(s * 0.07)))
            p.setPen(pen); p.setBrush(Qt.NoBrush)
            fh = int(s * 0.36); fw = int(s * 0.24)
            p.drawLine(cx, cy - fh // 2, cx, cy + fh // 2)
            p.drawLine(cx, cy - fh // 2, cx + fw, cy - fh // 2 + int(fh * 0.25))
        elif self._icon_type == self.RESET:
            pen = QPen(QColor(self._fg), max(2, int(s * 0.07)))
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen); p.setBrush(Qt.NoBrush)
            r = int(s * 0.22)
            p.drawArc(cx - r, cy - r, r * 2, r * 2, 60 * 16, 270 * 16)
            ah = int(s * 0.10)
            ax = cx + int(r * 0.5); ay = cy - r
            p.drawLine(ax, ay, ax + ah, ay - ah // 2)
            p.drawLine(ax, ay, ax + ah, ay + ah // 2)
        p.end()


class _TimerAlertOverlay(QWidget):
    """Fullscreen red alert overlay when timer finishes."""
    def __init__(self, parent=None):
        super().__init__(None)
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self._elapsed = 0

        root = QVBoxLayout(self)
        root.setAlignment(Qt.AlignCenter)

        self._title = QLabel("⏰ 计时已结束")
        self._title.setAlignment(Qt.AlignCenter)
        self._title.setStyleSheet("color: white; font-size: 48px; font-weight: bold; background: transparent;")
        root.addWidget(self._title)

        self._elapsed_lbl = QLabel("0 秒")
        self._elapsed_lbl.setAlignment(Qt.AlignCenter)
        self._elapsed_lbl.setStyleSheet("color: rgba(255,255,255,0.8); font-size: 72px; font-weight: bold; font-family: 'JetBrains Mono','Consolas',monospace; background: transparent;")
        root.addWidget(self._elapsed_lbl)

        hint = QLabel("按任意键退出")
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet("color: rgba(255,255,255,0.4); font-size: 16px; background: transparent; padding-top: 40px;")
        root.addWidget(hint)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(1000)

        self._sound_proc = None

    def start_sound(self):
        try:
            self._sound_proc = subprocess.Popen(
                ["paplay", "/usr/share/sounds/freedesktop/stereo/alarm-clock-elapsed.oga"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            try:
                self._sound_proc = subprocess.Popen(
                    ["paplay", "/usr/share/sounds/freedesktop/stereo/complete.oga"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass

    def _tick(self):
        self._elapsed += 1
        self._elapsed_lbl.setText(f"{self._elapsed} 秒")

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(180, 30, 30))
        p.end()

    def keyPressEvent(self, e):
        self._close()

    def mousePressEvent(self, e):
        self._close()

    def _close(self):
        self._timer.stop()
        if self._sound_proc:
            try: self._sound_proc.terminate()
            except Exception: pass
        self.close()


# ---------------------------------------------------------------------------
# Fullscreen Flip Clock (全屏翻页时钟)
# ---------------------------------------------------------------------------
class _FlipDigit(QWidget):
    """A single flip-clock digit card (displays 2-char text like '23')."""
    def __init__(self, text="00", parent=None):
        super().__init__(parent)
        self._text = text
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_text(self, text):
        if text != self._text:
            self._text = text
            self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        radius = min(w, h) * 0.08
        card_color = QColor("#2a2a2a")
        p.setBrush(card_color)
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(0, 0, w, h, radius, radius)
        gap_y = h // 2
        gap_color = QColor("#1a1a1a")
        p.setBrush(gap_color)
        p.drawRect(0, gap_y - 1, w, 2)
        text_color = QColor("#e8dcc8")
        p.setPen(text_color)
        font_size = int(h * 0.48)
        font = QFont("Arial Black", font_size, QFont.Black)
        font.setLetterSpacing(QFont.PercentageSpacing, 95)
        p.setFont(font)
        p.drawText(self.rect(), Qt.AlignCenter, self._text)
        p.end()


class FullscreenClockWindow(QWidget):
    """Fullscreen flip-clock overlay that prevents system sleep."""
    def __init__(self, clock_param="", parent=None):
        super().__init__(None)
        self._clock_param = clock_param
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setStyleSheet("background: #111111;")
        self.setCursor(Qt.BlankCursor)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addStretch(4)

        self._info_lbl = QLabel("")
        self._info_lbl.setAlignment(Qt.AlignCenter)
        self._info_lbl.setStyleSheet("color: #b0a890; font-size: 22px; background: transparent; padding: 0 0 18px 0;")
        root.addWidget(self._info_lbl)

        cards = QHBoxLayout()
        cards.setSpacing(20)
        cards.setAlignment(Qt.AlignCenter)
        self._h_card = _FlipDigit("00")
        self._m_card = _FlipDigit("00")
        self._s_card = _FlipDigit("00")
        for card in (self._h_card, self._m_card, self._s_card):
            cards.addWidget(card)
        self._cards_widget = QWidget()
        self._cards_widget.setStyleSheet("background: transparent;")
        self._cards_widget.setLayout(cards)
        root.addWidget(self._cards_widget)

        self._hint_lbl = QLabel("按 ESC 退出")
        self._hint_lbl.setAlignment(Qt.AlignCenter)
        self._hint_lbl.setStyleSheet("color: #444; font-size: 14px; background: transparent; padding: 24px 0 0 0;")
        root.addWidget(self._hint_lbl)

        root.addStretch(5)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(500)

        self._caffeine_proc = None
        self._start_caffeine()
        self._tick()

    def _start_caffeine(self):
        try:
            self._caffeine_proc = subprocess.Popen(
                ["systemd-inhibit", "--what=idle:sleep", "--who=FastPanel",
                 "--why=Fullscreen clock", "--mode=block", "sleep", "86400"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            try:
                self._caffeine_proc = subprocess.Popen(
                    ["xdg-screensaver", "suspend", str(int(self.winId()))],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                try:
                    self._caffeine_proc = subprocess.Popen(
                        ["caffeine"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                except Exception:
                    self._caffeine_proc = None

    def _stop_caffeine(self):
        if self._caffeine_proc:
            try:
                self._caffeine_proc.terminate()
                self._caffeine_proc.wait(timeout=3)
            except Exception:
                try: self._caffeine_proc.kill()
                except Exception: pass
            self._caffeine_proc = None

    def resizeEvent(self, e):
        super().resizeEvent(e)
        screen_w = self.width()
        card_w = min(int(screen_w * 0.22), 380)
        card_h = int(card_w * 1.15)
        for card in (self._h_card, self._m_card, self._s_card):
            card.setFixedSize(card_w, card_h)
        info_size = max(18, int(card_h * 0.14))
        self._info_lbl.setStyleSheet(f"color: #b0a890; font-size: {info_size}px; background: transparent; padding: 0 0 18px 0;")

    def _tick(self):
        now = datetime.datetime.now()
        self._h_card.set_text(f"{now.hour:02d}")
        self._m_card.set_text(f"{now.minute:02d}")
        self._s_card.set_text(f"{now.second:02d}")
        weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        date_str = f"{now.year}年{now.month}月{now.day}日"
        lunar_str = ""
        try:
            ly, lm, ld, leap, gan, zhi, sx = _solar_to_lunar(now.year, now.month, now.day)
            _LM = ["正", "二", "三", "四", "五", "六", "七", "八", "九", "十", "冬", "腊"]
            _LD = ["初一", "初二", "初三", "初四", "初五", "初六", "初七", "初八", "初九", "初十",
                   "十一", "十二", "十三", "十四", "十五", "十六", "十七", "十八", "十九", "二十",
                   "廿一", "廿二", "廿三", "廿四", "廿五", "廿六", "廿七", "廿八", "廿九", "三十"]
            lm_name = ("闰" if leap else "") + _LM[lm - 1]
            ld_name = _LD[ld - 1] if 1 <= ld <= 30 else str(ld)
            lunar_str = f" {lm_name}月{ld_name}"
        except Exception:
            pass
        self._info_lbl.setText(f"{date_str}{lunar_str} {weekdays[now.weekday()]}")

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self._close_fullscreen()

    def mousePressEvent(self, e):
        pass

    def _close_fullscreen(self):
        self._stop_caffeine()
        self._timer.stop()
        self.close()

    def closeEvent(self, e):
        self._stop_caffeine()
        self._timer.stop()
        super().closeEvent(e)


# ---------------------------------------------------------------------------
# Clock Widget (时钟 / 世界时钟 / 秒表 / 计时器)
# ---------------------------------------------------------------------------
_WORLD_TIMEZONES = [
    ("亚洲/上海 (北京)", "Asia/Shanghai", 8),
    ("亚洲/东京", "Asia/Tokyo", 9),
    ("亚洲/首尔", "Asia/Seoul", 9),
    ("亚洲/新加坡", "Asia/Singapore", 8),
    ("亚洲/香港", "Asia/Hong_Kong", 8),
    ("亚洲/台北", "Asia/Taipei", 8),
    ("亚洲/曼谷", "Asia/Bangkok", 7),
    ("亚洲/雅加达", "Asia/Jakarta", 7),
    ("亚洲/加尔各答", "Asia/Kolkata", 5.5),
    ("亚洲/迪拜", "Asia/Dubai", 4),
    ("欧洲/伦敦", "Europe/London", 0),
    ("欧洲/巴黎", "Europe/Paris", 1),
    ("欧洲/柏林", "Europe/Berlin", 1),
    ("欧洲/莫斯科", "Europe/Moscow", 3),
    ("美洲/纽约", "America/New_York", -5),
    ("美洲/芝加哥", "America/Chicago", -6),
    ("美洲/洛杉矶", "America/Los_Angeles", -8),
    ("美洲/圣保罗", "America/Sao_Paulo", -3),
    ("大洋洲/悉尼", "Australia/Sydney", 11),
    ("大洋洲/奥克兰", "Pacific/Auckland", 13),
    ("非洲/开罗", "Africa/Cairo", 2),
    ("非洲/约翰内斯堡", "Africa/Johannesburg", 2),
]


class ClockWidget(CompBase):
    def __init__(self, data, parent=None):
        super().__init__(data, parent)
        self._parse_clock_cmd()
        self._build()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(100 if self._clock_sub == CLOCK_SUB_STOPWATCH else 1000)

    def refresh_theme(self):
        super().refresh_theme()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(100 if self._clock_sub == CLOCK_SUB_STOPWATCH else 1000)
        self._tick()

    def _parse_clock_cmd(self):
        raw = self.data.cmd.strip()
        parts = raw.split("|", 1) if raw else []
        self._clock_sub = parts[0] if parts and parts[0] else CLOCK_SUB_CLOCK
        self._clock_param = parts[1] if len(parts) > 1 else ""

    def _build(self):
        sub = self._clock_sub
        if sub == CLOCK_SUB_CLOCK:
            self._build_clock()
        elif sub == CLOCK_SUB_WORLD:
            self._build_world()
        elif sub == CLOCK_SUB_STOPWATCH:
            self._build_stopwatch()
        elif sub == CLOCK_SUB_TIMER:
            self._build_timer()
        elif sub == CLOCK_SUB_ALARM:
            self._build_alarm()

    def _build_clock(self):
        self._fs_win = None
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 10, 14, 8); root.setSpacing(4)
        root.setAlignment(Qt.AlignCenter)

        self._fs_btn = _ExpandBtn(self)
        self._fs_btn.setToolTip("全屏时钟")
        self._fs_btn.clicked.connect(self._open_fullscreen_clock)
        self._fs_btn.raise_()

        self._time_lbl = QLabel("--:--:--")
        self._time_lbl.setStyleSheet(f"color:{C['text']}; font-size:42px; font-weight:bold;")
        self._time_lbl.setAlignment(Qt.AlignCenter)
        root.addWidget(self._time_lbl)

        self._date_lbl = QLabel("")
        self._date_lbl.setStyleSheet(f"color:{C['subtext0']}; font-size:13px;")
        self._date_lbl.setAlignment(Qt.AlignCenter)
        root.addWidget(self._date_lbl)

        self._lunar_lbl = QLabel("")
        self._lunar_lbl.setStyleSheet(f"color:{C['overlay0']}; font-size:11px;")
        self._lunar_lbl.setAlignment(Qt.AlignCenter)
        root.addWidget(self._lunar_lbl)

        self._tick()

    def _open_fullscreen_clock(self):
        try:
            if self._fs_win and self._fs_win.isVisible():
                return
        except RuntimeError:
            self._fs_win = None
        self._fs_win = FullscreenClockWindow(self._clock_param)
        main_win = self.window()
        if main_win:
            screen = QApplication.screenAt(main_win.geometry().center())
            if screen:
                self._fs_win.setGeometry(screen.geometry())
        self._fs_win.showFullScreen()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if hasattr(self, '_fs_btn'):
            self._fs_btn.move(self.width() - self._fs_btn.width() - 6, 6)
            self._fs_btn.raise_()

    def _build_world(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 10, 14, 8); root.setSpacing(6)

        tz_label = self._clock_param or "亚洲/上海 (北京)"
        self._tz_offset = 8
        for name, tz_id, offset in _WORLD_TIMEZONES:
            if tz_id == self._clock_param or name == self._clock_param:
                tz_label = name
                self._tz_offset = offset
                break

        title = QLabel(tz_label)
        title.setStyleSheet(f"color:{C['text']}; font-size:13px; font-weight:bold;")
        title.setAlignment(Qt.AlignCenter)
        root.addWidget(title)

        self._wtime_lbl = QLabel("--:--:--")
        self._wtime_lbl.setStyleSheet(f"color:{C['text']}; font-size:38px; font-weight:bold;")
        self._wtime_lbl.setAlignment(Qt.AlignCenter)
        root.addWidget(self._wtime_lbl)

        self._wdate_lbl = QLabel("")
        self._wdate_lbl.setStyleSheet(f"color:{C['subtext0']}; font-size:12px;")
        self._wdate_lbl.setAlignment(Qt.AlignCenter)
        root.addWidget(self._wdate_lbl)

        self._wdiff_lbl = QLabel("")
        self._wdiff_lbl.setStyleSheet(f"color:{C['overlay0']}; font-size:11px;")
        self._wdiff_lbl.setAlignment(Qt.AlignCenter)
        root.addWidget(self._wdiff_lbl)

        self._tick()

    def _build_stopwatch(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 8); root.setSpacing(0)

        self._sw_running = False
        self._sw_elapsed_ms = 0
        self._sw_start_time = None
        self._sw_laps = []
        self._sw_has_laps = False

        self._sw_main = QWidget(); self._sw_main.setStyleSheet("background:transparent;")
        main_lay = QVBoxLayout(self._sw_main); main_lay.setContentsMargins(0, 0, 0, 0); main_lay.setSpacing(8)
        main_lay.setAlignment(Qt.AlignCenter)

        self._sw_display = QLabel("00:00.000")
        self._sw_display.setStyleSheet(f"color:{C['text']}; font-size:38px; font-weight:bold; font-family:'JetBrains Mono','Consolas',monospace;")
        self._sw_display.setAlignment(Qt.AlignCenter)
        main_lay.addWidget(self._sw_display)

        btns = QHBoxLayout(); btns.setSpacing(16); btns.setAlignment(Qt.AlignCenter)
        self._sw_reset_btn = _CircleBtn(_CircleBtn.RESET, 38, self)
        self._sw_reset_btn.set_colors(C['surface1'], C['text'])
        self._sw_reset_btn.setToolTip("重置")
        self._sw_reset_btn.clicked.connect(self._sw_reset)
        btns.addWidget(self._sw_reset_btn)
        self._sw_start_btn = _CircleBtn(_CircleBtn.PLAY, 46, self)
        self._sw_start_btn.set_colors(C['green'], C['crust'])
        self._sw_start_btn.setToolTip("开始")
        self._sw_start_btn.clicked.connect(self._sw_toggle)
        btns.addWidget(self._sw_start_btn)
        self._sw_lap_btn = _CircleBtn(_CircleBtn.LAP, 38, self)
        self._sw_lap_btn.set_colors(C['surface2'], C['overlay0'])
        self._sw_lap_btn.setToolTip("分段")
        self._sw_lap_btn.setEnabled(False)
        self._sw_lap_btn.clicked.connect(self._sw_lap)
        btns.addWidget(self._sw_lap_btn)
        main_lay.addLayout(btns)

        self._sw_hint = QLabel("点击开始计时")
        self._sw_hint.setStyleSheet(f"color:{C['overlay0']}; font-size:12px; background:transparent;")
        self._sw_hint.setAlignment(Qt.AlignCenter)
        main_lay.addWidget(self._sw_hint)

        root.addStretch(1)
        root.addWidget(self._sw_main)
        root.addStretch(1)
        self._sw_bottom_stretch_idx = root.count() - 1

        self._sw_lap_scroll = QScrollArea()
        self._sw_lap_scroll.setWidgetResizable(True)
        self._sw_lap_scroll.setStyleSheet(f"""QScrollArea {{ border: none; background: transparent; }}
            QScrollBar:vertical {{ width:4px; background:transparent; }}
            QScrollBar::handle:vertical {{ background:{C['surface2']}; border-radius:2px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; }}""")
        self._sw_lap_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._sw_lap_container = QWidget()
        self._sw_lap_container.setStyleSheet("background:transparent;")
        self._sw_lap_lay = QVBoxLayout(self._sw_lap_container)
        self._sw_lap_lay.setSpacing(3); self._sw_lap_lay.setContentsMargins(0, 4, 0, 0)
        self._sw_lap_scroll.setWidget(self._sw_lap_container)
        self._sw_lap_scroll.hide()
        root.addWidget(self._sw_lap_scroll, 1)

    def _build_timer(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 8); root.setSpacing(8)
        root.setAlignment(Qt.AlignCenter)

        self._tm_total_secs = 0
        self._tm_remain_secs = 0
        self._tm_running = False

        param = self._clock_param
        self._tm_alert = "alert" in param
        self._tm_h_val = 0
        self._tm_m_val = 0
        self._tm_s_val = 0
        for part in param.split("|"):
            if ":" in part:
                try:
                    hms = part.split(":")
                    self._tm_h_val = int(hms[0])
                    self._tm_m_val = int(hms[1]) if len(hms) > 1 else 0
                    self._tm_s_val = int(hms[2]) if len(hms) > 2 else 0
                except (ValueError, IndexError):
                    pass

        self._tm_display = QLabel("00:00:00")
        self._tm_display.setStyleSheet(f"color:{C['text']}; font-size:38px; font-weight:bold; font-family:'JetBrains Mono','Consolas',monospace;")
        self._tm_display.setAlignment(Qt.AlignCenter)
        self._tm_display.hide()
        root.addWidget(self._tm_display)

        set_row = QHBoxLayout(); set_row.setSpacing(2); set_row.setAlignment(Qt.AlignCenter)
        _arrow_style = f"background:transparent; color:{C['subtext0']}; border:none; font-size:14px; padding:2px 0;"
        _edit_style = f"""QLineEdit {{ color:{C['text']}; font-size:32px; font-weight:bold;
            font-family:'JetBrains Mono','Consolas',monospace; background:transparent;
            border:none; padding:0; }}
            QLineEdit:focus {{ border-bottom:2px solid {C['blue']}; }}"""

        def _make_digit_col(max_val, attr_name):
            col = QVBoxLayout(); col.setSpacing(0); col.setAlignment(Qt.AlignCenter)
            up_btn = QPushButton("▲"); up_btn.setFixedSize(44, 22)
            up_btn.setStyleSheet(_arrow_style); up_btn.setCursor(Qt.PointingHandCursor)
            col.addWidget(up_btn, alignment=Qt.AlignCenter)
            val_edit = QLineEdit("00")
            val_edit.setFixedWidth(48); val_edit.setAlignment(Qt.AlignCenter)
            val_edit.setStyleSheet(_edit_style)
            val_edit.setValidator(QIntValidator(0, max_val))
            val_edit.setMaxLength(2)
            col.addWidget(val_edit, alignment=Qt.AlignCenter)
            dn_btn = QPushButton("▼"); dn_btn.setFixedSize(44, 22)
            dn_btn.setStyleSheet(_arrow_style); dn_btn.setCursor(Qt.PointingHandCursor)
            col.addWidget(dn_btn, alignment=Qt.AlignCenter)
            def _up():
                v = getattr(self, attr_name) + 1
                if v > max_val: v = 0
                setattr(self, attr_name, v)
                val_edit.setText(f"{v:02d}")
                self._tm_update_display_from_dials()
            def _dn():
                v = getattr(self, attr_name) - 1
                if v < 0: v = max_val
                setattr(self, attr_name, v)
                val_edit.setText(f"{v:02d}")
                self._tm_update_display_from_dials()
            def _on_edit():
                txt = val_edit.text().strip()
                v = int(txt) if txt.isdigit() else 0
                v = min(v, max_val)
                setattr(self, attr_name, v)
                self._tm_update_display_from_dials()
            up_btn.clicked.connect(_up); dn_btn.clicked.connect(_dn)
            val_edit.editingFinished.connect(_on_edit)
            setattr(self, f'{attr_name}_edit', val_edit)
            return col

        set_row.addLayout(_make_digit_col(23, '_tm_h_val'))
        sep1 = QLabel(":"); sep1.setStyleSheet(f"color:{C['overlay0']}; font-size:28px; font-weight:bold; background:transparent;")
        set_row.addWidget(sep1)
        set_row.addLayout(_make_digit_col(59, '_tm_m_val'))
        sep2 = QLabel(":"); sep2.setStyleSheet(f"color:{C['overlay0']}; font-size:28px; font-weight:bold; background:transparent;")
        set_row.addWidget(sep2)
        set_row.addLayout(_make_digit_col(59, '_tm_s_val'))

        self._tm_set_row = QWidget(); self._tm_set_row.setLayout(set_row)
        root.addWidget(self._tm_set_row)

        if self._tm_h_val or self._tm_m_val or self._tm_s_val:
            if hasattr(self, '_tm_h_val_edit'):
                self._tm_h_val_edit.setText(f"{self._tm_h_val:02d}")
            if hasattr(self, '_tm_m_val_edit'):
                self._tm_m_val_edit.setText(f"{self._tm_m_val:02d}")
            if hasattr(self, '_tm_s_val_edit'):
                self._tm_s_val_edit.setText(f"{self._tm_s_val:02d}")

        btns = QHBoxLayout(); btns.setSpacing(14); btns.setAlignment(Qt.AlignCenter)
        self._tm_reset_btn = _CircleBtn(_CircleBtn.RESET, 38, self)
        self._tm_reset_btn.set_colors(C['surface1'], C['text'])
        self._tm_reset_btn.setToolTip("重置")
        self._tm_reset_btn.clicked.connect(self._tm_reset)
        btns.addWidget(self._tm_reset_btn)
        self._tm_start_btn = _CircleBtn(_CircleBtn.PLAY, 46, self)
        self._tm_start_btn.set_colors(C['green'], C['crust'])
        self._tm_start_btn.setToolTip("开始")
        self._tm_start_btn.clicked.connect(self._tm_toggle)
        btns.addWidget(self._tm_start_btn)

        self._tm_alert_mode = 2 if self._tm_alert else 0
        _alert_icons = ["🔕", "🔇", "🔔"]
        _alert_tips = ["不提醒", "静音提醒（弹窗）", "声音提醒（弹窗+声音）"]
        _alert_colors = [(C['surface2'], C['overlay0']), (C['blue'], C['crust']), (C['peach'], C['crust'])]
        self._tm_alert_btn = QPushButton(_alert_icons[self._tm_alert_mode])
        self._tm_alert_btn.setFixedSize(38, 38)
        bg, fg = _alert_colors[self._tm_alert_mode]
        self._tm_alert_btn.setStyleSheet(f"background:{bg}; color:{fg}; border:none; border-radius:19px; font-size:16px;")
        self._tm_alert_btn.setCursor(Qt.PointingHandCursor)
        self._tm_alert_btn.setToolTip(_alert_tips[self._tm_alert_mode])
        def _cycle_alert():
            self._tm_alert_mode = (self._tm_alert_mode + 1) % 3
            self._tm_alert = self._tm_alert_mode >= 1
            self._tm_alert_btn.setText(_alert_icons[self._tm_alert_mode])
            self._tm_alert_btn.setToolTip(_alert_tips[self._tm_alert_mode])
            bg, fg = _alert_colors[self._tm_alert_mode]
            self._tm_alert_btn.setStyleSheet(f"background:{bg}; color:{fg}; border:none; border-radius:19px; font-size:16px;")
            self._tm_save_values()
        self._tm_alert_btn.clicked.connect(_cycle_alert)
        btns.addWidget(self._tm_alert_btn)
        root.addLayout(btns)

        self._tm_status_lbl = QLabel("")
        self._tm_status_lbl.setStyleSheet(f"color:{C['overlay0']}; font-size:12px;")
        self._tm_status_lbl.setAlignment(Qt.AlignCenter)
        root.addWidget(self._tm_status_lbl)
        self._tm_alert_overlay = None

    def _tm_update_display_from_dials(self):
        self._tm_display.setText(f"{self._tm_h_val:02d}:{self._tm_m_val:02d}:{self._tm_s_val:02d}")
        self._tm_save_values()

    def _tm_save_values(self):
        parts = [f"{self._tm_h_val:02d}:{self._tm_m_val:02d}:{self._tm_s_val:02d}"]
        if self._tm_alert:
            parts.append("alert")
        self.data.cmd = f"{CLOCK_SUB_TIMER}|{'|'.join(parts)}"
        w = self.window()
        if w and hasattr(w, '_save_data'):
            w._save_data()

    def _tick(self):
        sub = self._clock_sub
        if sub == CLOCK_SUB_CLOCK:
            self._tick_clock()
        elif sub == CLOCK_SUB_WORLD:
            self._tick_world()
        elif sub == CLOCK_SUB_STOPWATCH:
            self._tick_stopwatch()
        elif sub == CLOCK_SUB_TIMER:
            self._tick_timer()
        elif sub == CLOCK_SUB_ALARM:
            self._tick_alarm()

    def _tick_clock(self):
        now = datetime.datetime.now()
        fmt = self._clock_param or "%H:%M:%S"
        self._time_lbl.setText(now.strftime(fmt))
        weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        self._date_lbl.setText(f"{now.year}年{now.month}月{now.day}日 {weekdays[now.weekday()]}")
        try:
            ly, lm, ld, leap, gan, zhi, sx = _solar_to_lunar(now.year, now.month, now.day)
            _LM = ["正", "二", "三", "四", "五", "六", "七", "八", "九", "十", "冬", "腊"]
            _LD = ["初一", "初二", "初三", "初四", "初五", "初六", "初七", "初八", "初九", "初十",
                   "十一", "十二", "十三", "十四", "十五", "十六", "十七", "十八", "十九", "二十",
                   "廿一", "廿二", "廿三", "廿四", "廿五", "廿六", "廿七", "廿八", "廿九", "三十"]
            lm_name = ("闰" if leap else "") + _LM[lm - 1]
            ld_name = _LD[ld - 1] if 1 <= ld <= 30 else str(ld)
            self._lunar_lbl.setText(f"{gan}{zhi}年({sx})  {lm_name}月{ld_name}")
        except Exception:
            self._lunar_lbl.setText("")

    def _tick_world(self):
        import time as _time
        utc_now = datetime.datetime.utcnow()
        local_offset = _time.timezone / -3600 if _time.daylight == 0 else _time.altzone / -3600
        tz_now = utc_now + datetime.timedelta(hours=self._tz_offset)
        weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        self._wtime_lbl.setText(tz_now.strftime("%H:%M:%S"))
        self._wdate_lbl.setText(f"{tz_now.year}/{tz_now.month}/{tz_now.day} {weekdays[tz_now.weekday()]}")
        diff = self._tz_offset - local_offset
        sign = "+" if diff >= 0 else ""
        self._wdiff_lbl.setText(f"与本地时差 {sign}{diff:.1f}h".replace(".0h", "h"))

    def _tick_stopwatch(self):
        if self._sw_running and self._sw_start_time:
            import time as _t
            elapsed = self._sw_elapsed_ms + int((_t.monotonic() - self._sw_start_time) * 1000)
        else:
            elapsed = self._sw_elapsed_ms
        mins = elapsed // 60000
        secs = (elapsed % 60000) // 1000
        ms = elapsed % 1000
        self._sw_display.setText(f"{mins:02d}:{secs:02d}.{ms:03d}")

    def _tick_timer(self):
        if self._tm_running and self._tm_remain_secs > 0:
            self._tm_remain_secs -= 1
            h = self._tm_remain_secs // 3600
            m = (self._tm_remain_secs % 3600) // 60
            s = self._tm_remain_secs % 60
            self._tm_display.setText(f"{h:02d}:{m:02d}:{s:02d}")
            if self._tm_remain_secs <= 0:
                self._tm_running = False
                self._tm_start_btn.set_icon_type(_CircleBtn.PLAY)
                self._tm_start_btn.set_colors(C['green'], C['crust'])
                self._tm_start_btn.setToolTip("开始")
                self._tm_display.hide()
                self._tm_set_row.show()
                self._tm_status_lbl.setText("⏰ 计时结束")
                self._tm_status_lbl.setStyleSheet(f"color:{C['red']}; font-size:13px; font-weight:bold;")
                if self._tm_alert_mode >= 1:
                    self._tm_show_alert_overlay()
                if self._tm_alert_mode == 2:
                    self._tm_play_sound()

    def _tm_show_alert_overlay(self):
        try:
            if self._tm_alert_overlay and self._tm_alert_overlay.isVisible():
                return
        except RuntimeError:
            self._tm_alert_overlay = None
        self._tm_alert_overlay = _TimerAlertOverlay()
        main_win = self.window()
        if main_win:
            screen = QApplication.screenAt(main_win.geometry().center())
            if screen:
                self._tm_alert_overlay.setGeometry(screen.geometry())
        self._tm_alert_overlay.showFullScreen()

    def _tm_play_sound(self):
        try:
            subprocess.Popen(["paplay", "/usr/share/sounds/freedesktop/stereo/alarm-clock-elapsed.oga"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            try:
                subprocess.Popen(["paplay", "/usr/share/sounds/freedesktop/stereo/complete.oga"],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass

    def _sw_toggle(self):
        import time as _t
        if self._sw_running:
            self._sw_elapsed_ms += int((_t.monotonic() - self._sw_start_time) * 1000)
            self._sw_start_time = None
            self._sw_running = False
            self._sw_start_btn.set_icon_type(_CircleBtn.PLAY)
            self._sw_start_btn.set_colors(C['green'], C['crust'])
            self._sw_start_btn.setToolTip("继续")
            self._sw_lap_btn.setEnabled(False)
            self._sw_lap_btn.set_colors(C['surface2'], C['overlay0'])
        else:
            self._sw_start_time = _t.monotonic()
            self._sw_running = True
            self._sw_start_btn.set_icon_type(_CircleBtn.PAUSE)
            self._sw_start_btn.set_colors(C['peach'], C['crust'])
            self._sw_start_btn.setToolTip("暂停")
            self._sw_lap_btn.setEnabled(True)
            self._sw_lap_btn.set_colors(C['blue'], C['crust'])
            self._sw_hint.hide()

    def _sw_lap(self):
        import time as _t
        if self._sw_running and self._sw_start_time:
            elapsed = self._sw_elapsed_ms + int((_t.monotonic() - self._sw_start_time) * 1000)
            prev = self._sw_laps[-1] if self._sw_laps else 0
            lap_ms = elapsed - prev
            self._sw_laps.append(elapsed)
            idx = len(self._sw_laps)
            if not self._sw_has_laps:
                self._sw_has_laps = True
                self._sw_lap_scroll.show()
            lap_str = f"{lap_ms // 60000:02d}:{(lap_ms % 60000) // 1000:02d}.{lap_ms % 1000:03d}"
            total_str = f"{elapsed // 60000:02d}:{(elapsed % 60000) // 1000:02d}.{elapsed % 1000:03d}"
            row_w = QWidget()
            row_w.setStyleSheet(f"background:{_bg('surface0')}; border-radius:6px;")
            rl = QHBoxLayout(row_w); rl.setContentsMargins(10, 4, 10, 4); rl.setSpacing(0)
            idx_lbl = QLabel(f"#{idx}")
            idx_lbl.setStyleSheet(f"color:{C['blue']}; font-size:11px; font-weight:bold; font-family:'JetBrains Mono','Consolas',monospace; background:transparent;")
            idx_lbl.setFixedWidth(30)
            rl.addWidget(idx_lbl)
            lap_lbl = QLabel(f"{lap_str}")
            lap_lbl.setStyleSheet(f"color:{C['text']}; font-size:11px; font-family:'JetBrains Mono','Consolas',monospace; background:transparent;")
            rl.addWidget(lap_lbl, 1)
            total_lbl = QLabel(f"{total_str}")
            total_lbl.setStyleSheet(f"color:{C['subtext0']}; font-size:11px; font-family:'JetBrains Mono','Consolas',monospace; background:transparent;")
            total_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            rl.addWidget(total_lbl)
            self._sw_lap_lay.insertWidget(0, row_w)

    def _sw_reset(self):
        self._sw_running = False
        self._sw_elapsed_ms = 0
        self._sw_start_time = None
        self._sw_laps.clear()
        self._sw_has_laps = False
        self._sw_display.setText("00:00.000")
        self._sw_start_btn.set_icon_type(_CircleBtn.PLAY)
        self._sw_start_btn.set_colors(C['green'], C['crust'])
        self._sw_start_btn.setToolTip("开始")
        self._sw_lap_btn.setEnabled(False)
        self._sw_lap_btn.set_colors(C['surface2'], C['overlay0'])
        self._sw_hint.show()
        self._sw_lap_scroll.hide()
        while self._sw_lap_lay.count():
            item = self._sw_lap_lay.takeAt(0)
            w = item.widget()
            if w: w.deleteLater()

    def _tm_toggle(self):
        _mono = "font-family:'JetBrains Mono','Consolas',monospace;"
        if self._tm_running:
            self._tm_running = False
            self._tm_start_btn.set_icon_type(_CircleBtn.PLAY)
            self._tm_start_btn.set_colors(C['green'], C['crust'])
            self._tm_start_btn.setToolTip("继续")
        else:
            if self._tm_remain_secs <= 0:
                total = self._tm_h_val * 3600 + self._tm_m_val * 60 + self._tm_s_val
                if total <= 0:
                    return
                self._tm_total_secs = total
                self._tm_remain_secs = total
            self._tm_running = True
            self._tm_start_btn.set_icon_type(_CircleBtn.PAUSE)
            self._tm_start_btn.set_colors(C['peach'], C['crust'])
            self._tm_start_btn.setToolTip("暂停")
            self._tm_set_row.hide()
            self._tm_display.show()
            self._tm_display.setStyleSheet(f"color:{C['text']}; font-size:38px; font-weight:bold; {_mono}")
            self._tm_status_lbl.setText("")

    def _tm_reset(self):
        _mono = "font-family:'JetBrains Mono','Consolas',monospace;"
        self._tm_running = False
        self._tm_remain_secs = 0
        self._tm_total_secs = 0
        if hasattr(self, '_tm_h_val_edit'):
            self._tm_h_val_edit.setText(f"{self._tm_h_val:02d}")
            self._tm_m_val_edit.setText(f"{self._tm_m_val:02d}")
            self._tm_s_val_edit.setText(f"{self._tm_s_val:02d}")
        self._tm_display.setText("00:00:00")
        self._tm_display.setStyleSheet(f"color:{C['text']}; font-size:38px; font-weight:bold; {_mono}")
        self._tm_start_btn.set_icon_type(_CircleBtn.PLAY)
        self._tm_start_btn.set_colors(C['green'], C['crust'])
        self._tm_start_btn.setToolTip("开始")
        self._tm_display.hide()
        self._tm_set_row.show()
        self._tm_status_lbl.setText("")

    # --- Alarm (闹钟) ---

    def _alarm_load(self):
        try:
            self._alarms = json.loads(self._clock_param) if self._clock_param else []
        except Exception:
            self._alarms = []
        for a in self._alarms:
            a.setdefault("time", "08:00")
            a.setdefault("date", "")
            a.setdefault("label", "")
            a.setdefault("enabled", True)
            a.setdefault("repeat", "once")

    def _alarm_save(self):
        self._clock_param = json.dumps(self._alarms, ensure_ascii=False)
        self.data.cmd = f"{CLOCK_SUB_ALARM}|{self._clock_param}"
        w = self.window()
        if w and hasattr(w, '_save_data'):
            w._save_data()

    def _build_alarm(self):
        self._alarm_load()
        self._alarm_fired_set = set()
        self._alarm_alert_overlay = None

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(6)

        header = QHBoxLayout()
        title = QLabel("⏰ 闹钟")
        title.setStyleSheet(f"color:{C['text']}; font-size:15px; font-weight:bold; background:transparent;")
        header.addWidget(title)
        header.addStretch()

        add_btn = QPushButton("＋")
        add_btn.setFixedSize(28, 28)
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.setStyleSheet(f"background:{C['blue']}; color:{C['crust']}; border:none; border-radius:14px; font-size:16px; font-weight:bold;")
        add_btn.setToolTip("添加闹钟")
        add_btn.clicked.connect(self._alarm_add_dialog)
        header.addWidget(add_btn)
        root.addLayout(header)

        self._alarm_scroll = QScrollArea()
        self._alarm_scroll.setWidgetResizable(True)
        self._alarm_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._alarm_scroll.setStyleSheet(f"""QScrollArea {{ border: none; background: transparent; }}
            QScrollBar:vertical {{ width:4px; background:transparent; }}
            QScrollBar::handle:vertical {{ background:{C['surface2']}; border-radius:2px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; }}""")
        self._alarm_container = QWidget()
        self._alarm_container.setStyleSheet("background:transparent;")
        self._alarm_list_lay = QVBoxLayout(self._alarm_container)
        self._alarm_list_lay.setSpacing(4)
        self._alarm_list_lay.setContentsMargins(0, 0, 0, 0)
        self._alarm_list_lay.addStretch()
        self._alarm_scroll.setWidget(self._alarm_container)
        root.addWidget(self._alarm_scroll, 1)

        self._alarm_empty_hint = QLabel("暂无闹钟，点击 ＋ 添加")
        self._alarm_empty_hint.setAlignment(Qt.AlignCenter)
        self._alarm_empty_hint.setStyleSheet(f"color:{C['overlay0']}; font-size:12px; background:transparent;")
        root.addWidget(self._alarm_empty_hint)

        self._alarm_rebuild_list()

    def _alarm_rebuild_list(self):
        while self._alarm_list_lay.count() > 1:
            item = self._alarm_list_lay.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        _REPEAT_LABELS = {"once": "单次", "daily": "每天", "weekdays": "工作日", "weekends": "周末"}

        for i, a in enumerate(self._alarms):
            row = QPushButton()
            row.setFixedHeight(56)
            row.setCursor(Qt.PointingHandCursor)
            en = a.get("enabled", True)
            row.setStyleSheet(f"""
                QPushButton {{ background:{_bg('surface0')}; border-radius:8px; border:none; text-align:left; padding:0; }}
                QPushButton:hover {{ background:{_bg('surface1')}; }}""")
            idx = i
            row.clicked.connect(lambda _, ii=idx: self._alarm_edit(ii))
            rl = QHBoxLayout(row)
            rl.setContentsMargins(10, 4, 6, 4)
            rl.setSpacing(8)

            toggle = QPushButton("●" if en else "○")
            toggle.setFixedSize(28, 28)
            toggle.setCursor(Qt.PointingHandCursor)
            toggle.setStyleSheet(f"background:transparent; color:{C['green'] if en else C['overlay0']}; border:none; font-size:20px;")
            toggle.setToolTip("禁用" if en else "启用")
            toggle.clicked.connect(lambda _, ii=idx: self._alarm_toggle(ii))
            rl.addWidget(toggle)

            time_lbl = QLabel(a.get("time", "08:00"))
            time_lbl.setStyleSheet(f"color:{C['text'] if en else C['overlay0']}; font-size:22px; font-weight:bold; "
                                   f"font-family:'JetBrains Mono','Consolas',monospace; background:transparent;")
            rl.addWidget(time_lbl)

            info_col = QVBoxLayout()
            info_col.setSpacing(0)
            repeat_text = _REPEAT_LABELS.get(a.get("repeat", "once"), "单次")
            date_str = a.get("date", "")
            if a.get("repeat") == "once" and date_str:
                info_text = date_str
            else:
                info_text = repeat_text
            label_str = a.get("label", "")
            if label_str:
                info_text = f"{info_text}  {label_str}"
            info_lbl = QLabel(info_text)
            info_lbl.setStyleSheet(f"color:{C['subtext0'] if en else C['overlay0']}; font-size:11px; background:transparent;")
            info_col.addWidget(info_lbl)
            rl.addLayout(info_col, 1)

            del_btn = QPushButton("✕")
            del_btn.setFixedSize(24, 24)
            del_btn.setCursor(Qt.PointingHandCursor)
            del_btn.setStyleSheet(f"""QPushButton {{ background:transparent; color:{C['overlay0']}; border:none; font-size:12px; }}
                QPushButton:hover {{ color:{C['red']}; }}""")
            del_btn.setToolTip("删除")
            del_btn.clicked.connect(lambda _, ii=idx: self._alarm_remove(ii))
            rl.addWidget(del_btn)

            self._alarm_list_lay.insertWidget(self._alarm_list_lay.count() - 1, row)

        self._alarm_empty_hint.setVisible(len(self._alarms) == 0)

    def _alarm_toggle(self, idx):
        if 0 <= idx < len(self._alarms):
            self._alarms[idx]["enabled"] = not self._alarms[idx].get("enabled", True)
            self._alarm_save()
            self._alarm_rebuild_list()

    def _alarm_remove(self, idx):
        if 0 <= idx < len(self._alarms):
            self._alarms.pop(idx)
            self._alarm_save()
            self._alarm_rebuild_list()

    def _alarm_edit(self, idx):
        if 0 <= idx < len(self._alarms):
            result = self._alarm_dialog(self._alarms[idx])
            if result:
                self._alarms[idx] = result
                self._alarm_save()
                self._alarm_rebuild_list()

    def _alarm_add_dialog(self):
        result = self._alarm_dialog()
        if result:
            self._alarms.append(result)
            self._alarm_save()
            self._alarm_rebuild_list()

    def _alarm_dialog(self, existing=None):
        from PyQt5.QtWidgets import QTimeEdit, QDateEdit
        from PyQt5.QtCore import QTime, QDate

        is_edit = existing is not None
        dlg = QDialog(self)
        dlg.setWindowTitle("编辑闹钟" if is_edit else "添加闹钟")
        dlg.setFixedWidth(360)
        dlg.setStyleSheet(f"""
            QDialog {{ background: {C['base']}; color: {C['text']}; border-radius: 12px; }}
            QLabel {{ color: {C['text']}; background: transparent; }}
            QLabel#dialogTitle {{ color: {C['text']}; font-size: 16px; font-weight: bold; }}
            QLineEdit {{ background: {_bg('surface0')}; color: {C['text']}; border: 1px solid {C['surface2']};
                border-radius: 8px; padding: 8px 12px; font-size: 13px; }}
            QLineEdit:focus {{ border: 1px solid {C['blue']}; }}
            QComboBox {{ background: {_bg('surface0')}; color: {C['text']}; border: 1px solid {C['surface2']};
                border-radius: 8px; padding: 8px 12px; font-size: 13px; }}
            QComboBox:focus {{ border: 1px solid {C['blue']}; }}
            QComboBox::drop-down {{ border: none; padding-right: 8px; }}
            QComboBox QAbstractItemView {{ background: {_bg('surface0')}; color: {C['text']};
                selection-background-color: {C['surface2']}; border: 1px solid {C['surface2']}; border-radius: 6px; }}
            QDateEdit, QTimeEdit {{ background: {_bg('surface0')}; color: {C['text']}; border: 1px solid {C['surface2']};
                border-radius: 8px; padding: 8px 12px; font-size: 15px; font-weight: bold;
                font-family: 'JetBrains Mono','Consolas',monospace; }}
            QDateEdit:focus, QTimeEdit:focus {{ border: 1px solid {C['blue']}; }}
            QDateEdit::up-button, QDateEdit::down-button, QTimeEdit::up-button, QTimeEdit::down-button {{
                width: 20px; border: none; background: transparent; }}
            QCalendarWidget {{ background: {_bg('surface0')}; color: {C['text']}; }}
            QPushButton#okBtn {{ background: {C['blue']}; color: {C['crust']}; border: none;
                border-radius: 8px; padding: 10px 24px; font-size: 13px; font-weight: bold; }}
            QPushButton#okBtn:hover {{ background: {C['sky']}; }}
            QPushButton#cancelBtn {{ background: {_bg('surface1')}; color: {C['text']}; border: none;
                border-radius: 8px; padding: 10px 24px; font-size: 13px; }}
            QPushButton#cancelBtn:hover {{ background: {C['surface2']}; }}
        """)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(14)

        title = QLabel("⏰ 编辑闹钟" if is_edit else "⏰ 新闹钟")
        title.setObjectName("dialogTitle")
        lay.addWidget(title)

        time_edit = QTimeEdit()
        time_edit.setDisplayFormat("HH : mm")
        time_edit.setAlignment(Qt.AlignCenter)
        time_edit.setFixedHeight(48)
        if is_edit:
            parts = existing.get("time", "08:00").split(":")
            time_edit.setTime(QTime(int(parts[0]), int(parts[1])))
        else:
            time_edit.setTime(QTime.currentTime().addSecs(3600))
        lay.addWidget(time_edit)

        grid = QHBoxLayout()
        grid.setSpacing(8)
        repeat_col = QVBoxLayout()
        repeat_lbl = QLabel("重复")
        repeat_lbl.setStyleSheet(f"color:{C['subtext0']}; font-size:11px;")
        repeat_col.addWidget(repeat_lbl)
        repeat_combo = QComboBox()
        for k, v in [("once", "单次"), ("daily", "每天"), ("weekdays", "工作日"), ("weekends", "周末")]:
            repeat_combo.addItem(v, k)
        if is_edit:
            repeat_keys = ["once", "daily", "weekdays", "weekends"]
            r = existing.get("repeat", "once")
            if r in repeat_keys:
                repeat_combo.setCurrentIndex(repeat_keys.index(r))
        repeat_col.addWidget(repeat_combo)
        grid.addLayout(repeat_col, 1)

        date_col = QVBoxLayout()
        date_lbl = QLabel("日期")
        date_lbl.setStyleSheet(f"color:{C['subtext0']}; font-size:11px;")
        date_col.addWidget(date_lbl)
        date_edit = QDateEdit()
        date_edit.setDisplayFormat("yyyy-MM-dd")
        date_edit.setCalendarPopup(True)
        if is_edit and existing.get("date"):
            parts = existing["date"].split("-")
            date_edit.setDate(QDate(int(parts[0]), int(parts[1]), int(parts[2])))
        else:
            date_edit.setDate(QDate.currentDate())
        date_col.addWidget(date_edit)
        grid.addLayout(date_col, 1)
        lay.addLayout(grid)

        def _on_repeat_changed(_=0):
            is_once = repeat_combo.currentData() == "once"
            for w in [date_lbl, date_edit]:
                w.setVisible(is_once)
        repeat_combo.currentIndexChanged.connect(_on_repeat_changed)
        _on_repeat_changed()

        label_col = QVBoxLayout()
        label_col.setSpacing(2)
        label_hint = QLabel("标签")
        label_hint.setStyleSheet(f"color:{C['subtext0']}; font-size:11px;")
        label_col.addWidget(label_hint)
        label_edit = QLineEdit()
        label_edit.setPlaceholderText('可选，如"起床""开会"')
        if is_edit:
            label_edit.setText(existing.get("label", ""))
        label_col.addWidget(label_edit)
        lay.addLayout(label_col)

        lay.addSpacing(4)
        btns = QHBoxLayout()
        btns.addStretch()
        cancel = QPushButton("取消")
        cancel.setObjectName("cancelBtn")
        cancel.setCursor(Qt.PointingHandCursor)
        cancel.clicked.connect(dlg.reject)
        btns.addWidget(cancel)
        ok = QPushButton("保存" if is_edit else "添加")
        ok.setObjectName("okBtn")
        ok.setCursor(Qt.PointingHandCursor)
        ok.clicked.connect(dlg.accept)
        btns.addWidget(ok)
        lay.addLayout(btns)

        if dlg.exec_() == QDialog.Accepted:
            alarm = {
                "time": time_edit.time().toString("HH:mm"),
                "repeat": repeat_combo.currentData(),
                "label": label_edit.text().strip(),
                "enabled": existing.get("enabled", True) if is_edit else True,
            }
            if alarm["repeat"] == "once":
                alarm["date"] = date_edit.date().toString("yyyy-MM-dd")
            return alarm
        return None

    def _tick_alarm(self):
        now = datetime.datetime.now()
        now_hm = now.strftime("%H:%M")
        now_date = now.strftime("%Y-%m-%d")
        weekday = now.weekday()
        changed = False

        for i, a in enumerate(self._alarms):
            if not a.get("enabled", True):
                continue
            if a.get("time") != now_hm:
                self._alarm_fired_set.discard(i)
                continue
            if i in self._alarm_fired_set:
                continue

            should_fire = False
            repeat = a.get("repeat", "once")
            if repeat == "once":
                if a.get("date", "") == now_date:
                    should_fire = True
                elif not a.get("date"):
                    should_fire = True
            elif repeat == "daily":
                should_fire = True
            elif repeat == "weekdays" and weekday < 5:
                should_fire = True
            elif repeat == "weekends" and weekday >= 5:
                should_fire = True

            if should_fire:
                self._alarm_fired_set.add(i)
                if repeat == "once":
                    a["enabled"] = False
                    changed = True
                label = a.get("label", "") or "闹钟"
                self._alarm_show_alert(label, a.get("time", ""))

        if changed:
            self._alarm_save()
            self._alarm_rebuild_list()

    def _alarm_show_alert(self, label, time_str):
        try:
            if self._alarm_alert_overlay and self._alarm_alert_overlay.isVisible():
                return
        except RuntimeError:
            self._alarm_alert_overlay = None
        overlay = _TimerAlertOverlay()
        overlay._title.setText(f"⏰ {label}")
        overlay._elapsed_lbl.setText(time_str)
        overlay._elapsed_lbl.setStyleSheet(
            "color: rgba(255,255,255,0.9); font-size: 72px; font-weight: bold; "
            "font-family: 'JetBrains Mono','Consolas',monospace; background: transparent;")
        overlay._timer.stop()
        overlay.start_sound()
        main_win = self.window()
        if main_win:
            screen = QApplication.screenAt(main_win.geometry().center())
            if screen:
                overlay.setGeometry(screen.geometry())
        overlay.showFullScreen()
        self._alarm_alert_overlay = overlay


class MonitorWidget(CompBase):
    def __init__(self, data, parent=None):
        super().__init__(data, parent)
        self._parse_monitor_cmd()
        self._history_len = 60
        self._cpu_history = [0.0] * self._history_len
        self._net_sent_history = [0.0] * self._history_len
        self._net_recv_history = [0.0] * self._history_len
        self._mem_history = [0.0] * self._history_len
        self._prev_net = None
        self._build()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(1500)
        self._tick()

    def refresh_theme(self):
        cpu_h = list(self._cpu_history)
        mem_h = list(self._mem_history)
        net_s = list(self._net_sent_history)
        net_r = list(self._net_recv_history)
        prev = self._prev_net
        super().refresh_theme()
        self._cpu_history = cpu_h
        self._mem_history = mem_h
        self._net_sent_history = net_s
        self._net_recv_history = net_r
        self._prev_net = prev
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(1500)

    def _parse_monitor_cmd(self):
        raw = self.data.cmd.strip()
        self._monitor_sub = raw if raw in MONITOR_SUB_LABELS else MONITOR_SUB_ALL

    def _build(self):
        self._canvas = QWidget(self)
        self._canvas.setAttribute(Qt.WA_TransparentForMouseEvents)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._canvas)

    _shared_cpu_val = 0.0
    _shared_cpu_ts = 0.0

    @classmethod
    def _get_shared_cpu(cls):
        import time, psutil
        now = time.monotonic()
        if now - cls._shared_cpu_ts > 0.5:
            cls._shared_cpu_val = psutil.cpu_percent(interval=0)
            cls._shared_cpu_ts = now
        return cls._shared_cpu_val

    def _tick(self):
        try:
            import psutil
            self._cpu_history.append(self._get_shared_cpu())
            self._cpu_history = self._cpu_history[-self._history_len:]
            mem = psutil.virtual_memory()
            self._mem_percent = mem.percent
            self._mem_used = mem.used
            self._mem_total = mem.total
            self._mem_history.append(mem.percent)
            self._mem_history = self._mem_history[-self._history_len:]
            parts = psutil.disk_partitions()
            self._disks = []
            seen = set()
            for p in parts:
                if p.mountpoint in seen:
                    continue
                seen.add(p.mountpoint)
                try:
                    u = psutil.disk_usage(p.mountpoint)
                    self._disks.append((p.mountpoint, u.used, u.total, u.percent))
                except Exception:
                    pass
            net = psutil.net_io_counters()
            if self._prev_net:
                dt = 1.5
                sent_speed = (net.bytes_sent - self._prev_net.bytes_sent) / dt
                recv_speed = (net.bytes_recv - self._prev_net.bytes_recv) / dt
            else:
                sent_speed = recv_speed = 0.0
            self._prev_net = net
            self._net_sent_history.append(sent_speed)
            self._net_recv_history.append(recv_speed)
            self._net_sent_history = self._net_sent_history[-self._history_len:]
            self._net_recv_history = self._net_recv_history[-self._history_len:]
            self._net_sent_speed = sent_speed
            self._net_recv_speed = recv_speed
        except Exception:
            pass
        self._canvas.update()

    def _fmt_bytes(self, b):
        for u in ['B', 'KB', 'MB', 'GB', 'TB']:
            if b < 1024:
                return f"{b:.1f}{u}"
            b /= 1024
        return f"{b:.1f}PB"

    def _fmt_speed(self, bps):
        for u in ['B/s', 'KB/s', 'MB/s', 'GB/s']:
            if bps < 1024:
                return f"{bps:.1f}{u}"
            bps /= 1024
        return f"{bps:.1f}TB/s"

    def paintEvent(self, e):
        super().paintEvent(e)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        sub = self._monitor_sub
        rect = self._canvas.geometry()
        pad = 12
        area = QRect(rect.x() + pad, rect.y() + pad, rect.width() - pad * 2, rect.height() - pad * 2)
        if sub == MONITOR_SUB_CPU:
            self._paint_cpu(p, area)
        elif sub == MONITOR_SUB_MEM:
            self._paint_mem(p, area)
        elif sub == MONITOR_SUB_DISK:
            self._paint_disk(p, area)
        elif sub == MONITOR_SUB_NET:
            self._paint_net(p, area)
        else:
            self._paint_all(p, area)
        p.end()

    def _draw_line_chart(self, p, rect, data, color, max_val=100.0, label="", cur_text=""):
        bg = QColor(C['surface0'])
        bg.setAlpha(60)
        p.setBrush(bg)
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(rect, 8, 8)

        if label:
            p.setPen(QColor(C['subtext0']))
            p.setFont(QFont("JetBrains Mono", 9))
            p.drawText(rect.adjusted(8, 4, 0, 0), Qt.AlignLeft | Qt.AlignTop, label)
        if cur_text:
            p.setPen(QColor(C['text']))
            p.setFont(QFont("JetBrains Mono", 10, QFont.Bold))
            p.drawText(rect.adjusted(0, 4, -8, 0), Qt.AlignRight | Qt.AlignTop, cur_text)

        chart_rect = QRect(rect.x() + 8, rect.y() + 24, rect.width() - 16, rect.height() - 32)
        if chart_rect.height() < 10 or chart_rect.width() < 10:
            return

        line_color = QColor(color)
        fill_color = QColor(color)
        fill_color.setAlpha(40)

        n = len(data)
        if n < 2 or max_val <= 0:
            return
        dx = chart_rect.width() / (n - 1) if n > 1 else 0

        points = []
        for i, v in enumerate(data):
            x = chart_rect.x() + i * dx
            ratio = min(v / max_val, 1.0)
            y = chart_rect.bottom() - ratio * chart_rect.height()
            points.append(QPoint(int(x), int(y)))

        from PyQt5.QtGui import QPolygonF, QPainterPath, QLinearGradient
        from PyQt5.QtCore import QPointF
        path = QPainterPath()
        path.moveTo(QPointF(points[0].x(), chart_rect.bottom()))
        for pt in points:
            path.lineTo(QPointF(pt.x(), pt.y()))
        path.lineTo(QPointF(points[-1].x(), chart_rect.bottom()))
        path.closeSubpath()

        grad = QLinearGradient(0, chart_rect.top(), 0, chart_rect.bottom())
        grad.setColorAt(0, fill_color)
        fc2 = QColor(color)
        fc2.setAlpha(5)
        grad.setColorAt(1, fc2)
        p.setBrush(grad)
        p.setPen(Qt.NoPen)
        p.drawPath(path)

        pen = QPen(line_color, 2)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        for i in range(len(points) - 1):
            p.drawLine(points[i], points[i + 1])

    def _paint_cpu(self, p, area):
        cur = self._cpu_history[-1] if self._cpu_history else 0
        self._draw_line_chart(p, area, self._cpu_history, C['green'],
                              max_val=100.0, label="CPU", cur_text=f"{cur:.0f}%")

    def _draw_ring(self, p, rect, percent, color, label="", detail=""):
        cx = rect.center().x()
        cy = rect.y() + min(rect.width(), rect.height() - 30) // 2 + 4
        radius = min(rect.width(), rect.height() - 30) // 2 - 8
        if radius < 15:
            return

        ring_w = max(8, radius // 4)
        ring_rect = QRect(cx - radius, cy - radius, radius * 2, radius * 2)

        track_color = QColor(C['surface1'])
        p.setPen(QPen(track_color, ring_w, Qt.SolidLine, Qt.RoundCap))
        p.setBrush(Qt.NoBrush)
        p.drawArc(ring_rect, 0, 360 * 16)

        arc_color = QColor(color)
        p.setPen(QPen(arc_color, ring_w, Qt.SolidLine, Qt.RoundCap))
        span = int(-percent / 100.0 * 360 * 16)
        p.drawArc(ring_rect, 90 * 16, span)

        p.setPen(QColor(C['text']))
        p.setFont(QFont("JetBrains Mono", max(10, radius // 3), QFont.Bold))
        p.drawText(ring_rect, Qt.AlignCenter, f"{percent:.0f}%")

        if detail:
            p.setPen(QColor(C['subtext0']))
            p.setFont(QFont("JetBrains Mono", 8))
            text_y = cy + radius + ring_w // 2 + 4
            p.drawText(QRect(rect.x(), text_y, rect.width(), 20), Qt.AlignCenter, detail)
        if label:
            p.setPen(QColor(C['subtext0']))
            p.setFont(QFont("JetBrains Mono", 9))
            p.drawText(QRect(rect.x(), rect.y(), rect.width(), 18), Qt.AlignCenter, label)

    def _paint_mem(self, p, area):
        pct = getattr(self, '_mem_percent', 0)
        used = getattr(self, '_mem_used', 0)
        total = getattr(self, '_mem_total', 1)
        detail = f"{self._fmt_bytes(used)} / {self._fmt_bytes(total)}"
        self._draw_ring(p, area, pct, C['blue'], label="内存", detail=detail)

    def _paint_disk(self, p, area):
        disks = getattr(self, '_disks', [])
        if not disks:
            p.setPen(QColor(C['subtext0']))
            p.setFont(QFont("JetBrains Mono", 10))
            p.drawText(area, Qt.AlignCenter, "无磁盘信息")
            return

        p.setPen(QColor(C['subtext0']))
        p.setFont(QFont("JetBrains Mono", 9))
        p.drawText(QRect(area.x(), area.y(), area.width(), 18), Qt.AlignLeft, "磁盘")

        bar_h = max(14, min(22, (area.height() - 24) // max(len(disks), 1) - 8))
        colors = [C['teal'], C['peach'], C['blue'], C['green'], C['mauve'], C['yellow']]
        y = area.y() + 24

        for i, (mount, used, total, pct) in enumerate(disks[:6]):
            color = colors[i % len(colors)]
            name = mount if len(mount) <= 12 else "…" + mount[-11:]
            detail = f"{self._fmt_bytes(used)}/{self._fmt_bytes(total)}"

            p.setPen(QColor(C['text']))
            p.setFont(QFont("JetBrains Mono", 8))
            p.drawText(QRect(area.x(), y, area.width(), bar_h), Qt.AlignLeft | Qt.AlignVCenter, name)

            bar_x = area.x() + min(100, area.width() // 3)
            bar_w = area.width() - min(100, area.width() // 3) - 80
            bar_rect = QRect(bar_x, y + 2, bar_w, bar_h - 4)

            track = QColor(C['surface1'])
            p.setBrush(track)
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(bar_rect, 4, 4)

            fill_w = int(bar_rect.width() * pct / 100.0)
            if fill_w > 0:
                fill_rect = QRect(bar_rect.x(), bar_rect.y(), fill_w, bar_rect.height())
                p.setBrush(QColor(color))
                p.drawRoundedRect(fill_rect, 4, 4)

            p.setPen(QColor(C['subtext0']))
            p.setFont(QFont("JetBrains Mono", 8))
            text_rect = QRect(bar_rect.right() + 6, y, 74, bar_h)
            p.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter, f"{pct:.0f}% {detail}")

            y += bar_h + 6
            if y + bar_h > area.bottom():
                break

    def _paint_net(self, p, area):
        max_s = max(max(self._net_sent_history, default=1), max(self._net_recv_history, default=1), 1024)
        h_half = area.height() // 2 - 4
        up_rect = QRect(area.x(), area.y(), area.width(), h_half)
        dn_rect = QRect(area.x(), area.y() + h_half + 8, area.width(), h_half)
        up_spd = self._fmt_speed(getattr(self, '_net_sent_speed', 0))
        dn_spd = self._fmt_speed(getattr(self, '_net_recv_speed', 0))
        self._draw_line_chart(p, up_rect, self._net_sent_history, C['peach'],
                              max_val=max_s, label="↑ 上传", cur_text=up_spd)
        self._draw_line_chart(p, dn_rect, self._net_recv_history, C['teal'],
                              max_val=max_s, label="↓ 下载", cur_text=dn_spd)

    def _paint_all(self, p, area):
        w_half = area.width() // 2 - 4
        h_half = area.height() // 2 - 4

        cpu_rect = QRect(area.x(), area.y(), w_half, h_half)
        cur_cpu = self._cpu_history[-1] if self._cpu_history else 0
        self._draw_line_chart(p, cpu_rect, self._cpu_history, C['green'],
                              max_val=100.0, label="CPU", cur_text=f"{cur_cpu:.0f}%")

        mem_rect = QRect(area.x() + w_half + 8, area.y(), w_half, h_half)
        pct = getattr(self, '_mem_percent', 0)
        used = getattr(self, '_mem_used', 0)
        total = getattr(self, '_mem_total', 1)
        self._draw_ring(p, mem_rect, pct, C['blue'], label="内存",
                        detail=f"{self._fmt_bytes(used)}/{self._fmt_bytes(total)}")

        disk_rect = QRect(area.x(), area.y() + h_half + 8, w_half, h_half)
        self._paint_disk_mini(p, disk_rect)

        net_rect = QRect(area.x() + w_half + 8, area.y() + h_half + 8, w_half, h_half)
        max_s = max(max(self._net_sent_history, default=1), max(self._net_recv_history, default=1), 1024)
        net_h = net_rect.height() // 2 - 2
        up_r = QRect(net_rect.x(), net_rect.y(), net_rect.width(), net_h)
        dn_r = QRect(net_rect.x(), net_rect.y() + net_h + 4, net_rect.width(), net_h)
        up_spd = self._fmt_speed(getattr(self, '_net_sent_speed', 0))
        dn_spd = self._fmt_speed(getattr(self, '_net_recv_speed', 0))
        self._draw_line_chart(p, up_r, self._net_sent_history, C['peach'],
                              max_val=max_s, label="↑", cur_text=up_spd)
        self._draw_line_chart(p, dn_r, self._net_recv_history, C['teal'],
                              max_val=max_s, label="↓", cur_text=dn_spd)

    def _paint_disk_mini(self, p, area):
        disks = getattr(self, '_disks', [])
        if not disks:
            p.setPen(QColor(C['subtext0']))
            p.setFont(QFont("JetBrains Mono", 8))
            p.drawText(area, Qt.AlignCenter, "磁盘: N/A")
            return
        p.setPen(QColor(C['subtext0']))
        p.setFont(QFont("JetBrains Mono", 8))
        p.drawText(QRect(area.x(), area.y(), area.width(), 14), Qt.AlignLeft, "磁盘")
        bar_h = max(10, min(16, (area.height() - 18) // max(len(disks), 1) - 4))
        colors = [C['teal'], C['peach'], C['blue'], C['green']]
        y = area.y() + 18
        for i, (mount, used, total, pct) in enumerate(disks[:4]):
            color = colors[i % len(colors)]
            name = mount if len(mount) <= 8 else "…" + mount[-7:]
            p.setPen(QColor(C['text']))
            p.setFont(QFont("JetBrains Mono", 7))
            p.drawText(QRect(area.x(), y, 60, bar_h), Qt.AlignLeft | Qt.AlignVCenter, name)
            bx = area.x() + 64
            bw = area.width() - 64 - 36
            br = QRect(bx, y + 1, max(bw, 10), bar_h - 2)
            p.setBrush(QColor(C['surface1']))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(br, 3, 3)
            fw = int(br.width() * pct / 100.0)
            if fw > 0:
                p.setBrush(QColor(color))
                p.drawRoundedRect(QRect(br.x(), br.y(), fw, br.height()), 3, 3)
            p.setPen(QColor(C['subtext0']))
            p.setFont(QFont("JetBrains Mono", 7))
            p.drawText(QRect(br.right() + 4, y, 32, bar_h), Qt.AlignLeft | Qt.AlignVCenter, f"{pct:.0f}%")
            y += bar_h + 3
            if y + bar_h > area.bottom():
                break


class _DesktopEntry:
    __slots__ = ('name', 'generic_name', 'exec_cmd', 'icon', 'categories', 'keywords', 'no_display', 'terminal')

    def __init__(self, name='', generic_name='', exec_cmd='', icon='', categories='',
                 keywords='', no_display=False, terminal=False):
        self.name = name
        self.generic_name = generic_name
        self.exec_cmd = exec_cmd
        self.icon = icon
        self.categories = categories
        self.keywords = keywords
        self.no_display = no_display
        self.terminal = terminal

    def matches(self, query):
        q = query.lower()
        return (q in self.name.lower() or q in self.generic_name.lower()
                or q in self.categories.lower() or q in self.keywords.lower()
                or q in self.exec_cmd.lower())


def _scan_desktop_entries():
    dirs = []
    for d in ['/usr/share/applications', '/usr/local/share/applications',
              os.path.expanduser('~/.local/share/applications'), '/var/lib/flatpak/exports/share/applications',
              os.path.expanduser('~/.local/share/flatpak/exports/share/applications')]:
        if os.path.isdir(d):
            dirs.append(d)
    entries = []
    seen_names = set()
    cfg = configparser.ConfigParser(interpolation=None)
    for d in dirs:
        try:
            files = [f for f in os.listdir(d) if f.endswith('.desktop')]
        except OSError:
            continue
        for fname in files:
            fp = os.path.join(d, fname)
            try:
                cfg.clear()
                cfg.read(fp, encoding='utf-8')
                if not cfg.has_section('Desktop Entry'):
                    continue
                sec = cfg['Desktop Entry']
                etype = sec.get('Type', 'Application')
                if etype != 'Application':
                    continue
                nd = sec.get('NoDisplay', 'false').lower() == 'true'
                hidden = sec.get('Hidden', 'false').lower() == 'true'
                if nd or hidden:
                    continue
                name = sec.get('Name', fname)
                if name in seen_names:
                    continue
                seen_names.add(name)
                entries.append(_DesktopEntry(
                    name=name,
                    generic_name=sec.get('GenericName', ''),
                    exec_cmd=sec.get('Exec', ''),
                    icon=sec.get('Icon', ''),
                    categories=sec.get('Categories', ''),
                    keywords=sec.get('Keywords', ''),
                    no_display=nd,
                    terminal=sec.get('Terminal', 'false').lower() == 'true',
                ))
            except Exception:
                continue
    entries.sort(key=lambda e: e.name.lower())
    return entries


def _resolve_icon(icon_name, size=48):
    if not icon_name:
        return QIcon()
    if os.path.isabs(icon_name) and os.path.isfile(icon_name):
        return QIcon(icon_name)
    theme_icon = QIcon.fromTheme(icon_name)
    if not theme_icon.isNull():
        return theme_icon
    for ext in ('png', 'svg', 'xpm'):
        for base in [f'/usr/share/icons/hicolor/{size}x{size}/apps',
                     '/usr/share/pixmaps',
                     f'/usr/share/icons/hicolor/scalable/apps']:
            path = os.path.join(base, f'{icon_name}.{ext}')
            if os.path.isfile(path):
                return QIcon(path)
    return QIcon()


class _AppItemWidget(QFrame):
    clicked = pyqtSignal()

    def __init__(self, entry, parent=None):
        super().__init__(parent)
        self.entry = entry
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(40)
        self.setStyleSheet(f"""
            QFrame {{ background: transparent; border-radius: 6px; }}
            QFrame:hover {{ background: {C['surface0']}; }}
        """)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 4, 8, 4)
        lay.setSpacing(10)
        icon_lbl = QLabel()
        ic = _resolve_icon(entry.icon)
        if not ic.isNull():
            icon_lbl.setPixmap(ic.pixmap(24, 24))
        else:
            icon_lbl.setText("◆")
            icon_lbl.setStyleSheet(f"color: {C['blue']}; font-size: 16px;")
        icon_lbl.setFixedSize(28, 28)
        icon_lbl.setAlignment(Qt.AlignCenter)
        lay.addWidget(icon_lbl)
        name_lbl = QLabel(entry.name)
        name_lbl.setStyleSheet(f"color: {C['text']}; font-size: 13px; background: transparent;")
        lay.addWidget(name_lbl, 1)
        if entry.generic_name and entry.generic_name != entry.name:
            desc_lbl = QLabel(entry.generic_name)
            desc_lbl.setStyleSheet(f"color: {C['subtext0']}; font-size: 10px; background: transparent;")
            lay.addWidget(desc_lbl)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(e)


class LauncherWidget(CompBase):
    def __init__(self, data, parent=None):
        super().__init__(data, parent)
        self._entries = []
        self._filtered = []
        self._build_ui()
        self._load_entries()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(6)

        title_row = QHBoxLayout()
        title_lbl = QLabel("🔍  应用启动器")
        title_lbl.setStyleSheet(f"color: {C['text']}; font-size: 14px; font-weight: bold; background: transparent;")
        title_row.addWidget(title_lbl)
        title_row.addStretch()
        refresh_btn = QPushButton("↻")
        refresh_btn.setFixedSize(24, 24)
        refresh_btn.setCursor(Qt.PointingHandCursor)
        refresh_btn.setStyleSheet(f"""
            QPushButton {{ background: {_bg('surface0')}; color: {C['text']}; border: none; border-radius: 12px; font-size: 14px; }}
            QPushButton:hover {{ background: {_bg('surface1')}; }}
        """)
        refresh_btn.clicked.connect(self._load_entries)
        title_row.addWidget(refresh_btn)
        lay.addLayout(title_row)

        self._search = QLineEdit()
        self._search.setPlaceholderText("搜索应用…")
        self._search.setStyleSheet(f"""
            QLineEdit {{
                background: {_bg('surface0')}; color: {C['text']}; border: 1px solid {C['surface1']};
                border-radius: 8px; padding: 6px 12px; font-size: 13px;
            }}
            QLineEdit:focus {{ border-color: {C['blue']}; }}
        """)
        self._search.textChanged.connect(self._filter)
        lay.addWidget(self._search)

        self._count_lbl = QLabel()
        self._count_lbl.setStyleSheet(f"color: {C['subtext0']}; font-size: 10px; background: transparent;")
        lay.addWidget(self._count_lbl)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"QScrollArea {{ background: transparent; border: none; }}" + _scrollbar_style(6))
        self._list_container = QWidget()
        self._list_container.setStyleSheet("background: transparent;")
        self._list_layout = QVBoxLayout(self._list_container)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(2)
        self._list_layout.addStretch()
        scroll.setWidget(self._list_container)
        lay.addWidget(scroll, 1)

    def _load_entries(self):
        self._entries = _scan_desktop_entries()
        self._filter()

    def _filter(self):
        query = self._search.text().strip()
        if query:
            self._filtered = [e for e in self._entries if e.matches(query)]
        else:
            self._filtered = list(self._entries)
        self._rebuild_list()

    def _rebuild_list(self):
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        show = self._filtered[:100]
        for entry in show:
            item = _AppItemWidget(entry, self._list_container)
            item.clicked.connect(lambda e=entry: self._launch(e))
            self._list_layout.addWidget(item)
        self._list_layout.addStretch()
        total = len(self._filtered)
        self._count_lbl.setText(f"共 {total} 个应用" + (f"（显示前 100）" if total > 100 else ""))

    def _launch(self, entry):
        cmd = entry.exec_cmd
        cmd = re.sub(r'%[fFuUdDnNickvm]', '', cmd).strip()
        if not cmd:
            return
        try:
            if entry.terminal:
                terminal_cmds = ['x-terminal-emulator', 'gnome-terminal', 'xterm']
                for t in terminal_cmds:
                    if subprocess.run(['which', t], capture_output=True).returncode == 0:
                        subprocess.Popen([t, '-e', cmd])
                        return
            subprocess.Popen(cmd, shell=True, start_new_session=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass


NOTE_COLORS = [
    ("#f9e2af", "#1e1e2e"),
    ("#a6e3a1", "#1e1e2e"),
    ("#89b4fa", "#1e1e2e"),
    ("#f38ba8", "#1e1e2e"),
    ("#cba6f7", "#1e1e2e"),
    ("#fab387", "#1e1e2e"),
    ("#94e2d5", "#1e1e2e"),
]


class NoteWidget(CompBase):
    def __init__(self, data, parent=None):
        super().__init__(data, parent)
        self._parse_note_data()
        self._build_ui()

    def refresh_theme(self):
        if hasattr(self, '_text_edit') and not self._md_mode:
            self._note_text = self._text_edit.toPlainText()
        self._save_cmd()
        super().refresh_theme()

    def _parse_note_data(self):
        raw = self.data.cmd.strip()
        parts = raw.split("|", 2) if raw else []
        self._color_idx = 0
        self._note_text = ""
        if len(parts) >= 1:
            try:
                self._color_idx = int(parts[0]) % len(NOTE_COLORS)
            except ValueError:
                pass
        if len(parts) >= 2:
            self._note_text = parts[1]

    def _build_ui(self):
        bg, fg = NOTE_COLORS[self._color_idx]

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self._header = QWidget()
        self._header.setFixedHeight(32)
        self._header.setStyleSheet(f"background: {bg}; border-radius: 0px;")
        h_lay = QHBoxLayout(self._header)
        h_lay.setContentsMargins(10, 4, 6, 4)

        self._title_lbl = QLabel(self.data.name or "便签")
        self._title_lbl.setStyleSheet(f"color: {fg}; font-size: 14px; font-weight: bold; background: transparent;")
        h_lay.addWidget(self._title_lbl, 1)

        self._md_mode = False
        self._md_btn = QPushButton("Md")
        self._md_btn.setFixedSize(24, 20); self._md_btn.setCursor(Qt.PointingHandCursor)
        self._md_btn.setStyleSheet(f"QPushButton{{background:transparent;color:{fg};border:1px solid {fg}44;"
                                   f"border-radius:4px;font-size:9px;font-weight:bold;}}"
                                   f"QPushButton:hover{{background:{fg}22;}}")
        self._md_btn.clicked.connect(self._toggle_md)
        h_lay.addWidget(self._md_btn)

        self._color_btns = []
        for ci in range(len(NOTE_COLORS)):
            btn = QPushButton()
            c_bg, _ = NOTE_COLORS[ci]
            btn.setFixedSize(16, 16)
            btn.setCursor(Qt.PointingHandCursor)
            border = "2px solid #000" if ci == self._color_idx else "1px solid rgba(0,0,0,0.3)"
            btn.setStyleSheet(f"QPushButton {{ background: {c_bg}; border: {border}; border-radius: 8px; }}"
                              f"QPushButton:hover {{ border: 2px solid #000; }}")
            btn.clicked.connect(lambda _, idx=ci: self._change_color(idx))
            h_lay.addWidget(btn)
            self._color_btns.append(btn)

        lay.addWidget(self._header)

        self._text_edit = QTextEdit()
        self._text_edit.setPlainText(self._note_text)
        self._text_style = (f"QTextEdit {{ background: {bg}88; color: {C['text']}; border: none;"
                            f"font-size: 13px; padding: 8px; font-family: 'Noto Sans CJK SC','Microsoft YaHei',sans-serif; }}")
        self._text_edit.setStyleSheet(self._text_style)
        self._text_edit.textChanged.connect(self._save_text)
        lay.addWidget(self._text_edit, 1)

    def _change_color(self, idx):
        self._color_idx = idx
        self._save_cmd()
        bg, fg = NOTE_COLORS[idx]
        self._header.setStyleSheet(f"background: {bg}; border-radius: 0px;")
        self._title_lbl.setStyleSheet(f"color: {fg}; font-size: 14px; font-weight: bold; background: transparent;")
        self._text_style = (f"QTextEdit {{ background: {bg}88; color: {C['text']}; border: none;"
                            f"font-size: 13px; padding: 8px; font-family: 'Noto Sans CJK SC','Microsoft YaHei',sans-serif; }}")
        self._text_edit.setStyleSheet(self._text_style)
        self._md_btn.setStyleSheet(f"QPushButton{{background:transparent;color:{fg};border:1px solid {fg}44;"
                                   f"border-radius:4px;font-size:9px;font-weight:bold;}}"
                                   f"QPushButton:hover{{background:{fg}22;}}")
        for ci, btn in enumerate(self._color_btns):
            c_bg, _ = NOTE_COLORS[ci]
            border = "2px solid #000" if ci == idx else "1px solid rgba(0,0,0,0.3)"
            btn.setStyleSheet(f"QPushButton {{ background: {c_bg}; border: {border}; border-radius: 8px; }}"
                              f"QPushButton:hover {{ border: 2px solid #000; }}")

    def _toggle_md(self):
        if self._md_mode:
            self._md_mode = False
            self._md_btn.setText("Md")
            self._text_edit.setReadOnly(False)
            self._text_edit.textChanged.disconnect()
            self._text_edit.setPlainText(self._note_text)
            self._text_edit.textChanged.connect(self._save_text)
            self._text_edit.setStyleSheet(self._text_style)
        else:
            self._md_mode = True
            self._md_btn.setText("✎")
            self._note_text = self._text_edit.toPlainText()
            self._save_cmd()
            self._text_edit.setReadOnly(True)
            html = self._md_to_html(self._note_text)
            bg, _ = NOTE_COLORS[self._color_idx]
            self._text_edit.setStyleSheet(
                self._text_style + f"\nQTextEdit {{ selection-background-color: {C['surface1']}; }}")
            self._text_edit.setHtml(html)

    @staticmethod
    def _md_to_html(md):
        import re
        lines = md.split("\n")
        html_lines = []
        in_code = False
        in_list = False
        for line in lines:
            if line.startswith("```"):
                if in_code:
                    html_lines.append("</pre>")
                    in_code = False
                else:
                    html_lines.append(f"<pre style='background:{_bg('surface0')};padding:8px;"
                                      f"border-radius:6px;font-size:12px;color:{C['green']};'>")
                    in_code = True
                continue
            if in_code:
                html_lines.append(line.replace("<", "&lt;").replace(">", "&gt;"))
                continue

            escaped = line.replace("<", "&lt;").replace(">", "&gt;")

            if escaped.startswith("### "):
                escaped = f"<h3 style='margin:4px 0;font-size:14px;color:{C['mauve']};'>{escaped[4:]}</h3>"
            elif escaped.startswith("## "):
                escaped = f"<h2 style='margin:4px 0;font-size:15px;color:{C['mauve']};'>{escaped[3:]}</h2>"
            elif escaped.startswith("# "):
                escaped = f"<h1 style='margin:4px 0;font-size:16px;color:{C['mauve']};'>{escaped[2:]}</h1>"
            elif escaped.startswith("- ") or escaped.startswith("* "):
                escaped = f"<li style='margin-left:16px;'>{escaped[2:]}</li>"
            elif re.match(r'^\d+\.\s', escaped):
                ol_text = re.sub(r'^[0-9]+\.\s', '', escaped)
                escaped = f"<li style='margin-left:16px;'>{ol_text}</li>"
            elif escaped.startswith("> "):
                escaped = (f"<blockquote style='border-left:3px solid {C['overlay0']};padding-left:8px;"
                           f"color:{C['subtext0']};margin:4px 0;'>{escaped[2:]}</blockquote>")
            elif escaped.strip() == "---" or escaped.strip() == "***":
                escaped = f"<hr style='border:1px solid {C['surface1']};margin:6px 0;'>"
            elif escaped.strip() == "":
                escaped = "<br>"
            else:
                escaped = f"<p style='margin:2px 0;'>{escaped}</p>"

            escaped = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', escaped)
            escaped = re.sub(r'\*(.+?)\*', r'<i>\1</i>', escaped)
            escaped = re.sub(r'`(.+?)`', f'<code style="background:{C["surface0"]};padding:1px 4px;'
                             f'border-radius:3px;font-size:12px;">\\1</code>', escaped)
            escaped = re.sub(r'\[(.+?)\]\((.+?)\)',
                             f'<a style="color:{C["blue"]};text-decoration:underline;" href="\\2">\\1</a>',
                             escaped)

            html_lines.append(escaped)

        if in_code:
            html_lines.append("</pre>")
        return "\n".join(html_lines)

    def _save_text(self):
        if not self._md_mode:
            self._note_text = self._text_edit.toPlainText()
            self._save_cmd()

    def _save_cmd(self):
        self.data.cmd = f"{self._color_idx}|{self._note_text}"
        main_win = self.window()
        if hasattr(main_win, '_save_panels'):
            main_win._save_panels()


_QUICK_ACTIONS = [
    ("system-lock-screen", "锁屏", "loginctl lock-session", C['blue'], False),
    ("system-suspend", "挂起", "systemctl suspend", C['lavender'], False),
    ("camera-photo", "截图", "gnome-screenshot -i", C['teal'], False),
    ("system-file-manager", "文件", "xdg-open ~", C['green'], False),
    ("preferences-system", "设置", "gnome-control-center", C['sky'], False),
    ("system-reboot", "重启", "systemctl reboot", C['red'], True),
    ("system-shutdown", "关机", "systemctl poweroff", C['red'], True),
    ("system-log-out", "注销", "gnome-session-quit --logout --no-prompt", C['red'], True),
]


class _QAButton(QFrame):
    clicked = pyqtSignal()

    def __init__(self, icon_name, label, color, dangerous, parent=None):
        super().__init__(parent)
        self._color = color
        self._dangerous = dangerous
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(72, 72)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 6, 0, 4)
        lay.setSpacing(2)
        lay.setAlignment(Qt.AlignCenter)

        icon_lbl = QLabel()
        icon_lbl.setAlignment(Qt.AlignCenter)
        icon_lbl.setStyleSheet("background: transparent;")
        icon_lbl.setFixedSize(28, 28)
        qicon = QIcon.fromTheme(icon_name)
        if not qicon.isNull():
            icon_lbl.setPixmap(qicon.pixmap(28, 28))
        else:
            icon_lbl.setText(icon_name[:2])
            icon_lbl.setStyleSheet(f"font-size:20px; background:transparent; color:{C['text']};")
        lay.addWidget(icon_lbl, 0, Qt.AlignCenter)

        name_lbl = QLabel(label)
        name_lbl.setAlignment(Qt.AlignCenter)
        name_lbl.setStyleSheet(f"color: {C['subtext0']}; font-size: 10px; background: transparent;")
        lay.addWidget(name_lbl)

        self._update_style(False)

    def _update_style(self, hovered):
        if hovered:
            self.setStyleSheet(f"_QAButton {{ background: {self._color}; border-radius: 14px; }}")
        else:
            self.setStyleSheet(f"""
                _QAButton {{ background: {_bg('surface0')}; border-radius: 14px; }}
                _QAButton:hover {{ background: {self._color}44; }}
            """)

    def enterEvent(self, e):
        self._update_style(True)
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._update_style(False)
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(e)


class QuickActionWidget(CompBase):
    def __init__(self, data, parent=None):
        super().__init__(data, parent)
        self._build_ui()
        self._vol_timer = QTimer(self)
        self._vol_timer.timeout.connect(self._poll_volume)
        self._vol_timer.start(2000)
        QTimer.singleShot(200, self._poll_volume)

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(6)

        from PyQt5.QtWidgets import QGridLayout, QSlider
        grid = QGridLayout()
        grid.setSpacing(8)

        cols = 4
        for i, (icon, name, cmd, color, dangerous) in enumerate(_QUICK_ACTIONS):
            btn = _QAButton(icon, name, color, dangerous, self)
            btn.clicked.connect(lambda c=cmd, n=name, d=dangerous: self._run(c, n, d))
            grid.addWidget(btn, i // cols, i % cols, Qt.AlignCenter)

        lay.addLayout(grid)

        vol_row = QHBoxLayout(); vol_row.setSpacing(8)
        self._is_muted = False
        self._mute_btn = QPushButton()
        self._mute_btn.setFixedSize(32, 32)
        self._mute_btn.setCursor(Qt.PointingHandCursor)
        self._mute_btn.clicked.connect(self._toggle_mute)
        self._update_mute_btn_style()
        vol_row.addWidget(self._mute_btn)
        self._vol_slider = QSlider(Qt.Horizontal)
        self._vol_slider.setRange(0, 100)
        self._vol_slider.setValue(50)
        self._vol_slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                background: {_bg('surface1')}; height: 6px; border-radius: 3px;
            }}
            QSlider::handle:horizontal {{
                background: {C['blue']}; width: 16px; height: 16px; margin: -5px 0;
                border-radius: 8px;
            }}
            QSlider::handle:horizontal:hover {{ background: {C.get('sapphire', C['blue'])}; }}
            QSlider::sub-page:horizontal {{ background: {C['blue']}; border-radius: 3px; }}
        """)
        self._vol_slider.valueChanged.connect(self._set_volume)
        vol_row.addWidget(self._vol_slider, 1)
        self._vol_label = QLabel("50%")
        self._vol_label.setFixedWidth(36)
        self._vol_label.setStyleSheet(f"color:{C['text']};font-size:11px;background:transparent;")
        vol_row.addWidget(self._vol_label)
        lay.addLayout(vol_row)
        lay.addStretch()

    def _poll_volume(self):
        try:
            out = subprocess.check_output(
                ["pactl", "get-sink-volume", "@DEFAULT_SINK@"],
                timeout=2, stderr=subprocess.DEVNULL).decode()
            import re
            m = re.search(r'(\d+)%', out)
            if m:
                vol = int(m.group(1))
                self._vol_slider.blockSignals(True)
                self._vol_slider.setValue(vol)
                self._vol_slider.blockSignals(False)
                self._vol_label.setText(f"{vol}%")
        except Exception:
            pass
        try:
            out = subprocess.check_output(
                ["pactl", "get-sink-mute", "@DEFAULT_SINK@"],
                timeout=2, stderr=subprocess.DEVNULL).decode()
            self._is_muted = "yes" in out.lower()
            self._update_mute_btn_style()
        except Exception:
            pass

    def _set_volume(self, val):
        self._vol_label.setText(f"{val}%")
        try:
            subprocess.Popen(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{val}%"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

    def _toggle_mute(self):
        try:
            subprocess.Popen(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass
        self._is_muted = not self._is_muted
        self._update_mute_btn_style()
        QTimer.singleShot(300, self._poll_volume)

    def _update_mute_btn_style(self):
        icon_name = "audio-volume-muted" if self._is_muted else "audio-volume-high"
        qicon = QIcon.fromTheme(icon_name)
        if not qicon.isNull():
            self._mute_btn.setIcon(qicon)
            self._mute_btn.setIconSize(self._mute_btn.size() * 0.6)
        else:
            self._mute_btn.setText("🔇" if self._is_muted else "🔊")
        if self._is_muted:
            self._mute_btn.setStyleSheet(
                f"QPushButton{{background:{C['red']};border:none;border-radius:8px;font-size:16px;}}"
                f"QPushButton:hover{{background:{C['peach']};}}")
        else:
            self._mute_btn.setStyleSheet(
                f"QPushButton{{background:{_bg('surface0')};border:none;border-radius:8px;font-size:16px;}}"
                f"QPushButton:hover{{background:{_bg('surface1')};}}")

    def _run(self, cmd, name, dangerous):
        if dangerous:
            if not _confirm_dialog(self, "确认操作", f"确定要执行「{name}」吗？"):
                return
        try:
            subprocess.Popen(cmd, shell=True, start_new_session=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

    def refresh_theme(self):
        super().refresh_theme()
        self._vol_timer = QTimer(self); self._vol_timer.timeout.connect(self._poll_volume)
        self._vol_timer.start(2000)
        QTimer.singleShot(200, self._poll_volume)


# ---------------------------------------------------------------------------
# Media Controller Widget (MPRIS D-Bus)
# ---------------------------------------------------------------------------
class MediaWidget(CompBase):
    def __init__(self, data, parent=None):
        super().__init__(data, parent)
        self._title = ""; self._artist = ""; self._album = ""
        self._playing = False; self._art_pixmap = None
        self._timer = QTimer(self); self._timer.timeout.connect(self._tick); self._timer.start(1500)
        self._build_ui()
        QTimer.singleShot(100, self._tick)

    def _build_ui(self):
        lay = QVBoxLayout(self); lay.setContentsMargins(16, 12, 16, 12); lay.setSpacing(6)
        top = QHBoxLayout(); top.setSpacing(12)
        self._art_label = QLabel(); self._art_label.setFixedSize(60, 60)
        self._art_label.setStyleSheet(f"background: {_bg('surface1')}; border-radius: 8px;")
        self._art_label.setAlignment(Qt.AlignCenter)
        top.addWidget(self._art_label)
        info = QVBoxLayout(); info.setSpacing(2)
        self._title_lbl = QLabel("无媒体播放")
        self._title_lbl.setStyleSheet(f"color:{C['text']};font-size:14px;font-weight:bold;background:transparent;")
        self._artist_lbl = QLabel("")
        self._artist_lbl.setStyleSheet(f"color:{C['subtext0']};font-size:11px;background:transparent;")
        self._album_lbl = QLabel("")
        self._album_lbl.setStyleSheet(f"color:{C['overlay0']};font-size:10px;background:transparent;")
        info.addWidget(self._title_lbl); info.addWidget(self._artist_lbl); info.addWidget(self._album_lbl)
        info.addStretch()
        top.addLayout(info); top.addStretch()
        lay.addLayout(top)
        btns = QHBoxLayout(); btns.setSpacing(12); btns.addStretch()
        _media_icons = [
            ("media-skip-backward", "Previous", 36),
            ("media-playback-start", "PlayPause", 44),
            ("media-skip-forward", "Next", 36),
        ]
        self._play_btn = None
        for icon_name, cmd, sz in _media_icons:
            b = QPushButton(); b.setFixedSize(sz, sz); b.setCursor(Qt.PointingHandCursor)
            qicon = QIcon.fromTheme(icon_name)
            if not qicon.isNull():
                b.setIcon(qicon)
                b.setIconSize(b.size() * 0.55)
            else:
                fallback = {"Previous": "◂◂", "PlayPause": "▶", "Next": "▸▸"}
                b.setText(fallback.get(cmd, "?"))
            is_main = (cmd == "PlayPause")
            if is_main:
                b.setStyleSheet(f"""QPushButton {{background:{C['blue']};color:{C['crust']};
                    border:none;border-radius:{sz // 2}px;}}
                    QPushButton:hover {{background:{C['lavender']};}}""")
                self._play_btn = b
            else:
                b.setStyleSheet(f"""QPushButton {{background:{_bg('surface1')};color:{C['text']};
                    border:none;border-radius:{sz // 2}px;}}
                    QPushButton:hover {{background:{C['surface2']};}}""")
            b.clicked.connect(lambda _, c=cmd: self._mpris_cmd(c))
            btns.addWidget(b)
        btns.addStretch()
        lay.addLayout(btns)

    def _mpris_cmd(self, method):
        try:
            subprocess.Popen(
                ["dbus-send", "--print-reply", "--dest=org.mpris.MediaPlayer2.*",
                 "/org/mpris/MediaPlayer2", f"org.mpris.MediaPlayer2.Player.{method}"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            players = self._get_players()
            if players:
                try:
                    subprocess.Popen(
                        ["dbus-send", "--print-reply", f"--dest={players[0]}",
                         "/org/mpris/MediaPlayer2", f"org.mpris.MediaPlayer2.Player.{method}"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                except Exception:
                    pass

    def _get_players(self):
        try:
            out = subprocess.check_output(
                ["dbus-send", "--session", "--dest=org.freedesktop.DBus",
                 "--type=method_call", "--print-reply",
                 "/org/freedesktop/DBus", "org.freedesktop.DBus.ListNames"],
                timeout=2, stderr=subprocess.DEVNULL).decode()
            return [line.strip().strip('"') for line in out.split('\n')
                    if 'org.mpris.MediaPlayer2.' in line]
        except Exception:
            return []

    def _tick(self):
        players = self._get_players()
        if not players:
            self._title_lbl.setText("无媒体播放"); self._artist_lbl.setText(""); self._album_lbl.setText("")
            return
        player = players[0]
        try:
            out = subprocess.check_output(
                ["dbus-send", "--session", "--print-reply", f"--dest={player}",
                 "/org/mpris/MediaPlayer2",
                 "org.freedesktop.DBus.Properties.Get",
                 "string:org.mpris.MediaPlayer2.Player", "string:Metadata"],
                timeout=2, stderr=subprocess.DEVNULL).decode()
            title = self._extract_meta(out, "xesam:title")
            artist = self._extract_meta(out, "xesam:artist")
            album = self._extract_meta(out, "xesam:album")
            self._title_lbl.setText(title or "未知曲目")
            self._artist_lbl.setText(artist or "")
            self._album_lbl.setText(album or "")
        except Exception:
            pass

    def refresh_theme(self):
        super().refresh_theme()
        self._timer = QTimer(self); self._timer.timeout.connect(self._tick); self._timer.start(1500)
        QTimer.singleShot(100, self._tick)

    @staticmethod
    def _extract_meta(raw, key):
        idx = raw.find(key)
        if idx < 0:
            return ""
        sub = raw[idx:]
        for marker in ['string "', 'variant       string "']:
            si = sub.find(marker)
            if si >= 0:
                start = si + len(marker)
                end = sub.find('"', start)
                if end > start:
                    return sub[start:end]
        return ""


# ---------------------------------------------------------------------------
# Clipboard Manager Widget
# ---------------------------------------------------------------------------
class ClipboardWidget(CompBase):
    _shared_history = []
    _shared_img_history = []

    def __init__(self, data, parent=None):
        super().__init__(data, parent)
        self._max = 30
        self._last_text = ""
        self._last_img_hash = 0
        self._build_ui()
        self._timer = QTimer(self); self._timer.timeout.connect(self._poll); self._timer.start(800)

    def refresh_theme(self):
        last = self._last_text
        super().refresh_theme()
        self._last_text = last
        self._rebuild()
        self._timer = QTimer(self); self._timer.timeout.connect(self._poll); self._timer.start(800)

    def _build_ui(self):
        lay = QVBoxLayout(self); lay.setContentsMargins(12, 10, 12, 10); lay.setSpacing(6)
        hdr = QHBoxLayout()
        title = QLabel("📋 剪贴板历史")
        title.setStyleSheet(f"color:{C['text']};font-size:14px;font-weight:bold;background:transparent;")
        hdr.addWidget(title); hdr.addStretch()
        cnt_lbl = QLabel(f"文本 {len(ClipboardWidget._shared_history)} · 图片 {len(ClipboardWidget._shared_img_history)}")
        cnt_lbl.setStyleSheet(f"color:{C['subtext0']};font-size:10px;background:transparent;")
        self._cnt_lbl = cnt_lbl
        hdr.addWidget(cnt_lbl)
        clr = QPushButton("清空"); clr.setCursor(Qt.PointingHandCursor)
        clr.setStyleSheet(f"background:{_bg('surface1')};color:{C['red']};border:none;border-radius:8px;"
                          f"font-size:11px;padding:4px 12px;")
        clr.clicked.connect(self._clear)
        hdr.addWidget(clr)
        lay.addLayout(hdr)
        sc = QScrollArea(); sc.setWidgetResizable(True)
        sc.setStyleSheet(f"QScrollArea{{background:transparent;border:none;}}QScrollArea > QWidget{{background:transparent;}}{_scrollbar_style(6)}")
        sc.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._list_w = QWidget()
        self._list_w.setStyleSheet("background:transparent;")
        self._list_lay = QVBoxLayout(self._list_w); self._list_lay.setContentsMargins(0, 0, 0, 0)
        self._list_lay.setSpacing(4); self._list_lay.addStretch()
        sc.setWidget(self._list_w)
        lay.addWidget(sc)

    def _poll(self):
        cb = QApplication.clipboard()
        mime = cb.mimeData()
        if mime and mime.hasImage():
            img = cb.image()
            if not img.isNull():
                h = hash(img.bits().asstring(img.byteCount()) if hasattr(img.bits(), 'asstring')
                         else img.sizeInBytes())
                if h != self._last_img_hash:
                    self._last_img_hash = h
                    pm = QPixmap.fromImage(img)
                    ClipboardWidget._shared_img_history.insert(0, pm)
                    if len(ClipboardWidget._shared_img_history) > 10:
                        ClipboardWidget._shared_img_history = ClipboardWidget._shared_img_history[:10]
                    self._rebuild()
                    return
        text = cb.text()
        if text and text != self._last_text:
            self._last_text = text
            if text in ClipboardWidget._shared_history:
                ClipboardWidget._shared_history.remove(text)
            ClipboardWidget._shared_history.insert(0, text)
            if len(ClipboardWidget._shared_history) > self._max:
                ClipboardWidget._shared_history = ClipboardWidget._shared_history[:self._max]
            self._rebuild()

    def _rebuild(self):
        while self._list_lay.count() > 1:
            item = self._list_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        idx = 0
        for pm in ClipboardWidget._shared_img_history:
            frame = QFrame()
            frame.setCursor(Qt.PointingHandCursor)
            frame.setStyleSheet(f"QFrame{{background:{_bg('surface0')};border-radius:6px;padding:4px;}}"
                                f"QFrame:hover{{background:{_bg('surface1')};}}")
            fl = QHBoxLayout(frame); fl.setContentsMargins(6, 4, 6, 4); fl.setSpacing(6)
            thumb = QLabel()
            scaled = pm.scaled(48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            thumb.setPixmap(scaled)
            thumb.setStyleSheet("background:transparent;")
            fl.addWidget(thumb)
            info = QLabel(f"🖼 图片 {pm.width()}×{pm.height()}")
            info.setStyleSheet(f"color:{C['text']};font-size:10px;background:transparent;")
            fl.addWidget(info, 1)
            frame.mousePressEvent = lambda e, p=pm: self._paste_image(p)
            self._list_lay.insertWidget(idx, frame); idx += 1
        for text in ClipboardWidget._shared_history:
            preview = text[:80].replace('\n', ' ')
            btn = QPushButton(preview); btn.setCursor(Qt.PointingHandCursor)
            btn.setToolTip(text[:300])
            btn.setStyleSheet(f"""QPushButton {{
                background:{_bg('surface0')};color:{C['text']};border:none;border-radius:6px;
                text-align:left;padding:6px 8px;font-size:11px;}}
                QPushButton:hover {{background:{_bg('surface1')};}}""")
            btn.clicked.connect(lambda _, t=text: self._paste_text(t))
            self._list_lay.insertWidget(idx, btn); idx += 1
        self._cnt_lbl.setText(f"文本 {len(ClipboardWidget._shared_history)} · 图片 {len(ClipboardWidget._shared_img_history)}")

    def _paste_text(self, text):
        QApplication.clipboard().setText(text)

    def _paste_image(self, pm):
        QApplication.clipboard().setPixmap(pm)

    def _clear(self):
        ClipboardWidget._shared_history.clear()
        ClipboardWidget._shared_img_history.clear()
        self._rebuild()


class _ClipboardPopup(QWidget):
    """Themed floating popup for quick clipboard access via hotkey."""

    _instance = None

    @classmethod
    def get_or_create(cls, parent=None):
        try:
            if cls._instance is not None and cls._instance.isVisible():
                cls._instance.hide()
                return cls._instance
        except RuntimeError:
            cls._instance = None
        cls._instance = cls(parent)
        return cls._instance

    def __init__(self, parent=None):
        super().__init__(None, Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setFixedWidth(380)
        self.setMaximumHeight(500)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAttribute(Qt.WA_ShowWithoutActivating, False)
        self.installEventFilter(self)
        self._build_ui()

    def _build_ui(self):
        self.setStyleSheet(f"""
            _ClipboardPopup {{
                background: {C['base']}; border: 1px solid {C['surface1']}; border-radius: 14px;
            }}""")
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(30); shadow.setOffset(0, 6); shadow.setColor(QColor(0, 0, 0, 120))
        self.setGraphicsEffect(shadow)

        lay = QVBoxLayout(self); lay.setContentsMargins(14, 14, 14, 10); lay.setSpacing(8)

        header = QHBoxLayout(); header.setSpacing(8)
        icon_lbl = QLabel("📋")
        icon_lbl.setStyleSheet(f"font-size:18px;background:transparent;")
        header.addWidget(icon_lbl)
        title = QLabel("剪贴板历史")
        title.setStyleSheet(f"color:{C['text']};font-size:15px;font-weight:bold;background:transparent;")
        header.addWidget(title)
        header.addStretch()
        count_lbl = QLabel()
        count_lbl.setStyleSheet(f"color:{C['subtext0']};font-size:11px;background:transparent;")
        header.addWidget(count_lbl)
        self._count_lbl = count_lbl
        lay.addLayout(header)

        sep = QFrame(); sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"background:{C['surface0']};border:none;max-height:1px;")
        lay.addWidget(sep)

        sc = QScrollArea(); sc.setWidgetResizable(True)
        sc.setFixedHeight(400)
        sc.setStyleSheet(f"QScrollArea{{background:transparent;border:none;}}"
                         f"QScrollArea>QWidget{{background:transparent;}}"
                         f"{_scrollbar_style(6)}")
        sc.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._list_w = QWidget()
        self._list_w.setStyleSheet("background:transparent;")
        self._list_lay = QVBoxLayout(self._list_w)
        self._list_lay.setContentsMargins(0, 0, 0, 0)
        self._list_lay.setSpacing(4)
        self._list_lay.addStretch()
        sc.setWidget(self._list_w)
        lay.addWidget(sc)

        hint = QLabel("选择条目即可粘贴  ·  按 Esc 关闭")
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet(f"color:{C['overlay0']};font-size:10px;background:transparent;")
        lay.addWidget(hint)

    def _rebuild(self):
        while self._list_lay.count() > 1:
            item = self._list_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        idx = 0
        total = len(ClipboardWidget._shared_img_history) + len(ClipboardWidget._shared_history)
        self._count_lbl.setText(f"{total} 条记录")

        for pm in ClipboardWidget._shared_img_history:
            frame = QFrame(); frame.setCursor(Qt.PointingHandCursor)
            frame.setStyleSheet(f"""QFrame{{background:{C['surface0']};border-radius:8px;}}
                QFrame:hover{{background:{C['surface1']};border:1px solid {C['blue']};}}""")
            fl = QHBoxLayout(frame); fl.setContentsMargins(8, 6, 8, 6); fl.setSpacing(8)
            thumb = QLabel()
            scaled = pm.scaled(48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            thumb.setPixmap(scaled)
            thumb.setStyleSheet("background:transparent;border-radius:4px;")
            fl.addWidget(thumb)
            info_lay = QVBoxLayout(); info_lay.setSpacing(1)
            info = QLabel(f"图片  {pm.width()}×{pm.height()}")
            info.setStyleSheet(f"color:{C['text']};font-size:11px;background:transparent;")
            info_lay.addWidget(info)
            tag = QLabel("🖼 图像")
            tag.setStyleSheet(f"color:{C['subtext0']};font-size:9px;background:transparent;")
            info_lay.addWidget(tag)
            fl.addLayout(info_lay, 1)
            frame.mousePressEvent = lambda e, p=pm: self._pick_image(p)
            self._list_lay.insertWidget(idx, frame); idx += 1

        for text in ClipboardWidget._shared_history:
            preview = text[:120].replace(chr(10), " ↵ ")
            frame = QFrame(); frame.setCursor(Qt.PointingHandCursor)
            frame.setStyleSheet(f"""QFrame{{background:{C['surface0']};border-radius:8px;padding:8px 10px;}}
                QFrame:hover{{background:{C['surface1']};border:1px solid {C['blue']};}}""")
            fl = QVBoxLayout(frame); fl.setContentsMargins(10, 8, 10, 8); fl.setSpacing(2)
            lbl = QLabel(preview)
            lbl.setWordWrap(True)
            lbl.setStyleSheet(f"color:{C['text']};font-size:12px;background:transparent;")
            fl.addWidget(lbl)
            if len(text) > 120:
                more = QLabel(f"…共 {len(text)} 字符")
                more.setStyleSheet(f"color:{C['overlay0']};font-size:9px;background:transparent;")
                fl.addWidget(more)
            frame.mousePressEvent = lambda e, t=text: self._pick_text(t)
            self._list_lay.insertWidget(idx, frame); idx += 1

        if total == 0:
            empty = QLabel("剪贴板为空")
            empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet(f"color:{C['overlay0']};font-size:13px;padding:40px;background:transparent;")
            self._list_lay.insertWidget(0, empty)

    def _pick_text(self, text):
        QApplication.clipboard().setText(text)
        self.hide()
        QTimer.singleShot(300, self._simulate_paste)

    def _pick_image(self, pm):
        QApplication.clipboard().setPixmap(pm)
        self.hide()
        QTimer.singleShot(300, self._simulate_paste)

    @staticmethod
    def _simulate_paste():
        try:
            from Xlib import X, display as xdisplay, XK, ext
            d = xdisplay.Display()
            root = d.screen().root
            focus_win = d.get_input_focus().focus
            ctrl_keycode = d.keysym_to_keycode(XK.string_to_keysym("Control_L"))
            v_keycode = d.keysym_to_keycode(XK.string_to_keysym("v"))
            import Xlib.protocol.event as xevent
            for keycode in [ctrl_keycode, v_keycode]:
                ev = xevent.KeyPress(time=X.CurrentTime, root=root, window=focus_win,
                    same_screen=True, child=X.NONE, root_x=0, root_y=0, event_x=0, event_y=0,
                    state=(X.ControlMask if keycode == v_keycode else 0), detail=keycode)
                focus_win.send_event(ev, propagate=True)
            for keycode in [v_keycode, ctrl_keycode]:
                ev = xevent.KeyRelease(time=X.CurrentTime, root=root, window=focus_win,
                    same_screen=True, child=X.NONE, root_x=0, root_y=0, event_x=0, event_y=0,
                    state=(X.ControlMask if keycode == v_keycode else 0), detail=keycode)
                focus_win.send_event(ev, propagate=True)
            d.sync()
            d.close()
        except Exception as ex:
            print(f"[Clipboard] paste simulate error: {ex}", flush=True)
            try:
                subprocess.Popen(["xdotool", "key", "ctrl+v"],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.hide()
            e.accept()
        else:
            super().keyPressEvent(e)

    def eventFilter(self, obj, event):
        from PyQt5.QtCore import QEvent
        if event.type() == QEvent.WindowDeactivate:
            QTimer.singleShot(100, self._check_deactivate)
        return super().eventFilter(obj, event)

    def _check_deactivate(self):
        if not self.isActiveWindow():
            self.hide()

    def show_at_cursor(self):
        self._rebuild()
        pos = QCursor.pos()
        screen = QApplication.screenAt(pos)
        if screen:
            sg = screen.availableGeometry()
            x = min(pos.x(), sg.right() - self.width())
            y = min(pos.y(), sg.bottom() - self.height())
            self.move(max(x, sg.left()), max(y, sg.top()))
        else:
            self.move(pos)
        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus()

# ---------------------------------------------------------------------------
# Timer / Countdown Widget
# ---------------------------------------------------------------------------
class TimerWidget(CompBase):
    def __init__(self, data, parent=None):
        super().__init__(data, parent)
        self._elapsed = 0
        self._target = 0
        self._running = False
        self._mode = "stopwatch"
        self._build_ui()
        self._tick_timer = QTimer(self); self._tick_timer.timeout.connect(self._tick)

    def _build_ui(self):
        lay = QVBoxLayout(self); lay.setContentsMargins(16, 12, 16, 12); lay.setSpacing(6)
        self._display = QLabel("00:00:00")
        self._display.setAlignment(Qt.AlignCenter)
        self._display.setStyleSheet(f"color:{C['text']};font-size:36px;font-weight:bold;"
                                    f"font-family:'JetBrains Mono','Courier New',monospace;"
                                    f"background:transparent;")
        lay.addWidget(self._display)
        mode_row = QHBoxLayout(); mode_row.addStretch()
        self._sw_btn = QPushButton("秒表"); self._cd_btn = QPushButton("倒计时")
        for btn, m in [(self._sw_btn, "stopwatch"), (self._cd_btn, "countdown")]:
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedHeight(28)
            btn.clicked.connect(lambda _, md=m: self._set_mode(md))
            mode_row.addWidget(btn)
        mode_row.addStretch()
        lay.addLayout(mode_row)
        self._input_row = QHBoxLayout(); self._input_row.addStretch()
        self._min_edit = QLineEdit("5"); self._min_edit.setFixedWidth(50)
        self._min_edit.setAlignment(Qt.AlignCenter)
        self._min_edit.setValidator(QIntValidator(0, 999))
        self._min_edit.setStyleSheet(f"background:{_bg('surface0')};color:{C['text']};border:1px solid {C['surface1']};"
                                     f"border-radius:8px;padding:6px;font-size:13px;")
        self._min_label = QLabel("分钟")
        self._min_label.setStyleSheet(f"color:{C['subtext0']};font-size:12px;background:transparent;")
        self._input_row.addWidget(self._min_edit); self._input_row.addWidget(self._min_label)
        self._input_row.addStretch()
        lay.addLayout(self._input_row)
        btn_row = QHBoxLayout(); btn_row.addStretch()
        self._start_btn = QPushButton("开始"); self._start_btn.setCursor(Qt.PointingHandCursor)
        self._reset_btn = QPushButton("重置"); self._reset_btn.setCursor(Qt.PointingHandCursor)
        for b in [self._start_btn, self._reset_btn]:
            b.setFixedSize(70, 32)
            btn_row.addWidget(b)
        btn_row.addStretch()
        lay.addLayout(btn_row)
        self._start_btn.clicked.connect(self._toggle)
        self._reset_btn.clicked.connect(self._reset)
        self._set_mode("stopwatch")
        self._update_btn_styles()

    def _update_btn_styles(self):
        active = f"background:{C['blue']};color:{C['crust']};border:none;border-radius:8px;font-size:13px;padding:4px 12px;"
        inactive = f"background:{_bg('surface1')};color:{C['text']};border:none;border-radius:8px;font-size:13px;padding:4px 12px;"
        self._sw_btn.setStyleSheet(active if self._mode == "stopwatch" else inactive)
        self._cd_btn.setStyleSheet(active if self._mode == "countdown" else inactive)
        start_style = (f"background:{C['red']};color:{C['crust']};" if self._running
                       else f"background:{C['green']};color:{C['crust']};")
        self._start_btn.setStyleSheet(start_style + "border:none;border-radius:8px;font-size:13px;font-weight:bold;")
        self._start_btn.setText("停止" if self._running else "开始")
        self._reset_btn.setStyleSheet(f"background:{_bg('surface1')};color:{C['text']};border:none;"
                                      f"border-radius:8px;font-size:13px;")

    def _set_mode(self, mode):
        self._mode = mode
        self._reset()
        visible = mode == "countdown"
        self._min_edit.setVisible(visible)
        self._min_label.setVisible(visible)
        self._update_btn_styles()

    def _toggle(self):
        if self._running:
            self._running = False; self._tick_timer.stop()
        else:
            if self._mode == "countdown":
                try:
                    mins = int(self._min_edit.text() or "0")
                except ValueError:
                    mins = 0
                if mins <= 0 and self._target <= 0:
                    return
                if self._target <= 0:
                    self._target = mins * 60
                    self._elapsed = 0
            self._running = True; self._tick_timer.start(100)
        self._update_btn_styles()

    def _reset(self):
        self._running = False; self._tick_timer.stop()
        self._elapsed = 0; self._target = 0
        self._display.setText("00:00:00")
        self._display.setStyleSheet(f"color:{C['text']};font-size:36px;font-weight:bold;"
                                    f"font-family:'JetBrains Mono','Courier New',monospace;background:transparent;")
        self._update_btn_styles()

    def _tick(self):
        self._elapsed += 0.1
        if self._mode == "stopwatch":
            t = int(self._elapsed)
            h, m, s = t // 3600, (t % 3600) // 60, t % 60
            ms = int((self._elapsed - t) * 10)
            self._display.setText(f"{h:02d}:{m:02d}:{s:02d}.{ms}")
        else:
            remaining = max(0, self._target - self._elapsed)
            t = int(remaining)
            h, m, s = t // 3600, (t % 3600) // 60, t % 60
            self._display.setText(f"{h:02d}:{m:02d}:{s:02d}")
            if remaining <= 0:
                self._running = False; self._tick_timer.stop()
                self._display.setStyleSheet(
                    f"color:{C['red']};font-size:36px;font-weight:bold;"
                    f"font-family:'JetBrains Mono','Courier New',monospace;background:transparent;")
                self._update_btn_styles()

    def refresh_theme(self):
        saved_elapsed = self._elapsed
        saved_target = self._target
        saved_running = self._running
        saved_mode = self._mode
        self._running = False
        super().refresh_theme()
        self._tick_timer = QTimer(self); self._tick_timer.timeout.connect(self._tick)
        self._elapsed = saved_elapsed
        self._target = saved_target
        self._mode = saved_mode
        self._set_mode(saved_mode)
        self._elapsed = saved_elapsed
        self._target = saved_target
        if saved_running:
            self._running = True; self._tick_timer.start(100)
            self._update_btn_styles()


# ---------------------------------------------------------------------------
# Gallery / Photo Widget
# ---------------------------------------------------------------------------
class GalleryWidget(CompBase):
    def __init__(self, data, parent=None):
        super().__init__(data, parent)
        self._images: list[str] = []
        self._idx = 0
        self._pixmap = None
        self._interval = 5
        self._build_ui()
        self._slide_timer = QTimer(self); self._slide_timer.timeout.connect(self._next)
        if data.cmd:
            self._load_dir(data.cmd.split("|")[0].strip())

    def _build_ui(self):
        lay = QVBoxLayout(self); lay.setContentsMargins(4, 4, 4, 4); lay.setSpacing(0)
        self._img_label = QLabel(); self._img_label.setAlignment(Qt.AlignCenter)
        self._img_label.setStyleSheet("background:transparent;")
        self._img_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        lay.addWidget(self._img_label, 1)

        self._browse_btn = QPushButton("\U0001f4c2", self)
        self._browse_btn.setFixedSize(28, 28)
        self._browse_btn.setCursor(Qt.PointingHandCursor)
        self._browse_btn.setStyleSheet(
            f"QPushButton{{background:rgba(0,0,0,0.4);color:white;border:none;border-radius:6px;font-size:14px;}}"
            f"QPushButton:hover{{background:{C['blue']};color:{C['crust']};}}")
        self._browse_btn.clicked.connect(self._browse)
        self._browse_btn.setToolTip("选择图片目录")

        _nav_s = (f"QPushButton{{background:rgba(0,0,0,0.35);color:white;"
                  f"border:none;border-radius:16px;font-size:18px;font-weight:bold;}}"
                  f"QPushButton:hover{{background:rgba(0,0,0,0.65);}}")
        self._prev_btn = QPushButton("\u2039", self)
        self._prev_btn.setFixedSize(32, 32); self._prev_btn.setCursor(Qt.PointingHandCursor)
        self._prev_btn.setStyleSheet(_nav_s)
        self._prev_btn.clicked.connect(self._prev)
        self._prev_btn.hide()

        self._next_btn = QPushButton("\u203a", self)
        self._next_btn.setFixedSize(32, 32); self._next_btn.setCursor(Qt.PointingHandCursor)
        self._next_btn.setStyleSheet(_nav_s)
        self._next_btn.clicked.connect(self._next)
        self._next_btn.hide()

        self._counter = QLabel("", self)
        self._counter.setAlignment(Qt.AlignCenter)
        self._counter.setStyleSheet(
            "color:white;font-size:10px;background:rgba(0,0,0,0.4);border-radius:8px;padding:2px 8px;")
        self._counter.hide()
        self._browse_btn.hide()

    def enterEvent(self, e):
        super().enterEvent(e)
        self._browse_btn.show()
        if self._images:
            self._prev_btn.show(); self._next_btn.show(); self._counter.show()

    def leaveEvent(self, e):
        super().leaveEvent(e)
        self._browse_btn.hide(); self._prev_btn.hide(); self._next_btn.hide(); self._counter.hide()

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "选择图片目录", os.path.expanduser("~"))
        if d:
            self._load_dir(d)

    def _load_dir(self, path):
        if not path or not os.path.isdir(path):
            return
        exts = {'.png', '.jpg', '.jpeg', '.bmp', '.webp', '.gif'}
        self._images = sorted([os.path.join(path, f) for f in os.listdir(path)
                                if os.path.splitext(f)[1].lower() in exts])
        self._idx = 0
        self.data.cmd = path
        if self._images:
            self._show_image()
            self._slide_timer.start(self._interval * 1000)
        self._save_cmd()

    def _save_cmd(self):
        if hasattr(self.data, '_save_cb'):
            self.data._save_cb()

    def _show_image(self):
        if not self._images:
            return
        path = self._images[self._idx]
        pm = QPixmap(path)
        if not pm.isNull():
            self._pixmap = pm
            lbl_size = self._img_label.size()
            scaled = pm.scaled(lbl_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self._img_label.setPixmap(scaled)
        self._counter.setText(f"{self._idx + 1} / {len(self._images)}")

    def _next(self):
        if self._images:
            self._idx = (self._idx + 1) % len(self._images)
            self._show_image()

    def _prev(self):
        if self._images:
            self._idx = (self._idx - 1) % len(self._images)
            self._show_image()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self._pixmap and not self._pixmap.isNull():
            scaled = self._pixmap.scaled(self._img_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self._img_label.setPixmap(scaled)
        self._position_overlays()

    def _position_overlays(self):
        w, h = self.width(), self.height()
        self._browse_btn.move(w - 34, 6)
        cy = h // 2 - 16
        self._prev_btn.move(8, cy)
        self._next_btn.move(w - 40, cy)
        self._counter.adjustSize()
        self._counter.move((w - self._counter.width()) // 2, h - 24)

    def refresh_theme(self):
        saved_images = self._images
        saved_idx = self._idx
        saved_pixmap = self._pixmap
        saved_interval = self._interval
        super().refresh_theme()
        self._slide_timer = QTimer(self); self._slide_timer.timeout.connect(self._next)
        self._images = saved_images
        self._idx = saved_idx
        self._pixmap = saved_pixmap
        self._interval = saved_interval
        if self._images:
            self._show_image()
            self._slide_timer.start(self._interval * 1000)


# ---------------------------------------------------------------------------
# System Info Widget
# ---------------------------------------------------------------------------
class SysInfoWidget(CompBase):
    def __init__(self, data, parent=None):
        super().__init__(data, parent)
        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self); lay.setContentsMargins(16, 12, 16, 12); lay.setSpacing(6)
        title = QLabel("💻 系统信息")
        title.setStyleSheet(f"color:{C['text']};font-size:14px;font-weight:bold;background:transparent;")
        lay.addWidget(title)
        import platform
        import socket
        info_items = []
        info_items.append(("主机名", socket.gethostname()))
        info_items.append(("用  户", os.environ.get("USER", "unknown")))
        info_items.append(("系  统", f"{platform.system()} {platform.release()}"))
        info_items.append(("发行版", platform.freedesktop_os_release().get("PRETTY_NAME", "N/A")
                           if hasattr(platform, 'freedesktop_os_release') else platform.platform()))
        info_items.append(("架  构", platform.machine()))
        info_items.append(("Python", platform.python_version()))
        try:
            info_items.append(("CPU", self._cpu_model()))
        except Exception:
            pass
        try:
            import psutil
            mem = psutil.virtual_memory()
            info_items.append(("内  存", f"{mem.total / (1024**3):.1f} GB"))
        except Exception:
            pass
        try:
            ips = self._get_ips()
            for name, ip in ips:
                info_items.append((name, ip))
        except Exception:
            pass
        try:
            info_items.append(("桌面环境", os.environ.get("XDG_CURRENT_DESKTOP", "N/A")))
            info_items.append(("显示协议", os.environ.get("XDG_SESSION_TYPE", "N/A")))
        except Exception:
            pass
        try:
            uptime = self._uptime()
            if uptime:
                info_items.append(("运行时间", uptime))
        except Exception:
            pass

        for label, value in info_items:
            row = QHBoxLayout(); row.setSpacing(8)
            lbl = QLabel(label)
            lbl.setStyleSheet(f"color:{C['subtext0']};font-size:11px;background:transparent;min-width:60px;")
            val = QLabel(str(value))
            val.setStyleSheet(f"color:{C['text']};font-size:11px;background:transparent;")
            val.setTextInteractionFlags(Qt.TextSelectableByMouse)
            row.addWidget(lbl); row.addWidget(val); row.addStretch()
            lay.addLayout(row)
        lay.addStretch()

    @staticmethod
    def _cpu_model():
        try:
            with open("/proc/cpuinfo") as f:
                for line in f:
                    if "model name" in line:
                        return line.split(":")[1].strip()
        except Exception:
            pass
        import platform
        return platform.processor() or "N/A"

    @staticmethod
    def _get_ips():
        result = []
        try:
            import psutil
            for name, addrs in psutil.net_if_addrs().items():
                if name == "lo":
                    continue
                for addr in addrs:
                    if addr.family == 2:
                        result.append((name, addr.address))
        except Exception:
            import socket
            result.append(("IP", socket.gethostbyname(socket.gethostname())))
        return result

    @staticmethod
    def _uptime():
        try:
            with open("/proc/uptime") as f:
                secs = float(f.read().split()[0])
            days = int(secs // 86400)
            hours = int((secs % 86400) // 3600)
            mins = int((secs % 3600) // 60)
            parts = []
            if days:
                parts.append(f"{days}天")
            parts.append(f"{hours}时{mins}分")
            return " ".join(parts)
        except Exception:
            return None


# ---------------------------------------------------------------------------
# Bookmark Manager Widget
# ---------------------------------------------------------------------------
class BookmarkWidget(CompBase):
    def __init__(self, data, parent=None):
        super().__init__(data, parent)
        self._bookmarks: list[dict] = []
        self._load()
        self._build_ui()

    def _load(self):
        try:
            if self.data.cmd:
                self._bookmarks = json.loads(self.data.cmd)
        except Exception:
            self._bookmarks = []

    def _save(self):
        self.data.cmd = json.dumps(self._bookmarks, ensure_ascii=False)

    def _build_ui(self):
        lay = QVBoxLayout(self); lay.setContentsMargins(12, 10, 12, 10); lay.setSpacing(6)
        hdr = QHBoxLayout()
        title = QLabel("🔖 书签管理")
        title.setStyleSheet(f"color:{C['text']};font-size:14px;font-weight:bold;background:transparent;")
        hdr.addWidget(title); hdr.addStretch()
        add_btn = QPushButton("＋"); add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.setStyleSheet(f"background:{C['blue']};color:{C['crust']};border:none;border-radius:8px;"
                              f"font-size:14px;padding:4px 12px;font-weight:bold;")
        add_btn.clicked.connect(self._add_bookmark)
        hdr.addWidget(add_btn)
        lay.addLayout(hdr)
        sc = QScrollArea(); sc.setWidgetResizable(True)
        sc.setStyleSheet(f"QScrollArea{{background:transparent;border:none;}}QScrollArea > QWidget{{background:transparent;}}{_scrollbar_style(6)}")
        sc.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._list_w = QWidget()
        self._list_w.setStyleSheet("background:transparent;")
        self._list_lay = QVBoxLayout(self._list_w); self._list_lay.setContentsMargins(0, 0, 0, 0)
        self._list_lay.setSpacing(4); self._list_lay.addStretch()
        sc.setWidget(self._list_w)
        lay.addWidget(sc)
        self._rebuild()

    def _rebuild(self):
        while self._list_lay.count() > 1:
            item = self._list_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for i, bm in enumerate(self._bookmarks):
            row = QFrame()
            row.setStyleSheet(f"QFrame{{background:{_bg('surface0')};border-radius:6px;}}"
                              f"QFrame:hover{{background:{_bg('surface1')};}}")
            rl = QHBoxLayout(row); rl.setContentsMargins(8, 4, 4, 4); rl.setSpacing(6)
            icon = QLabel(bm.get("icon", "🌐"))
            icon.setStyleSheet(f"font-size:16px;background:transparent;")
            rl.addWidget(icon)
            name = QLabel(bm.get("name", ""))
            name.setStyleSheet(f"color:{C['text']};font-size:11px;background:transparent;")
            name.setCursor(Qt.PointingHandCursor)
            name.mousePressEvent = lambda e, url=bm.get("url", ""): self._open(url)
            rl.addWidget(name); rl.addStretch()
            del_btn = QPushButton("✕"); del_btn.setFixedSize(20, 20); del_btn.setCursor(Qt.PointingHandCursor)
            del_btn.setStyleSheet(f"background:transparent;color:{C['red']};border:none;font-size:12px;")
            del_btn.clicked.connect(lambda _, idx=i: self._delete(idx))
            rl.addWidget(del_btn)
            self._list_lay.insertWidget(i, row)

    def _add_bookmark(self):
        ok, name = _input_dialog(self, "添加书签", "名称：")
        if not ok or not name:
            return
        ok, url = _input_dialog(self, "添加书签", "网址：", "https://")
        if not ok or not url:
            return
        self._bookmarks.append({"name": name, "url": url, "icon": "🌐"})
        self._save(); self._rebuild()

    def _delete(self, idx):
        if 0 <= idx < len(self._bookmarks):
            self._bookmarks.pop(idx)
            self._save(); self._rebuild()

    def _open(self, url):
        if url:
            try:
                subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Calculator Widget
# ---------------------------------------------------------------------------
class CalcWidget(CompBase):
    def __init__(self, data, parent=None):
        super().__init__(data, parent)
        self._expr = ""
        self._result = ""
        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self); lay.setContentsMargins(12, 10, 12, 10); lay.setSpacing(6)
        self._display = QLabel("0")
        self._display.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._display.setStyleSheet(f"color:{C['text']};font-size:28px;font-weight:bold;"
                                    f"font-family:'JetBrains Mono','Courier New',monospace;"
                                    f"background:{_bg('surface0')};border-radius:8px;padding:12px 16px;"
                                    f"min-height:40px;")
        lay.addWidget(self._display)
        self._expr_lbl = QLabel("")
        self._expr_lbl.setAlignment(Qt.AlignRight)
        self._expr_lbl.setStyleSheet(f"color:{C['subtext0']};font-size:11px;background:transparent;padding:0 16px;")
        lay.addWidget(self._expr_lbl)
        from PyQt5.QtWidgets import QGridLayout
        grid = QGridLayout(); grid.setSpacing(6)
        buttons = [
            ("C", 0, 0, C['red']), ("(", 0, 1, C['surface1']), (")", 0, 2, C['surface1']), ("÷", 0, 3, C['peach']),
            ("7", 1, 0, ""), ("8", 1, 1, ""), ("9", 1, 2, ""), ("×", 1, 3, C['peach']),
            ("4", 2, 0, ""), ("5", 2, 1, ""), ("6", 2, 2, ""), ("−", 2, 3, C['peach']),
            ("1", 3, 0, ""), ("2", 3, 1, ""), ("3", 3, 2, ""), ("+", 3, 3, C['peach']),
            ("±", 4, 0, C['surface1']), ("0", 4, 1, ""), (".", 4, 2, ""), ("=", 4, 3, C['blue']),
        ]
        for text, r, c, color in buttons:
            b = QPushButton(text); b.setFixedHeight(40); b.setCursor(Qt.PointingHandCursor)
            bg = color or C['surface0']
            fg = C['crust'] if color in (C['blue'], C['red'], C['peach']) else C['text']
            b.setStyleSheet(f"""QPushButton {{background:{bg};color:{fg};border:none;
                border-radius:8px;font-size:16px;font-weight:bold;}}
                QPushButton:hover {{background:{C['surface2'] if not color else color};opacity:0.8;}}""")
            b.clicked.connect(lambda _, t=text: self._on_btn(t))
            grid.addWidget(b, r, c)
        lay.addLayout(grid)

    def _on_btn(self, text):
        if text == "C":
            self._expr = ""; self._result = ""
            self._display.setText("0"); self._expr_lbl.setText("")
        elif text == "=":
            self._calc()
        elif text == "±":
            if self._expr and self._expr[0] == '-':
                self._expr = self._expr[1:]
            elif self._expr:
                self._expr = '-' + self._expr
            self._expr_lbl.setText(self._expr)
        else:
            op_map = {"÷": "/", "×": "*", "−": "-"}
            self._expr += op_map.get(text, text)
            self._expr_lbl.setText(self._expr)

    def _calc(self):
        try:
            safe_expr = self._expr.replace("^", "**")
            for ch in safe_expr:
                if ch not in "0123456789.+-*/() ":
                    self._display.setText("错误"); return
            result = eval(safe_expr)
            self._result = str(result)
            if '.' in self._result:
                self._result = self._result.rstrip('0').rstrip('.')
            self._display.setText(self._result)
            self._expr_lbl.setText(f"{self._expr} =")
            self._expr = self._result
        except Exception:
            self._display.setText("错误")

    def refresh_theme(self):
        saved_expr = self._expr
        saved_result = self._result
        super().refresh_theme()
        self._expr = saved_expr
        self._result = saved_result
        self._expr_lbl.setText(saved_expr)
        if saved_result:
            self._display.setText(saved_result)


# ---------------------------------------------------------------------------
# Trash / Recycle Bin Widget
# ---------------------------------------------------------------------------
class TrashWidget(CompBase):
    def __init__(self, data, parent=None):
        super().__init__(data, parent)
        self._trash_dir = os.path.expanduser("~/.local/share/Trash")
        self._count = 0
        self._size = 0
        self._build_ui()
        self._timer = QTimer(self); self._timer.timeout.connect(self._refresh); self._timer.start(5000)
        QTimer.singleShot(100, self._refresh)

    def _build_ui(self):
        lay = QVBoxLayout(self); lay.setContentsMargins(16, 12, 16, 12); lay.setSpacing(6)
        top = QHBoxLayout()
        self._icon_lbl = QLabel("🗑️")
        self._icon_lbl.setStyleSheet("font-size:32px;background:transparent;")
        top.addWidget(self._icon_lbl)
        info = QVBoxLayout(); info.setSpacing(2)
        self._count_lbl = QLabel("0 个文件")
        self._count_lbl.setStyleSheet(f"color:{C['text']};font-size:14px;font-weight:bold;background:transparent;")
        self._size_lbl = QLabel("0 B")
        self._size_lbl.setStyleSheet(f"color:{C['subtext0']};font-size:11px;background:transparent;")
        info.addWidget(self._count_lbl); info.addWidget(self._size_lbl)
        top.addLayout(info); top.addStretch()
        lay.addLayout(top)
        btns = QHBoxLayout(); btns.addStretch()
        open_btn = QPushButton("打开回收站"); open_btn.setCursor(Qt.PointingHandCursor)
        open_btn.setStyleSheet(f"background:{_bg('surface1')};color:{C['text']};border:none;"
                               f"border-radius:8px;padding:6px 16px;font-size:13px;")
        open_btn.clicked.connect(self._open_trash)
        btns.addWidget(open_btn)
        empty_btn = QPushButton("清空"); empty_btn.setCursor(Qt.PointingHandCursor)
        empty_btn.setStyleSheet(f"background:{C['red']};color:{C['crust']};border:none;"
                                f"border-radius:8px;padding:6px 16px;font-size:13px;font-weight:bold;")
        empty_btn.clicked.connect(self._empty_trash)
        btns.addWidget(empty_btn)
        btns.addStretch()
        lay.addLayout(btns); lay.addStretch()

    def _refresh(self):
        files_dir = os.path.join(self._trash_dir, "files")
        if not os.path.isdir(files_dir):
            self._count = 0; self._size = 0
        else:
            items = os.listdir(files_dir)
            self._count = len(items)
            total = 0
            for item in items:
                p = os.path.join(files_dir, item)
                try:
                    if os.path.isfile(p):
                        total += os.path.getsize(p)
                    elif os.path.isdir(p):
                        for root, dirs, fs in os.walk(p):
                            for f in fs:
                                try:
                                    total += os.path.getsize(os.path.join(root, f))
                                except OSError:
                                    pass
                except OSError:
                    pass
            self._size = total
        self._count_lbl.setText(f"{self._count} 个文件")
        self._size_lbl.setText(self._fmt_size(self._size))

    @staticmethod
    def _fmt_size(b):
        for unit in ['B', 'KB', 'MB', 'GB']:
            if b < 1024:
                return f"{b:.1f} {unit}"
            b /= 1024
        return f"{b:.1f} TB"

    def _open_trash(self):
        try:
            subprocess.Popen(["xdg-open", f"trash:///"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

    def _empty_trash(self):
        if not _confirm_dialog(self, "清空回收站", f"确定要永久删除 {self._count} 个文件吗？\n此操作不可撤销！"):
            return
        try:
            subprocess.run(["gio", "trash", "--empty"], timeout=30, capture_output=True)
        except Exception:
            files_dir = os.path.join(self._trash_dir, "files")
            info_dir = os.path.join(self._trash_dir, "info")
            for d in [files_dir, info_dir]:
                if os.path.isdir(d):
                    import shutil
                    for item in os.listdir(d):
                        p = os.path.join(d, item)
                        try:
                            if os.path.isdir(p):
                                shutil.rmtree(p)
                            else:
                                os.remove(p)
                        except Exception:
                            pass
            self._refresh()

    def refresh_theme(self):
        super().refresh_theme()
        self._timer = QTimer(self); self._timer.timeout.connect(self._refresh); self._timer.start(5000)
        QTimer.singleShot(100, self._refresh)


# ---------------------------------------------------------------------------
# RSS Reader Widget
# ---------------------------------------------------------------------------
class RSSWidget(CompBase):
    def __init__(self, data, parent=None):
        super().__init__(data, parent)
        self._feeds: list[dict] = []
        self._items: list[dict] = []
        self._load_feeds()
        self._build_ui()
        QTimer.singleShot(500, self._fetch_all)

    def _load_feeds(self):
        try:
            if self.data.cmd:
                self._feeds = json.loads(self.data.cmd)
        except Exception:
            self._feeds = [{"name": "Hacker News", "url": "https://hnrss.org/frontpage?count=10"}]

    def _save_feeds(self):
        self.data.cmd = json.dumps(self._feeds, ensure_ascii=False)

    def _build_ui(self):
        lay = QVBoxLayout(self); lay.setContentsMargins(12, 10, 12, 10); lay.setSpacing(6)
        hdr = QHBoxLayout()
        title = QLabel("📰 RSS 阅读器")
        title.setStyleSheet(f"color:{C['text']};font-size:14px;font-weight:bold;background:transparent;")
        hdr.addWidget(title); hdr.addStretch()
        add_btn = QPushButton("＋"); add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.setStyleSheet(f"background:{C['blue']};color:{C['crust']};border:none;border-radius:8px;"
                              f"font-size:14px;padding:4px 12px;font-weight:bold;")
        add_btn.clicked.connect(self._add_feed)
        hdr.addWidget(add_btn)
        refresh_btn = QPushButton("↻"); refresh_btn.setCursor(Qt.PointingHandCursor)
        refresh_btn.setStyleSheet(f"background:{_bg('surface1')};color:{C['text']};border:none;border-radius:8px;"
                                  f"font-size:14px;padding:4px 12px;")
        refresh_btn.clicked.connect(self._fetch_all)
        hdr.addWidget(refresh_btn)
        lay.addLayout(hdr)
        self._status = QLabel("")
        self._status.setStyleSheet(f"color:{C['subtext0']};font-size:10px;background:transparent;")
        lay.addWidget(self._status)
        sc = QScrollArea(); sc.setWidgetResizable(True)
        sc.setStyleSheet(f"QScrollArea{{background:transparent;border:none;}}QScrollArea > QWidget{{background:transparent;}}{_scrollbar_style(6)}")
        sc.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._list_w = QWidget()
        self._list_w.setStyleSheet("background:transparent;")
        self._list_lay = QVBoxLayout(self._list_w); self._list_lay.setContentsMargins(0, 0, 0, 0)
        self._list_lay.setSpacing(4); self._list_lay.addStretch()
        sc.setWidget(self._list_w)
        lay.addWidget(sc)

    def _add_feed(self):
        ok, url = _input_dialog(self, "添加 RSS 源", "RSS URL：", "https://")
        if not ok or not url:
            return
        ok2, name = _input_dialog(self, "添加 RSS 源", "名称（可选）：")
        self._feeds.append({"name": name or (url.split("/")[2] if len(url.split("/")) > 2 else "Feed"), "url": url})
        self._save_feeds()
        self._fetch_all()

    def _fetch_all(self):
        self._status.setText("加载中...")
        self._items = []
        t = threading.Thread(target=self._fetch_worker, daemon=True)
        t.start()

    def _fetch_worker(self):
        items = []
        for feed in self._feeds:
            try:
                req = urllib.request.Request(feed["url"], headers={"User-Agent": "FastPanel/1.0"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = resp.read().decode("utf-8", errors="replace")
                items.extend(self._parse_rss(data, feed.get("name", "")))
            except Exception:
                pass
        self._items = items[:30]
        QTimer.singleShot(0, self._rebuild)

    @staticmethod
    def _parse_rss(xml_text, source=""):
        items = []
        import re
        for m in re.finditer(r'<item>(.*?)</item>', xml_text, re.DOTALL):
            block = m.group(1)
            title_m = re.search(r'<title>(.*?)</title>', block, re.DOTALL)
            link_m = re.search(r'<link>(.*?)</link>', block, re.DOTALL)
            if title_m:
                title = title_m.group(1).strip()
                title = re.sub(r'<!\[CDATA\[(.*?)\]\]>', r'\1', title)
                link = link_m.group(1).strip() if link_m else ""
                link = re.sub(r'<!\[CDATA\[(.*?)\]\]>', r'\1', link)
                items.append({"title": title, "link": link, "source": source})
        return items

    def _rebuild(self):
        while self._list_lay.count() > 1:
            item = self._list_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._status.setText(f"{len(self._items)} 条 · {len(self._feeds)} 个源")
        for i, item in enumerate(self._items):
            row = QFrame()
            row.setStyleSheet(f"QFrame{{background:{_bg('surface0')};border-radius:6px;}}"
                              f"QFrame:hover{{background:{_bg('surface1')};}}")
            rl = QVBoxLayout(row); rl.setContentsMargins(8, 6, 8, 6); rl.setSpacing(2)
            title = QLabel(item["title"])
            title.setWordWrap(True); title.setCursor(Qt.PointingHandCursor)
            title.setStyleSheet(f"color:{C['text']};font-size:11px;background:transparent;")
            title.mousePressEvent = lambda e, url=item.get("link", ""): self._open(url)
            rl.addWidget(title)
            if item.get("source"):
                src = QLabel(item["source"])
                src.setStyleSheet(f"color:{C['overlay0']};font-size:9px;background:transparent;")
                rl.addWidget(src)
            self._list_lay.insertWidget(i, row)

    def _open(self, url):
        if url:
            try:
                subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass

    def refresh_theme(self):
        saved_items = list(self._items)
        super().refresh_theme()
        self._items = saved_items
        if self._items:
            self._rebuild()
        else:
            QTimer.singleShot(500, self._fetch_all)


def create_widget(data: ComponentData, parent=None) -> CompBase:
    if data.comp_type == TYPE_CMD_WINDOW:
        return CmdWindowWidget(data, parent)
    if data.comp_type == TYPE_SHORTCUT:
        return ShortcutWidget(data, parent)
    if data.comp_type == TYPE_CALENDAR:
        return CalendarWidget(data, parent)
    if data.comp_type == TYPE_WEATHER:
        return WeatherWidget(data, parent)
    if data.comp_type == TYPE_DOCK:
        return DockWidget(data, parent)
    if data.comp_type == TYPE_TODO:
        return TodoWidget(data, parent)
    if data.comp_type == TYPE_CLOCK:
        return ClockWidget(data, parent)
    if data.comp_type == TYPE_MONITOR:
        return MonitorWidget(data, parent)
    if data.comp_type == TYPE_LAUNCHER:
        return LauncherWidget(data, parent)
    if data.comp_type == TYPE_NOTE:
        return NoteWidget(data, parent)
    if data.comp_type == TYPE_QUICKACTION:
        return QuickActionWidget(data, parent)
    if data.comp_type == TYPE_MEDIA:
        return MediaWidget(data, parent)
    if data.comp_type == TYPE_CLIPBOARD:
        return ClipboardWidget(data, parent)
    if data.comp_type == TYPE_TIMER:
        return TimerWidget(data, parent)
    if data.comp_type == TYPE_GALLERY:
        return GalleryWidget(data, parent)
    if data.comp_type == TYPE_SYSINFO:
        return SysInfoWidget(data, parent)
    if data.comp_type == TYPE_BOOKMARK:
        return BookmarkWidget(data, parent)
    if data.comp_type == TYPE_CALC:
        return CalcWidget(data, parent)
    if data.comp_type == TYPE_TRASH:
        return TrashWidget(data, parent)
    if data.comp_type == TYPE_RSS:
        return RSSWidget(data, parent)
    return CmdWidget(data, parent)


# ---------------------------------------------------------------------------
# Grid Panel
# ---------------------------------------------------------------------------
class _SelectionOverlay(QWidget):
    """Transparent overlay drawn above components for selection / group frames."""
    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.sel_rect = QRect()
        self.selecting = False
        self.bounding = QRect()
        self.group_bounds = []

    def paintEvent(self, e):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)

        for gr in self.group_bounds:
            p.setBrush(Qt.NoBrush)
            pen = QColor(C['peach']); pen.setAlpha(120)
            p.setPen(pen)
            p.drawRoundedRect(gr.adjusted(-4, -4, 4, 4), 14, 14)

        if not self.bounding.isNull():
            sc = QColor(C['blue']); sc.setAlpha(25)
            p.setBrush(sc)
            pen = QColor(C['blue']); pen.setAlpha(160)
            p.setPen(pen)
            p.drawRoundedRect(self.bounding.adjusted(-4, -4, 4, 4), 14, 14)

        if self.selecting and not self.sel_rect.isNull():
            sc = QColor(C['blue']); sc.setAlpha(30)
            p.setBrush(sc)
            p.setPen(QColor(C['blue']))
            p.drawRect(self.sel_rect)
        p.end()


class GridPanel(QWidget):
    data_changed = pyqtSignal()
    desktop_ctx_menu_requested = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._components: list[CompBase] = []
        self._selected: list[CompBase] = []
        self._groups: dict = {}
        self._selecting = False
        self._sel_origin = QPoint()
        self._multi_dragging = False
        self._multi_drag_origin = QPoint()
        self._multi_drag_offsets = []
        self._bg_pixmap = None
        self._bg_opacity = 30
        self._bg_slideshow_dir = ""
        self._bg_slideshow_interval = 300
        self._bg_slideshow_files = []
        self._bg_slideshow_idx = 0
        self._bg_slideshow_timer = QTimer(self)
        self._bg_slideshow_timer.timeout.connect(self._next_slideshow)
        self._bg_gradient = ""
        self._bg_mode = _settings.get("bg_mode", "tile")
        self._bg_per_monitor = {}
        per_mon = _settings.get("bg_per_monitor", {})
        for name, path in per_mon.items():
            if path and os.path.isfile(path):
                self._bg_per_monitor[name] = QPixmap(path)
        self._show_grid = _settings.get("show_grid", True)
        self._safe_margin_top = 0
        self._safe_margin_bottom = 0
        self.setAutoFillBackground(True)
        self.setMouseTracking(True)
        pal = self.palette(); pal.setColor(pal.Window, QColor(C["crust"])); self.setPalette(pal)
        self._overlay = _SelectionOverlay(self)
        self._overlay.show()
        bg = _settings.get("bg_image", "")
        if bg and os.path.isfile(bg):
            self._bg_pixmap = QPixmap(bg)
        self._bg_opacity = _settings.get("bg_opacity", 30)
        grad = _settings.get("bg_gradient", "")
        if grad:
            self._bg_gradient = grad
        ss_dir = _settings.get("bg_slideshow_dir", "")
        if ss_dir:
            self.set_bg_slideshow(ss_dir, _settings.get("bg_slideshow_interval", 300))

    def set_bg_image(self, path, opacity=30):
        if path and os.path.isfile(path):
            self._bg_pixmap = QPixmap(path)
        else:
            self._bg_pixmap = None
        self._bg_opacity = opacity

    def set_bg_gradient(self, gradient_str):
        self._bg_gradient = gradient_str
        self.update()

    def set_bg_mode(self, mode):
        self._bg_mode = mode
        self.update()

    def set_per_monitor_bg(self, mapping):
        self._bg_per_monitor = {}
        for name, path in mapping.items():
            if path and os.path.isfile(path):
                self._bg_per_monitor[name] = QPixmap(path)
        self.update()

    def set_bg_slideshow(self, directory, interval=300):
        self._bg_slideshow_dir = directory
        self._bg_slideshow_interval = max(10, interval)
        self._bg_slideshow_timer.stop()
        self._bg_slideshow_files = []
        self._bg_slideshow_idx = 0
        if directory and os.path.isdir(directory):
            exts = {'.png', '.jpg', '.jpeg', '.bmp', '.webp'}
            self._bg_slideshow_files = sorted(
                [os.path.join(directory, f) for f in os.listdir(directory)
                 if os.path.splitext(f)[1].lower() in exts])
            if self._bg_slideshow_files:
                self._bg_pixmap = QPixmap(self._bg_slideshow_files[0])
                self._bg_slideshow_timer.start(interval * 1000)
                self.update()

    def _next_slideshow(self):
        if not self._bg_slideshow_files:
            return
        self._bg_slideshow_idx = (self._bg_slideshow_idx + 1) % len(self._bg_slideshow_files)
        path = self._bg_slideshow_files[self._bg_slideshow_idx]
        if os.path.isfile(path):
            self._bg_pixmap = QPixmap(path)
            self.update()

    def set_safe_margins(self, top, bottom):
        self._safe_margin_top = ((top + GRID_SIZE - 1) // GRID_SIZE) * GRID_SIZE
        self._safe_margin_bottom = ((bottom + GRID_SIZE - 1) // GRID_SIZE) * GRID_SIZE

    def set_show_grid(self, show):
        self._show_grid = show

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._overlay.setGeometry(0, 0, self.width(), self.height())
        self._overlay.raise_()

    def paintEvent(self, e):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(e.rect(), QColor(C["crust"]))
        if self._bg_gradient:
            from PyQt5.QtGui import QLinearGradient
            parts = self._bg_gradient.split(",")
            if len(parts) >= 2:
                grad = QLinearGradient(0, 0, self.width(), self.height())
                for i, color_str in enumerate(parts):
                    stop = i / max(len(parts) - 1, 1)
                    grad.setColorAt(stop, QColor(color_str.strip()))
                p.setOpacity(self._bg_opacity / 100.0)
                p.fillRect(e.rect(), grad)
                p.setOpacity(1.0)
        if self._bg_pixmap and not self._bg_pixmap.isNull():
            p.setOpacity(self._bg_opacity / 100.0)
            if self._bg_mode == "clone":
                screens = QApplication.screens()
                win = self.window()
                win_pos = win.pos() if win else QPoint(0, 0)
                for s in screens:
                    sg = s.geometry()
                    local_rect = QRect(sg.x() - win_pos.x(), sg.y() - win_pos.y(), sg.width(), sg.height())
                    scaled = self._bg_pixmap.scaled(local_rect.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                    ox = local_rect.x() + (local_rect.width() - scaled.width()) // 2
                    oy = local_rect.y() + (local_rect.height() - scaled.height()) // 2
                    p.setClipRect(local_rect)
                    p.drawPixmap(ox, oy, scaled)
                p.setClipping(False)
            elif self._bg_mode == "per_monitor" and self._bg_per_monitor:
                screens = QApplication.screens()
                win = self.window()
                win_pos = win.pos() if win else QPoint(0, 0)
                for s in screens:
                    sg = s.geometry()
                    local_rect = QRect(sg.x() - win_pos.x(), sg.y() - win_pos.y(), sg.width(), sg.height())
                    pm = self._bg_per_monitor.get(s.name())
                    if pm is None:
                        pm = self._bg_pixmap
                    if pm and not pm.isNull():
                        scaled = pm.scaled(local_rect.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                        ox = local_rect.x() + (local_rect.width() - scaled.width()) // 2
                        oy = local_rect.y() + (local_rect.height() - scaled.height()) // 2
                        p.setClipRect(local_rect)
                        p.drawPixmap(ox, oy, scaled)
                p.setClipping(False)
            else:
                scaled = self._bg_pixmap.scaled(self.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                x = (self.width() - scaled.width()) // 2
                y = (self.height() - scaled.height()) // 2
                p.drawPixmap(x, y, scaled)
            p.setOpacity(1.0)
        safe_top = self._safe_margin_top
        safe_bot = self._safe_margin_bottom
        if self._show_grid:
            dc = QColor(C["overlay0"]); dc.setAlpha(80); p.setPen(Qt.NoPen); p.setBrush(dc)
            grid_top = ((safe_top + GRID_SIZE - 1) // GRID_SIZE) * GRID_SIZE
            grid_bottom = ((self.height() - safe_bot) // GRID_SIZE) * GRID_SIZE
            r = e.rect(); x0 = (r.left()//GRID_SIZE)*GRID_SIZE
            for x in range(x0, r.right()+1, GRID_SIZE):
                for y in range(grid_top, min(r.bottom()+1, grid_bottom + 1), GRID_SIZE):
                    p.drawEllipse(x-1, y-1, 2, 2)
        if safe_top > 0 or safe_bot > 0:
            boundary_color = QColor(C['surface1']); boundary_color.setAlpha(60)
            pen = QPen(boundary_color, 1, Qt.DashLine)
            p.setPen(pen)
            if safe_top > 0:
                p.drawLine(0, safe_top, self.width(), safe_top)
            if safe_bot > 0:
                p.drawLine(0, self.height() - safe_bot, self.width(), self.height() - safe_bot)
        p.end()

    def _sel_bounding(self):
        if not self._selected:
            return QRect()
        rects = [w.geometry() for w in self._selected]
        r = rects[0]
        for rr in rects[1:]:
            r = r.united(rr)
        return r

    def _group_bounding(self, gid):
        members = [w for w in self._components if getattr(w.data, '_group_id', None) == gid]
        if not members:
            return QRect()
        r = members[0].geometry()
        for w in members[1:]:
            r = r.united(w.geometry())
        return r

    def _update_overlay(self):
        if self._selecting:
            self._overlay.sel_rect = QRect(self._sel_origin, self._sel_origin).normalized()
            self._overlay.selecting = True
        else:
            self._overlay.selecting = False
            self._overlay.sel_rect = QRect()
        self._overlay.bounding = self._sel_bounding()
        seen = set()
        gbs = []
        for gid, _ in self._groups.items():
            if gid not in seen:
                seen.add(gid)
                gb = self._group_bounding(gid)
                if not gb.isNull():
                    gbs.append(gb)
        self._overlay.group_bounds = gbs
        self._overlay.raise_()
        self._overlay.update()

    def contextMenuEvent(self, e):
        child = self.childAt(e.pos())
        comp = self._find_comp(child) if child and child is not self._overlay else None
        if comp is None and _DESKTOP_MODE:
            self.desktop_ctx_menu_requested.emit(e.globalPos())
            e.accept()
            return
        super().contextMenuEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            child = self.childAt(e.pos())
            if child is None or child is self._overlay:
                if self._selected:
                    self._clear_selection()
                self._selecting = True
                self._sel_origin = e.pos()
                self._overlay.selecting = True
                self._overlay.sel_rect = QRect(e.pos(), e.pos())
                self._overlay.raise_()
                self._overlay.update()

    def mouseMoveEvent(self, e):
        if self._selecting:
            self._overlay.sel_rect = QRect(self._sel_origin, e.pos()).normalized()
            self._overlay.update()

    def mouseReleaseEvent(self, e):
        if self._selecting:
            self._selecting = False
            sr = self._overlay.sel_rect
            self._selected = [w for w in self._components if sr.intersects(w.geometry())]
            self._update_overlay()

    def _find_comp(self, widget):
        w = widget
        while w and w is not self:
            if isinstance(w, CompBase):
                return w
            w = w.parent()
        return None

    def _clear_selection(self):
        self._selected.clear()
        self._update_overlay()

    def _group_selected(self):
        if len(self._selected) < 2:
            return
        gid = str(uuid.uuid4())
        self._groups[gid] = [w.data.id for w in self._selected]
        for w in self._selected:
            w.data._group_id = gid
            w.setProperty("locked", True)
        self._clear_selection()
        self._update_overlay()
        self.data_changed.emit()

    def _ungroup(self, gid):
        if gid in self._groups:
            for w in self._components:
                if getattr(w.data, '_group_id', None) == gid:
                    w.data._group_id = None
                    w.setProperty("locked", False)
            del self._groups[gid]
        self._clear_selection()
        self._update_overlay()
        self.data_changed.emit()

    def _get_group_of(self, w):
        return getattr(w.data, '_group_id', None)

    def recalc_size(self, vw, vh):
        if _DESKTOP_MODE:
            self.setFixedSize(vw, vh)
            return
        mb = vh
        for c in self._components:
            b = c.data.y + c.data.h + PANEL_PADDING
            if b > mb: mb = b
        self.setFixedSize(vw, max(vh, mb))

    def add_component(self, data):
        w = create_widget(data, self)
        w.delete_requested.connect(self._remove)
        w.edit_requested.connect(self._edit)
        w.copy_requested.connect(self._copy)
        w.geometry_changed.connect(self._child_moved)
        w.show(); self._components.append(w); self.data_changed.emit()
        return w

    def _show_toast(self, text, duration=2500):
        toast = QLabel(text, self)
        toast.setAlignment(Qt.AlignCenter)
        toast.setStyleSheet(f"""
            QLabel {{
                background: {C['red']}; color: {C['crust']};
                font-size: 16px; font-weight: bold;
                padding: 16px 32px; border-radius: 10px;
            }}
        """)
        toast.adjustSize()
        cursor_pos = self.mapFromGlobal(QApplication.desktop().cursor().pos())
        screen = QApplication.screenAt(QApplication.desktop().cursor().pos())
        if screen:
            sg = screen.geometry()
            local_center_x = self.mapFromGlobal(QPoint(sg.center().x(), sg.y())).x()
            local_top_y = self.mapFromGlobal(QPoint(0, sg.y())).y()
            toast.move(local_center_x - toast.width() // 2, local_top_y + self._safe_margin_top + 40)
        else:
            toast.move((self.width() - toast.width()) // 2, self._safe_margin_top + 40)
        toast.show()
        toast.raise_()
        shadow = QGraphicsDropShadowEffect(toast)
        shadow.setBlurRadius(20); shadow.setOffset(0, 4); shadow.setColor(QColor(0, 0, 0, 120))
        toast.setGraphicsEffect(shadow)
        QTimer.singleShot(duration, toast.deleteLater)

    def _child_moved(self):
        mover = self.sender()
        if mover:
            mover_origin = getattr(mover, '_drag_origin', None)
            snapshot = [(w, w.data.x, w.data.y) for w in self._components if w is not mover]
            self._resolve_overlaps(mover)
            if self._layout_overflow():
                for w, ox, oy in snapshot:
                    w.move(ox, oy)
                    w.data.x, w.data.y = ox, oy
                if mover_origin:
                    mover.move(mover_origin)
                    mover.data.x, mover.data.y = mover_origin.x(), mover_origin.y()
                self._show_toast("⚠ 布局空间不足，组件已回到原位")
        par = self.parent()
        if par:
            vp = par.viewport() if hasattr(par, 'viewport') else par
            self.recalc_size(vp.width(), vp.height())
        self._update_overlay()
        self.data_changed.emit()

    def _layout_overflow(self):
        if not _DESKTOP_MODE:
            return False
        safe_bot = self._safe_margin_bottom
        max_bottom = self.height() - safe_bot
        for w in self._components:
            if w.data.y + w.data.h > max_bottom:
                return True
            if w.data.x + w.data.w > self.width():
                return True
        return False

    def _resolve_overlaps(self, mover):
        mover_gid = getattr(mover.data, '_group_id', None)
        if mover_gid:
            mr = self._group_bounding(mover_gid)
            skip_ids = set(self._groups.get(mover_gid, []))
        else:
            mr = mover.geometry()
            skip_ids = {mover.data.id}
        for w in self._components:
            if w.data.id in skip_ids:
                continue
            w_gid = getattr(w.data, '_group_id', None)
            if w_gid and w_gid == mover_gid:
                continue
            wr = w.geometry()
            if mr.intersects(wr):
                ny = snap(mr.bottom() + GRID_SIZE)
                dy = ny - wr.y()
                if w_gid:
                    for gw in self._components:
                        if getattr(gw.data, '_group_id', None) == w_gid:
                            gw.move(gw.x(), gw.y() + dy)
                            gw.data.y = gw.y()
                    self._resolve_overlaps(w)
                else:
                    w.move(wr.x(), ny)
                    w.data.x, w.data.y = wr.x(), ny
                    self._resolve_overlaps(w)

    def _remove(self, w):
        if _confirm_dialog(self, "确认删除", f"确定删除组件「{w.data.name}」？"):
            self._components.remove(w)
            w.setParent(None)
            w.deleteLater()
            self.update()
            self.data_changed.emit()

    def _edit(self, w):
        dlg = EditDialog(w.data, self)
        if dlg.exec_() == QDialog.Accepted:
            new = dlg.get_data()
            need_rebuild = (
                w.data.comp_type != new.comp_type
                or w.data.sub_type != new.sub_type
                or w.data.show_output != new.show_output
                or count_params(w.data.cmd) != count_params(new.cmd)
                or w.data.param_hints != new.param_hints
                or w.data.param_defaults != new.param_defaults
            )
            if need_rebuild:
                geo = w.geometry()
                self._components.remove(w); w.deleteLater()
                nd = ComponentData(
                    name=new.name, comp_type=new.comp_type, sub_type=new.sub_type,
                    cmd=new.cmd, show_output=new.show_output,
                    icon=new.icon, path=new.path,
                    x=geo.x(), y=geo.y(), w=geo.width(), h=geo.height(), uid=w.data.id,
                    param_hints=new.param_hints, param_defaults=new.param_defaults,
                    pre_cmd=new.pre_cmd,
                )
                self.add_component(nd)
            else:
                w.data.name = new.name; w.data.cmd = new.cmd
                w.data.show_output = new.show_output
                w.data.sub_type = new.sub_type
                w.data.icon = new.icon; w.data.path = new.path
                w.data.param_hints = new.param_hints
                w.data.param_defaults = new.param_defaults
                w.data.pre_cmd = new.pre_cmd
                w.update_from_data()
            self.data_changed.emit()

    def _copy(self, w):
        copy_data = ComponentData(
            name=w.data.name, comp_type=w.data.comp_type, sub_type=w.data.sub_type,
            cmd=w.data.cmd, show_output=w.data.show_output,
            icon=w.data.icon, path=w.data.path,
            param_hints=list(w.data.param_hints),
            param_defaults=list(w.data.param_defaults),
            pre_cmd=w.data.pre_cmd,
        )
        dlg = EditDialog(copy_data, self)
        dlg.setWindowTitle("复制组件")
        if dlg.exec_() == QDialog.Accepted:
            nd = dlg.get_data()
            nd.x = w.data.x + GRID_SIZE * 2
            nd.y = w.data.y + GRID_SIZE * 2
            nd.w = w.data.w
            nd.h = w.data.h
            self.add_component(nd)
            self.data_changed.emit()

    def clear_all(self):
        for w in self._components: w.deleteLater()
        self._components.clear()

    @property
    def components(self):
        return list(self._components)


def _load_city_db():
    fp = os.path.join(_BASE_DIR, "cities.json")
    try:
        with open(fp, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

_CITY_DB = _load_city_db()

def _city_db_by_letter():
    groups = {}
    for c in _CITY_DB:
        py = c.get("pinyin", "")
        letter = py[0].upper() if py else "#"
        groups.setdefault(letter, []).append(c)
    return groups


class CitySelectDialog(QDialog):
    def __init__(self, current_code="", parent=None):
        super().__init__(parent)
        self.setWindowTitle("选择城市")
        self.setMinimumSize(520, 560)
        self.setStyleSheet(f"""
            QDialog {{ background: {C['base']}; }}
            QLabel {{ color: {C['text']}; background: transparent; }}
            QLineEdit {{ background: {C['surface0']}; color: {C['text']}; border: 1px solid {C['surface2']}; border-radius: 6px; padding: 6px 10px; font-size: 13px; }}
            QPushButton#letterBtn {{ background: {C['surface1']}; color: {C['text']}; border: none; border-radius: 4px; font-size: 12px; font-weight: bold; min-width: 28px; min-height: 28px; }}
            QPushButton#letterBtn:hover {{ background: {C['blue']}; color: {C['crust']}; }}
            QPushButton#cityBtn {{ background: {C['surface0']}; color: {C['text']}; border: 1px solid {C['surface1']}; border-radius: 6px; padding: 6px 12px; font-size: 12px; }}
            QPushButton#cityBtn:hover {{ background: {C['surface1']}; }}
            QPushButton#okBtn {{ background: {C['blue']}; color: {C['crust']}; border: none; border-radius: 8px; padding: 8px 24px; font-size: 13px; font-weight: bold; }}
            QPushButton#okBtn:hover {{ background: {C['lavender']}; }}
            QPushButton#cancelBtn {{ background: {C['surface1']}; color: {C['text']}; border: none; border-radius: 8px; padding: 8px 24px; font-size: 13px; }}
            QPushButton#cancelBtn:hover {{ background: {C['surface2']}; }}
        """)
        self._selected_code = current_code
        self._selected_name = ""
        for c in _CITY_DB:
            if c["code"] == current_code:
                self._selected_name = f"{c['province']}-{c['city']}-{c['name']}"
                break

        root = QVBoxLayout(self); root.setSpacing(10)
        self._search = QLineEdit()
        self._search.setPlaceholderText("搜索城市（名称或拼音）…")
        self._search.textChanged.connect(self._filter)
        root.addWidget(self._search)

        letter_bar = QHBoxLayout(); letter_bar.setSpacing(3)
        self._letter_anchors = {}
        groups = _city_db_by_letter()
        for ch in sorted(groups.keys()):
            if ch == "#": continue
            b = QPushButton(ch); b.setObjectName("letterBtn"); b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _, c=ch: self._scroll_to(c))
            letter_bar.addWidget(b)
        letter_bar.addStretch()
        root.addLayout(letter_bar)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet(f"QScrollArea {{ border: none; background: {C['base']}; }}")
        self._content = QWidget()
        self._content.setStyleSheet(f"background: {C['base']};")
        self._content_lay = QVBoxLayout(self._content)
        self._content_lay.setSpacing(6); self._content_lay.setContentsMargins(4, 4, 4, 4)
        self._scroll.setWidget(self._content)
        root.addWidget(self._scroll, 1)

        self._city_btns = {}
        self._build_list()

        btns = QHBoxLayout(); btns.addStretch()
        cb = QPushButton("取消"); cb.setObjectName("cancelBtn"); cb.setCursor(Qt.PointingHandCursor)
        cb.clicked.connect(self.reject); btns.addWidget(cb)
        ob = QPushButton("确定"); ob.setObjectName("okBtn"); ob.setCursor(Qt.PointingHandCursor)
        ob.clicked.connect(self.accept); btns.addWidget(ob)
        root.addLayout(btns)

    def _build_list(self, filter_text=""):
        while self._content_lay.count():
            item = self._content_lay.takeAt(0)
            w = item.widget()
            if w: w.deleteLater()
        self._letter_anchors.clear()
        self._city_btns.clear()
        ft = filter_text.strip().lower()
        groups = _city_db_by_letter()
        from PyQt5.QtWidgets import QGridLayout as _GL
        for ch in sorted(groups.keys()):
            if ch == "#": continue
            items = groups[ch]
            if ft:
                items = [c for c in items if ft in c["name"].lower()
                         or ft in c.get("pinyin", "").lower()
                         or ft in c.get("city", "").lower()
                         or ft in c.get("province", "").lower()]
            if not items:
                continue
            lbl = QLabel(ch)
            lbl.setStyleSheet(f"color:{C['blue']}; font-size:14px; font-weight:bold; margin-top:6px;")
            self._content_lay.addWidget(lbl)
            self._letter_anchors[ch] = lbl
            flow = QWidget()
            gl = _GL(flow); gl.setSpacing(6); gl.setContentsMargins(0, 0, 0, 0)
            col = 0; row = 0
            for c in items:
                display = c["name"]
                if c["city"] != c["name"]:
                    display = f"{c['name']}({c['city']})"
                b = QPushButton(display); b.setObjectName("cityBtn"); b.setCursor(Qt.PointingHandCursor)
                b.setToolTip(f"{c['province']} - {c['city']} - {c['name']}")
                if c["code"] == self._selected_code:
                    b.setStyleSheet(f"background:{C['blue']}; color:{C['crust']}; border:none; border-radius:6px; padding:6px 12px; font-size:12px; font-weight:bold;")
                b.clicked.connect(lambda _, ci=c, btn=b: self._pick(ci, btn))
                gl.addWidget(b, row, col)
                self._city_btns[c["code"]] = b
                col += 1
                if col >= 5:
                    col = 0; row += 1
            self._content_lay.addWidget(flow)
        self._content_lay.addStretch()

    def _pick(self, city_info, btn):
        self._selected_code = city_info["code"]
        self._selected_name = city_info["name"]
        for code, b in self._city_btns.items():
            if code == self._selected_code:
                b.setStyleSheet(f"background:{C['blue']}; color:{C['crust']}; border:none; border-radius:6px; padding:6px 12px; font-size:12px; font-weight:bold;")
            else:
                b.setStyleSheet("")

    def _scroll_to(self, ch):
        lbl = self._letter_anchors.get(ch)
        if lbl:
            self._scroll.ensureWidgetVisible(lbl, 0, 10)

    def _filter(self, text):
        self._build_list(text)

    def selected_city(self):
        return self._selected_name

    def selected_code(self):
        return self._selected_code


# ---------------------------------------------------------------------------
# Dialogs
# ---------------------------------------------------------------------------
def _build_comp_dialog(dialog, heading_text, ok_text, data=None):
    dialog.setStyleSheet(_dialog_style())
    lay = QVBoxLayout(dialog)
    lay.setContentsMargins(28, 24, 28, 24)
    lay.setSpacing(16)

    heading = QLabel(heading_text)
    heading.setObjectName("heading")
    lay.addWidget(heading)

    form = QFormLayout()
    form.setLabelAlignment(Qt.AlignRight)
    form.setSpacing(12)

    dialog.cat = QComboBox()
    for k, v in TYPE_LABELS.items():
        dialog.cat.addItem(v, k)
    form.addRow("类  别", dialog.cat)

    dialog.name_edit = QLineEdit(data.name if data else "")
    dialog.name_edit.setPlaceholderText("组件名称")
    form.addRow("名  称", dialog.name_edit)

    # --- CMD fields ---
    dialog.cmd_edit = QLineEdit(data.cmd if data else "")
    dialog.cmd_edit.setPlaceholderText("例如：curl ($) | grep ($)")
    form.addRow("命  令", dialog.cmd_edit)

    dialog._hint = QLabel('提示：使用 ($) 作为动态参数占位符')
    dialog._hint.setStyleSheet(f"color:{C['overlay0']}; font-size:11px;")
    form.addRow("", dialog._hint)

    dialog._param_container = QWidget()
    dialog._param_layout = QVBoxLayout(dialog._param_container)
    dialog._param_layout.setContentsMargins(0, 0, 0, 0)
    dialog._param_layout.setSpacing(6)
    dialog._param_hint_edits = []
    dialog._param_default_edits = []
    dialog._param_rows = []
    form.addRow("", dialog._param_container)

    def _update_param_hints():
        n = count_params(dialog.cmd_edit.text())
        old_hints = [e.text() for e in dialog._param_hint_edits]
        old_defaults = [e.text() for e in dialog._param_default_edits]
        for row_w in dialog._param_rows:
            dialog._param_layout.removeWidget(row_w); row_w.deleteLater()
        dialog._param_hint_edits.clear()
        dialog._param_default_edits.clear()
        dialog._param_rows.clear()
        ph = data.param_hints if data else []
        pd = data.param_defaults if data else []
        for i in range(n):
            row_w = QWidget()
            rl = QHBoxLayout(row_w); rl.setContentsMargins(0, 0, 0, 0); rl.setSpacing(6)
            lbl = QLabel(f"参数{i+1}"); lbl.setFixedWidth(40)
            lbl.setStyleSheet(f"color:{C['subtext0']}; font-size:11px;")
            rl.addWidget(lbl)
            hint_e = QLineEdit()
            hint_e.setPlaceholderText("说明")
            if i < len(old_hints) and old_hints[i]:
                hint_e.setText(old_hints[i])
            elif i < len(ph) and ph[i]:
                hint_e.setText(ph[i])
            rl.addWidget(hint_e)
            def_e = QLineEdit()
            def_e.setPlaceholderText("默认值")
            if i < len(old_defaults) and old_defaults[i]:
                def_e.setText(old_defaults[i])
            elif i < len(pd) and pd[i]:
                def_e.setText(pd[i])
            rl.addWidget(def_e)
            dialog._param_layout.addWidget(row_w)
            dialog._param_hint_edits.append(hint_e)
            dialog._param_default_edits.append(def_e)
            dialog._param_rows.append(row_w)
        dialog._param_container.setVisible(n > 0 and dialog.cat.currentData() == TYPE_CMD)

    dialog.cmd_edit.textChanged.connect(_update_param_hints)
    dialog._update_param_hints = _update_param_hints

    dialog.output_chk = QCheckBox("显示命令输出结果")
    if data:
        dialog.output_chk.setChecked(data.show_output)
    form.addRow("", dialog.output_chk)

    # --- CMD Window fields ---
    dialog._cmdwin_hint = QLabel("CMD窗口只需填写名称即可，启动后可交互")
    dialog._cmdwin_hint.setStyleSheet(f"color:{C['overlay0']}; font-size:12px;")
    form.addRow("", dialog._cmdwin_hint)

    dialog.pre_cmd_edit = QTextEdit()
    dialog.pre_cmd_edit.setPlaceholderText("启动后自动执行的命令，每行一条（可选）")
    dialog.pre_cmd_edit.setFixedHeight(80)
    if data and data.pre_cmd:
        dialog.pre_cmd_edit.setPlainText(data.pre_cmd)
    form.addRow("预命令", dialog.pre_cmd_edit)

    # --- Shortcut fields ---
    dialog._shortcut_import_btn = QPushButton("📦 从系统导入应用")
    dialog._shortcut_import_btn.setCursor(Qt.PointingHandCursor)
    dialog._shortcut_import_btn.setStyleSheet(f"""
        QPushButton {{ background:{C['surface1']}; color:{C['text']}; border:none; border-radius:8px; padding:6px; font-size:11px; }}
        QPushButton:hover {{ background:{C['surface2']}; }}
    """)
    def _import_sys_shortcut():
        dlg = _SystemAppDialog(dialog)
        if dlg.exec_() == QDialog.Accepted:
            app = dlg.selected_app()
            if app:
                dialog.name_edit.setText(app["name"])
                dialog.icon_edit.setText(app.get("icon", ""))
                dialog.path_edit.setText(app.get("exec", ""))
                dialog.sub_type_combo.setCurrentIndex(0)
    dialog._shortcut_import_btn.clicked.connect(_import_sys_shortcut)
    form.addRow("", dialog._shortcut_import_btn)

    dialog.sub_type_combo = QComboBox()
    for k, v in SUB_LABELS.items():
        dialog.sub_type_combo.addItem(v, k)
    if data and data.sub_type in SUB_LABELS:
        idx_st = list(SUB_LABELS.keys()).index(data.sub_type)
        dialog.sub_type_combo.setCurrentIndex(idx_st)
    form.addRow("类  型", dialog.sub_type_combo)

    icon_w = QWidget()
    icon_lay = QHBoxLayout(icon_w)
    icon_lay.setContentsMargins(0, 0, 0, 0)
    icon_lay.setSpacing(6)
    dialog.icon_edit = QLineEdit(data.icon if data else "")
    dialog.icon_edit.setPlaceholderText("图标文件路径（可选）")
    icon_lay.addWidget(dialog.icon_edit)
    ib = QPushButton("…")
    ib.setFixedWidth(36)
    ib.setStyleSheet(f"background:{C['surface1']}; color:{C['text']}; border:none; border-radius:6px;")
    ib.clicked.connect(lambda: _dlg_browse(dialog, dialog.icon_edit, "图标", "图片 (*.png *.svg *.ico *.jpg)"))
    icon_lay.addWidget(ib)
    dialog._icon_widget = icon_w
    form.addRow("图  标", icon_w)

    path_w = QWidget()
    path_lay = QHBoxLayout(path_w)
    path_lay.setContentsMargins(0, 0, 0, 0)
    path_lay.setSpacing(6)
    dialog.path_edit = QLineEdit(data.path if data else "")
    dialog.path_edit.setPlaceholderText("程序/文件/脚本路径")
    path_lay.addWidget(dialog.path_edit)
    pb = QPushButton("…")
    pb.setFixedWidth(36)
    pb.setStyleSheet(f"background:{C['surface1']}; color:{C['text']}; border:none; border-radius:6px;")
    pb.clicked.connect(lambda: _dlg_browse(dialog, dialog.path_edit, "选择", "所有文件 (*)"))
    path_lay.addWidget(pb)
    dialog._path_widget = path_w
    form.addRow("路  径", path_w)

    # --- Dock hint ---
    dialog._dock_hint = QLabel("Dock栏只需填写名称，创建后右键添加快捷方式项目")
    dialog._dock_hint.setStyleSheet(f"color:{C['overlay0']}; font-size:12px;")
    form.addRow("", dialog._dock_hint)

    # --- Todo hint ---
    dialog._todo_hint = QLabel("待办组件只需填写名称，创建后可添加待办事项")
    dialog._todo_hint.setStyleSheet(f"color:{C['overlay0']}; font-size:12px;")
    form.addRow("", dialog._todo_hint)

    # --- Calendar hint ---
    dialog._cal_hint = QLabel("自动显示当月日历和农历")
    dialog._cal_hint.setStyleSheet(f"color:{C['overlay0']}; font-size:12px;")
    form.addRow("", dialog._cal_hint)

    # --- Refresh interval (shared by calendar & weather) ---
    from PyQt5.QtWidgets import QSpinBox
    dialog._refresh_spin = QSpinBox()
    dialog._refresh_spin.setRange(1, 1440)
    dialog._refresh_spin.setSuffix(" 分钟")
    dialog._refresh_spin.setValue(data.refresh_interval // 60 if data else 5)
    dialog._refresh_spin.setStyleSheet(f"background:{C['surface0']}; color:{C['text']}; border:1px solid {C['surface2']}; border-radius:6px; padding:4px;")
    form.addRow("刷新间隔", dialog._refresh_spin)

    # --- Weather fields ---
    dialog._weather_hint = QLabel("选择城市后获取天气信息")
    dialog._weather_hint.setStyleSheet(f"color:{C['overlay0']}; font-size:12px;")
    form.addRow("", dialog._weather_hint)
    _city_row = QHBoxLayout(); _city_row.setSpacing(6)
    _init_city_cmd = data.cmd if data and data.comp_type == TYPE_WEATHER else ""
    _init_code = _init_city_cmd.split("|")[0].strip() if "|" in _init_city_cmd else ""
    _init_name = _init_city_cmd.split("|")[1].strip() if "|" in _init_city_cmd else _init_city_cmd
    dialog.city_edit = QLineEdit(_init_name)
    dialog.city_edit.setPlaceholderText("点击右侧按钮选择城市")
    dialog.city_edit.setReadOnly(True)
    dialog._city_code = _init_code
    _city_row.addWidget(dialog.city_edit)
    _city_pick_btn = QPushButton("选择城市"); _city_pick_btn.setCursor(Qt.PointingHandCursor)
    _city_pick_btn.setStyleSheet(f"background:{C['surface1']}; color:{C['text']}; border:none; border-radius:6px; padding:6px 12px; font-size:12px;")
    def _open_city_dlg():
        d = CitySelectDialog(getattr(dialog, '_city_code', ''), dialog)
        if d.exec_() == QDialog.Accepted:
            dialog._city_code = d.selected_code()
            dialog.city_edit.setText(d.selected_city())
    _city_pick_btn.clicked.connect(_open_city_dlg)
    _city_row.addWidget(_city_pick_btn)
    dialog._city_w = QWidget(); dialog._city_w.setLayout(_city_row)
    form.addRow("城  市", dialog._city_w)

    # --- Clock fields ---
    dialog._clock_sub_combo = QComboBox()
    for k, v in CLOCK_SUB_LABELS.items():
        dialog._clock_sub_combo.addItem(v, k)
    form.addRow("时钟类型", dialog._clock_sub_combo)

    dialog._clock_world_combo = QComboBox()
    for name, tz_id, offset in _WORLD_TIMEZONES:
        sign = "+" if offset >= 0 else ""
        dialog._clock_world_combo.addItem(f"{name} (UTC{sign}{offset})", tz_id)
    form.addRow("时  区", dialog._clock_world_combo)

    dialog._clock_date_fmt = QComboBox()
    for fmt, desc in [("%H:%M:%S", "24小时制 (14:30:00)"), ("%I:%M:%S %p", "12小时制 (02:30:00 PM)")]:
        dialog._clock_date_fmt.addItem(desc, fmt)
    form.addRow("时间格式", dialog._clock_date_fmt)

    def _on_clock_sub_changed(_=0):
        sub = dialog._clock_sub_combo.currentData()
        for w in dialog._clock_world_fields:
            if w: w.setVisible(sub == CLOCK_SUB_WORLD)
        for w in dialog._clock_fmt_fields:
            if w: w.setVisible(sub == CLOCK_SUB_CLOCK)

    dialog._clock_sub_combo.currentIndexChanged.connect(_on_clock_sub_changed)

    # --- Monitor fields ---
    dialog._monitor_sub_combo = QComboBox()
    for k, v in MONITOR_SUB_LABELS.items():
        dialog._monitor_sub_combo.addItem(v, k)
    form.addRow("监控类型", dialog._monitor_sub_combo)

    if data and data.comp_type == TYPE_MONITOR:
        msub = data.cmd.strip() if data.cmd else MONITOR_SUB_ALL
        idx = list(MONITOR_SUB_LABELS.keys()).index(msub) if msub in MONITOR_SUB_LABELS else list(MONITOR_SUB_LABELS.keys()).index(MONITOR_SUB_ALL)
        dialog._monitor_sub_combo.setCurrentIndex(idx)

    # --- Launcher fields ---
    dialog._launcher_hint = QLabel("自动扫描系统已安装应用，提供搜索和快速启动")
    dialog._launcher_hint.setStyleSheet(f"color:{C['overlay0']}; font-size:12px;")
    form.addRow("", dialog._launcher_hint)

    # --- Note fields ---
    dialog._note_hint = QLabel("桌面便签，支持多种颜色，文字自动保存")
    dialog._note_hint.setStyleSheet(f"color:{C['overlay0']}; font-size:12px;")
    form.addRow("", dialog._note_hint)

    # --- QuickAction fields ---
    dialog._quickaction_hint = QLabel("系统快捷操作：锁屏、关机、重启、音量控制等")
    dialog._quickaction_hint.setStyleSheet(f"color:{C['overlay0']}; font-size:12px;")
    form.addRow("", dialog._quickaction_hint)

    if data and data.comp_type == TYPE_CLOCK:
        parts = data.cmd.split("|", 1)
        sub = parts[0] if parts else CLOCK_SUB_CLOCK
        param = parts[1] if len(parts) > 1 else ""
        idx = list(CLOCK_SUB_LABELS.keys()).index(sub) if sub in CLOCK_SUB_LABELS else 0
        dialog._clock_sub_combo.setCurrentIndex(idx)
        if sub == CLOCK_SUB_WORLD:
            for i in range(dialog._clock_world_combo.count()):
                if dialog._clock_world_combo.itemData(i) == param:
                    dialog._clock_world_combo.setCurrentIndex(i); break
        elif sub == CLOCK_SUB_CLOCK and param:
            for i in range(dialog._clock_date_fmt.count()):
                if dialog._clock_date_fmt.itemData(i) == param:
                    dialog._clock_date_fmt.setCurrentIndex(i); break

    lay.addLayout(form)
    lay.addStretch()

    btns = QHBoxLayout()
    btns.addStretch()
    cancel = QPushButton("取消")
    cancel.setObjectName("cancelBtn")
    cancel.setCursor(Qt.PointingHandCursor)
    cancel.clicked.connect(dialog.reject)
    btns.addWidget(cancel)
    ok = QPushButton(ok_text)
    ok.setObjectName("okBtn")
    ok.setCursor(Qt.PointingHandCursor)
    ok.clicked.connect(dialog._validate)
    btns.addWidget(ok)
    lay.addLayout(btns)

    _lbl = form.labelForField
    dialog._cmd_fields = [_lbl(dialog.cmd_edit), dialog.cmd_edit,
                          _lbl(dialog._hint), dialog._hint,
                          _lbl(dialog._param_container), dialog._param_container,
                          _lbl(dialog.output_chk), dialog.output_chk]
    dialog._cmdwin_fields = [_lbl(dialog._cmdwin_hint), dialog._cmdwin_hint,
                             _lbl(dialog.pre_cmd_edit), dialog.pre_cmd_edit]
    dialog._shortcut_fields = [_lbl(dialog._shortcut_import_btn), dialog._shortcut_import_btn,
                               _lbl(dialog.sub_type_combo), dialog.sub_type_combo,
                               _lbl(icon_w), dialog._icon_widget,
                               _lbl(path_w), dialog._path_widget]
    dialog._dock_fields = [_lbl(dialog._dock_hint), dialog._dock_hint]
    dialog._todo_fields = [_lbl(dialog._todo_hint), dialog._todo_hint]
    dialog._refresh_fields = [_lbl(dialog._refresh_spin), dialog._refresh_spin]
    dialog._cal_fields = [_lbl(dialog._cal_hint), dialog._cal_hint]
    dialog._weather_fields = [_lbl(dialog._weather_hint), dialog._weather_hint,
                              _lbl(dialog._city_w), dialog._city_w]
    dialog._clock_fields = [_lbl(dialog._clock_sub_combo), dialog._clock_sub_combo]
    dialog._clock_world_fields = [_lbl(dialog._clock_world_combo), dialog._clock_world_combo]
    dialog._clock_fmt_fields = [_lbl(dialog._clock_date_fmt), dialog._clock_date_fmt]
    dialog._monitor_fields = [_lbl(dialog._monitor_sub_combo), dialog._monitor_sub_combo]
    dialog._launcher_fields = [_lbl(dialog._launcher_hint), dialog._launcher_hint]
    dialog._note_fields = [_lbl(dialog._note_hint), dialog._note_hint]
    dialog._quickaction_fields = [_lbl(dialog._quickaction_hint), dialog._quickaction_hint]

    dialog._name_fields = [_lbl(dialog.name_edit), dialog.name_edit]
    _NO_NAME_TYPES = {TYPE_CALENDAR, TYPE_WEATHER, TYPE_DOCK, TYPE_TODO, TYPE_CLOCK, TYPE_MONITOR, TYPE_LAUNCHER, TYPE_QUICKACTION}

    def on_type_changed(_=0):
        t = dialog.cat.currentData()
        for w in dialog._name_fields:
            if w: w.setVisible(t not in _NO_NAME_TYPES)
        for w in dialog._cmd_fields:
            if w: w.setVisible(t == TYPE_CMD)
        for w in dialog._cmdwin_fields:
            if w: w.setVisible(t == TYPE_CMD_WINDOW)
        for w in dialog._shortcut_fields:
            if w: w.setVisible(t == TYPE_SHORTCUT)
        for w in dialog._dock_fields:
            if w: w.setVisible(t == TYPE_DOCK)
        for w in dialog._todo_fields:
            if w: w.setVisible(t == TYPE_TODO)
        for w in dialog._refresh_fields:
            if w: w.setVisible(t in (TYPE_CALENDAR, TYPE_WEATHER))
        for w in dialog._cal_fields:
            if w: w.setVisible(t == TYPE_CALENDAR)
        for w in dialog._weather_fields:
            if w: w.setVisible(t == TYPE_WEATHER)
        for w in dialog._clock_fields:
            if w: w.setVisible(t == TYPE_CLOCK)
        for w in dialog._clock_world_fields:
            if w: w.setVisible(t == TYPE_CLOCK and dialog._clock_sub_combo.currentData() == CLOCK_SUB_WORLD)
        for w in dialog._clock_fmt_fields:
            if w: w.setVisible(t == TYPE_CLOCK and dialog._clock_sub_combo.currentData() == CLOCK_SUB_CLOCK)
        for w in dialog._monitor_fields:
            if w: w.setVisible(t == TYPE_MONITOR)
        for w in dialog._launcher_fields:
            if w: w.setVisible(t == TYPE_LAUNCHER)
        for w in dialog._note_fields:
            if w: w.setVisible(t == TYPE_NOTE)
        for w in dialog._quickaction_fields:
            if w: w.setVisible(t == TYPE_QUICKACTION)
        dialog._update_param_hints()

    dialog.cat.currentIndexChanged.connect(on_type_changed)

    if data:
        idx = list(TYPE_LABELS.keys()).index(data.comp_type)
        dialog.cat.setCurrentIndex(idx)

    on_type_changed()


def _dlg_browse(dialog, edit, title, filt):
    p, _ = QFileDialog.getOpenFileName(dialog, title, os.path.expanduser("~"), filt)
    if p:
        edit.setText(p)


def _dlg_validate(dialog):
    t = dialog.cat.currentData()
    _no_name = {TYPE_CALENDAR, TYPE_WEATHER, TYPE_DOCK, TYPE_TODO, TYPE_CLOCK, TYPE_MONITOR, TYPE_LAUNCHER, TYPE_QUICKACTION}
    if t not in _no_name and not dialog.name_edit.text().strip():
        dialog.name_edit.setFocus(); return False
    if t == TYPE_CMD and not dialog.cmd_edit.text().strip():
        dialog.cmd_edit.setFocus(); return False
    if t == TYPE_SHORTCUT and not dialog.path_edit.text().strip():
        dialog.path_edit.setFocus(); return False
    return True


def _dlg_get_data(dialog):
    t = dialog.cat.currentData()
    st = dialog.sub_type_combo.currentData() if t == TYPE_SHORTCUT else SUB_APP
    hints = [e.text().strip() for e in dialog._param_hint_edits] if hasattr(dialog, '_param_hint_edits') else []
    defaults = [e.text().strip() for e in dialog._param_default_edits] if hasattr(dialog, '_param_default_edits') else []
    pre = dialog.pre_cmd_edit.toPlainText().strip() if t == TYPE_CMD_WINDOW else ""
    cmd = dialog.cmd_edit.text().strip()
    if t == TYPE_WEATHER:
        city_code = getattr(dialog, '_city_code', '')
        city_name = dialog.city_edit.text().strip()
        cmd = f"{city_code}|{city_name}" if city_code else city_name or "大连"
    elif t == TYPE_CLOCK:
        clock_sub = dialog._clock_sub_combo.currentData()
        if clock_sub == CLOCK_SUB_WORLD:
            cmd = f"{clock_sub}|{dialog._clock_world_combo.currentData()}"
        elif clock_sub == CLOCK_SUB_CLOCK:
            cmd = f"{clock_sub}|{dialog._clock_date_fmt.currentData()}"
        elif clock_sub == CLOCK_SUB_ALARM:
            existing = getattr(dialog, '_data', None)
            if existing and existing.cmd.startswith(CLOCK_SUB_ALARM + "|"):
                cmd = existing.cmd
            else:
                cmd = f"{clock_sub}|[]"
        else:
            cmd = clock_sub
    if t == TYPE_MONITOR:
        cmd = dialog._monitor_sub_combo.currentData()
    if t == TYPE_NOTE:
        existing = getattr(dialog, '_data', None)
        if existing and existing.comp_type == TYPE_NOTE:
            cmd = existing.cmd
        else:
            cmd = "0|"
    name = dialog.name_edit.text().strip()
    if not name:
        _defaults = {TYPE_CALENDAR: "日历", TYPE_WEATHER: "天气", TYPE_DOCK: "Dock栏", TYPE_TODO: "待办",
                     TYPE_CLOCK: "时钟", TYPE_MONITOR: "系统监控", TYPE_LAUNCHER: "应用启动器",
                     TYPE_NOTE: "便签", TYPE_QUICKACTION: "快捷操作"}
        name = _defaults.get(t, t)
    ri = dialog._refresh_spin.value() * 60 if t in (TYPE_CALENDAR, TYPE_WEATHER) else 300
    return ComponentData(
        name=name, comp_type=t, sub_type=st,
        cmd=cmd, show_output=dialog.output_chk.isChecked(),
        icon=dialog.icon_edit.text().strip(), path=dialog.path_edit.text().strip(),
        param_hints=hints, param_defaults=defaults, pre_cmd=pre, refresh_interval=ri,
    )


class CreateDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("创建组件")
        self.setFixedWidth(440)
        _build_comp_dialog(self, "✦  创建新组件", "创  建")

    def _validate(self):
        if _dlg_validate(self):
            self.accept()

    def get_data(self):
        return _dlg_get_data(self)


class EditDialog(QDialog):
    def __init__(self, data: ComponentData, parent=None):
        super().__init__(parent)
        self.setWindowTitle("修改组件")
        self.setFixedWidth(440)
        self._data = data
        _build_comp_dialog(self, "✎  修改组件", "保  存", data)

    def _validate(self):
        if _dlg_validate(self):
            self.accept()

    def get_data(self):
        return _dlg_get_data(self)


# ---------------------------------------------------------------------------
# Export Dialog
# ---------------------------------------------------------------------------
class ExportDialog(QDialog):
    def __init__(self, panels_data, parent=None):
        super().__init__(parent)
        self.setWindowTitle("导出")
        self.setFixedWidth(460)
        self.setStyleSheet(_dialog_style())
        self._panels_data = panels_data

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20); lay.setSpacing(12)

        heading = QLabel("📤  选择导出内容")
        heading.setObjectName("heading")
        lay.addWidget(heading)

        self._all_chk = QCheckBox("全选")
        self._all_chk.setChecked(True)
        self._all_chk.stateChanged.connect(self._on_all_changed)
        lay.addWidget(self._all_chk)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(360)
        scroll.setStyleSheet(f"QScrollArea {{ border: 1px solid {C['surface1']}; border-radius: 8px; background: {C['base']}; }}")
        content = QWidget()
        content.setStyleSheet(f"background: {C['base']};");
        self._tree_layout = QVBoxLayout(content)
        self._tree_layout.setContentsMargins(8, 8, 8, 8)
        self._tree_layout.setSpacing(4)

        self._panel_chks = []
        self._comp_chks = []
        for pi, pd in enumerate(panels_data):
            p_chk = QCheckBox(f"📁 {pd.name}")
            p_chk.setChecked(True)
            p_chk.setStyleSheet(f"font-weight: bold; color: {C['text']};")
            self._tree_layout.addWidget(p_chk)
            self._panel_chks.append(p_chk)
            comp_list = []
            for ci, cd in enumerate(pd.components):
                c_chk = QCheckBox(f"    {TYPE_LABELS.get(cd.comp_type, '')} {cd.name}")
                c_chk.setChecked(True)
                self._tree_layout.addWidget(c_chk)
                comp_list.append(c_chk)
            self._comp_chks.append(comp_list)
            p_chk.stateChanged.connect(lambda state, idx=pi: self._on_panel_changed(idx, state))

        self._tree_layout.addStretch()
        scroll.setWidget(content)
        lay.addWidget(scroll)

        btns = QHBoxLayout(); btns.addStretch()
        cancel = QPushButton("取消"); cancel.setObjectName("cancelBtn")
        cancel.setCursor(Qt.PointingHandCursor); cancel.clicked.connect(self.reject)
        btns.addWidget(cancel)
        ok = QPushButton("导  出"); ok.setObjectName("okBtn")
        ok.setCursor(Qt.PointingHandCursor); ok.clicked.connect(self.accept)
        btns.addWidget(ok)
        lay.addLayout(btns)

    def _on_all_changed(self, state):
        checked = state == Qt.Checked
        for p_chk in self._panel_chks:
            p_chk.blockSignals(True); p_chk.setChecked(checked); p_chk.blockSignals(False)
        for comp_list in self._comp_chks:
            for c_chk in comp_list:
                c_chk.setChecked(checked)

    def _on_panel_changed(self, idx, state):
        checked = state == Qt.Checked
        for c_chk in self._comp_chks[idx]:
            c_chk.setChecked(checked)

    def get_export_data(self):
        result = []
        for pi, pd in enumerate(self._panels_data):
            comps = []
            for ci, cd in enumerate(pd.components):
                if self._comp_chks[pi][ci].isChecked():
                    comps.append(cd.to_dict())
            if comps:
                result.append({"name": pd.name, "components": comps})
        return result


# ---------------------------------------------------------------------------
# Settings Dialog
# ---------------------------------------------------------------------------
class _CropView(QWidget):
    def __init__(self, pixmap, parent=None):
        super().__init__(parent)
        self._src = pixmap
        sw, sh = pixmap.width(), pixmap.height()
        max_w, max_h = 640, 480
        scale = min(max_w / sw, max_h / sh, 1.0)
        self._dw = int(sw * scale)
        self._dh = int(sh * scale)
        self._scale = scale
        self._disp = pixmap.scaled(self._dw, self._dh, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.setFixedSize(self._dw, self._dh)
        self._crop = QRect(0, 0, self._dw, self._dh)
        self._drag = None
        self._drag_edge = None

    def paintEvent(self, e):
        p = QPainter(self)
        p.drawPixmap(0, 0, self._disp)
        dim = QColor(0, 0, 0, 120)
        cr = self._crop
        p.fillRect(QRect(0, 0, self._dw, cr.top()), dim)
        p.fillRect(QRect(0, cr.bottom(), self._dw, self._dh - cr.bottom()), dim)
        p.fillRect(QRect(0, cr.top(), cr.left(), cr.height()), dim)
        p.fillRect(QRect(cr.right(), cr.top(), self._dw - cr.right(), cr.height()), dim)
        p.setPen(QColor(255, 255, 255))
        p.drawRect(cr)
        p.setPen(QColor(255, 255, 255, 100))
        tw = cr.width() / 3; th = cr.height() / 3
        for i in range(1, 3):
            p.drawLine(int(cr.left() + tw * i), cr.top(), int(cr.left() + tw * i), cr.bottom())
            p.drawLine(cr.left(), int(cr.top() + th * i), cr.right(), int(cr.top() + th * i))
        p.end()

    def _edge_at(self, pos):
        cr = self._crop; m = 8
        edges = []
        if abs(pos.y() - cr.top()) < m: edges.append("t")
        if abs(pos.y() - cr.bottom()) < m: edges.append("b")
        if abs(pos.x() - cr.left()) < m: edges.append("l")
        if abs(pos.x() - cr.right()) < m: edges.append("r")
        if not edges and cr.contains(pos): return "move"
        return "".join(edges) if edges else None

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag_edge = self._edge_at(e.pos())
            self._drag = e.pos()

    def mouseMoveEvent(self, e):
        if not self._drag:
            edge = self._edge_at(e.pos())
            cursors = {"t": Qt.SizeVerCursor, "b": Qt.SizeVerCursor, "l": Qt.SizeHorCursor, "r": Qt.SizeHorCursor,
                       "tl": Qt.SizeFDiagCursor, "br": Qt.SizeFDiagCursor, "tr": Qt.SizeBDiagCursor, "bl": Qt.SizeBDiagCursor, "move": Qt.SizeAllCursor}
            self.setCursor(cursors.get(edge, Qt.ArrowCursor))
            return
        dx = e.pos().x() - self._drag.x()
        dy = e.pos().y() - self._drag.y()
        cr = QRect(self._crop)
        de = self._drag_edge
        if de == "move":
            cr.translate(dx, dy)
            if cr.left() < 0: cr.moveLeft(0)
            if cr.top() < 0: cr.moveTop(0)
            if cr.right() > self._dw: cr.moveRight(self._dw)
            if cr.bottom() > self._dh: cr.moveBottom(self._dh)
        else:
            if de and "t" in de: cr.setTop(max(0, min(cr.bottom() - 20, cr.top() + dy)))
            if de and "b" in de: cr.setBottom(min(self._dh, max(cr.top() + 20, cr.bottom() + dy)))
            if de and "l" in de: cr.setLeft(max(0, min(cr.right() - 20, cr.left() + dx)))
            if de and "r" in de: cr.setRight(min(self._dw, max(cr.left() + 20, cr.right() + dx)))
        self._crop = cr
        self._drag = e.pos()
        self.update()

    def mouseReleaseEvent(self, e):
        self._drag = None; self._drag_edge = None

    def get_crop_rect(self):
        s = 1 / self._scale
        return QRect(int(self._crop.left() * s), int(self._crop.top() * s),
                     int(self._crop.width() * s), int(self._crop.height() * s))


class ImageCropDialog(QDialog):
    def __init__(self, image_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("裁剪壁纸")
        self.setStyleSheet(f"QDialog {{ background: {C['base']}; }} QLabel {{ color: {C['text']}; }}")
        self._path = image_path
        self._src = QPixmap(image_path)
        self._cropped_path = None
        lay = QVBoxLayout(self); lay.setSpacing(12); lay.setContentsMargins(16, 16, 16, 16)
        hint = QLabel("拖动白色边框调整裁剪区域")
        hint.setStyleSheet(f"color:{C['subtext0']}; font-size:12px;")
        hint.setAlignment(Qt.AlignCenter); lay.addWidget(hint)
        self._view = _CropView(self._src, self)
        lay.addWidget(self._view, 0, Qt.AlignCenter)
        btns = QHBoxLayout(); btns.addStretch()
        cb = QPushButton("取消"); cb.setStyleSheet(f"background:{C['surface1']}; color:{C['text']}; border:none; border-radius:8px; padding:8px 24px; font-size:13px;")
        cb.setCursor(Qt.PointingHandCursor); cb.clicked.connect(self.reject); btns.addWidget(cb)
        ob = QPushButton("确认裁剪"); ob.setStyleSheet(f"background:{C['blue']}; color:{C['crust']}; border:none; border-radius:8px; padding:8px 24px; font-size:13px; font-weight:bold;")
        ob.setCursor(Qt.PointingHandCursor); ob.clicked.connect(self._do_crop); btns.addWidget(ob)
        lay.addLayout(btns)
        self.adjustSize()

    def _do_crop(self):
        r = self._view.get_crop_rect()
        cropped = self._src.copy(r)
        out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".wallpaper")
        os.makedirs(out_dir, exist_ok=True)
        self._cropped_path = os.path.join(out_dir, f"cropped_{uuid.uuid4().hex[:8]}.png")
        cropped.save(self._cropped_path, "PNG")
        self.accept()

    def cropped_path(self):
        return self._cropped_path


_KEY_NAMES = {
    Qt.Key_F1: "F1", Qt.Key_F2: "F2", Qt.Key_F3: "F3", Qt.Key_F4: "F4",
    Qt.Key_F5: "F5", Qt.Key_F6: "F6", Qt.Key_F7: "F7", Qt.Key_F8: "F8",
    Qt.Key_F9: "F9", Qt.Key_F10: "F10", Qt.Key_F11: "F11", Qt.Key_F12: "F12",
    Qt.Key_Space: "space", Qt.Key_Return: "Return", Qt.Key_Enter: "Return",
    Qt.Key_Escape: "Escape", Qt.Key_Tab: "Tab", Qt.Key_Backspace: "BackSpace",
    Qt.Key_Delete: "Delete", Qt.Key_Up: "Up", Qt.Key_Down: "Down",
    Qt.Key_Left: "Left", Qt.Key_Right: "Right", Qt.Key_Home: "Home",
    Qt.Key_End: "End", Qt.Key_PageUp: "Prior", Qt.Key_PageDown: "Next",
    Qt.Key_Comma: "comma", Qt.Key_Period: "period", Qt.Key_Slash: "slash",
    Qt.Key_Semicolon: "semicolon", Qt.Key_Apostrophe: "apostrophe",
    Qt.Key_BracketLeft: "bracketleft", Qt.Key_BracketRight: "bracketright",
    Qt.Key_Minus: "minus", Qt.Key_Equal: "equal", Qt.Key_QuoteLeft: "grave",
}
_MOD_KEYS = {Qt.Key_Control, Qt.Key_Alt, Qt.Key_Shift, Qt.Key_Meta,
             Qt.Key_Super_L, Qt.Key_Super_R, Qt.Key_AltGr}


def _parse_key_event(e):
    parts = []
    mods = e.modifiers()
    if mods & Qt.ControlModifier: parts.append("Ctrl")
    if mods & Qt.AltModifier: parts.append("Alt")
    if mods & Qt.ShiftModifier: parts.append("Shift")
    if mods & Qt.MetaModifier: parts.append("Super")
    key = e.key()
    if key in _MOD_KEYS:
        return None, "+".join(parts) + "+" if parts else ""
    if key in _KEY_NAMES:
        parts.append(_KEY_NAMES[key])
    elif Qt.Key_A <= key <= Qt.Key_Z:
        parts.append(chr(key).lower())
    elif Qt.Key_0 <= key <= Qt.Key_9:
        parts.append(chr(key))
    else:
        return None, ""
    return "+".join(parts), "+".join(parts)


class _HotkeyCaptureDlg(QDialog):
    def __init__(self, current_val="", parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置快捷键")
        self.setFixedSize(320, 160)
        self.setStyleSheet(_dialog_style())
        self._result = current_val
        lay = QVBoxLayout(self); lay.setContentsMargins(24, 20, 24, 20); lay.setSpacing(12)
        hint = QLabel("请按下快捷键组合…")
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet(f"color: {C['subtext0']}; font-size: 13px;")
        lay.addWidget(hint)
        self._display = QLabel(current_val or "—")
        self._display.setAlignment(Qt.AlignCenter)
        self._display.setStyleSheet(f"""
            color: {C['text']}; font-size: 18px; font-weight: bold;
            background: {C['surface0']}; border: 2px solid {C['blue']};
            border-radius: 8px; padding: 12px; min-height: 30px;
        """)
        lay.addWidget(self._display)
        self._pending = ""

    def keyPressEvent(self, e):
        combo, display = _parse_key_event(e)
        if combo:
            self._result = combo
            self._display.setText(combo)
            self._display.setStyleSheet(f"""
                color: {C['green']}; font-size: 18px; font-weight: bold;
                background: {C['surface0']}; border: 2px solid {C['green']};
                border-radius: 8px; padding: 12px; min-height: 30px;
            """)
            QTimer.singleShot(400, self.accept)
        elif display:
            self._display.setText(display)

    def get_result(self):
        return self._result


class _HotkeyEdit(QLineEdit):
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setReadOnly(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setPlaceholderText("点击设置快捷键")

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            dlg = _HotkeyCaptureDlg(self.text(), self.window())
            if dlg.exec_() == QDialog.Accepted:
                self.setText(dlg.get_result())
        else:
            super().mousePressEvent(e)


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setFixedWidth(480)
        self.setStyleSheet(_dialog_style())

        lay = QVBoxLayout(self); lay.setContentsMargins(28, 24, 28, 24); lay.setSpacing(16)
        heading = QLabel("⚙  设置"); heading.setObjectName("heading"); lay.addWidget(heading)

        form = QFormLayout(); form.setLabelAlignment(Qt.AlignRight); form.setSpacing(12)

        self.theme_combo = QComboBox()
        for name in THEMES:
            self.theme_combo.addItem(name)
        cur = _settings.get("theme", "Catppuccin Mocha")
        if cur in THEMES:
            self.theme_combo.setCurrentText(cur)
        self.theme_combo.currentTextChanged.connect(self._preview_theme)
        form.addRow("主  题", self.theme_combo)

        self._preview_bar = QWidget()
        self._preview_bar.setFixedHeight(28)
        self._update_preview_colors(cur)
        form.addRow("预  览", self._preview_bar)

        # --- Monitor mode ---
        screens = QApplication.screens()
        if len(screens) > 1:
            self._monitor_mode_combo = QComboBox()
            self._monitor_mode_combo.addItem("所有显示器共用一个面板", "single")
            self._monitor_mode_combo.addItem("每个显示器独立面板", "per_monitor")
            cur_mm = _settings.get("monitor_mode", "single")
            for i in range(self._monitor_mode_combo.count()):
                if self._monitor_mode_combo.itemData(i) == cur_mm:
                    self._monitor_mode_combo.setCurrentIndex(i); break
            form.addRow("显示器模式", self._monitor_mode_combo)

        # --- Wallpaper mode selector (mutually exclusive) ---
        _WP_MODES = [
            ("theme", "随主题颜色"),
            ("image", "壁纸（单图）"),
            ("per_monitor", "每个显示器"),
            ("gradient", "渐变色"),
            ("slideshow", "壁纸轮播"),
        ]
        cur_wp = _settings.get("wp_mode", "")
        if not cur_wp:
            if _settings.get("bg_slideshow_dir", ""):
                cur_wp = "slideshow"
            elif _settings.get("bg_gradient", ""):
                cur_wp = "gradient"
            elif _settings.get("bg_per_monitor", {}):
                cur_wp = "per_monitor"
            elif _settings.get("bg_image", ""):
                cur_wp = "image"
            else:
                cur_wp = "theme"

        self._wp_mode_combo = QComboBox()
        for mode_id, mode_label in _WP_MODES:
            self._wp_mode_combo.addItem(mode_label, mode_id)
        for i in range(self._wp_mode_combo.count()):
            if self._wp_mode_combo.itemData(i) == cur_wp:
                self._wp_mode_combo.setCurrentIndex(i); break
        form.addRow("壁纸模式", self._wp_mode_combo)

        # -- Image mode settings --
        self._wp_image_w = QWidget()
        _img_lay = QVBoxLayout(self._wp_image_w); _img_lay.setContentsMargins(0, 0, 0, 0); _img_lay.setSpacing(6)
        bg_w = QWidget()
        bg_lay = QHBoxLayout(bg_w); bg_lay.setContentsMargins(0, 0, 0, 0); bg_lay.setSpacing(6)
        self.bg_edit = QLineEdit(_settings.get("bg_image", ""))
        self.bg_edit.setPlaceholderText("背景图片路径")
        bg_lay.addWidget(self.bg_edit)
        bb = QPushButton("…"); bb.setFixedWidth(36)
        bb.setStyleSheet(f"background:{C['surface1']}; color:{C['text']}; border:none; border-radius:6px;")
        bb.clicked.connect(self._browse_bg)
        bg_lay.addWidget(bb)
        clr = QPushButton("✕"); clr.setFixedWidth(36)
        clr.setStyleSheet(f"background:{C['surface1']}; color:{C['red']}; border:none; border-radius:6px;")
        clr.clicked.connect(lambda: self.bg_edit.clear())
        bg_lay.addWidget(clr)
        _img_lay.addWidget(bg_w)
        _img_mode_w = QWidget()
        _img_mode_lay = QHBoxLayout(_img_mode_w); _img_mode_lay.setContentsMargins(0, 0, 0, 0); _img_mode_lay.setSpacing(6)
        _img_mode_lay.addWidget(QLabel("显示方式"))
        self._bg_mode_combo = QComboBox()
        for mode_id, mode_label in [("tile", "平铺"), ("clone", "复制")]:
            self._bg_mode_combo.addItem(mode_label, mode_id)
        cur_mode = _settings.get("bg_mode", "tile")
        for i in range(self._bg_mode_combo.count()):
            if self._bg_mode_combo.itemData(i) == cur_mode:
                self._bg_mode_combo.setCurrentIndex(i); break
        _img_mode_lay.addWidget(self._bg_mode_combo)
        _img_lay.addWidget(_img_mode_w)
        form.addRow("", self._wp_image_w)

        # -- Opacity (shared for image/per_monitor/slideshow) --
        from PyQt5.QtWidgets import QSlider
        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(10, 100)
        self.opacity_slider.setValue(_settings.get("bg_opacity", 30))
        self._opa_label = QLabel(f"{self.opacity_slider.value()}%")
        self._opa_label.setFixedWidth(36)
        self.opacity_slider.valueChanged.connect(lambda v: self._opa_label.setText(f"{v}%"))
        self._wp_opa_w = QWidget()
        opa_lay = QHBoxLayout(self._wp_opa_w); opa_lay.setContentsMargins(0, 0, 0, 0); opa_lay.setSpacing(6)
        opa_lay.addWidget(self.opacity_slider); opa_lay.addWidget(self._opa_label)
        form.addRow("背景透明度", self._wp_opa_w)

        # -- Component opacity --
        self._comp_opa_slider = QSlider(Qt.Horizontal)
        self._comp_opa_slider.setRange(20, 100)
        self._comp_opa_slider.setValue(_settings.get("comp_opacity", 90))
        self._comp_opa_label = QLabel(f"{self._comp_opa_slider.value()}%")
        self._comp_opa_label.setFixedWidth(36)
        self._comp_opa_slider.valueChanged.connect(lambda v: self._comp_opa_label.setText(f"{v}%"))
        comp_opa_w = QWidget()
        comp_opa_lay = QHBoxLayout(comp_opa_w); comp_opa_lay.setContentsMargins(0, 0, 0, 0); comp_opa_lay.setSpacing(6)
        comp_opa_lay.addWidget(self._comp_opa_slider); comp_opa_lay.addWidget(self._comp_opa_label)
        form.addRow("组件透明度", comp_opa_w)

        # -- Per monitor settings --
        self._per_monitor_container = QWidget()
        self._per_monitor_lay = QVBoxLayout(self._per_monitor_container)
        self._per_monitor_lay.setContentsMargins(0, 0, 0, 0); self._per_monitor_lay.setSpacing(6)
        self._per_monitor_edits = {}
        screens = QApplication.screens()
        saved_per_mon = _settings.get("bg_per_monitor", {})
        for s in screens:
            row_w = QWidget()
            row_l = QHBoxLayout(row_w); row_l.setContentsMargins(0, 0, 0, 0); row_l.setSpacing(4)
            lbl = QLabel(f"{s.name()} ({s.geometry().width()}×{s.geometry().height()})")
            lbl.setFixedWidth(160)
            lbl.setStyleSheet(f"color:{C['subtext0']}; font-size:11px;")
            row_l.addWidget(lbl)
            edit = QLineEdit(saved_per_mon.get(s.name(), ""))
            edit.setPlaceholderText("壁纸路径")
            row_l.addWidget(edit)
            browse_btn = QPushButton("…"); browse_btn.setFixedWidth(28)
            browse_btn.setStyleSheet(f"background:{C['surface1']}; color:{C['text']}; border:none; border-radius:6px;")
            browse_btn.clicked.connect(lambda _, e=edit: self._browse_per_monitor(e))
            row_l.addWidget(browse_btn)
            self._per_monitor_lay.addWidget(row_w)
            self._per_monitor_edits[s.name()] = edit
        form.addRow("", self._per_monitor_container)

        # -- Gradient settings --
        self._wp_gradient_w = QWidget()
        _grad_lay = QVBoxLayout(self._wp_gradient_w); _grad_lay.setContentsMargins(0, 0, 0, 0); _grad_lay.setSpacing(6)
        self.gradient_edit = QLineEdit(_settings.get("bg_gradient", ""))
        self.gradient_edit.setPlaceholderText("渐变色，如: #1a1b26,#24283b,#414868")
        _grad_lay.addWidget(self.gradient_edit)
        _GRADIENT_PRESETS = [
            ("深空", "#0f0c29,#302b63,#24243e"),
            ("日落", "#ee9ca7,#ffdde1"),
            ("海洋", "#2193b0,#6dd5ed"),
            ("森林", "#134e5e,#71b280"),
            ("极光", "#00c9ff,#92fe9d"),
            ("暗夜", "#0f2027,#203a43,#2c5364"),
            ("火焰", "#f12711,#f5af19"),
        ]
        grad_preset_w = QWidget()
        grad_preset_lay = QHBoxLayout(grad_preset_w); grad_preset_lay.setContentsMargins(0, 0, 0, 0); grad_preset_lay.setSpacing(4)
        for name, val in _GRADIENT_PRESETS:
            pb = QPushButton(name); pb.setFixedHeight(24); pb.setCursor(Qt.PointingHandCursor)
            colors = val.split(",")
            if len(colors) >= 2:
                pb.setStyleSheet(f"""
                    QPushButton {{
                        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 {colors[0]},stop:1 {colors[-1]});
                        color: white; border: none; border-radius: 4px; font-size: 10px; padding: 2px 6px;
                    }}
                    QPushButton:hover {{ border: 1px solid white; }}
                """)
            pb.clicked.connect(lambda _, v=val: self.gradient_edit.setText(v))
            grad_preset_lay.addWidget(pb)
        grad_preset_lay.addStretch()
        _grad_lay.addWidget(grad_preset_w)
        form.addRow("", self._wp_gradient_w)

        # -- Slideshow settings --
        self._wp_slideshow_w = QWidget()
        _ss_lay = QVBoxLayout(self._wp_slideshow_w); _ss_lay.setContentsMargins(0, 0, 0, 0); _ss_lay.setSpacing(6)
        ss_row = QWidget()
        ss_hlay = QHBoxLayout(ss_row); ss_hlay.setContentsMargins(0, 0, 0, 0); ss_hlay.setSpacing(6)
        self.slideshow_dir = QLineEdit(_settings.get("bg_slideshow_dir", ""))
        self.slideshow_dir.setPlaceholderText("壁纸目录")
        ss_hlay.addWidget(self.slideshow_dir)
        ssb = QPushButton("…"); ssb.setFixedWidth(36)
        ssb.setStyleSheet(f"background:{C['surface1']}; color:{C['text']}; border:none; border-radius:6px;")
        ssb.clicked.connect(self._browse_slideshow)
        ss_hlay.addWidget(ssb)
        _ss_lay.addWidget(ss_row)
        int_row = QWidget()
        int_hlay = QHBoxLayout(int_row); int_hlay.setContentsMargins(0, 0, 0, 0); int_hlay.setSpacing(6)
        int_hlay.addWidget(QLabel("切换间隔"))
        self.slideshow_interval = QSpinBox()
        self.slideshow_interval.setRange(10, 3600)
        self.slideshow_interval.setSuffix(" 秒")
        self.slideshow_interval.setValue(_settings.get("bg_slideshow_interval", 300))
        int_hlay.addWidget(self.slideshow_interval)
        _ss_lay.addWidget(int_row)
        form.addRow("", self._wp_slideshow_w)

        # -- Mode switch handler --
        def _on_wp_mode_change(idx):
            mode = self._wp_mode_combo.itemData(idx)
            self._wp_image_w.setVisible(mode == "image")
            self._wp_opa_w.setVisible(mode in ("image", "per_monitor", "slideshow"))
            self._per_monitor_container.setVisible(mode == "per_monitor")
            self._wp_gradient_w.setVisible(mode == "gradient")
            self._wp_slideshow_w.setVisible(mode == "slideshow")
        self._wp_mode_combo.currentIndexChanged.connect(_on_wp_mode_change)
        _on_wp_mode_change(self._wp_mode_combo.currentIndex())

        if _DESKTOP_MODE:
            sep = QFrame(); sep.setFrameShape(QFrame.HLine)
            sep.setStyleSheet(f"color: {C['surface1']};")
            form.addRow(sep)
            hotkeys = _settings.get("hotkeys", {})
            self._autostart_cb = QCheckBox("开机自动启动 FastPanel（桌面模式）")
            self._autostart_cb.setChecked(_is_autostart_enabled())
            form.addRow("自启动", self._autostart_cb)

            sep2 = QFrame(); sep2.setFrameShape(QFrame.HLine)
            sep2.setStyleSheet(f"color: {C['surface1']};")
            form.addRow(sep2)
            hk_label = QLabel("快捷键  （点击输入框设置，×按钮清除）")
            hk_label.setStyleSheet(f"color: {C['subtext0']}; font-size: 11px; padding-top: 4px;")
            form.addRow("", hk_label)
            _hk_defs = [
                ("显示/隐藏", "toggle_visibility", "_hk_toggle"),
                ("新建组件", "add_component", "_hk_add"),
                ("锁定切换", "toggle_lock", "_hk_lock"),
                ("打开设置", "open_settings", "_hk_settings"),
                ("剪贴板弹出", "clipboard_popup", "_hk_clipboard"),
            ]
            for label_text, key, attr in _hk_defs:
                hk_edit = _HotkeyEdit(hotkeys.get(key, ""))
                setattr(self, attr, hk_edit)
                row = QHBoxLayout(); row.setSpacing(4)
                row.addWidget(hk_edit, 1)
                clr_btn = QPushButton("×")
                clr_btn.setFixedSize(28, 28)
                clr_btn.setCursor(Qt.PointingHandCursor)
                clr_btn.setStyleSheet(f"""
                    QPushButton {{ background: {C['surface1']}; color: {C['red']};
                        border: none; border-radius: 14px; font-size: 16px; font-weight: bold; }}
                    QPushButton:hover {{ background: {C['red']}; color: {C['crust']}; }}
                """)
                clr_btn.clicked.connect(lambda _, e=hk_edit: e.setText(""))
                row.addWidget(clr_btn)
                w = QWidget(); w.setLayout(row)
                form.addRow(label_text, w)

        lay.addLayout(form); lay.addStretch()
        btns = QHBoxLayout(); btns.addStretch()
        cancel = QPushButton("取消"); cancel.setObjectName("cancelBtn")
        cancel.setCursor(Qt.PointingHandCursor); cancel.clicked.connect(self.reject); btns.addWidget(cancel)
        ok = QPushButton("应  用"); ok.setObjectName("okBtn")
        ok.setCursor(Qt.PointingHandCursor); ok.clicked.connect(self.accept); btns.addWidget(ok)
        lay.addLayout(btns)

    def _preview_theme(self, name):
        self._update_preview_colors(name)

    def _update_preview_colors(self, name):
        t = THEMES.get(name, THEMES["Catppuccin Mocha"])
        colors = [t["base"], t["surface0"], t["blue"], t["green"], t["red"], t["peach"], t["mauve"], t["text"]]
        swatches = "".join(f'<span style="display:inline-block;width:24px;height:24px;background:{c};border-radius:4px;margin:0 2px;">&nbsp;</span>' for c in colors)
        self._preview_bar.setStyleSheet(
            f"background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            f"stop:0 {t['base']}, stop:0.25 {t['surface0']}, stop:0.5 {t['blue']}, stop:0.75 {t['green']}, stop:1 {t['peach']});"
            f"border-radius: 6px;"
        )

    def _browse_bg(self):
        f, _ = QFileDialog.getOpenFileName(self, "选择背景图片", "", "图片 (*.png *.jpg *.jpeg *.bmp *.webp)")
        if f:
            dlg = ImageCropDialog(f, self)
            if dlg.exec_() == QDialog.Accepted and dlg.cropped_path():
                self.bg_edit.setText(dlg.cropped_path())
            else:
                self.bg_edit.setText(f)

    def _browse_slideshow(self):
        d = QFileDialog.getExistingDirectory(self, "选择壁纸目录", os.path.expanduser("~"))
        if d:
            self.slideshow_dir.setText(d)

    def _browse_per_monitor(self, edit):
        f, _ = QFileDialog.getOpenFileName(self, "选择壁纸", "", "图片 (*.png *.jpg *.jpeg *.bmp *.webp)")
        if f:
            edit.setText(f)

    def accept(self):
        if _DESKTOP_MODE and hasattr(self, '_hk_toggle'):
            hk_edits = {
                "显示/隐藏": self._hk_toggle, "新建组件": self._hk_add,
                "锁定切换": self._hk_lock, "打开设置": self._hk_settings,
                "剪贴板弹出": self._hk_clipboard,
            }
            used = {}
            for name, edit in hk_edits.items():
                key = edit.text().strip().lower()
                if key:
                    if key in used:
                        _confirm_dialog(self, "快捷键冲突",
                                        f"「{name}」与「{used[key]}」使用了相同的快捷键：{edit.text().strip()}\n请修改后重试。")
                        edit.setFocus()
                        return
                    used[key] = name
        super().accept()

    def get_settings(self):
        bg_mode = self._bg_mode_combo.itemData(self._bg_mode_combo.currentIndex())
        per_mon = {}
        for name, edit in self._per_monitor_edits.items():
            val = edit.text().strip()
            if val:
                per_mon[name] = val
        wp_mode = self._wp_mode_combo.itemData(self._wp_mode_combo.currentIndex())
        if hasattr(self, '_monitor_mode_combo'):
            _settings["monitor_mode"] = self._monitor_mode_combo.itemData(self._monitor_mode_combo.currentIndex())
            _settings["_monitor_mode_chosen"] = True
        s = {
            "theme": self.theme_combo.currentText(),
            "wp_mode": wp_mode,
            "bg_image": self.bg_edit.text().strip() if wp_mode == "image" else "",
            "bg_opacity": self.opacity_slider.value(),
            "comp_opacity": self._comp_opa_slider.value(),
            "bg_gradient": self.gradient_edit.text().strip() if wp_mode == "gradient" else "",
            "bg_slideshow_dir": self.slideshow_dir.text().strip() if wp_mode == "slideshow" else "",
            "bg_slideshow_interval": self.slideshow_interval.value(),
            "show_grid": _settings.get("show_grid", True),
            "bg_mode": bg_mode if wp_mode == "image" else "tile",
            "bg_per_monitor": per_mon if wp_mode == "per_monitor" else {},
        }
        if _DESKTOP_MODE and hasattr(self, '_hk_toggle'):
            s["hotkeys"] = {
                "toggle_visibility": self._hk_toggle.text().strip(),
                "add_component": self._hk_add.text().strip(),
                "toggle_lock": self._hk_lock.text().strip(),
                "open_settings": self._hk_settings.text().strip(),
                "clipboard_popup": self._hk_clipboard.text().strip(),
            }
        if hasattr(self, '_autostart_cb'):
            s["_autostart"] = self._autostart_cb.isChecked()
        return s


# ---------------------------------------------------------------------------
# Panel Tab Bar
# ---------------------------------------------------------------------------
class PanelTabBar(QFrame):
    tab_clicked = pyqtSignal(int)
    add_clicked = pyqtSignal()
    rename_requested = pyqtSignal(int)
    delete_requested = pyqtSignal(int)
    copy_requested = pyqtSignal(int)
    autohide_toggled = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent); self.setFixedHeight(42); self.setObjectName("panelTabBar")
        self._tabs = []; self._active = -1
        self._layout = QHBoxLayout(self); self._layout.setContentsMargins(8,4,8,4); self._layout.setSpacing(4)
        self._add_btn = QPushButton("＋"); self._add_btn.setObjectName("tabAddBtn")
        self._add_btn.setFixedSize(32,32); self._add_btn.setCursor(Qt.PointingHandCursor)
        self._add_btn.clicked.connect(self.add_clicked.emit); self._layout.addWidget(self._add_btn)
        self._layout.addStretch()
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._bar_menu)

    def _bar_menu(self, pos):
        menu = QMenu(self); menu.setStyleSheet(f"""
            QMenu {{ background:{C['base']}; border:1px solid {C['surface0']}; border-radius:6px; padding:4px 0; }}
            QMenu::item {{ color:{C['text']}; padding:6px 24px 6px 12px; font-size:12px; }}
            QMenu::item:selected {{ background:{C['surface1']}; }}
        """)
        ah = menu.addAction("📌  自动隐藏")
        a = menu.exec_(self.mapToGlobal(pos))
        if a == ah:
            self.autohide_toggled.emit()

    def add_tab(self, name):
        btn = QPushButton(name); btn.setObjectName("tabBtn"); btn.setCursor(Qt.PointingHandCursor)
        btn.setCheckable(True); idx = len(self._tabs)
        btn.clicked.connect(lambda _,i=idx: self._on_click(i))
        btn.setContextMenuPolicy(Qt.CustomContextMenu)
        btn.customContextMenuRequested.connect(lambda pos,i=idx: self._tab_menu(i, pos))
        self._tabs.append(btn); self._layout.insertWidget(self._layout.count()-1, btn)
        return idx

    def set_active(self, idx):
        self._active = idx
        for i, b in enumerate(self._tabs): b.setChecked(i==idx)

    def rename_tab(self, idx, name):
        if 0<=idx<len(self._tabs): self._tabs[idx].setText(name)

    def remove_tab(self, idx):
        if 0<=idx<len(self._tabs):
            b = self._tabs.pop(idx); self._layout.removeWidget(b); b.deleteLater()
            for i, b in enumerate(self._tabs):
                b.clicked.disconnect(); b.clicked.connect(lambda _,ii=i: self._on_click(ii))
                b.customContextMenuRequested.disconnect()
                b.customContextMenuRequested.connect(lambda pos,ii=i: self._tab_menu(ii, pos))

    def _on_click(self, idx): self.set_active(idx); self.tab_clicked.emit(idx)

    def _tab_menu(self, idx, pos):
        menu = QMenu(self); menu.setStyleSheet(f"""
            QMenu {{ background:{C['base']}; border:1px solid {C['surface0']}; border-radius:6px; padding:4px 0; }}
            QMenu::item {{ color:{C['text']}; padding:6px 24px 6px 12px; font-size:12px; }}
            QMenu::item:selected {{ background:{C['surface1']}; }}
            QMenu::separator {{ height:1px; background:{C['surface0']}; margin:3px 6px; }}
        """)
        ra = menu.addAction("✏  重命名"); ca = menu.addAction("📋  复制")
        menu.addSeparator(); da = menu.addAction("🗑  删除")
        a = menu.exec_(self._tabs[idx].mapToGlobal(pos))
        if a == ra: self.rename_requested.emit(idx)
        elif a == ca: self.copy_requested.emit(idx)
        elif a == da: self.delete_requested.emit(idx)


# ---------------------------------------------------------------------------
# Windowed Panel (launched from desktop mode)
# ---------------------------------------------------------------------------
class _PanelWindow(QMainWindow):
    closed = pyqtSignal(str)

    def __init__(self, panel_data, parent_main):
        super().__init__()
        self._panel_data = panel_data
        self._parent_main = parent_main
        self._panel_id = panel_data.id
        self._locked = False
        self.setWindowTitle(f"FastPanel — {panel_data.name}")
        self.setWindowFlags(Qt.FramelessWindowHint)
        _icon_path = os.path.join(_BASE_DIR, "fastpanel.svg")
        if os.path.isfile(_icon_path):
            self.setWindowIcon(QIcon(_icon_path))
        self.setMinimumSize(640, 480)
        self.resize(1000, 700)
        self._tb_dragging = False
        self._tb_offset = QPoint()
        self._resizing = False
        self._resize_edge = 0
        self._build_ui()
        self._apply_style()

    def _build_ui(self):
        cw = QWidget(); self.setCentralWidget(cw)
        root = QVBoxLayout(cw); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)

        tb = QFrame(); tb.setObjectName("toolbar"); tb.setFixedHeight(32)
        tl = QHBoxLayout(tb); tl.setContentsMargins(12, 0, 4, 0); tl.setSpacing(6)
        logo = QLabel(f"⚡ {self._panel_data.name}")
        logo.setObjectName("logo"); tl.addWidget(logo)
        tl.addStretch()
        self._cnt = QLabel("0 个组件"); self._cnt.setObjectName("countLabel"); tl.addWidget(self._cnt)

        self._grid_btn = QPushButton("▦"); self._grid_btn.setObjectName("gridBtn")
        self._grid_btn.setCursor(Qt.PointingHandCursor); self._grid_btn.setToolTip("显示/隐藏网格")
        self._grid_btn.setProperty("active", True)
        self._grid_btn.clicked.connect(self._toggle_grid); tl.addWidget(self._grid_btn)

        self._lock_btn = QPushButton("🔓"); self._lock_btn.setObjectName("lockBtn")
        self._lock_btn.setCursor(Qt.PointingHandCursor); self._lock_btn.setToolTip("锁定/解锁布局")
        self._lock_btn.clicked.connect(self._toggle_lock); tl.addWidget(self._lock_btn)

        for txt, oid, slot in [("—", "winMinBtn", self.showMinimized),
                                ("", "winMaxBtn", self._toggle_max),
                                ("✕", "winCloseBtn", self.close)]:
            b = QPushButton(txt); b.setObjectName(oid); b.setFixedSize(30, 22)
            b.setCursor(Qt.PointingHandCursor); b.clicked.connect(slot); tl.addWidget(b)
            if oid == "winMaxBtn":
                self._max_btn = b
        self._max_btn._is_restore = False
        _orig_paint = self._max_btn.paintEvent
        def _max_paint(event):
            _orig_paint(event)
            pp = QPainter(self._max_btn)
            pp.setRenderHint(QPainter.Antialiasing)
            pen = QPen(QColor(C['subtext0']), 1.2)
            pp.setPen(pen); pp.setBrush(Qt.NoBrush)
            if self._max_btn._is_restore:
                pp.drawRect(12, 4, 8, 8); pp.drawRect(9, 9, 8, 8)
            else:
                pp.drawRect(10, 5, 10, 10)
            pp.end()
        self._max_btn.paintEvent = _max_paint
        root.addWidget(tb)

        sc = QScrollArea(); sc.setWidgetResizable(False)
        sc.setStyleSheet(f"QScrollArea {{ background: transparent; border: none; }}" + _scrollbar_style(6))
        self._grid = GridPanel()
        self._grid.data_changed.connect(self._on_data_changed)
        sc.setWidget(self._grid)
        self._scroll = sc
        root.addWidget(sc, 1)

        desktop_safe_top = 0
        if self._parent_main and self._parent_main._grids:
            desktop_safe_top = self._parent_main._grids[0]._safe_margin_top

        for cd in self._panel_data.components:
            self._grid.add_component(cd)
        if desktop_safe_top > 0:
            for w in self._grid.components:
                w.data.y = max(0, w.data.y - desktop_safe_top)
                w.move(w.data.x, w.data.y)
        self._desktop_safe_top = desktop_safe_top

        groups = {}
        for w in self._grid.components:
            gid = getattr(w.data, '_group_id', None)
            if gid:
                groups.setdefault(gid, []).append(w.data.id)
                w.setProperty("locked", True)
        self._grid._groups = groups
        self._grid._update_overlay()
        self._cnt.setText(f"{len(self._grid.components)} 个组件")

    def _apply_style(self):
        self.setStyleSheet(f"""
            QMainWindow {{ background: {C['crust']}; }}
            #toolbar {{ background: {C['mantle']}; border-bottom: 1px solid {C['surface0']}; }}
            #logo {{ color: {C['blue']}; font-size: 13px; font-weight: bold; letter-spacing: 1px; }}
            #countLabel {{ color: {C['overlay0']}; font-size: 11px; margin-right: 8px; }}
            #gridBtn, #lockBtn {{
                background: {C['surface1']}; color: {C['text']};
                border: none; border-radius: 6px; padding: 4px 8px; font-size: 13px;
            }}
            #gridBtn:hover, #lockBtn:hover {{ background: {C['surface2']}; }}
            #winMinBtn, #winMaxBtn {{ background: transparent; color: {C['subtext0']}; border: none; border-radius: 6px; font-size: 14px; }}
            #winMinBtn:hover, #winMaxBtn:hover {{ background: {C['surface1']}; }}
            #winCloseBtn {{ background: transparent; color: {C['subtext0']}; border: none; border-radius: 6px; font-size: 14px; }}
            #winCloseBtn:hover {{ background: {C['red']}; color: {C['crust']}; }}
        """)

    def _toggle_grid(self):
        show = not self._grid._show_grid
        self._grid.set_show_grid(show)
        self._grid_btn.setProperty("active", show)
        self._grid_btn.style().unpolish(self._grid_btn)
        self._grid_btn.style().polish(self._grid_btn)

    def _toggle_lock(self):
        self._locked = not self._locked
        self._lock_btn.setText("🔒" if self._locked else "🔓")
        for w in self._grid.components:
            w.setProperty("locked", self._locked)

    def _toggle_max(self):
        if self._max_btn._is_restore:
            self.showNormal(); self._max_btn._is_restore = False
        else:
            self.showMaximized(); self._max_btn._is_restore = True
        self._max_btn.update()

    def _on_data_changed(self):
        self._cnt.setText(f"{len(self._grid.components)} 个组件")
        self._sync_back()

    def _sync_back(self):
        self._panel_data.components = [w.data for w in self._grid.components]
        if self._parent_main:
            self._parent_main._save_data()

    def _restore_desktop_offsets(self):
        if self._desktop_safe_top > 0:
            for w in self._grid.components:
                w.data.y = w.data.y + self._desktop_safe_top
                w.move(w.data.x, w.data.y)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        QTimer.singleShot(0, self._sync_size)

    def showEvent(self, e):
        super().showEvent(e)
        QTimer.singleShot(0, self._sync_size)

    def _sync_size(self):
        vp = self._scroll.viewport()
        self._grid.recalc_size(vp.width(), vp.height())

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            edge = self._hit_edge(e.pos())
            if edge:
                self._resizing = True; self._resize_edge = edge
                self._resize_origin = e.globalPos(); self._resize_geo = self.geometry()
            elif e.pos().y() < 32:
                self._tb_dragging = True; self._tb_offset = e.globalPos() - self.pos()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._resizing:
            self._do_resize(e.globalPos())
        elif self._tb_dragging:
            self.move(e.globalPos() - self._tb_offset)
        else:
            edge = self._hit_edge(e.pos())
            cursors = {1: Qt.SizeVerCursor, 2: Qt.SizeVerCursor, 4: Qt.SizeHorCursor, 8: Qt.SizeHorCursor,
                       5: Qt.SizeFDiagCursor, 6: Qt.SizeBDiagCursor, 9: Qt.SizeBDiagCursor, 10: Qt.SizeFDiagCursor}
            self.setCursor(cursors.get(edge, Qt.ArrowCursor))
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        self._tb_dragging = False; self._resizing = False
        super().mouseReleaseEvent(e)

    def mouseDoubleClickEvent(self, e):
        if e.pos().y() < 32:
            self._toggle_max()

    def _hit_edge(self, pos, m=6):
        w, h = self.width(), self.height()
        edge = 0
        if pos.y() >= h - m: edge |= 2
        if pos.x() <= m: edge |= 4
        if pos.x() >= w - m: edge |= 8
        return edge

    def _do_resize(self, gpos):
        dx = gpos.x() - self._resize_origin.x()
        dy = gpos.y() - self._resize_origin.y()
        g = QRect(self._resize_geo)
        e = self._resize_edge
        if e & 2: g.setBottom(g.bottom() + dy)
        if e & 4: g.setLeft(g.left() + dx)
        if e & 8: g.setRight(g.right() + dx)
        if g.width() >= 400 and g.height() >= 300:
            self.setGeometry(g)

    def closeEvent(self, e):
        self._restore_desktop_offsets()
        self._sync_back()
        self.closed.emit(self._panel_id)
        super().closeEvent(e)


# ---------------------------------------------------------------------------
# Main Window
# ---------------------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._desktop_mode = _DESKTOP_MODE
        self._desktop_backend = None
        self.setWindowTitle("FastPanel")
        _icon_path = os.path.join(_BASE_DIR, "fastpanel.svg")
        if os.path.isfile(_icon_path):
            self.setWindowIcon(QIcon(_icon_path))
        self._panels_data = []; self._grids = []; self._scrolls = []; self._active = 0
        self._per_monitor_active = False
        self._locked = False
        self._panel_windows = {}
        self._tb_dragging = False; self._tb_offset = QPoint()

        if self._desktop_mode:
            self._desktop_backend = DesktopBackend.create()
            self._desktop_backend.setup_window(self)
        else:
            self.setWindowFlags(Qt.FramelessWindowHint)
            self.setMinimumSize(960, 640); self.resize(1200, 800)

        self._build_ui(); self._apply_style(); self._load_data()
        if not self._panels_data:
            self._first_launch_setup()
        elif self._desktop_mode and len(QApplication.screens()) > 1 and not _settings.get("_monitor_mode_chosen"):
            self._ask_monitor_mode()
        elif self._desktop_mode and _settings.get("monitor_mode") == "per_monitor":
            self._apply_per_monitor_panels()
        if self._desktop_mode:
            self._setup_tray()
            self._setup_hotkeys()
            if _settings.get("monitor_mode") == "per_monitor":
                self._mon_switch_timer = QTimer(self)
                self._mon_switch_timer.timeout.connect(self._auto_switch_monitor_panel)
                self._mon_switch_timer.start(500)

    def _build_ui(self):
        cw = QWidget(); self.setCentralWidget(cw)
        root = QVBoxLayout(cw); root.setContentsMargins(0,0,0,0); root.setSpacing(0)

        # Toolbar (hidden in desktop mode)
        tb = QFrame(); tb.setObjectName("toolbar"); tb.setFixedHeight(48)
        self._toolbar = tb
        tl = QHBoxLayout(tb); tl.setContentsMargins(16,0,8,0); tl.setSpacing(8)
        logo = QLabel("⚡ FastPanel"); logo.setObjectName("logo"); tl.addWidget(logo)
        tl.addStretch()
        self._cnt = QLabel("0 个组件"); self._cnt.setObjectName("countLabel"); tl.addWidget(self._cnt)
        for txt, slot in [("📥 导入", self._on_import), ("📤 导出", self._on_export)]:
            b = QPushButton(txt); b.setObjectName("ioBtn"); b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(slot); tl.addWidget(b)
        self._grid_btn = QPushButton("▦"); self._grid_btn.setObjectName("gridBtn")
        self._grid_btn.setCursor(Qt.PointingHandCursor); self._grid_btn.setToolTip("显示/隐藏网格")
        self._grid_btn.setProperty("active", _settings.get("show_grid", True))
        self._grid_btn.clicked.connect(self._toggle_grid); tl.addWidget(self._grid_btn)
        self._lock_btn = QPushButton("🔓"); self._lock_btn.setObjectName("lockBtn")
        self._lock_btn.setCursor(Qt.PointingHandCursor); self._lock_btn.setToolTip("锁定/解锁布局")
        self._lock_btn.clicked.connect(self._toggle_lock); tl.addWidget(self._lock_btn)
        sb = QPushButton("⚙"); sb.setObjectName("settingsBtn")
        sb.setCursor(Qt.PointingHandCursor); sb.setToolTip("设置")
        sb.clicked.connect(self._on_settings); tl.addWidget(sb)
        ab = QPushButton("＋  新建组件"); ab.setObjectName("addBtn"); ab.setCursor(Qt.PointingHandCursor)
        ab.clicked.connect(self._on_add); tl.addWidget(ab)

        self._max_btn = None
        if not self._desktop_mode:
            for txt, oid, slot in [("—", "winMinBtn", self.showMinimized),
                                    ("", "winMaxBtn", self._toggle_max),
                                    ("✕", "winCloseBtn", self.close)]:
                b = QPushButton(txt); b.setObjectName(oid); b.setFixedSize(36, 28)
                b.setCursor(Qt.PointingHandCursor); b.clicked.connect(slot); tl.addWidget(b)
                if oid == "winMaxBtn": self._max_btn = b
            self._max_btn._is_restore = False
            _orig_paint = self._max_btn.paintEvent
            def _max_paint(event):
                _orig_paint(event)
                pp = QPainter(self._max_btn)
                pp.setRenderHint(QPainter.Antialiasing)
                pen = QPen(QColor(C['subtext0']), 1.2)
                pp.setPen(pen); pp.setBrush(Qt.NoBrush)
                if self._max_btn._is_restore:
                    pp.drawRect(15, 6, 10, 10)
                    pp.drawRect(11, 11, 10, 10)
                else:
                    pp.drawRect(12, 8, 12, 12)
                pp.end()
            self._max_btn.paintEvent = _max_paint

        if self._desktop_mode:
            tb.hide()
        else:
            root.addWidget(tb)

        self._stack = QStackedWidget(); root.addWidget(self._stack, 1)

        self._tab_bar_container = QWidget()
        self._tab_bar_container.setFixedHeight(42)
        tcl = QVBoxLayout(self._tab_bar_container)
        tcl.setContentsMargins(0, 0, 0, 0); tcl.setSpacing(0)
        self._tab_bar = PanelTabBar()
        self._tab_bar.add_clicked.connect(self._on_add_panel)
        self._tab_bar.tab_clicked.connect(self._switch_panel)
        self._tab_bar.rename_requested.connect(self._on_rename_panel)
        self._tab_bar.delete_requested.connect(self._on_delete_panel)
        self._tab_bar.copy_requested.connect(self._on_copy_panel)
        self._tab_bar.autohide_toggled.connect(self._toggle_tab_autohide)
        tcl.addWidget(self._tab_bar)

        if self._desktop_mode:
            self._tab_bar_container.hide()
        else:
            root.addWidget(self._tab_bar_container)

        self._tab_autohide = self._desktop_mode
        self._tab_hover_zone = QWidget(cw)
        self._tab_hover_zone.setFixedHeight(4)
        self._tab_hover_zone.setStyleSheet(f"background: {C['surface0']};")
        self._tab_hover_zone.hide()
        self._tab_hover_zone.setMouseTracking(True)
        self._tab_hover_zone.installEventFilter(self)
        self._tab_bar_container.installEventFilter(self)

    def _apply_style(self):
        self.setStyleSheet(f"""
            QMainWindow {{ background: {C['crust']}; }}
            #toolbar {{ background: {C['mantle']}; border-bottom: 1px solid {C['surface0']}; }}
            #logo {{ color: {C['blue']}; font-size: 22px; font-weight: bold; letter-spacing: 1px; }}
            #countLabel {{ color: {C['overlay0']}; font-size: 12px; margin-right: 16px; }}
            #addBtn {{
                background: {C['blue']}; color: {C['crust']};
                border: none; border-radius: 10px; padding: 10px 22px;
                font-size: 13px; font-weight: bold;
            }}
            #addBtn:hover {{ background: {C['lavender']}; }}
            #ioBtn {{
                background: {C['surface1']}; color: {C['text']};
                border: none; border-radius: 8px; padding: 8px 16px;
                font-size: 12px; margin-right: 4px;
            }}
            #ioBtn:hover {{ background: {C['surface2']}; }}
            #gridBtn {{
                background: {C['surface1']}; color: {C['text']};
                border: none; border-radius: 8px; padding: 8px 12px;
                font-size: 18px; margin-right: 4px;
            }}
            #gridBtn:hover {{ background: {C['surface2']}; }}
            #gridBtn[active="true"] {{
                background: {C['blue']}; color: {C['crust']};
            }}
            #gridBtn[active="true"]:hover {{ background: {C['lavender']}; color: {C['crust']}; }}
            #lockBtn {{
                background: {C['surface1']}; color: {C['text']};
                border: none; border-radius: 8px; padding: 8px 12px;
                font-size: 18px; margin-right: 4px;
            }}
            #lockBtn:hover {{ background: {C['surface2']}; }}
            #lockBtn[locked="true"] {{
                background: {C['red']}; color: {C['crust']};
            }}
            #lockBtn[locked="true"]:hover {{ background: {C['peach']}; color: {C['crust']}; }}
            #settingsBtn {{
                background: {C['surface1']}; color: {C['text']};
                border: none; border-radius: 8px; padding: 8px 12px;
                font-size: 18px; margin-right: 4px;
            }}
            #settingsBtn:hover {{ background: {C['surface2']}; }}
            QScrollArea {{ border: none; background: {C['crust']}; }}
            QScrollBar:vertical {{
                background: {C['mantle']}; width: 8px; border-radius: 4px;
            }}
            QScrollBar::handle:vertical {{
                background: {C['surface1']}; border-radius: 4px; min-height: 40px;
            }}
            QScrollBar::handle:vertical:hover {{ background: {C['surface2']}; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            #panelTabBar {{ background: {C['mantle']}; border-top: 1px solid {C['surface0']}; }}
            #tabAddBtn {{
                background: {C['surface1']}; color: {C['text']};
                border: none; border-radius: 8px; font-size: 16px; font-weight: bold;
            }}
            #tabAddBtn:hover {{ background: {C['blue']}; color: {C['crust']}; }}
            #tabBtn {{
                background: {C['surface0']}; color: {C['subtext0']};
                border: none; border-radius: 8px; padding: 6px 18px; font-size: 12px;
            }}
            #tabBtn:hover {{ background: {C['surface1']}; }}
            #tabBtn:checked {{ background: {C['blue']}; color: {C['crust']}; font-weight: bold; }}
            #winMinBtn, #winMaxBtn {{
                background: transparent; color: {C['subtext0']};
                border: none; border-radius: 4px; font-size: 14px;
            }}
            #winMinBtn:hover, #winMaxBtn:hover {{ background: {C['surface1']}; color: {C['text']}; }}
            #winCloseBtn {{
                background: transparent; color: {C['subtext0']};
                border: none; border-radius: 4px; font-size: 14px;
            }}
            #winCloseBtn:hover {{ background: {C['red']}; color: {C['crust']}; }}
        """)

    # ---- System Tray (desktop mode) ----
    def _setup_tray(self):
        self._tray = QSystemTrayIcon(self)
        _icon_path = os.path.join(_BASE_DIR, "fastpanel.svg")
        if os.path.isfile(_icon_path):
            self._tray.setIcon(QIcon(_icon_path))
        else:
            self._tray.setIcon(self.style().standardIcon(self.style().SP_ComputerIcon))
        tray_menu = QMenu()
        tray_menu.setStyleSheet(self._ctx_menu_style())
        show_act = tray_menu.addAction("显示/隐藏桌面")
        show_act.triggered.connect(self._toggle_visibility)
        tray_menu.addSeparator()
        add_act = tray_menu.addAction("新建组件")
        add_act.triggered.connect(self._on_add)
        settings_act = tray_menu.addAction("设置")
        settings_act.triggered.connect(self._on_settings)
        tray_menu.addSeparator()
        lock_act = tray_menu.addAction("锁定布局" if not self._locked else "解锁布局")
        lock_act.triggered.connect(self._toggle_lock)
        self._tray_lock_act = lock_act
        tray_menu.addSeparator()
        quit_act = tray_menu.addAction("退出 FastPanel")
        quit_act.triggered.connect(self._quit_app)
        self._tray.setContextMenu(tray_menu)
        self._tray.activated.connect(self._on_tray_activated)
        self._tray.show()

    def _setup_hotkeys(self):
        self._hotkey_mgr = _HotkeyManager.create()
        hotkeys = _settings.get("hotkeys", {})
        toggle_key = hotkeys.get("toggle_visibility", "")
        add_key = hotkeys.get("add_component", "")
        lock_key = hotkeys.get("toggle_lock", "")
        settings_key = hotkeys.get("open_settings", "")
        if toggle_key:
            self._hotkey_mgr.register(toggle_key, self._toggle_visibility)
        if add_key:
            self._hotkey_mgr.register(add_key, self._on_add)
        if lock_key:
            self._hotkey_mgr.register(lock_key, self._toggle_lock)
        if settings_key:
            self._hotkey_mgr.register(settings_key, self._on_settings)
        clip_key = hotkeys.get("clipboard_popup", "")
        if clip_key:
            self._hotkey_mgr.register(clip_key, self._show_clipboard_popup)
        self._hotkey_mgr.start()

    def _stop_hotkeys(self):
        if hasattr(self, '_hotkey_mgr'):
            self._hotkey_mgr.stop()

    def _show_clipboard_popup(self):
        print(f"[Clipboard] popup requested", flush=True)
        try:
            popup = _ClipboardPopup.get_or_create(None)
            popup.show_at_cursor()
            print(f"[Clipboard] popup shown at {popup.pos()}, visible={popup.isVisible()}", flush=True)
        except Exception as e:
            print(f"[Clipboard] ERROR: {e}", flush=True)
            import traceback; traceback.print_exc()

    def _toggle_visibility(self):
        if self.isVisible():
            self.hide()
        else:
            self.show()
            if self._desktop_mode and self._desktop_backend:
                self._desktop_backend.setup_window(self)

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self._toggle_visibility()

    def _launch_panel_window(self, panel_idx):
        if 0 <= panel_idx < len(self._panels_data):
            pd = self._panels_data[panel_idx]
            if pd.id in self._panel_windows:
                win = self._panel_windows[pd.id]
                win.raise_()
                win.activateWindow()
                return
            win = _PanelWindow(pd, self)
            win.closed.connect(self._on_panel_window_closed)
            self._panel_windows[pd.id] = win
            win.show()

    def _on_panel_window_closed(self, panel_id):
        self._panel_windows.pop(panel_id, None)

    def _quit_app(self):
        self._save_data()
        self._stop_hotkeys()
        for win in list(self._panel_windows.values()):
            win.close()
        self._panel_windows.clear()
        if hasattr(self, '_tray'):
            self._tray.hide()
        _X11DesktopBackend.restore_gnome_desktop()
        QApplication.instance().quit()

    # ---- Desktop right-click context menu ----
    def _ctx_menu_style(self):
        return f"""
            QMenu {{
                background: {C['surface0']}; color: {C['text']};
                border: 1px solid {C['surface1']}; border-radius: 8px;
                padding: 6px 4px; font-size: 13px;
            }}
            QMenu::item {{
                padding: 8px 28px 8px 16px; border-radius: 4px; margin: 2px 4px;
            }}
            QMenu::item:selected {{ background: {C['blue']}; color: {C['crust']}; }}
            QMenu::separator {{ height: 1px; background: {C['surface1']}; margin: 4px 8px; }}
        """

    def _quick_add(self, comp_type, cmd=""):
        _DEFAULT_NAMES = {TYPE_CALENDAR: "日历", TYPE_WEATHER: "天气", TYPE_DOCK: "Dock栏",
                          TYPE_TODO: "待办", TYPE_CLOCK: "时钟", TYPE_MONITOR: "系统监控",
                          TYPE_LAUNCHER: "应用启动器", TYPE_QUICKACTION: "快捷操作",
                          TYPE_NOTE: "便签", TYPE_MEDIA: "媒体控制", TYPE_CLIPBOARD: "剪贴板",
                          TYPE_TIMER: "计时器", TYPE_GALLERY: "相册", TYPE_SYSINFO: "系统信息",
                          TYPE_BOOKMARK: "书签", TYPE_CALC: "计算器", TYPE_TRASH: "回收站",
                          TYPE_RSS: "RSS"}
        _NEEDS_DIALOG = {TYPE_CMD, TYPE_CMD_WINDOW, TYPE_SHORTCUT}
        if comp_type in _NEEDS_DIALOG:
            self._on_add_with_type(comp_type)
            return
        if comp_type == TYPE_WEATHER:
            self._on_add_with_type(comp_type)
            return
        name = _DEFAULT_NAMES.get(comp_type, comp_type)
        d = ComponentData(name=name, comp_type=comp_type, cmd=cmd)
        if comp_type == TYPE_NOTE:
            d.cmd = "0|"
        elif comp_type == TYPE_CLOCK and cmd in (CLOCK_SUB_ALARM,):
            d.cmd = f"{cmd}|[]"
        d.x, d.y = self._next_pos()
        size_map = {
            TYPE_CALENDAR: (16, 16), TYPE_DOCK: (20, 5), TYPE_TODO: (14, 12),
            TYPE_LAUNCHER: (16, 20), TYPE_QUICKACTION: (18, 12), TYPE_NOTE: (12, 10),
            TYPE_MEDIA: (16, 7), TYPE_CLIPBOARD: (14, 14), TYPE_TIMER: (12, 10),
            TYPE_GALLERY: (14, 12), TYPE_SYSINFO: (16, 14), TYPE_BOOKMARK: (14, 12),
            TYPE_CALC: (14, 16), TYPE_TRASH: (10, 8), TYPE_RSS: (16, 16),
            TYPE_CLOCK: (10, 8), TYPE_WEATHER: (14, 12),
        }
        if comp_type == TYPE_MONITOR:
            mon_sizes = {MONITOR_SUB_ALL: (22, 18), MONITOR_SUB_DISK: (18, 10)}
            gw, gh = mon_sizes.get(cmd, (14, 10))
        elif comp_type == TYPE_CLOCK:
            clk_sizes = {CLOCK_SUB_STOPWATCH: (12, 12), CLOCK_SUB_TIMER: (12, 10)}
            gw, gh = clk_sizes.get(cmd, (10, 8))
        else:
            gw, gh = size_map.get(comp_type, (10, 8))
        d.w = GRID_SIZE * gw; d.h = GRID_SIZE * gh
        grid = self._cg()
        safe_top = grid._safe_margin_top
        safe_bot = grid._safe_margin_bottom
        avail_h = grid.height() - safe_top - safe_bot
        if d.w > grid.width() or d.h > avail_h:
            _confirm_dialog(self, "提示", "布局空间不足，请先调整布局")
            return
        free = self._find_free_pos(grid, d.w, d.h, safe_top, safe_bot)
        if free is None:
            _confirm_dialog(self, "提示", "布局空间不足，请先调整布局")
            return
        d.x, d.y = free
        grid.add_component(d)
        self._panels_data[self._active].components.append(d)
        self._update_count(); self._sync_sizes()

    def _on_add_with_type(self, comp_type):
        dlg = CreateDialog(self)
        idx = list(TYPE_LABELS.keys()).index(comp_type) if comp_type in TYPE_LABELS else 0
        dlg.cat.setCurrentIndex(idx)
        if dlg.exec_() == QDialog.Accepted:
            d = dlg.get_data()
            d.x, d.y = self._next_pos()
            self._apply_default_size(d)
            grid = self._cg()
            safe_top = grid._safe_margin_top
            safe_bot = grid._safe_margin_bottom
            avail_h = grid.height() - safe_top - safe_bot
            if d.w > grid.width() or d.h > avail_h:
                _confirm_dialog(self, "提示", "布局空间不足，请先调整布局")
                return
            free = self._find_free_pos(grid, d.w, d.h, safe_top, safe_bot)
            if free is None:
                _confirm_dialog(self, "提示", "布局空间不足，请先调整布局")
                return
            d.x, d.y = free
            grid.add_component(d)
            self._panels_data[self._active].components.append(d)
            self._update_count(); self._sync_sizes()

    def _show_desktop_ctx_menu(self, pos):
        menu = QMenu(self)
        menu.setStyleSheet(self._ctx_menu_style())

        add_menu = menu.addMenu("＋  新建组件")
        add_menu.setStyleSheet(self._ctx_menu_style())
        _style = self._ctx_menu_style()

        _simple = [
            ("📋 剪贴板", TYPE_CLIPBOARD, ""),
            ("📝 便签", TYPE_NOTE, ""),
            ("✅ 待办", TYPE_TODO, ""),
            ("🎛 快捷操作", TYPE_QUICKACTION, ""),
            ("📅 日历", TYPE_CALENDAR, ""),
            ("🔢 计算器", TYPE_CALC, ""),
            ("🔖 书签", TYPE_BOOKMARK, ""),
            ("🗑 回收站", TYPE_TRASH, ""),
            ("🚀 应用启动器", TYPE_LAUNCHER, ""),
            ("🎵 媒体控制", TYPE_MEDIA, ""),
            ("🖼 相册", TYPE_GALLERY, ""),
            ("💻 系统信息", TYPE_SYSINFO, ""),
            ("📰 RSS", TYPE_RSS, ""),
            ("📌 Dock栏", TYPE_DOCK, ""),
        ]
        for label, t, cmd in _simple:
            act = add_menu.addAction(label)
            act.triggered.connect(lambda _, tp=t, c=cmd: self._quick_add(tp, c))

        add_menu.addSeparator()

        clock_sub = add_menu.addMenu("🕐 时钟")
        clock_sub.setStyleSheet(_style)
        for sub_id, sub_name in CLOCK_SUB_LABELS.items():
            act = clock_sub.addAction(sub_name)
            act.triggered.connect(lambda _, s=sub_id: self._quick_add(TYPE_CLOCK, s))

        mon_sub = add_menu.addMenu("📊 系统监控")
        mon_sub.setStyleSheet(_style)
        for sub_id, sub_name in MONITOR_SUB_LABELS.items():
            act = mon_sub.addAction(sub_name)
            act.triggered.connect(lambda _, s=sub_id: self._quick_add(TYPE_MONITOR, s))

        weather_act = add_menu.addAction("🌤 天气")
        weather_act.triggered.connect(lambda: self._quick_add(TYPE_WEATHER))

        add_menu.addSeparator()
        cmd_act = add_menu.addAction("⌨ CMD 命令")
        cmd_act.triggered.connect(lambda: self._quick_add(TYPE_CMD))
        cmdwin_act = add_menu.addAction("🖥 CMD 窗口")
        cmdwin_act.triggered.connect(lambda: self._quick_add(TYPE_CMD_WINDOW))
        shortcut_act = add_menu.addAction("🔗 快捷方式")
        shortcut_act.triggered.connect(lambda: self._quick_add(TYPE_SHORTCUT))

        menu.addSeparator()

        panel_menu = menu.addMenu("面板")
        panel_menu.setStyleSheet(self._ctx_menu_style())
        _is_per_mon = _settings.get("monitor_mode") == "per_monitor"
        _mpm = _settings.get("monitor_panel_map", {})
        _cur_screen = QApplication.screenAt(pos)
        _cur_screen_name = _cur_screen.name() if _cur_screen else ""
        _cur_panel_idx = _mpm.get(_cur_screen_name, self._active) if _is_per_mon else self._active
        for i, pd in enumerate(self._panels_data):
            is_cur = (i == _cur_panel_idx) if _is_per_mon else (i == self._active)
            label = ("● " if is_cur else "    ") + pd.name
            if _is_per_mon:
                tags = []
                for sn, pi in _mpm.items():
                    if pi == i:
                        if sn == _cur_screen_name:
                            tags.append("当前显示器")
                        else:
                            tags.append(sn)
                if tags:
                    label += "  (" + ", ".join(tags) + ")"
            act = panel_menu.addAction(label)
            if _is_per_mon and _cur_screen_name:
                act.triggered.connect(lambda checked, idx=i, scr=_cur_screen_name: self._assign_panel_to_monitor(scr, idx))
            else:
                act.triggered.connect(lambda checked, idx=i: self._switch_panel(idx))
        panel_menu.addSeparator()
        add_panel_act = panel_menu.addAction("＋  新建面板")
        add_panel_act.triggered.connect(self._on_add_panel)
        if len(self._panels_data) > 1:
            _can_delete = True
            if _is_per_mon and len(self._panels_data) <= len(QApplication.screens()):
                _can_delete = False
            rename_act = panel_menu.addAction("✏  重命名当前面板")
            rename_act.triggered.connect(lambda: self._on_rename_panel(self._active))
            if _can_delete:
                del_act = panel_menu.addAction("🗑  删除当前面板")
                del_act.triggered.connect(lambda: self._on_delete_panel(self._active))
        copy_act = panel_menu.addAction("📋  复制当前面板")
        copy_act.triggered.connect(lambda: self._on_copy_panel(self._active))

        menu.addSeparator()
        win_menu = menu.addMenu("🪟  启动窗口级面板")
        win_menu.setStyleSheet(self._ctx_menu_style())
        for i, pd in enumerate(self._panels_data):
            is_open = pd.id in self._panel_windows
            label = ("✔ " if is_open else "    ") + pd.name
            act = win_menu.addAction(label)
            act.triggered.connect(lambda checked, idx=i: self._launch_panel_window(idx))

        menu.addSeparator()
        grid_act = menu.addAction("隐藏网格" if _settings.get("show_grid", True) else "显示网格")
        grid_act.triggered.connect(self._toggle_grid)
        lock_act = menu.addAction("解锁布局" if self._locked else "锁定布局")
        lock_act.triggered.connect(self._toggle_lock)

        menu.addSeparator()
        imp_act = menu.addAction("📥  导入")
        imp_act.triggered.connect(self._on_import)
        exp_act = menu.addAction("📤  导出")
        exp_act.triggered.connect(self._on_export)

        menu.addSeparator()
        settings_act = menu.addAction("⚙  设置")
        settings_act.triggered.connect(self._on_settings)

        menu.addSeparator()
        quit_act = menu.addAction("退出 FastPanel")
        quit_act.triggered.connect(self._quit_app)

        menu.exec_(pos)

    def _create_panel(self, name, pd=None):
        pd = pd or PanelData(name=name); self._panels_data.append(pd)
        sc = QScrollArea(); sc.setWidgetResizable(False)
        sc.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        if _DESKTOP_MODE:
            sc.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        g = GridPanel(); g.data_changed.connect(self._on_data_changed)
        if self._desktop_mode:
            g.desktop_ctx_menu_requested.connect(self._show_desktop_ctx_menu)
            if self._desktop_backend:
                avail = self._desktop_backend.get_available_geometry()
                full = self._desktop_backend.get_full_geometry()
                safe_t = avail.y() - full.y()
                safe_b = (full.y() + full.height()) - (avail.y() + avail.height())
                g.set_safe_margins(safe_t, safe_b)
        sc.setWidget(g)
        self._grids.append(g); self._scrolls.append(sc); self._stack.addWidget(sc)
        idx = self._tab_bar.add_tab(name)
        for cd in pd.components: g.add_component(cd)
        groups: dict[str, list[str]] = {}
        for w in g.components:
            gid = getattr(w.data, '_group_id', None)
            if gid:
                groups.setdefault(gid, []).append(w.data.id)
                w.setProperty("locked", True)
        g._groups = groups
        g._update_overlay()
        return idx

    def _switch_panel(self, idx):
        if 0<=idx<len(self._panels_data):
            self._active = idx; self._stack.setCurrentIndex(idx)
            self._tab_bar.set_active(idx); self._update_count()
            QTimer.singleShot(0, self._sync_sizes)

    def _on_add_panel(self):
        ok, name = _input_dialog(self, "新建 Panel", "名称：", "新面板")
        if ok:
            n = name.strip() or "新面板"
            idx = self._create_panel(n); self._switch_panel(idx); self._save_data()

    def _on_rename_panel(self, idx):
        if 0<=idx<len(self._panels_data):
            ok, name = _input_dialog(self, "重命名", "新名称：", self._panels_data[idx].name)
            if ok:
                n = name.strip()
                if n: self._panels_data[idx].name = n; self._tab_bar.rename_tab(idx, n); self._save_data()

    def _on_copy_panel(self, idx):
        if 0 <= idx < len(self._panels_data):
            src = self._panels_data[idx]
            ok, name = _input_dialog(self, "复制面板", "新面板名称：", src.name + " - 副本")
            if ok:
                n = name.strip() or src.name + " - 副本"
                new_pd = PanelData(name=n, components=[
                    ComponentData(
                        name=c.name, comp_type=c.comp_type, sub_type=c.sub_type,
                        cmd=c.cmd, show_output=c.show_output,
                        icon=c.icon, path=c.path,
                        x=c.x, y=c.y, w=c.w, h=c.h,
                        param_hints=list(c.param_hints),
                        param_defaults=list(c.param_defaults),
                    ) for c in src.components
                ])
                new_idx = self._create_panel(n)
                grid = self._grids[new_idx]
                for c in new_pd.components:
                    grid.add_component(c)
                self._switch_panel(new_idx)
                self._save_data()

    def _on_delete_panel(self, idx):
        if len(self._panels_data) <= 1: return
        if _settings.get("monitor_mode") == "per_monitor":
            n_screens = len(QApplication.screens())
            if len(self._panels_data) <= n_screens:
                _confirm_dialog(self, "无法删除",
                    f"当前为「每个显示器独立面板」模式，面板数量（{len(self._panels_data)}）"
                    f"不能少于显示器数量（{n_screens}）。")
                return
        if not _confirm_dialog(self, "确认", f"删除面板「{self._panels_data[idx].name}」？"): return
        self._panels_data.pop(idx); g = self._grids.pop(idx); s = self._scrolls.pop(idx)
        g.clear_all(); s.deleteLater(); self._tab_bar.remove_tab(idx)
        if _settings.get("monitor_mode") == "per_monitor":
            mpm = _settings.get("monitor_panel_map", {})
            new_mpm = {}
            for sn, pi in mpm.items():
                if pi == idx:
                    new_mpm[sn] = min(idx, len(self._panels_data) - 1)
                elif pi > idx:
                    new_mpm[sn] = pi - 1
                else:
                    new_mpm[sn] = pi
            _settings["monitor_panel_map"] = new_mpm
            _save_settings(_settings)
            self._enter_per_monitor_mode()
        else:
            self._switch_panel(min(idx, len(self._panels_data)-1))
        self._save_data()

    def _assign_panel_to_monitor(self, screen_name, panel_idx):
        mpm = _settings.get("monitor_panel_map", {})
        old_panel = mpm.get(screen_name)
        for sn, pi in list(mpm.items()):
            if pi == panel_idx and sn != screen_name:
                if old_panel is not None:
                    mpm[sn] = old_panel
                break
        mpm[screen_name] = panel_idx
        _settings["monitor_panel_map"] = mpm
        _save_settings(_settings)
        if getattr(self, '_per_monitor_active', False):
            self._enter_per_monitor_mode()
        else:
            self._switch_panel(panel_idx)

    def _enter_per_monitor_mode(self):
        if not self._desktop_mode:
            return
        mpm = _settings.get("monitor_panel_map", {})
        if not mpm:
            return
        self._per_monitor_active = True
        self._stack.hide()
        cw = self.centralWidget()
        full_geo = self._desktop_backend.get_full_geometry() if self._desktop_backend else QApplication.primaryScreen().virtualGeometry()
        for sc in self._scrolls:
            sc.hide()
        shown_panels = set()
        for screen in QApplication.screens():
            sn = screen.name()
            pi = mpm.get(sn, 0)
            if 0 <= pi < len(self._scrolls) and pi not in shown_panels:
                shown_panels.add(pi)
                sc = self._scrolls[pi]
                if sc.parent() != cw:
                    sc.setParent(cw)
                geo = screen.geometry()
                x = geo.x() - full_geo.x()
                y = geo.y() - full_geo.y()
                sc.setGeometry(x, y, geo.width(), geo.height())
                sc.show()
                sc.raise_()
                g = self._grids[pi]
                g.recalc_size(geo.width(), geo.height())
        cur_screen = QApplication.screenAt(QCursor.pos())
        if cur_screen and cur_screen.name() in mpm:
            self._active = mpm[cur_screen.name()]
            self._tab_bar.set_active(self._active)
            self._update_count()

    def _exit_per_monitor_mode(self):
        self._per_monitor_active = False
        for sc in self._scrolls:
            sc.setParent(self._stack)
            self._stack.addWidget(sc)
        self._stack.show()
        self._switch_panel(self._active)

    def _auto_switch_monitor_panel(self):
        if not self._desktop_mode or _settings.get("monitor_mode") != "per_monitor":
            return
        mpm = _settings.get("monitor_panel_map", {})
        cur_screen = QApplication.screenAt(QCursor.pos())
        if cur_screen and cur_screen.name() in mpm:
            target = mpm[cur_screen.name()]
            if target != self._active and 0 <= target < len(self._panels_data):
                self._active = target
                self._tab_bar.set_active(target)
                self._update_count()

    def _cg(self): return self._grids[self._active]
    def _cs(self): return self._scrolls[self._active]

    def resizeEvent(self, e):
        super().resizeEvent(e); self._sync_sizes()
        if self._tab_autohide:
            self._position_hover_zone()
    def showEvent(self, e): super().showEvent(e); QTimer.singleShot(0, self._sync_sizes)
    def _sync_sizes(self):
        if getattr(self, '_per_monitor_active', False):
            self._enter_per_monitor_mode()
            return
        for s, g in zip(self._scrolls, self._grids):
            vp = s.viewport(); g.recalc_size(vp.width(), vp.height())
    def _update_count(self): self._cnt.setText(f"{len(self._cg().components)} 个组件")

    def _next_pos(self):
        cs = self._cg().components
        safe_top = self._cg()._safe_margin_top
        start_y = max(40, safe_top + GRID_SIZE)
        if not cs: return 40, snap(start_y)
        vw = self._cs().viewport().width(); mr, ry, rb = 0, 0, 0
        for c in cs:
            r = c.data.x+c.data.w; b = c.data.y+c.data.h
            if r > mr: mr, ry = r, c.data.y
            if b > rb: rb = b
        x, y = mr+GRID_SIZE, ry
        if x+320 > vw: x, y = 40, rb+GRID_SIZE
        return snap(x), snap(y)

    def _find_free_pos(self, grid, w, h, safe_top, safe_bot):
        gw = grid.width()
        gh = grid.height()
        occupied = [(c.data.x, c.data.y, c.data.w, c.data.h) for c in grid.components]
        start_y = ((safe_top + GRID_SIZE - 1) // GRID_SIZE) * GRID_SIZE
        max_y = gh - safe_bot - h

        def overlaps(nx, ny):
            for ox, oy, ow, oh in occupied:
                if nx < ox + ow and nx + w > ox and ny < oy + oh and ny + h > oy:
                    return True
            return False

        for y in range(start_y, max_y + 1, GRID_SIZE):
            for x in range(0, gw - w + 1, GRID_SIZE):
                if not overlaps(x, y):
                    return (x, y)
        return None

    def _apply_default_size(self, d):
        """Set default w/h for a ComponentData based on its type."""
        t = d.comp_type
        if t == TYPE_CMD:
            np = count_params(d.cmd)
            if d.show_output:
                d.w = 320; d.h = max(160 + np * 38 + 120, 300)
            elif np > 0:
                d.w = 320; d.h = GRID_SIZE * 2 + np * 38
            else:
                d.w = GRID_SIZE * 13; d.h = GRID_SIZE * 2
        elif t == TYPE_CMD_WINDOW:
            d.w = 320; d.h = 340
        elif t == TYPE_SHORTCUT:
            d.w = GRID_SIZE * 4; d.h = GRID_SIZE * 4
        elif t == TYPE_CALENDAR:
            d.w = GRID_SIZE * 16; d.h = GRID_SIZE * 16
        elif t == TYPE_WEATHER:
            d.w = GRID_SIZE * 14; d.h = GRID_SIZE * 12
        elif t == TYPE_DOCK:
            d.w = GRID_SIZE * 20; d.h = GRID_SIZE * 5
        elif t == TYPE_TODO:
            d.w = GRID_SIZE * 14; d.h = GRID_SIZE * 12
        elif t == TYPE_CLOCK:
            sub = d.cmd.split("|")[0] if d.cmd else CLOCK_SUB_CLOCK
            if sub == CLOCK_SUB_STOPWATCH:
                d.w = GRID_SIZE * 12; d.h = GRID_SIZE * 12
            elif sub == CLOCK_SUB_TIMER:
                d.w = GRID_SIZE * 12; d.h = GRID_SIZE * 10
            else:
                d.w = GRID_SIZE * 10; d.h = GRID_SIZE * 8
        elif t == TYPE_MONITOR:
            sub = d.cmd.strip() if d.cmd else MONITOR_SUB_ALL
            if sub == MONITOR_SUB_ALL:
                d.w = GRID_SIZE * 22; d.h = GRID_SIZE * 18
            elif sub == MONITOR_SUB_DISK:
                d.w = GRID_SIZE * 18; d.h = GRID_SIZE * 10
            else:
                d.w = GRID_SIZE * 14; d.h = GRID_SIZE * 10
        else:
            _sizes = {
                TYPE_LAUNCHER: (16, 20), TYPE_NOTE: (12, 10), TYPE_QUICKACTION: (18, 12),
                TYPE_MEDIA: (16, 7), TYPE_CLIPBOARD: (14, 14), TYPE_TIMER: (12, 10),
                TYPE_GALLERY: (14, 12), TYPE_SYSINFO: (16, 14), TYPE_BOOKMARK: (14, 12),
                TYPE_CALC: (14, 16), TYPE_TRASH: (10, 8), TYPE_RSS: (16, 16),
            }
            gw, gh = _sizes.get(t, (10, 8))
            d.w = GRID_SIZE * gw; d.h = GRID_SIZE * gh

    def _on_add(self):
        dlg = CreateDialog(self)
        if dlg.exec_()==QDialog.Accepted:
            d = dlg.get_data()
            d.x, d.y = self._next_pos()
            if d.comp_type == TYPE_CMD:
                np = count_params(d.cmd)
                if d.show_output:
                    d.w = 320; d.h = max(160 + np * 38 + 120, 300)
                elif np > 0:
                    d.w = 320; d.h = GRID_SIZE * 2 + np * 38
                else:
                    d.w = GRID_SIZE * 13; d.h = GRID_SIZE * 2
            elif d.comp_type == TYPE_CMD_WINDOW:
                d.w = 320; d.h = 340
            elif d.comp_type == TYPE_SHORTCUT:
                d.w = GRID_SIZE * 4; d.h = GRID_SIZE * 4
            elif d.comp_type == TYPE_CALENDAR:
                d.w = GRID_SIZE * 16; d.h = GRID_SIZE * 16
            elif d.comp_type == TYPE_WEATHER:
                d.w = GRID_SIZE * 14; d.h = GRID_SIZE * 12
            elif d.comp_type == TYPE_DOCK:
                d.w = GRID_SIZE * 20; d.h = GRID_SIZE * 5
            elif d.comp_type == TYPE_TODO:
                d.w = GRID_SIZE * 14; d.h = GRID_SIZE * 12
            elif d.comp_type == TYPE_CLOCK:
                sub = d.cmd.split("|")[0] if d.cmd else CLOCK_SUB_CLOCK
                if sub == CLOCK_SUB_STOPWATCH:
                    d.w = GRID_SIZE * 12; d.h = GRID_SIZE * 12
                elif sub == CLOCK_SUB_TIMER:
                    d.w = GRID_SIZE * 12; d.h = GRID_SIZE * 10
                else:
                    d.w = GRID_SIZE * 10; d.h = GRID_SIZE * 8
            elif d.comp_type == TYPE_MONITOR:
                sub = d.cmd.strip() if d.cmd else MONITOR_SUB_ALL
                if sub == MONITOR_SUB_ALL:
                    d.w = GRID_SIZE * 22; d.h = GRID_SIZE * 18
                elif sub == MONITOR_SUB_DISK:
                    d.w = GRID_SIZE * 18; d.h = GRID_SIZE * 10
                else:
                    d.w = GRID_SIZE * 14; d.h = GRID_SIZE * 10
            elif d.comp_type == TYPE_LAUNCHER:
                d.w = GRID_SIZE * 16; d.h = GRID_SIZE * 20
            elif d.comp_type == TYPE_NOTE:
                d.w = GRID_SIZE * 12; d.h = GRID_SIZE * 10
            elif d.comp_type == TYPE_QUICKACTION:
                d.w = GRID_SIZE * 18; d.h = GRID_SIZE * 12
            elif d.comp_type == TYPE_MEDIA:
                d.w = GRID_SIZE * 16; d.h = GRID_SIZE * 7
            elif d.comp_type == TYPE_CLIPBOARD:
                d.w = GRID_SIZE * 14; d.h = GRID_SIZE * 14
            elif d.comp_type == TYPE_TIMER:
                d.w = GRID_SIZE * 12; d.h = GRID_SIZE * 10
            elif d.comp_type == TYPE_GALLERY:
                d.w = GRID_SIZE * 14; d.h = GRID_SIZE * 12
            elif d.comp_type == TYPE_SYSINFO:
                d.w = GRID_SIZE * 16; d.h = GRID_SIZE * 14
            elif d.comp_type == TYPE_BOOKMARK:
                d.w = GRID_SIZE * 14; d.h = GRID_SIZE * 12
            elif d.comp_type == TYPE_CALC:
                d.w = GRID_SIZE * 14; d.h = GRID_SIZE * 16
            elif d.comp_type == TYPE_TRASH:
                d.w = GRID_SIZE * 12; d.h = GRID_SIZE * 7
            elif d.comp_type == TYPE_RSS:
                d.w = GRID_SIZE * 16; d.h = GRID_SIZE * 16
            else:
                d.w = 320; d.h = 200
            grid = self._cg()
            gw = grid.width()
            safe_top = grid._safe_margin_top
            safe_bot = grid._safe_margin_bottom
            gh = grid.height() - safe_top - safe_bot
            if d.w > gw or d.h > gh:
                _confirm_dialog(self, "提示", "布局空间不足，请先调整布局")
                return
            pos = self._find_free_pos(grid, d.w, d.h, safe_top, safe_bot)
            if pos is None:
                _confirm_dialog(self, "提示", "布局空间不足，请先调整布局")
                return
            d.x, d.y = pos
            grid.add_component(d)
            self._panels_data[self._active].components.append(d)
            self._update_count(); self._sync_sizes()

    def _on_data_changed(self):
        self._update_count(); self._sync_data(); self._save_data()

    def _sync_data(self):
        for i, g in enumerate(self._grids):
            self._panels_data[i].components = [w.data for w in g.components]

    def _save_data(self):
        self._sync_data()
        try:
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump({"active": self._active, "panels": [p.to_dict() for p in self._panels_data]},
                          f, ensure_ascii=False, indent=2)
        except Exception: pass

    def _load_data(self):
        if not os.path.exists(DATA_FILE): return
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f: obj = json.load(f)
            if isinstance(obj, list):
                pd = PanelData(name="默认", components=[ComponentData.from_dict(d) for d in obj])
                self._create_panel("默认", pd); self._switch_panel(0); return
            for p in obj.get("panels", []): self._create_panel(PanelData.from_dict(p).name, PanelData.from_dict(p))
            if self._panels_data: self._switch_panel(min(obj.get("active", 0), len(self._panels_data)-1))
        except Exception: pass

    def _first_launch_setup(self):
        screens = QApplication.screens()
        if self._desktop_mode and len(screens) > 1 and not _settings.get("_monitor_mode_chosen"):
            from PyQt5.QtWidgets import QDialogButtonBox
            dlg = QDialog(self)
            dlg.setWindowTitle("多显示器设置")
            dlg.setFixedWidth(420)
            dlg.setStyleSheet(_dialog_style())
            lay = QVBoxLayout(dlg); lay.setSpacing(16); lay.setContentsMargins(28, 24, 28, 24)
            h = QLabel("🖥  检测到多个显示器"); h.setObjectName("heading"); lay.addWidget(h)
            info = QLabel(f"当前有 {len(screens)} 个显示器，请选择布局方式：")
            info.setStyleSheet(f"color:{C['subtext0']};font-size:13px;")
            info.setWordWrap(True); lay.addWidget(info)

            opt1 = QPushButton("📐 所有显示器共用一个面板")
            opt1.setStyleSheet(f"QPushButton{{background:{C['surface0']};color:{C['text']};border:1px solid {C['surface2']};"
                               f"border-radius:10px;padding:14px;font-size:13px;text-align:left;}}"
                               f"QPushButton:hover{{border-color:{C['blue']};background:{C['surface1']};}}")
            opt1.setCursor(Qt.PointingHandCursor)
            lay.addWidget(opt1)

            opt2 = QPushButton("🖥 每个显示器独立面板")
            opt2.setStyleSheet(f"QPushButton{{background:{C['surface0']};color:{C['text']};border:1px solid {C['surface2']};"
                               f"border-radius:10px;padding:14px;font-size:13px;text-align:left;}}"
                               f"QPushButton:hover{{border-color:{C['blue']};background:{C['surface1']};}}")
            opt2.setCursor(Qt.PointingHandCursor)
            lay.addWidget(opt2)

            choice = [None]
            opt1.clicked.connect(lambda: (choice.__setitem__(0, "single"), dlg.accept()))
            opt2.clicked.connect(lambda: (choice.__setitem__(0, "per_monitor"), dlg.accept()))
            dlg.exec_()

            _settings["_monitor_mode_chosen"] = True
            _settings["monitor_mode"] = choice[0] or "single"
            _save_settings(_settings)

            if choice[0] == "per_monitor":
                for s in screens:
                    self._create_panel(s.name())
                self._switch_panel(0)
                return

        self._create_panel("默认"); self._switch_panel(0)

    def _ask_monitor_mode(self):
        screens = QApplication.screens()
        dlg = QDialog(self)
        dlg.setWindowTitle("多显示器设置")
        dlg.setFixedWidth(420)
        dlg.setStyleSheet(_dialog_style())
        lay = QVBoxLayout(dlg); lay.setSpacing(16); lay.setContentsMargins(28, 24, 28, 24)
        h = QLabel("🖥  检测到多个显示器"); h.setObjectName("heading"); lay.addWidget(h)
        info = QLabel(f"当前有 {len(screens)} 个显示器，请选择布局方式：")
        info.setStyleSheet(f"color:{C['subtext0']};font-size:13px;")
        info.setWordWrap(True); lay.addWidget(info)

        opt1 = QPushButton("📐 所有显示器共用一个面板")
        opt1.setStyleSheet(f"QPushButton{{background:{C['surface0']};color:{C['text']};border:1px solid {C['surface2']};"
                           f"border-radius:10px;padding:14px;font-size:13px;text-align:left;}}"
                           f"QPushButton:hover{{border-color:{C['blue']};background:{C['surface1']};}}")
        opt1.setCursor(Qt.PointingHandCursor); lay.addWidget(opt1)

        opt2 = QPushButton("🖥 每个显示器独立面板")
        opt2.setStyleSheet(f"QPushButton{{background:{C['surface0']};color:{C['text']};border:1px solid {C['surface2']};"
                           f"border-radius:10px;padding:14px;font-size:13px;text-align:left;}}"
                           f"QPushButton:hover{{border-color:{C['blue']};background:{C['surface1']};}}")
        opt2.setCursor(Qt.PointingHandCursor); lay.addWidget(opt2)

        choice = [None]
        opt1.clicked.connect(lambda: (choice.__setitem__(0, "single"), dlg.accept()))
        opt2.clicked.connect(lambda: (choice.__setitem__(0, "per_monitor"), dlg.accept()))
        dlg.exec_()

        _settings["_monitor_mode_chosen"] = True
        _settings["monitor_mode"] = choice[0] or "single"
        _save_settings(_settings)

        if choice[0] == "per_monitor":
            self._apply_per_monitor_panels()

    def _apply_per_monitor_panels(self):
        screens = QApplication.screens()
        needed = len(screens) - len(self._panels_data)
        if needed > 0:
            existing_names = {p.name for p in self._panels_data}
            idx = 1
            for _ in range(needed):
                name = f"面板{idx}"
                while name in existing_names:
                    idx += 1
                    name = f"面板{idx}"
                existing_names.add(name)
                self._create_panel(name)
                idx += 1
        mpm = _settings.get("monitor_panel_map", {})
        for i, s in enumerate(screens):
            if s.name() not in mpm:
                mpm[s.name()] = min(i, len(self._panels_data) - 1)
        _settings["monitor_panel_map"] = mpm
        _save_settings(_settings)
        self._enter_per_monitor_mode()
        self._save_data()

    def _on_export(self):
        dlg = ExportDialog(self._panels_data, self)
        if dlg.exec_() != QDialog.Accepted:
            return
        data = dlg.get_export_data()
        if not data:
            return
        p, _ = QFileDialog.getSaveFileName(self, "导出", os.path.expanduser("~/fastpanel_export.json"), "JSON (*.json)")
        if p:
            try:
                with open(p, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            except Exception:
                pass

    def _on_import(self):
        p, _ = QFileDialog.getOpenFileName(self, "导入", os.path.expanduser("~"), "JSON (*.json)")
        if not p: return
        try:
            with open(p, "r", encoding="utf-8") as f: obj = json.load(f)
        except Exception:
            return
        if not isinstance(obj, list) or not obj:
            return
        has_existing = any(len(pd.components) > 0 for pd in self._panels_data)
        mode = "direct"
        if has_existing:
            dlg = QDialog(self)
            dlg.setWindowTitle("导入方式")
            dlg.setFixedWidth(340)
            dlg.setStyleSheet(_dialog_style())
            dl = QVBoxLayout(dlg); dl.setContentsMargins(24, 20, 24, 20); dl.setSpacing(12)
            lbl = QLabel("检测到当前已有组件，请选择导入方式：")
            lbl.setStyleSheet(f"color:{C['text']}; font-size:13px;")
            dl.addWidget(lbl)
            overwrite_btn = QPushButton("覆盖 — 替换所有现有数据")
            overwrite_btn.setStyleSheet(f"background:{C['red']}; color:{C['crust']}; border:none; border-radius:8px; padding:10px; font-size:13px; font-weight:bold;")
            overwrite_btn.setCursor(Qt.PointingHandCursor)
            overwrite_btn.clicked.connect(lambda: (setattr(dlg, '_mode', 'overwrite'), dlg.accept()))
            dl.addWidget(overwrite_btn)
            append_btn = QPushButton("新增 — 导入到新面板，保留现有数据")
            append_btn.setStyleSheet(f"background:{C['blue']}; color:{C['crust']}; border:none; border-radius:8px; padding:10px; font-size:13px; font-weight:bold;")
            append_btn.setCursor(Qt.PointingHandCursor)
            append_btn.clicked.connect(lambda: (setattr(dlg, '_mode', 'append'), dlg.accept()))
            dl.addWidget(append_btn)
            cancel_btn = QPushButton("取消")
            cancel_btn.setStyleSheet(f"background:{C['surface1']}; color:{C['text']}; border:none; border-radius:8px; padding:8px; font-size:12px;")
            cancel_btn.setCursor(Qt.PointingHandCursor)
            cancel_btn.clicked.connect(dlg.reject)
            dl.addWidget(cancel_btn)
            if dlg.exec_() != QDialog.Accepted:
                return
            mode = getattr(dlg, '_mode', 'append')

        is_panel_format = obj and isinstance(obj[0], dict) and "components" in obj[0]

        if mode == "overwrite":
            while len(self._panels_data) > 0:
                idx = len(self._panels_data) - 1
                self._panels_data.pop(idx)
                g = self._grids.pop(idx); s = self._scrolls.pop(idx)
                g.clear_all(); self._stack.removeWidget(s); s.deleteLater()
            while self._tab_bar.count():
                self._tab_bar.removeTab(0)

        if is_panel_format:
            for panel_d in obj:
                name = panel_d.get("name", "导入面板")
                comps = [ComponentData.from_dict(c) for c in panel_d.get("components", [])]
                for c in comps: c.id = str(uuid.uuid4())
                pd = PanelData(name=name, components=comps)
                self._create_panel(name, pd)
        else:
            for d in obj:
                data = ComponentData.from_dict(d); data.id = str(uuid.uuid4())
                self._cg().add_component(data)

        if self._panels_data:
            self._tab_bar.setCurrentIndex(0)
            self._switch_panel(0)
        self._update_count(); self._sync_sizes(); self._save_data()

    def eventFilter(self, obj, event):
        if obj == self._tab_hover_zone and event.type() == event.Enter:
            if self._tab_autohide:
                self._tab_bar_container.show()
                self._tab_hover_zone.hide()
            return False
        if obj == self._tab_bar_container and event.type() == event.Leave:
            if self._tab_autohide:
                self._tab_bar_container.hide()
                self._tab_hover_zone.show()
                self._position_hover_zone()
            return False
        return super().eventFilter(obj, event)

    def _position_hover_zone(self):
        cw = self.centralWidget()
        if cw:
            self._tab_hover_zone.setGeometry(0, cw.height() - 4, cw.width(), 4)

    def _toggle_tab_autohide(self):
        self._tab_autohide = not self._tab_autohide
        if self._tab_autohide:
            self._tab_bar_container.hide()
            self._tab_hover_zone.show()
            self._position_hover_zone()
        else:
            self._tab_bar_container.show()
            self._tab_hover_zone.hide()

    def _toggle_max(self):
        if self._desktop_mode:
            return
        if self.isMaximized():
            self.showNormal()
            if self._max_btn: self._max_btn._is_restore = False
        else:
            self.showMaximized()
            if self._max_btn: self._max_btn._is_restore = True
        if self._max_btn: self._max_btn.update()

    def _toggle_grid(self):
        show = not _settings.get("show_grid", True)
        _settings["show_grid"] = show
        self._grid_btn.setProperty("active", show)
        self._grid_btn.style().unpolish(self._grid_btn)
        self._grid_btn.style().polish(self._grid_btn)
        for g in self._grids:
            g.set_show_grid(show)
            g.update()
        _save_settings(_settings)

    def _toggle_lock(self):
        self._locked = not self._locked
        if not self._desktop_mode:
            self._lock_btn.setText("🔒" if self._locked else "🔓")
            self._lock_btn.setProperty("locked", self._locked)
            self._lock_btn.style().unpolish(self._lock_btn)
            self._lock_btn.style().polish(self._lock_btn)
        if hasattr(self, '_tray_lock_act'):
            self._tray_lock_act.setText("解锁布局" if self._locked else "锁定布局")
        for g in self._grids:
            for w in g.components:
                w.setProperty("locked", self._locked)

    def _on_settings(self):
        if hasattr(self, '_settings_dlg') and self._settings_dlg is not None:
            try:
                if self._settings_dlg.isVisible():
                    self._settings_dlg.raise_()
                    self._settings_dlg.activateWindow()
                    return
            except RuntimeError:
                self._settings_dlg = None
        dlg = SettingsDialog(self)
        self._settings_dlg = dlg
        if dlg.exec_() == QDialog.Accepted:
            global C, _settings
            s = dlg.get_settings()
            _settings.update(s)
            _save_settings(_settings)
            C.update(THEMES.get(s["theme"], THEMES["Catppuccin Mocha"]))
            self._apply_style()
            cs = _comp_style()
            for g in self._grids:
                pal = g.palette(); pal.setColor(pal.Window, QColor(C["crust"])); g.setPalette(pal)
                g.set_bg_image(s.get("bg_image", ""), s.get("bg_opacity", 30))
                g.set_bg_gradient(s.get("bg_gradient", ""))
                g.set_bg_mode(s.get("bg_mode", "tile"))
                g.set_per_monitor_bg(s.get("bg_per_monitor", {}))
                g.set_bg_slideshow(s.get("bg_slideshow_dir", ""), s.get("bg_slideshow_interval", 300))
                g.set_show_grid(_settings.get("show_grid", True))
                for w in g.components:
                    w.setStyleSheet(cs)
                    w.refresh_theme()
                g.update()
            if self._desktop_mode and "hotkeys" in s:
                self._stop_hotkeys()
                self._setup_hotkeys()
            if "_autostart" in s:
                _set_autostart(s["_autostart"])
                s.pop("_autostart", None)
            if _settings.get("monitor_mode") == "per_monitor":
                self._apply_per_monitor_panels()
                if not hasattr(self, '_mon_switch_timer') or self._mon_switch_timer is None:
                    self._mon_switch_timer = QTimer(self)
                    self._mon_switch_timer.timeout.connect(self._auto_switch_monitor_panel)
                    self._mon_switch_timer.start(500)
            else:
                if hasattr(self, '_mon_switch_timer') and self._mon_switch_timer is not None:
                    self._mon_switch_timer.stop()
                    self._mon_switch_timer = None
                if getattr(self, '_per_monitor_active', False):
                    self._exit_per_monitor_mode()

    def mousePressEvent(self, e):
        if self._desktop_mode:
            super().mousePressEvent(e); return
        if e.button() == Qt.LeftButton and self._toolbar.geometry().contains(e.pos()):
            self._tb_dragging = True
            self._tb_offset = e.globalPos() - self.frameGeometry().topLeft()
            e.accept()
        else:
            super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._desktop_mode:
            super().mouseMoveEvent(e); return
        if self._tb_dragging:
            if self.isMaximized():
                ratio = e.pos().x() / self.width()
                self.showNormal()
                if self._max_btn:
                    self._max_btn._is_restore = False; self._max_btn.update()
                new_x = int(self.width() * ratio)
                self._tb_offset = QPoint(new_x, e.pos().y())
            self.move(e.globalPos() - self._tb_offset)
            e.accept()
        else:
            super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        self._tb_dragging = False
        super().mouseReleaseEvent(e)

    def mouseDoubleClickEvent(self, e):
        if self._desktop_mode:
            super().mouseDoubleClickEvent(e); return
        if self._toolbar.geometry().contains(e.pos()):
            self._toggle_max()
        else:
            super().mouseDoubleClickEvent(e)

    def closeEvent(self, e):
        self._save_data()
        if hasattr(self, '_tray'):
            self._tray.hide()
        super().closeEvent(e)


def _ensure_single_instance():
    import fcntl
    lock_path = os.path.join(os.path.expanduser("~"), ".fastpanel.lock")
    fp = open(lock_path, 'w')
    try:
        fcntl.flock(fp, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fp.write(str(os.getpid()))
        fp.flush()
        return fp
    except IOError:
        try:
            old_pid = int(open(lock_path).read().strip())
            os.kill(old_pid, 0)
            print(f"[FastPanel] 已有实例运行 (PID {old_pid})，正在退出...", flush=True)
            sys.exit(0)
        except (ValueError, ProcessLookupError, PermissionError):
            fcntl.flock(fp, fcntl.LOCK_EX)
            fp.seek(0); fp.truncate()
            fp.write(str(os.getpid()))
            fp.flush()
            return fp


def main():
    lock_fp = _ensure_single_instance()

    parser = argparse.ArgumentParser(description="FastPanel — Desktop Widget Engine")
    parser.add_argument("--windowed", action="store_true", help="以窗口模式运行（默认为桌面模式）")
    parser.add_argument("--desktop", action="store_true", help="强制桌面模式")
    args = parser.parse_args()

    global _DESKTOP_MODE
    if args.windowed:
        _DESKTOP_MODE = False
    elif args.desktop:
        _DESKTOP_MODE = True
    else:
        _DESKTOP_MODE = True

    os.environ.setdefault("QT_IM_MODULE", "fcitx")
    app = QApplication(sys.argv)
    app.setDesktopFileName("fastpanel")
    app.setQuitOnLastWindowClosed(not _DESKTOP_MODE)
    font = QFont(); font.setFamily("Noto Sans CJK SC"); font.setPointSize(10); app.setFont(font)
    app.setStyle("Fusion")
    app.setStyleSheet(f"""
        QToolTip {{
            background: {C['surface0']}; color: {C['text']};
            border: 1px solid {C['surface1']}; border-radius: 4px;
            padding: 4px 8px; font-size: 12px;
        }}
    """)
    if sys.platform == "linux":
        try:
            _install_desktop_entry()
        except Exception:
            pass
    win = MainWindow()
    if _DESKTOP_MODE:
        win.show()
    else:
        win.showMaximized()
        if win._max_btn:
            win._max_btn._is_restore = True; win._max_btn.update()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
