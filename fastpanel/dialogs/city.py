import json
import os
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QScrollArea, QFrame, QGridLayout, QWidget
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QColor

from fastpanel.constants import _BASE_DIR
from fastpanel.settings import C
from fastpanel.theme import _dialog_style, _scrollbar_style

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
        from fastpanel.utils import _prepare_dialog
        _prepare_dialog(self)
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
        self._scroll.setStyleSheet(
            f"QScrollArea {{ border: none; background: {C['base']}; }}"
            + _scrollbar_style(6)
        )
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

