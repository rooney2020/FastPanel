from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QColor

from fastpanel.settings import C
from fastpanel.theme import _dialog_style

_KEY_NAMES = {
    Qt.Key_F1: "F1", Qt.Key_F2: "F2", Qt.Key_F3: "F3", Qt.Key_F4: "F4",
    Qt.Key_F5: "F5", Qt.Key_F6: "F6", Qt.Key_F7: "F7", Qt.Key_F8: "F8",
    Qt.Key_F9: "F9", Qt.Key_F10: "F10", Qt.Key_F11: "F11", Qt.Key_F12: "F12",
    Qt.Key_Space: "space", Qt.Key_Return: "Return", Qt.Key_Enter: "Return",
    Qt.Key_Escape: "Escape", Qt.Key_Tab: "Tab", Qt.Key_Backspace: "BackSpace",
    Qt.Key_Delete: "Delete", Qt.Key_Up: "Up", Qt.Key_Down: "Down",
    Qt.Key_Left: "Left", Qt.Key_Right: "Right", Qt.Key_Home: "Home",
    Qt.Key_End: "End", Qt.Key_PageUp: "Prior", Qt.Key_PageDown: "Next",
    Qt.Key_Comma: "comma", Qt.Key_Period: "period", Qt.Key_Slash: "slash",
    Qt.Key_Semicolon: "semicolon", Qt.Key_Apostrophe: "apostrophe",
    Qt.Key_BracketLeft: "bracketleft", Qt.Key_BracketRight: "bracketright",
    Qt.Key_Minus: "minus", Qt.Key_Equal: "equal", Qt.Key_QuoteLeft: "grave",
}
_MOD_KEYS = {Qt.Key_Control, Qt.Key_Alt, Qt.Key_Shift, Qt.Key_Meta,
             Qt.Key_Super_L, Qt.Key_Super_R, Qt.Key_AltGr}


def _parse_key_event(e):
    parts = []
    mods = e.modifiers()
    if mods & Qt.ControlModifier: parts.append("Ctrl")
    if mods & Qt.AltModifier: parts.append("Alt")
    if mods & Qt.ShiftModifier: parts.append("Shift")
    if mods & Qt.MetaModifier: parts.append("Super")
    key = e.key()
    if key in _MOD_KEYS:
        return None, "+".join(parts) + "+" if parts else ""
    if key in _KEY_NAMES:
        parts.append(_KEY_NAMES[key])
    elif Qt.Key_A <= key <= Qt.Key_Z:
        parts.append(chr(key).lower())
    elif Qt.Key_0 <= key <= Qt.Key_9:
        parts.append(chr(key))
    else:
        return None, ""
    return "+".join(parts), "+".join(parts)


class _HotkeyCaptureDlg(QDialog):
    def __init__(self, current_val="", parent=None):
        super().__init__(parent)
        from fastpanel.utils import _prepare_dialog
        _prepare_dialog(self)
        self.setWindowTitle("设置快捷键")
        self.setFixedSize(320, 160)
        self.setStyleSheet(_dialog_style())
        self._result = current_val
        lay = QVBoxLayout(self); lay.setContentsMargins(24, 20, 24, 20); lay.setSpacing(12)
        hint = QLabel("请按下快捷键组合…")
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet(f"color: {C['subtext0']}; font-size: 13px;")
        lay.addWidget(hint)
        self._display = QLabel(current_val or "—")
        self._display.setAlignment(Qt.AlignCenter)
        self._display.setStyleSheet(f"""
            color: {C['text']}; font-size: 18px; font-weight: bold;
            background: {C['surface0']}; border: 2px solid {C['blue']};
            border-radius: 8px; padding: 12px; min-height: 30px;
        """)
        lay.addWidget(self._display)
        self._pending = ""

    def keyPressEvent(self, e):
        combo, display = _parse_key_event(e)
        if combo:
            self._result = combo
            self._display.setText(combo)
            self._display.setStyleSheet(f"""
                color: {C['green']}; font-size: 18px; font-weight: bold;
                background: {C['surface0']}; border: 2px solid {C['green']};
                border-radius: 8px; padding: 12px; min-height: 30px;
            """)
            QTimer.singleShot(400, self.accept)
        elif display:
            self._display.setText(display)

    def get_result(self):
        return self._result


class _HotkeyEdit(QLineEdit):
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setReadOnly(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setPlaceholderText("点击设置快捷键")

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            dlg = _HotkeyCaptureDlg(self.text(), self.window())
            if dlg.exec_() == QDialog.Accepted:
                self.setText(dlg.get_result())
        else:
            super().mousePressEvent(e)



