from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QLineEdit
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QColor, QIntValidator

from fastpanel.constants import GRID_SIZE
from fastpanel.settings import C, _settings
from fastpanel.theme import _comp_style, _bg
from fastpanel.widgets.base import CompBase

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

