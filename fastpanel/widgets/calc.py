from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QLineEdit, QGridLayout
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QColor

from fastpanel.constants import GRID_SIZE
from fastpanel.settings import C, _settings
from fastpanel.theme import _comp_style, _bg
from fastpanel.widgets.base import CompBase

class CalcWidget(CompBase):
    def __init__(self, data, parent=None):
        super().__init__(data, parent)
        self._expr = ""
        self._result = ""
        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self); lay.setContentsMargins(12, 10, 12, 10); lay.setSpacing(6)
        self._display = QLabel("0")
        self._display.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._display.setStyleSheet(f"color:{C['text']};font-size:28px;font-weight:bold;"
                                    f"font-family:'JetBrains Mono','Courier New',monospace;"
                                    f"background:{_bg('surface0')};border-radius:8px;padding:12px 16px;"
                                    f"min-height:40px;")
        lay.addWidget(self._display)
        self._expr_lbl = QLabel("")
        self._expr_lbl.setAlignment(Qt.AlignRight)
        self._expr_lbl.setStyleSheet(f"color:{C['subtext0']};font-size:11px;background:transparent;padding:0 16px;")
        lay.addWidget(self._expr_lbl)
        from PyQt5.QtWidgets import QGridLayout
        grid = QGridLayout(); grid.setSpacing(6)
        buttons = [
            ("C", 0, 0, C['red']), ("(", 0, 1, C['surface1']), (")", 0, 2, C['surface1']), ("÷", 0, 3, C['peach']),
            ("7", 1, 0, ""), ("8", 1, 1, ""), ("9", 1, 2, ""), ("×", 1, 3, C['peach']),
            ("4", 2, 0, ""), ("5", 2, 1, ""), ("6", 2, 2, ""), ("−", 2, 3, C['peach']),
            ("1", 3, 0, ""), ("2", 3, 1, ""), ("3", 3, 2, ""), ("+", 3, 3, C['peach']),
            ("±", 4, 0, C['surface1']), ("0", 4, 1, ""), (".", 4, 2, ""), ("=", 4, 3, C['blue']),
        ]
        for text, r, c, color in buttons:
            b = QPushButton(text); b.setFixedHeight(40); b.setCursor(Qt.PointingHandCursor)
            bg = color or C['surface0']
            fg = C['crust'] if color in (C['blue'], C['red'], C['peach']) else C['text']
            b.setStyleSheet(f"""QPushButton {{background:{bg};color:{fg};border:none;
                border-radius:8px;font-size:16px;font-weight:bold;}}
                QPushButton:hover {{background:{C['surface2'] if not color else color};opacity:0.8;}}""")
            b.clicked.connect(lambda _, t=text: self._on_btn(t))
            grid.addWidget(b, r, c)
        lay.addLayout(grid)

    def _on_btn(self, text):
        if text == "C":
            self._expr = ""; self._result = ""
            self._display.setText("0"); self._expr_lbl.setText("")
        elif text == "=":
            self._calc()
        elif text == "±":
            if self._expr and self._expr[0] == '-':
                self._expr = self._expr[1:]
            elif self._expr:
                self._expr = '-' + self._expr
            self._expr_lbl.setText(self._expr)
        else:
            op_map = {"÷": "/", "×": "*", "−": "-"}
            self._expr += op_map.get(text, text)
            self._expr_lbl.setText(self._expr)

    def _calc(self):
        try:
            safe_expr = self._expr.replace("^", "**")
            for ch in safe_expr:
                if ch not in "0123456789.+-*/() ":
                    self._display.setText("错误"); return
            result = eval(safe_expr)
            self._result = str(result)
            if '.' in self._result:
                self._result = self._result.rstrip('0').rstrip('.')
            self._display.setText(self._result)
            self._expr_lbl.setText(f"{self._expr} =")
            self._expr = self._result
        except Exception:
            self._display.setText("错误")

    def refresh_theme(self):
        saved_expr = self._expr
        saved_result = self._result
        super().refresh_theme()
        self._expr = saved_expr
        self._result = saved_result
        self._expr_lbl.setText(saved_expr)
        if saved_result:
            self._display.setText(saved_result)


# ---------------------------------------------------------------------------
# Trash / Recycle Bin Widget
# ---------------------------------------------------------------------------

