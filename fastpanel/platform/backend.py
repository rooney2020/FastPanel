import os
import sys
import subprocess
import ctypes

from PyQt5.QtCore import Qt, QRect, QTimer
from PyQt5.QtWidgets import QApplication

from fastpanel.settings import C

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

