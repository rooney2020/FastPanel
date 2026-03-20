import os
import subprocess
import shutil
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QColor

from fastpanel.constants import GRID_SIZE
from fastpanel.settings import C, _settings
from fastpanel.theme import _comp_style, _bg, _scrollbar_style
from fastpanel.widgets.base import CompBase
from fastpanel.utils import _confirm_dialog

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

