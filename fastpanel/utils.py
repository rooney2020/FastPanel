from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QGraphicsDropShadowEffect, QFileDialog
)
from PyQt5.QtCore import Qt, QObject, QEvent, QPoint
from PyQt5.QtGui import QColor

from fastpanel.constants import GRID_SIZE, PARAM_PATTERN, _DESKTOP_MODE
from fastpanel.settings import C
from fastpanel.theme import _dialog_style, _file_dialog_style

def snap(val, grid=GRID_SIZE):
    return round(val / grid) * grid


def _current_screen():
    """Return the screen under the mouse cursor, or primary screen."""
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtGui import QCursor
    screen = QApplication.screenAt(QCursor.pos())
    return screen or QApplication.primaryScreen()


def _center_on_screen(widget, screen=None):
    """Center *widget* on the given (or current) screen."""
    screen = screen or _current_screen()
    if screen:
        geo = screen.availableGeometry()
        x = geo.x() + (geo.width() - widget.width()) // 2
        y = geo.y() + (geo.height() - widget.height()) // 2
        widget.move(x, y)


class _DragFilter(QObject):
    """Allow dragging a frameless dialog by clicking on non-interactive areas."""
    def __init__(self, widget):
        super().__init__(widget)
        self._w = widget
        self._dragging = False
        self._offset = QPoint()

    def eventFilter(self, obj, event):
        if obj is not self._w:
            return False
        etype = event.type()
        if etype == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
            child = self._w.childAt(event.pos())
            if child is None or isinstance(child, (QLabel, QDialog)):
                self._dragging = True
                self._offset = event.globalPos() - self._w.pos()
                return True
        elif etype == QEvent.MouseMove and self._dragging:
            self._w.move(event.globalPos() - self._offset)
            return True
        elif etype == QEvent.MouseButtonRelease and self._dragging:
            self._dragging = False
            return True
        return False


def _prepare_dialog(dlg):
    """In desktop mode: use FramelessWindowHint to bypass Mutter's aggressive
    dialog placement, center on the screen under the mouse, and add drag support.
    Mutter's smart-placement algorithm ignores application-specified coordinates
    for framed dialogs whose height falls in a certain range relative to the
    work-area; frameless windows are exempt from this placement."""
    if _DESKTOP_MODE:
        target_screen = _current_screen()
        dlg.setParent(None)
        dlg.setWindowFlags(
            Qt.Dialog | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        )
        drag = _DragFilter(dlg)
        dlg.installEventFilter(drag)
        dlg._drag_filter = drag

        def _exec_centered():
            dlg.adjustSize()
            geo = target_screen.availableGeometry()
            x = geo.x() + (geo.width() - dlg.width()) // 2
            y = geo.y() + (geo.height() - dlg.height()) // 2
            dlg.move(x, y)
            return QDialog.exec(dlg)
        dlg.exec_ = _exec_centered
        dlg.exec = _exec_centered


def count_params(cmd):
    return len(PARAM_PATTERN.findall(cmd))


def _confirm_dialog(parent, title, text):
    dlg = QDialog(parent)
    _prepare_dialog(dlg)
    dlg.setWindowTitle(title)
    dlg.setFixedWidth(340)
    dlg.setStyleSheet(_dialog_style())
    lay = QVBoxLayout(dlg)
    lay.setSpacing(16)
    lay.setContentsMargins(24, 20, 24, 20)
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    lbl.setStyleSheet(f"color: {C['text']}; font-size: 14px;")
    lay.addWidget(lbl)
    btn_row = QHBoxLayout()
    btn_row.addStretch()
    cancel_btn = QPushButton("取消")
    cancel_btn.setObjectName("cancelBtn")
    cancel_btn.clicked.connect(dlg.reject)
    btn_row.addWidget(cancel_btn)
    ok_btn = QPushButton("确认")
    ok_btn.setObjectName("okBtn")
    ok_btn.clicked.connect(dlg.accept)
    btn_row.addWidget(ok_btn)
    lay.addLayout(btn_row)
    return dlg.exec_() == QDialog.Accepted


def _input_dialog(parent, title, label, default_text=""):
    dlg = QDialog(parent)
    _prepare_dialog(dlg)
    dlg.setWindowTitle(title)
    dlg.setFixedWidth(360)
    dlg.setStyleSheet(_dialog_style())
    lay = QVBoxLayout(dlg)
    lay.setSpacing(12)
    lay.setContentsMargins(24, 20, 24, 20)
    lbl = QLabel(label)
    lbl.setStyleSheet(f"color: {C['text']}; font-size: 14px;")
    lay.addWidget(lbl)
    edit = QLineEdit(default_text)
    lay.addWidget(edit)
    btn_row = QHBoxLayout()
    btn_row.addStretch()
    cancel_btn = QPushButton("取消")
    cancel_btn.setObjectName("cancelBtn")
    cancel_btn.clicked.connect(dlg.reject)
    btn_row.addWidget(cancel_btn)
    ok_btn = QPushButton("确定")
    ok_btn.setObjectName("okBtn")
    ok_btn.clicked.connect(dlg.accept)
    btn_row.addWidget(ok_btn)
    lay.addLayout(btn_row)
    if dlg.exec_() == QDialog.Accepted:
        return True, edit.text()
    return False, ""


def _desktop_file_dialog(dlg):
    """Style a non-native QFileDialog for desktop mode."""
    from PyQt5.QtWidgets import QComboBox as _QCB
    from PyQt5.QtGui import QPalette, QColor
    from PyQt5.QtCore import QTimer as _QT
    from fastpanel.theme import _combobox_popup_style
    target_screen = _current_screen()
    dlg.setWindowFlags(
        Qt.Dialog | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
    )
    dlg.setOption(QFileDialog.DontUseNativeDialog, True)
    dlg.setStyleSheet(_file_dialog_style())
    dlg.resize(720, 480)
    drag = _DragFilter(dlg)
    dlg.installEventFilter(drag)
    dlg._drag_filter = drag

    def _apply_popup_style_to(combo):
        from fastpanel.settings import C
        view = combo.view()
        if not view:
            return
        container = view.parent()
        if container and container is not combo:
            bg = QColor(C['surface0'])
            fg = QColor(C['text'])
            pal = container.palette()
            for role in (QPalette.Window, QPalette.Base, QPalette.AlternateBase, QPalette.Button):
                pal.setColor(QPalette.Active, role, bg)
                pal.setColor(QPalette.Inactive, role, bg)
            for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
                pal.setColor(QPalette.Active, role, fg)
                pal.setColor(QPalette.Inactive, role, fg)
            pal.setColor(QPalette.Highlight, QColor(C['surface1']))
            pal.setColor(QPalette.HighlightedText, fg)
            container.setPalette(pal)
            container.setAutoFillBackground(True)
            container.setStyleSheet(
                f"QFrame {{ background: {C['surface0']}; border: 1px solid {C['surface1']}; border-radius: 6px; }}"
            )
            view.setPalette(pal)
            view.setAutoFillBackground(True)
        view.setStyleSheet(_combobox_popup_style())

    for combo in dlg.findChildren(_QCB):
        if combo.view():
            combo.view().setStyleSheet(_combobox_popup_style())
        _cls_name = f"_Styled_{id(combo)}"
        _styled_cls = type(_cls_name, (_QCB,), {
            'showPopup': lambda self, _c=combo: (
                _QCB.showPopup(self),
                _QT.singleShot(0, lambda: _apply_popup_style_to(_c)),
            )
        })
        combo.__class__ = _styled_cls

    def _exec_centered():
        geo = target_screen.availableGeometry()
        x = geo.x() + (geo.width() - dlg.width()) // 2
        y = geo.y() + (geo.height() - dlg.height()) // 2
        dlg.move(x, y)
        return QDialog.exec(dlg)
    dlg.exec_ = _exec_centered
    dlg.exec = _exec_centered


def _open_file(parent, caption="", directory="", filter=""):
    """QFileDialog.getOpenFileName wrapper visible in desktop mode."""
    if _DESKTOP_MODE:
        dlg = QFileDialog(None, caption, directory, filter)
        _desktop_file_dialog(dlg)
        dlg.setAcceptMode(QFileDialog.AcceptOpen)
        dlg.setFileMode(QFileDialog.ExistingFile)
        if dlg.exec_() == QDialog.Accepted:
            files = dlg.selectedFiles()
            return (files[0] if files else "", "")
        return ("", "")
    return QFileDialog.getOpenFileName(parent, caption, directory, filter)


def _save_file(parent, caption="", directory="", filter=""):
    """QFileDialog.getSaveFileName wrapper visible in desktop mode."""
    if _DESKTOP_MODE:
        dlg = QFileDialog(None, caption, directory, filter)
        _desktop_file_dialog(dlg)
        dlg.setAcceptMode(QFileDialog.AcceptSave)
        dlg.setFileMode(QFileDialog.AnyFile)
        if dlg.exec_() == QDialog.Accepted:
            files = dlg.selectedFiles()
            return (files[0] if files else "", "")
        return ("", "")
    return QFileDialog.getSaveFileName(parent, caption, directory, filter)


def _open_dir(parent, caption="", directory=""):
    """QFileDialog.getExistingDirectory wrapper visible in desktop mode."""
    if _DESKTOP_MODE:
        dlg = QFileDialog(None, caption, directory)
        _desktop_file_dialog(dlg)
        dlg.setFileMode(QFileDialog.Directory)
        dlg.setOption(QFileDialog.ShowDirsOnly, True)
        if dlg.exec_() == QDialog.Accepted:
            dirs = dlg.selectedFiles()
            return dirs[0] if dirs else ""
        return ""
    return QFileDialog.getExistingDirectory(parent, caption, directory)

