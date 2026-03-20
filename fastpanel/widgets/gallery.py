import os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QFileDialog, QSizePolicy
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QColor, QPixmap

from fastpanel.constants import GRID_SIZE
from fastpanel.settings import C, _settings
from fastpanel.theme import _comp_style, _bg
from fastpanel.widgets.base import CompBase

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
        from fastpanel.utils import _open_dir
        d = _open_dir(self, "选择图片目录", os.path.expanduser("~"))
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

