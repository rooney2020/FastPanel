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

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFrame, QScrollArea, QLineEdit, QComboBox,
    QCheckBox, QTextEdit, QDialog, QFormLayout,
    QGraphicsDropShadowEffect, QGraphicsOpacityEffect, QSizePolicy, QFileDialog, QMenu,
    QStackedWidget, QStackedLayout
)
from PyQt5.QtCore import Qt, QPoint, QRect, QThread, pyqtSignal, QTimer, QPropertyAnimation, QEasingCurve
from PyQt5.QtGui import QFont, QPainter, QColor, QPixmap, QIcon, QFontMetrics, QPen

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
TYPE_LABELS = {TYPE_CMD: "CMD", TYPE_CMD_WINDOW: "CMD窗口", TYPE_SHORTCUT: "快捷方式",
               TYPE_CALENDAR: "日历", TYPE_WEATHER: "天气", TYPE_DOCK: "Dock栏", TYPE_TODO: "待办"}

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


def _comp_style():
    return f"""
    QFrame[compWidget="true"] {{
        background: {C['base']}; border: 1px solid {C['surface0']}; border-radius: 12px;
    }}
    QFrame[compWidget="true"]:hover {{ border: 1px solid {C['surface2']}; }}
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
        background: {C['crust']}; border-radius: 8px;
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
        background: {C['crust']}; color: {C['yellow']};
        border: 1px solid {C['surface0']}; border-radius: 6px;
        padding: 5px 10px;
        font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace;
        font-size: 12px;
    }}
    #paramInput:focus {{ border: 1px solid {C['yellow']}; }}
    #output {{
        background: {C['crust']}; color: {C['green']};
        border: 1px solid {C['surface0']}; border-radius: 8px;
        font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace;
        font-size: 11px; padding: 8px;
    }}
    #stdinInput {{
        background: {C['crust']}; color: {C['text']};
        border: 1px solid {C['surface0']}; border-radius: 6px;
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
    #sendBtn:disabled {{ background: {C['surface1']}; color: {C['overlay0']}; }}
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
            pw = self.parent().width() if self.parent() else 9999
            p.setX(max(0, min(p.x(), pw-self.width())))
            p.setY(max(0, p.y()))
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
            pw = self.parent().width() if self.parent() else 9999
            x = max(0, min(x, pw-self.width()))
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
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24); shadow.setOffset(0,4); shadow.setColor(QColor(0,0,0,100))
        self.setGraphicsEffect(shadow)

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
            QMenu::item:selected {{ background:{C['surface1']}; }}
            QMenu::separator {{ height:1px; background:{C['surface0']}; margin:4px 8px; }}
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
            pw = self.parent().width() if self.parent() else 9999
            min_x = min(orig.x() for _, orig in self._batch_offsets)
            min_y = min(orig.y() for _, orig in self._batch_offsets)
            max_r = max(orig.x() + w.width() for w, orig in self._batch_offsets)
            dx, dy = delta.x(), delta.y()
            if min_x + dx < 0: dx = -min_x
            if min_y + dy < 0: dy = -min_y
            if max_r + dx > pw: dx = pw - max_r
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
            for w, _ in self._batch_offsets:
                x, y = snap(w.x()), snap(w.y())
                w.move(x, y); w.data.x, w.data.y = x, y
            self.geometry_changed.emit()
            grid = self._get_grid()
            if grid:
                grid._update_overlay()
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
        cmd_q.setStyleSheet(f"background:{C['surface1']}; color:{C['subtext0']}; border-radius:9px; font-size:11px; font-weight:bold;")
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
                q.setStyleSheet(f"background:{C['surface1']}; color:{C['subtext0']}; border-radius:9px; font-size:11px; font-weight:bold;")
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
                self._run_btn.setStyleSheet(f"background:{C['surface1']}; color:{C['text']}; border:none; border-radius:6px; padding:0 14px; font-weight:bold; font-size:12px;")
            elif code == 0:
                self._run_btn.setText("✓ 完成")
                self._run_btn.setStyleSheet(f"background:{C['surface0']}; color:{C['green']}; border:none; border-radius:6px; padding:0 14px; font-weight:bold; font-size:12px;")
            else:
                self._run_btn.setText(f"✗ 失败({code})")
                self._run_btn.setStyleSheet(f"background:{C['surface0']}; color:{C['red']}; border:none; border-radius:6px; padding:0 14px; font-weight:bold; font-size:12px;")
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
        exp_btn.setToolTip("导出日志"); exp_btn.setStyleSheet(f"background:{C['surface1']}; color:{C['text']}; border:none; border-radius:6px; font-size:14px;")
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
        pb.setStyleSheet(f"background:{C['surface1']}; color:{C['text']}; border:none; border-radius:6px; font-size:12px;")
        pb.clicked.connect(self._prev_month); nav.addWidget(pb)
        self._month_lbl = QLabel(); self._month_lbl.setAlignment(Qt.AlignCenter)
        self._month_lbl.setStyleSheet(f"color:{C['text']}; font-size:14px; font-weight:bold;")
        nav.addWidget(self._month_lbl, 1)
        nb = QPushButton("▶"); nb.setFixedSize(28, 28); nb.setCursor(Qt.PointingHandCursor)
        nb.setStyleSheet(f"background:{C['surface1']}; color:{C['text']}; border:none; border-radius:6px; font-size:12px;")
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
                    w.setStyleSheet(f"background:{C['surface1']}; border-radius:6px; border:2px solid {C['blue']};")
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
                background: {C['surface0']}; color: {C['overlay0']}; border: 2px dashed {C['surface2']};
                border-radius: 12px; font-size: 22px; font-weight: bold;
            }}
            QPushButton:hover {{ background: {C['surface1']}; color: {C['text']}; border-color: {C['overlay0']}; }}
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
            QMenu {{ background: {C['surface0']}; color: {C['text']}; border: 1px solid {C['surface2']}; border-radius: 6px; padding: 4px; }}
            QMenu::item {{ padding: 6px 20px; border-radius: 4px; }}
            QMenu::item:selected {{ background: {C['surface1']}; }}
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
        self._add_edit.setStyleSheet(f"background:{C['surface0']}; color:{C['text']}; border:1px solid {C['surface2']}; border-radius:6px; padding:4px 8px; font-size:12px;")
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
        row.setStyleSheet(f"background:{C['surface0']}; border-radius:6px;")
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
            QPushButton {{ background:{C['surface1']}; color:{C['subtext0']}; border:none; border-radius:4px; font-size:10px; padding:2px 8px; }}
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
        self._show_grid = _settings.get("show_grid", True)
        self.setAutoFillBackground(True)
        self.setMouseTracking(True)
        pal = self.palette(); pal.setColor(pal.Window, QColor(C["crust"])); self.setPalette(pal)
        self._overlay = _SelectionOverlay(self)
        self._overlay.show()
        bg = _settings.get("bg_image", "")
        if bg and os.path.isfile(bg):
            self._bg_pixmap = QPixmap(bg)
            self._bg_opacity = _settings.get("bg_opacity", 30)

    def set_bg_image(self, path, opacity=30):
        if path and os.path.isfile(path):
            self._bg_pixmap = QPixmap(path)
        else:
            self._bg_pixmap = None
        self._bg_opacity = opacity

    def set_show_grid(self, show):
        self._show_grid = show

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._overlay.setGeometry(0, 0, self.width(), self.height())
        self._overlay.raise_()

    def paintEvent(self, e):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(e.rect(), QColor(C["crust"]))
        if self._bg_pixmap and not self._bg_pixmap.isNull():
            p.setOpacity(self._bg_opacity / 100.0)
            scaled = self._bg_pixmap.scaled(self.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            x = (self.width() - scaled.width()) // 2
            y = (self.height() - scaled.height()) // 2
            p.drawPixmap(x, y, scaled)
            p.setOpacity(1.0)
        if self._show_grid:
            dc = QColor(C["overlay0"]); dc.setAlpha(100); p.setPen(Qt.NoPen); p.setBrush(dc)
            r = e.rect(); x0 = (r.left()//GRID_SIZE)*GRID_SIZE; y0 = (r.top()//GRID_SIZE)*GRID_SIZE
            for x in range(x0, r.right()+1, GRID_SIZE):
                for y in range(y0, r.bottom()+1, GRID_SIZE):
                    p.drawEllipse(x-1, y-1, 3, 3)
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

    def _child_moved(self):
        mover = self.sender()
        if mover:
            self._resolve_overlaps(mover)
        par = self.parent()
        if par:
            vp = par.viewport() if hasattr(par, 'viewport') else par
            self.recalc_size(vp.width(), vp.height())
        self._update_overlay()
        self.data_changed.emit()

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
            self._components.remove(w); w.deleteLater(); self.data_changed.emit()

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

    dialog._name_fields = [_lbl(dialog.name_edit), dialog.name_edit]
    _NO_NAME_TYPES = {TYPE_CALENDAR, TYPE_WEATHER, TYPE_DOCK, TYPE_TODO}

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
    _no_name = {TYPE_CALENDAR, TYPE_WEATHER, TYPE_DOCK, TYPE_TODO}
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
    name = dialog.name_edit.text().strip()
    if not name:
        _defaults = {TYPE_CALENDAR: "日历", TYPE_WEATHER: "天气", TYPE_DOCK: "Dock栏", TYPE_TODO: "待办"}
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

        bg_w = QWidget()
        bg_lay = QHBoxLayout(bg_w); bg_lay.setContentsMargins(0, 0, 0, 0); bg_lay.setSpacing(6)
        self.bg_edit = QLineEdit(_settings.get("bg_image", ""))
        self.bg_edit.setPlaceholderText("背景图片路径（可选）")
        bg_lay.addWidget(self.bg_edit)
        bb = QPushButton("…"); bb.setFixedWidth(36)
        bb.setStyleSheet(f"background:{C['surface1']}; color:{C['text']}; border:none; border-radius:6px;")
        bb.clicked.connect(self._browse_bg)
        bg_lay.addWidget(bb)
        clr = QPushButton("✕"); clr.setFixedWidth(36)
        clr.setStyleSheet(f"background:{C['surface1']}; color:{C['red']}; border:none; border-radius:6px;")
        clr.clicked.connect(lambda: self.bg_edit.clear())
        bg_lay.addWidget(clr)
        form.addRow("背  景", bg_w)

        from PyQt5.QtWidgets import QSlider
        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(10, 100)
        self.opacity_slider.setValue(_settings.get("bg_opacity", 30))
        self._opa_label = QLabel(f"{self.opacity_slider.value()}%")
        self._opa_label.setFixedWidth(36)
        self.opacity_slider.valueChanged.connect(lambda v: self._opa_label.setText(f"{v}%"))
        opa_w = QWidget()
        opa_lay = QHBoxLayout(opa_w); opa_lay.setContentsMargins(0, 0, 0, 0); opa_lay.setSpacing(6)
        opa_lay.addWidget(self.opacity_slider); opa_lay.addWidget(self._opa_label)
        form.addRow("透明度", opa_w)

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

    def get_settings(self):
        return {
            "theme": self.theme_combo.currentText(),
            "bg_image": self.bg_edit.text().strip(),
            "bg_opacity": self.opacity_slider.value(),
            "show_grid": _settings.get("show_grid", True),
        }


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
# Main Window
# ---------------------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setWindowTitle("FastPanel — 组件管理器")
        _icon_path = os.path.join(_BASE_DIR, "fastpanel.svg")
        if os.path.isfile(_icon_path):
            self.setWindowIcon(QIcon(_icon_path))
        self.setMinimumSize(960, 640); self.resize(1200, 800)
        self._panels_data = []; self._grids = []; self._scrolls = []; self._active = 0
        self._locked = False
        self._tb_dragging = False; self._tb_offset = QPoint()
        self._build_ui(); self._apply_style(); self._load_data()
        if not self._panels_data:
            self._create_panel("默认"); self._switch_panel(0)

    def _build_ui(self):
        cw = QWidget(); self.setCentralWidget(cw)
        root = QVBoxLayout(cw); root.setContentsMargins(0,0,0,0); root.setSpacing(0)

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
        root.addWidget(self._tab_bar_container)

        self._tab_autohide = False
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

    def _create_panel(self, name, pd=None):
        pd = pd or PanelData(name=name); self._panels_data.append(pd)
        sc = QScrollArea(); sc.setWidgetResizable(False)
        sc.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        g = GridPanel(); g.data_changed.connect(self._on_data_changed); sc.setWidget(g)
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
        if len(self._panels_data)<=1: return
        if not _confirm_dialog(self, "确认", f"删除面板「{self._panels_data[idx].name}」？"): return
        self._panels_data.pop(idx); g = self._grids.pop(idx); s = self._scrolls.pop(idx)
        g.clear_all(); self._stack.removeWidget(s); s.deleteLater(); self._tab_bar.remove_tab(idx)
        self._switch_panel(min(idx, len(self._panels_data)-1)); self._save_data()

    def _cg(self): return self._grids[self._active]
    def _cs(self): return self._scrolls[self._active]

    def resizeEvent(self, e):
        super().resizeEvent(e); self._sync_sizes()
        if self._tab_autohide:
            self._position_hover_zone()
    def showEvent(self, e): super().showEvent(e); QTimer.singleShot(0, self._sync_sizes)
    def _sync_sizes(self):
        for s, g in zip(self._scrolls, self._grids):
            vp = s.viewport(); g.recalc_size(vp.width(), vp.height())
    def _update_count(self): self._cnt.setText(f"{len(self._cg().components)} 个组件")

    def _next_pos(self):
        cs = self._cg().components
        if not cs: return 40, 40
        vw = self._cs().viewport().width(); mr, ry, rb = 0, 0, 0
        for c in cs:
            r = c.data.x+c.data.w; b = c.data.y+c.data.h
            if r > mr: mr, ry = r, c.data.y
            if b > rb: rb = b
        x, y = mr+GRID_SIZE, ry
        if x+320 > vw: x, y = 40, rb+GRID_SIZE
        return snap(x), snap(y)

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
            else:
                d.w = 320; d.h = 200
            self._cg().add_component(d)
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
        if self.isMaximized():
            self.showNormal()
            self._max_btn._is_restore = False
        else:
            self.showMaximized()
            self._max_btn._is_restore = True
        self._max_btn.update()

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
        self._lock_btn.setText("🔒" if self._locked else "🔓")
        self._lock_btn.setProperty("locked", self._locked)
        self._lock_btn.style().unpolish(self._lock_btn)
        self._lock_btn.style().polish(self._lock_btn)
        for g in self._grids:
            for w in g.components:
                w.setProperty("locked", self._locked)

    def _on_settings(self):
        dlg = SettingsDialog(self)
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
                g.set_show_grid(_settings.get("show_grid", True))
                for w in g.components:
                    w.setStyleSheet(cs)
                g.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and self._toolbar.geometry().contains(e.pos()):
            self._tb_dragging = True
            self._tb_offset = e.globalPos() - self.frameGeometry().topLeft()
            e.accept()
        else:
            super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._tb_dragging:
            if self.isMaximized():
                ratio = e.pos().x() / self.width()
                self.showNormal()
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
        if self._toolbar.geometry().contains(e.pos()):
            self._toggle_max()
        else:
            super().mouseDoubleClickEvent(e)

    def closeEvent(self, e): self._save_data(); super().closeEvent(e)


def main():
    os.environ.setdefault("QT_IM_MODULE", "fcitx")
    app = QApplication(sys.argv)
    app.setDesktopFileName("fastpanel")
    font = QFont(); font.setFamily("Noto Sans CJK SC"); font.setPointSize(10); app.setFont(font)
    app.setStyle("Fusion")
    app.setStyleSheet(f"""
        QToolTip {{
            background: {C['surface0']}; color: {C['text']};
            border: 1px solid {C['surface1']}; border-radius: 4px;
            padding: 4px 8px; font-size: 12px;
        }}
    """)
    win = MainWindow(); win.showMaximized()
    if hasattr(win, '_max_btn'): win._max_btn._is_restore = True; win._max_btn.update()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
