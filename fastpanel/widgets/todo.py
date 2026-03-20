import json
import os
import uuid
import datetime
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QDialog, QFormLayout, QLineEdit, QCheckBox, QTextEdit
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QColor

from fastpanel.constants import GRID_SIZE, _BASE_DIR, CHECK_PATH
from fastpanel.settings import C, _settings
from fastpanel.theme import _comp_style, _bg, _dialog_style, _scrollbar_style
from fastpanel.widgets.base import CompBase

class _TodoEditDialog(QDialog):
    def __init__(self, text="", deadline="", parent=None):
        super().__init__(parent)
        from fastpanel.utils import _prepare_dialog
        _prepare_dialog(self)
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
        self._scroll.setStyleSheet(
            f"QScrollArea {{ border:none; background:transparent; }}"
            + _scrollbar_style(4)
        )
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
        self._add_edit.setStyleSheet(f"background:{_bg('surface0')}; color:{C['text']}; border:1px solid {C['surface2']}; border-radius:6px; padding:4px 8px; font-size:12px;")
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
        row.setStyleSheet(f"background:{_bg('surface0')}; border-radius:6px;")
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
            QPushButton {{ background:{_bg('surface1')}; color:{C['subtext0']}; border:none; border-radius:4px; font-size:10px; padding:2px 8px; }}
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


# ---------------------------------------------------------------------------
# Circle Icon Buttons for Stopwatch / Timer
# ---------------------------------------------------------------------------

