import subprocess
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QApplication, QGraphicsDropShadowEffect
)
from PyQt5.QtCore import Qt, QTimer, QEvent, pyqtSignal
from PyQt5.QtGui import QFont, QColor, QPixmap, QCursor, QIcon

from fastpanel.constants import GRID_SIZE
from fastpanel.settings import C, _settings
from fastpanel.theme import _comp_style, _bg, _scrollbar_style
from fastpanel.widgets.base import CompBase


class _ClipboardMonitor:
    """Singleton that polls the system clipboard regardless of whether a widget exists."""

    _instance = None
    history = []
    img_history = []
    MAX_TEXT = 30
    MAX_IMG = 10

    @classmethod
    def ensure_running(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self._last_text = ""
        self._last_img_hash = 0
        self._timer = QTimer()
        self._timer.timeout.connect(self._poll)
        self._timer.start(800)

    def _poll(self):
        cb = QApplication.clipboard()
        mime = cb.mimeData()
        if mime and mime.hasImage():
            img = cb.image()
            if not img.isNull():
                h = hash(img.bits().asstring(img.byteCount()) if hasattr(img.bits(), 'asstring')
                         else img.sizeInBytes())
                if h != self._last_img_hash:
                    self._last_img_hash = h
                    pm = QPixmap.fromImage(img)
                    _ClipboardMonitor.img_history.insert(0, pm)
                    if len(_ClipboardMonitor.img_history) > self.MAX_IMG:
                        _ClipboardMonitor.img_history = _ClipboardMonitor.img_history[:self.MAX_IMG]
                    return
        text = cb.text()
        if text and text != self._last_text:
            self._last_text = text
            if text in _ClipboardMonitor.history:
                _ClipboardMonitor.history.remove(text)
            _ClipboardMonitor.history.insert(0, text)
            if len(_ClipboardMonitor.history) > self.MAX_TEXT:
                _ClipboardMonitor.history = _ClipboardMonitor.history[:self.MAX_TEXT]


class ClipboardWidget(CompBase):
    @property
    def _shared_history(self):
        return _ClipboardMonitor.history

    @property
    def _shared_img_history(self):
        return _ClipboardMonitor.img_history

    def __init__(self, data, parent=None):
        super().__init__(data, parent)
        _ClipboardMonitor.ensure_running()
        self._build_ui()
        self._timer = QTimer(self); self._timer.timeout.connect(self._rebuild); self._timer.start(1000)

    def refresh_theme(self):
        super().refresh_theme()
        self._rebuild()
        self._timer = QTimer(self); self._timer.timeout.connect(self._rebuild); self._timer.start(1000)

    def _build_ui(self):
        lay = QVBoxLayout(self); lay.setContentsMargins(12, 10, 12, 10); lay.setSpacing(6)
        hdr = QHBoxLayout()
        title = QLabel("📋 剪贴板历史")
        title.setStyleSheet(f"color:{C['text']};font-size:14px;font-weight:bold;background:transparent;")
        hdr.addWidget(title); hdr.addStretch()
        cnt_lbl = QLabel(f"文本 {len(_ClipboardMonitor.history)} · 图片 {len(_ClipboardMonitor.img_history)}")
        cnt_lbl.setStyleSheet(f"color:{C['subtext0']};font-size:10px;background:transparent;")
        self._cnt_lbl = cnt_lbl
        hdr.addWidget(cnt_lbl)
        clr = QPushButton("清空"); clr.setCursor(Qt.PointingHandCursor)
        clr.setStyleSheet(f"background:{_bg('surface1')};color:{C['red']};border:none;border-radius:8px;"
                          f"font-size:11px;padding:4px 12px;")
        clr.clicked.connect(self._clear)
        hdr.addWidget(clr)
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

    def _rebuild(self):
        while self._list_lay.count() > 1:
            item = self._list_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        idx = 0
        for pm in _ClipboardMonitor.img_history:
            frame = QFrame()
            frame.setCursor(Qt.PointingHandCursor)
            frame.setStyleSheet(f"QFrame{{background:{_bg('surface0')};border-radius:6px;padding:4px;}}"
                                f"QFrame:hover{{background:{_bg('surface1')};}}")
            fl = QHBoxLayout(frame); fl.setContentsMargins(6, 4, 6, 4); fl.setSpacing(6)
            thumb = QLabel()
            scaled = pm.scaled(48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            thumb.setPixmap(scaled)
            thumb.setStyleSheet("background:transparent;")
            fl.addWidget(thumb)
            info = QLabel(f"🖼 图片 {pm.width()}×{pm.height()}")
            info.setStyleSheet(f"color:{C['text']};font-size:10px;background:transparent;")
            fl.addWidget(info, 1)
            frame.mousePressEvent = lambda e, p=pm: self._paste_image(p)
            self._list_lay.insertWidget(idx, frame); idx += 1
        for text in _ClipboardMonitor.history:
            preview = text[:80].replace('\n', ' ')
            btn = QPushButton(preview); btn.setCursor(Qt.PointingHandCursor)
            btn.setToolTip(text[:300])
            btn.setStyleSheet(f"""QPushButton {{
                background:{_bg('surface0')};color:{C['text']};border:none;border-radius:6px;
                text-align:left;padding:6px 8px;font-size:11px;}}
                QPushButton:hover {{background:{_bg('surface1')};}}""")
            btn.clicked.connect(lambda _, t=text: self._paste_text(t))
            self._list_lay.insertWidget(idx, btn); idx += 1
        self._cnt_lbl.setText(f"文本 {len(_ClipboardMonitor.history)} · 图片 {len(_ClipboardMonitor.img_history)}")

    def _paste_text(self, text):
        QApplication.clipboard().setText(text)

    def _paste_image(self, pm):
        QApplication.clipboard().setPixmap(pm)

    def _clear(self):
        _ClipboardMonitor.history.clear()
        _ClipboardMonitor.img_history.clear()
        self._rebuild()


class _ClipboardPopup(QWidget):
    """Themed floating popup for quick clipboard access via hotkey."""

    _instance = None

    @classmethod
    def get_or_create(cls, parent=None):
        try:
            if cls._instance is not None and cls._instance.isVisible():
                cls._instance.hide()
                return cls._instance
        except RuntimeError:
            cls._instance = None
        cls._instance = cls(parent)
        return cls._instance

    def __init__(self, parent=None):
        super().__init__(None, Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setFixedWidth(380)
        self.setMaximumHeight(500)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAttribute(Qt.WA_ShowWithoutActivating, False)
        self.installEventFilter(self)
        self._build_ui()

    def _build_ui(self):
        self.setStyleSheet(f"""
            _ClipboardPopup {{
                background: {C['base']}; border: 1px solid {C['surface1']}; border-radius: 14px;
            }}""")
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(30); shadow.setOffset(0, 6); shadow.setColor(QColor(0, 0, 0, 120))
        self.setGraphicsEffect(shadow)

        lay = QVBoxLayout(self); lay.setContentsMargins(14, 14, 14, 10); lay.setSpacing(8)

        header = QHBoxLayout(); header.setSpacing(8)
        icon_lbl = QLabel("📋")
        icon_lbl.setStyleSheet(f"font-size:18px;background:transparent;")
        header.addWidget(icon_lbl)
        title = QLabel("剪贴板历史")
        title.setStyleSheet(f"color:{C['text']};font-size:15px;font-weight:bold;background:transparent;")
        header.addWidget(title)
        header.addStretch()
        count_lbl = QLabel()
        count_lbl.setStyleSheet(f"color:{C['subtext0']};font-size:11px;background:transparent;")
        header.addWidget(count_lbl)
        self._count_lbl = count_lbl
        lay.addLayout(header)

        sep = QFrame(); sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"background:{C['surface0']};border:none;max-height:1px;")
        lay.addWidget(sep)

        sc = QScrollArea(); sc.setWidgetResizable(True)
        sc.setFixedHeight(400)
        sc.setStyleSheet(f"QScrollArea{{background:transparent;border:none;}}"
                         f"QScrollArea>QWidget{{background:transparent;}}"
                         f"{_scrollbar_style(6)}")
        sc.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._list_w = QWidget()
        self._list_w.setStyleSheet("background:transparent;")
        self._list_lay = QVBoxLayout(self._list_w)
        self._list_lay.setContentsMargins(0, 0, 0, 0)
        self._list_lay.setSpacing(4)
        self._list_lay.addStretch()
        sc.setWidget(self._list_w)
        lay.addWidget(sc)

        hint = QLabel("选择条目即可粘贴  ·  按 Esc 关闭")
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet(f"color:{C['overlay0']};font-size:10px;background:transparent;")
        lay.addWidget(hint)

    def _rebuild(self):
        while self._list_lay.count() > 1:
            item = self._list_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        idx = 0
        total = len(_ClipboardMonitor.img_history) + len(_ClipboardMonitor.history)
        self._count_lbl.setText(f"{total} 条记录")

        for pm in _ClipboardMonitor.img_history:
            frame = QFrame(); frame.setCursor(Qt.PointingHandCursor)
            frame.setStyleSheet(f"""QFrame{{background:{C['surface0']};border-radius:8px;}}
                QFrame:hover{{background:{C['surface1']};border:1px solid {C['blue']};}}""")
            fl = QHBoxLayout(frame); fl.setContentsMargins(8, 6, 8, 6); fl.setSpacing(8)
            thumb = QLabel()
            scaled = pm.scaled(48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            thumb.setPixmap(scaled)
            thumb.setStyleSheet("background:transparent;border-radius:4px;")
            fl.addWidget(thumb)
            info_lay = QVBoxLayout(); info_lay.setSpacing(1)
            info = QLabel(f"图片  {pm.width()}×{pm.height()}")
            info.setStyleSheet(f"color:{C['text']};font-size:11px;background:transparent;")
            info_lay.addWidget(info)
            tag = QLabel("🖼 图像")
            tag.setStyleSheet(f"color:{C['subtext0']};font-size:9px;background:transparent;")
            info_lay.addWidget(tag)
            fl.addLayout(info_lay, 1)
            frame.mousePressEvent = lambda e, p=pm: self._pick_image(p)
            self._list_lay.insertWidget(idx, frame); idx += 1

        for text in _ClipboardMonitor.history:
            preview = text[:120].replace(chr(10), " ↵ ")
            frame = QFrame(); frame.setCursor(Qt.PointingHandCursor)
            frame.setStyleSheet(f"""QFrame{{background:{C['surface0']};border-radius:8px;padding:8px 10px;}}
                QFrame:hover{{background:{C['surface1']};border:1px solid {C['blue']};}}""")
            fl = QVBoxLayout(frame); fl.setContentsMargins(10, 8, 10, 8); fl.setSpacing(2)
            lbl = QLabel(preview)
            lbl.setWordWrap(True)
            lbl.setStyleSheet(f"color:{C['text']};font-size:12px;background:transparent;")
            fl.addWidget(lbl)
            if len(text) > 120:
                more = QLabel(f"…共 {len(text)} 字符")
                more.setStyleSheet(f"color:{C['overlay0']};font-size:9px;background:transparent;")
                fl.addWidget(more)
            frame.mousePressEvent = lambda e, t=text: self._pick_text(t)
            self._list_lay.insertWidget(idx, frame); idx += 1

        if total == 0:
            empty = QLabel("剪贴板为空")
            empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet(f"color:{C['overlay0']};font-size:13px;padding:40px;background:transparent;")
            self._list_lay.insertWidget(0, empty)

    def _pick_text(self, text):
        QApplication.clipboard().setText(text)
        self.hide()
        QTimer.singleShot(300, self._simulate_paste)

    def _pick_image(self, pm):
        QApplication.clipboard().setPixmap(pm)
        self.hide()
        QTimer.singleShot(300, self._simulate_paste)

    @staticmethod
    def _simulate_paste():
        try:
            from Xlib import X, display as xdisplay, XK, ext
            d = xdisplay.Display()
            root = d.screen().root
            focus_win = d.get_input_focus().focus
            ctrl_keycode = d.keysym_to_keycode(XK.string_to_keysym("Control_L"))
            v_keycode = d.keysym_to_keycode(XK.string_to_keysym("v"))
            import Xlib.protocol.event as xevent
            for keycode in [ctrl_keycode, v_keycode]:
                ev = xevent.KeyPress(time=X.CurrentTime, root=root, window=focus_win,
                    same_screen=True, child=X.NONE, root_x=0, root_y=0, event_x=0, event_y=0,
                    state=(X.ControlMask if keycode == v_keycode else 0), detail=keycode)
                focus_win.send_event(ev, propagate=True)
            for keycode in [v_keycode, ctrl_keycode]:
                ev = xevent.KeyRelease(time=X.CurrentTime, root=root, window=focus_win,
                    same_screen=True, child=X.NONE, root_x=0, root_y=0, event_x=0, event_y=0,
                    state=(X.ControlMask if keycode == v_keycode else 0), detail=keycode)
                focus_win.send_event(ev, propagate=True)
            d.sync()
            d.close()
        except Exception as ex:
            print(f"[Clipboard] paste simulate error: {ex}", flush=True)
            try:
                subprocess.Popen(["xdotool", "key", "ctrl+v"],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.hide()
            e.accept()
        else:
            super().keyPressEvent(e)

    def eventFilter(self, obj, event):
        from PyQt5.QtCore import QEvent
        if event.type() == QEvent.WindowDeactivate:
            QTimer.singleShot(100, self._check_deactivate)
        return super().eventFilter(obj, event)

    def _check_deactivate(self):
        if not self.isActiveWindow():
            self.hide()

    def show_at_cursor(self):
        self._rebuild()
        pos = QCursor.pos()
        screen = QApplication.screenAt(pos)
        if screen:
            sg = screen.availableGeometry()
            x = min(pos.x(), sg.right() - self.width())
            y = min(pos.y(), sg.bottom() - self.height())
            self.move(max(x, sg.left()), max(y, sg.top()))
        else:
            self.move(pos)
        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus()

# ---------------------------------------------------------------------------
# Timer / Countdown Widget
# ---------------------------------------------------------------------------

