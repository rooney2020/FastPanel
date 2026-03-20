import re
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QTextEdit
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QColor

from fastpanel.constants import GRID_SIZE
from fastpanel.settings import C, _settings
from fastpanel.theme import _comp_style, _bg
from fastpanel.widgets.base import CompBase

NOTE_COLORS = [
    ("#f9e2af", "#1e1e2e"),
    ("#a6e3a1", "#1e1e2e"),
    ("#89b4fa", "#1e1e2e"),
    ("#f38ba8", "#1e1e2e"),
    ("#cba6f7", "#1e1e2e"),
    ("#fab387", "#1e1e2e"),
    ("#94e2d5", "#1e1e2e"),
]


class NoteWidget(CompBase):
    def __init__(self, data, parent=None):
        super().__init__(data, parent)
        self._parse_note_data()
        self._build_ui()

    def refresh_theme(self):
        if hasattr(self, '_text_edit') and not self._md_mode:
            self._note_text = self._text_edit.toPlainText()
        self._save_cmd()
        super().refresh_theme()

    def _parse_note_data(self):
        raw = self.data.cmd.strip()
        parts = raw.split("|", 2) if raw else []
        self._color_idx = 0
        self._note_text = ""
        if len(parts) >= 1:
            try:
                self._color_idx = int(parts[0]) % len(NOTE_COLORS)
            except ValueError:
                pass
        if len(parts) >= 2:
            self._note_text = parts[1]

    def _build_ui(self):
        bg, fg = NOTE_COLORS[self._color_idx]

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self._header = QWidget()
        self._header.setFixedHeight(32)
        self._header.setStyleSheet(f"background: {bg}; border-radius: 0px;")
        h_lay = QHBoxLayout(self._header)
        h_lay.setContentsMargins(10, 4, 6, 4)

        self._title_lbl = QLabel(self.data.name or "便签")
        self._title_lbl.setStyleSheet(f"color: {fg}; font-size: 14px; font-weight: bold; background: transparent;")
        h_lay.addWidget(self._title_lbl, 1)

        self._md_mode = False
        self._md_btn = QPushButton("Md")
        self._md_btn.setFixedSize(24, 20); self._md_btn.setCursor(Qt.PointingHandCursor)
        self._md_btn.setStyleSheet(f"QPushButton{{background:transparent;color:{fg};border:1px solid {fg}44;"
                                   f"border-radius:4px;font-size:9px;font-weight:bold;}}"
                                   f"QPushButton:hover{{background:{fg}22;}}")
        self._md_btn.clicked.connect(self._toggle_md)
        h_lay.addWidget(self._md_btn)

        self._color_btns = []
        for ci in range(len(NOTE_COLORS)):
            btn = QPushButton()
            c_bg, _ = NOTE_COLORS[ci]
            btn.setFixedSize(16, 16)
            btn.setCursor(Qt.PointingHandCursor)
            border = "2px solid #000" if ci == self._color_idx else "1px solid rgba(0,0,0,0.3)"
            btn.setStyleSheet(f"QPushButton {{ background: {c_bg}; border: {border}; border-radius: 8px; }}"
                              f"QPushButton:hover {{ border: 2px solid #000; }}")
            btn.clicked.connect(lambda _, idx=ci: self._change_color(idx))
            h_lay.addWidget(btn)
            self._color_btns.append(btn)

        lay.addWidget(self._header)

        self._text_edit = QTextEdit()
        self._text_edit.setPlainText(self._note_text)
        self._text_style = (f"QTextEdit {{ background: {bg}88; color: {C['text']}; border: none;"
                            f"font-size: 13px; padding: 8px; font-family: 'Noto Sans CJK SC','Microsoft YaHei',sans-serif; }}")
        self._text_edit.setStyleSheet(self._text_style)
        self._text_edit.textChanged.connect(self._save_text)
        lay.addWidget(self._text_edit, 1)

    def _change_color(self, idx):
        self._color_idx = idx
        self._save_cmd()
        bg, fg = NOTE_COLORS[idx]
        self._header.setStyleSheet(f"background: {bg}; border-radius: 0px;")
        self._title_lbl.setStyleSheet(f"color: {fg}; font-size: 14px; font-weight: bold; background: transparent;")
        self._text_style = (f"QTextEdit {{ background: {bg}88; color: {C['text']}; border: none;"
                            f"font-size: 13px; padding: 8px; font-family: 'Noto Sans CJK SC','Microsoft YaHei',sans-serif; }}")
        self._text_edit.setStyleSheet(self._text_style)
        self._md_btn.setStyleSheet(f"QPushButton{{background:transparent;color:{fg};border:1px solid {fg}44;"
                                   f"border-radius:4px;font-size:9px;font-weight:bold;}}"
                                   f"QPushButton:hover{{background:{fg}22;}}")
        for ci, btn in enumerate(self._color_btns):
            c_bg, _ = NOTE_COLORS[ci]
            border = "2px solid #000" if ci == idx else "1px solid rgba(0,0,0,0.3)"
            btn.setStyleSheet(f"QPushButton {{ background: {c_bg}; border: {border}; border-radius: 8px; }}"
                              f"QPushButton:hover {{ border: 2px solid #000; }}")

    def _toggle_md(self):
        if self._md_mode:
            self._md_mode = False
            self._md_btn.setText("Md")
            self._text_edit.setReadOnly(False)
            self._text_edit.textChanged.disconnect()
            self._text_edit.setPlainText(self._note_text)
            self._text_edit.textChanged.connect(self._save_text)
            self._text_edit.setStyleSheet(self._text_style)
        else:
            self._md_mode = True
            self._md_btn.setText("✎")
            self._note_text = self._text_edit.toPlainText()
            self._save_cmd()
            self._text_edit.setReadOnly(True)
            html = self._md_to_html(self._note_text)
            bg, _ = NOTE_COLORS[self._color_idx]
            self._text_edit.setStyleSheet(
                self._text_style + f"\nQTextEdit {{ selection-background-color: {C['surface1']}; }}")
            self._text_edit.setHtml(html)

    @staticmethod
    def _md_to_html(md):
        import re
        lines = md.split("\n")
        html_lines = []
        in_code = False
        in_list = False
        for line in lines:
            if line.startswith("```"):
                if in_code:
                    html_lines.append("</pre>")
                    in_code = False
                else:
                    html_lines.append(f"<pre style='background:{_bg('surface0')};padding:8px;"
                                      f"border-radius:6px;font-size:12px;color:{C['green']};'>")
                    in_code = True
                continue
            if in_code:
                html_lines.append(line.replace("<", "&lt;").replace(">", "&gt;"))
                continue

            escaped = line.replace("<", "&lt;").replace(">", "&gt;")

            if escaped.startswith("### "):
                escaped = f"<h3 style='margin:4px 0;font-size:14px;color:{C['mauve']};'>{escaped[4:]}</h3>"
            elif escaped.startswith("## "):
                escaped = f"<h2 style='margin:4px 0;font-size:15px;color:{C['mauve']};'>{escaped[3:]}</h2>"
            elif escaped.startswith("# "):
                escaped = f"<h1 style='margin:4px 0;font-size:16px;color:{C['mauve']};'>{escaped[2:]}</h1>"
            elif escaped.startswith("- ") or escaped.startswith("* "):
                escaped = f"<li style='margin-left:16px;'>{escaped[2:]}</li>"
            elif re.match(r'^\d+\.\s', escaped):
                ol_text = re.sub(r'^[0-9]+\.\s', '', escaped)
                escaped = f"<li style='margin-left:16px;'>{ol_text}</li>"
            elif escaped.startswith("> "):
                escaped = (f"<blockquote style='border-left:3px solid {C['overlay0']};padding-left:8px;"
                           f"color:{C['subtext0']};margin:4px 0;'>{escaped[2:]}</blockquote>")
            elif escaped.strip() == "---" or escaped.strip() == "***":
                escaped = f"<hr style='border:1px solid {C['surface1']};margin:6px 0;'>"
            elif escaped.strip() == "":
                escaped = "<br>"
            else:
                escaped = f"<p style='margin:2px 0;'>{escaped}</p>"

            escaped = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', escaped)
            escaped = re.sub(r'\*(.+?)\*', r'<i>\1</i>', escaped)
            escaped = re.sub(r'`(.+?)`', f'<code style="background:{C["surface0"]};padding:1px 4px;'
                             f'border-radius:3px;font-size:12px;">\\1</code>', escaped)
            escaped = re.sub(r'\[(.+?)\]\((.+?)\)',
                             f'<a style="color:{C["blue"]};text-decoration:underline;" href="\\2">\\1</a>',
                             escaped)

            html_lines.append(escaped)

        if in_code:
            html_lines.append("</pre>")
        return "\n".join(html_lines)

    def _save_text(self):
        if not self._md_mode:
            self._note_text = self._text_edit.toPlainText()
            self._save_cmd()

    def _save_cmd(self):
        self.data.cmd = f"{self._color_idx}|{self._note_text}"
        main_win = self.window()
        if hasattr(main_win, '_save_panels'):
            main_win._save_panels()



