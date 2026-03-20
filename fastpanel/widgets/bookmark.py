import subprocess
import json
import os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QDialog, QFormLayout, QLineEdit
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QColor

from fastpanel.constants import GRID_SIZE, _BASE_DIR
from fastpanel.settings import C, _settings
from fastpanel.theme import _comp_style, _bg, _dialog_style, _scrollbar_style
from fastpanel.utils import _input_dialog
from fastpanel.widgets.base import CompBase

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

