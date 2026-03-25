from PyQt5.QtWidgets import QWidget, QLabel, QHBoxLayout, QGraphicsOpacityEffect
from PyQt5.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QPoint
from PyQt5.QtGui import QPainter, QColor, QFont, QCursor

from fastpanel.settings import C


class _PulsingDot(QWidget):
    def __init__(self, color_key="red", parent=None):
        super().__init__(parent)
        self._color_key = color_key
        self._opacity = 1.0
        self._radius = 6
        self.setFixedSize(20, 20)

        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._pulse)
        self._phase = 0

    def start(self):
        self._phase = 0
        self._anim_timer.start(50)

    def stop(self):
        self._anim_timer.stop()
        self._opacity = 1.0
        self._radius = 6
        self.update()

    def set_color(self, key: str):
        self._color_key = key
        self.update()

    def _pulse(self):
        import math
        self._phase = (self._phase + 4) % 360
        rad = math.radians(self._phase)
        self._opacity = 0.5 + 0.5 * math.sin(rad)
        self._radius = 5 + int(2 * math.sin(rad))
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        color = QColor(C.get(self._color_key, "#f38ba8"))
        color.setAlphaF(self._opacity)
        p.setBrush(color)
        p.setPen(Qt.NoPen)
        cx, cy = self.width() // 2, self.height() // 2
        p.drawEllipse(cx - self._radius, cy - self._radius,
                       self._radius * 2, self._radius * 2)
        p.end()


class VoiceIndicator(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.ToolTip | Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint | Qt.X11BypassWindowManagerHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedHeight(36)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 6, 16, 6)
        lay.setSpacing(8)

        self._dot = _PulsingDot("red", self)
        lay.addWidget(self._dot)

        self._label = QLabel("录音中...")
        self._label.setStyleSheet(f"color: {C['text']}; font-size: 13px; font-weight: bold;")
        lay.addWidget(self._label)

        self._bg_color = C.get("surface0", "#313244")

        self._fade_effect = QGraphicsOpacityEffect(self)
        self._fade_effect.setOpacity(1.0)
        self.setGraphicsEffect(self._fade_effect)
        self._fade_anim = QPropertyAnimation(self._fade_effect, b"opacity")
        self._fade_anim.setDuration(300)
        self._fade_anim.setEasingCurve(QEasingCurve.OutQuad)

        self._auto_hide_timer = QTimer(self)
        self._auto_hide_timer.setSingleShot(True)
        self._auto_hide_timer.timeout.connect(self._fade_out)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        bg = QColor(self._bg_color)
        bg.setAlpha(220)
        p.setBrush(bg)
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(self.rect(), 12, 12)
        p.end()

    def show_downloading(self, pct: int = 0):
        self._auto_hide_timer.stop()
        self._dot.set_color("blue")
        self._dot.start()
        if pct <= 10:
            self._label.setText("准备语音引擎...")
        else:
            self._label.setText(f"下载语音模型... {pct}%")
        self._label.setStyleSheet(f"color: {C['blue']}; font-size: 13px; font-weight: bold;")
        self.adjustSize()
        self._fade_effect.setOpacity(1.0)
        if not self.isVisible():
            self._show_near_cursor()

    def show_recording(self):
        self._auto_hide_timer.stop()
        self._dot.set_color("red")
        self._dot.start()
        self._label.setText("录音中...")
        self._label.setStyleSheet(f"color: {C['text']}; font-size: 13px; font-weight: bold;")
        self.adjustSize()
        self._fade_effect.setOpacity(1.0)
        if not self.isVisible():
            self._show_near_cursor()

    def show_finalizing(self):
        self._dot.set_color("blue")
        self._label.setText("识别中...")
        self._label.setStyleSheet(f"color: {C['blue']}; font-size: 13px; font-weight: bold;")
        self.adjustSize()

    def show_result(self, text: str):
        self._dot.stop()
        self._dot.set_color("green")
        display = text if len(text) <= 20 else text[:18] + "…"
        self._label.setText(f"✓ {display}")
        self._label.setStyleSheet(f"color: {C['green']}; font-size: 13px; font-weight: bold;")
        self.adjustSize()
        self._auto_hide_timer.start(2000)

    def show_error(self, msg: str):
        self._dot.stop()
        self._dot.set_color("red")
        display = msg if len(msg) <= 24 else msg[:22] + "…"
        self._label.setText(f"✗ {display}")
        self._label.setStyleSheet(f"color: {C['red']}; font-size: 13px; font-weight: bold;")
        self.adjustSize()
        self._auto_hide_timer.start(3000)

    def _show_near_cursor(self):
        pos = QCursor.pos()
        self.move(pos.x() + 20, pos.y() - self.height() - 10)
        self.show()
        self.raise_()

    def _fade_out(self):
        self._fade_anim.setStartValue(1.0)
        self._fade_anim.setEndValue(0.0)
        self._fade_anim.finished.connect(self._on_fade_done)
        self._fade_anim.start()

    def _on_fade_done(self):
        self._fade_anim.finished.disconnect(self._on_fade_done)
        self.hide()
        self._dot.stop()
        self._fade_effect.setOpacity(1.0)
