import subprocess
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QGridLayout, QSlider
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFont, QColor, QIcon

from fastpanel.constants import GRID_SIZE
from fastpanel.settings import C, _settings
from fastpanel.theme import _comp_style, _bg
from fastpanel.utils import _confirm_dialog
from fastpanel.widgets.base import CompBase

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

