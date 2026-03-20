import datetime
import json
import os
import subprocess
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QDialog, QFormLayout, QLineEdit,
    QGraphicsDropShadowEffect, QCheckBox, QMenu, QComboBox, QSizePolicy,
    QTimeEdit, QDateEdit, QSpinBox
)
from PyQt5.QtCore import Qt, QTimer, QTime, QDate, QPoint, pyqtSignal
from PyQt5.QtGui import QFont, QColor, QPainter, QPen, QPolygon, QIntValidator

from fastpanel.constants import (
    GRID_SIZE, _BASE_DIR, CLOCK_SUB_CLOCK, CLOCK_SUB_WORLD,
    CLOCK_SUB_STOPWATCH, CLOCK_SUB_TIMER, CLOCK_SUB_ALARM
)
from fastpanel.settings import C, _settings
from fastpanel.theme import _comp_style, _bg, _dialog_style, _scrollbar_style, _style_combobox
from fastpanel.widgets.base import CompBase, _ExpandBtn
from fastpanel.widgets.calendar_w import _solar_to_lunar

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
        from fastpanel.utils import _prepare_dialog
        _prepare_dialog(dlg)
        dlg.setWindowTitle("编辑闹钟" if is_edit else "添加闹钟")
        dlg.setFixedWidth(360)
        dlg.setStyleSheet(f"""
            QDialog {{ background: {C['base']}; color: {C['text']}; border-radius: 12px; }}
            QLabel {{ color: {C['text']}; background: transparent; }}
            QLabel#dialogTitle {{ color: {C['text']}; font-size: 16px; font-weight: bold; }}
            QLineEdit {{ background: {_bg('surface0')}; color: {C['text']}; border: 1px solid {C['surface2']};
                border-radius: 8px; padding: 8px 12px; font-size: 13px; }}
            QLineEdit:focus {{ border: 1px solid {C['blue']}; }}
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
        _style_combobox(repeat_combo)
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



