import os
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea
)
from PyQt5.QtCore import Qt, QPoint, QRect, QTimer, pyqtSignal
from PyQt5.QtGui import QPainter, QColor, QPen, QIcon

from fastpanel.constants import GRID_SIZE, _BASE_DIR
from fastpanel.settings import C
from fastpanel.theme import _scrollbar_style
from fastpanel.panels.grid import GridPanel

class _PanelWindow(QMainWindow):
    closed = pyqtSignal(str)

    def __init__(self, panel_data, parent_main):
        super().__init__()
        self._panel_data = panel_data
        self._parent_main = parent_main
        self._panel_id = panel_data.id
        self._locked = False
        self.setWindowTitle(f"FastPanel — {panel_data.name}")
        self.setWindowFlags(Qt.FramelessWindowHint)
        _icon_path = os.path.join(_BASE_DIR, "fastpanel.svg")
        if os.path.isfile(_icon_path):
            self.setWindowIcon(QIcon(_icon_path))
        self.setMinimumSize(640, 480)
        self.resize(1000, 700)
        self._tb_dragging = False
        self._tb_offset = QPoint()
        self._resizing = False
        self._resize_edge = 0
        self._build_ui()
        self._apply_style()

    def _build_ui(self):
        cw = QWidget(); self.setCentralWidget(cw)
        root = QVBoxLayout(cw); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)

        tb = QFrame(); tb.setObjectName("toolbar"); tb.setFixedHeight(32)
        tl = QHBoxLayout(tb); tl.setContentsMargins(12, 0, 4, 0); tl.setSpacing(6)
        logo = QLabel(f"⚡ {self._panel_data.name}")
        logo.setObjectName("logo"); tl.addWidget(logo)
        tl.addStretch()
        self._cnt = QLabel("0 个组件"); self._cnt.setObjectName("countLabel"); tl.addWidget(self._cnt)

        self._grid_btn = QPushButton("▦"); self._grid_btn.setObjectName("gridBtn")
        self._grid_btn.setCursor(Qt.PointingHandCursor); self._grid_btn.setToolTip("显示/隐藏网格")
        self._grid_btn.setProperty("active", True)
        self._grid_btn.clicked.connect(self._toggle_grid); tl.addWidget(self._grid_btn)

        self._lock_btn = QPushButton("🔓"); self._lock_btn.setObjectName("lockBtn")
        self._lock_btn.setCursor(Qt.PointingHandCursor); self._lock_btn.setToolTip("锁定/解锁布局")
        self._lock_btn.clicked.connect(self._toggle_lock); tl.addWidget(self._lock_btn)

        for txt, oid, slot in [("—", "winMinBtn", self.showMinimized),
                                ("", "winMaxBtn", self._toggle_max),
                                ("✕", "winCloseBtn", self.close)]:
            b = QPushButton(txt); b.setObjectName(oid); b.setFixedSize(30, 22)
            b.setCursor(Qt.PointingHandCursor); b.clicked.connect(slot); tl.addWidget(b)
            if oid == "winMaxBtn":
                self._max_btn = b
        self._max_btn._is_restore = False
        _orig_paint = self._max_btn.paintEvent
        def _max_paint(event):
            _orig_paint(event)
            pp = QPainter(self._max_btn)
            pp.setRenderHint(QPainter.Antialiasing)
            pen = QPen(QColor(C['subtext0']), 1.2)
            pp.setPen(pen); pp.setBrush(Qt.NoBrush)
            if self._max_btn._is_restore:
                pp.drawRect(12, 4, 8, 8); pp.drawRect(9, 9, 8, 8)
            else:
                pp.drawRect(10, 5, 10, 10)
            pp.end()
        self._max_btn.paintEvent = _max_paint
        root.addWidget(tb)

        sc = QScrollArea(); sc.setWidgetResizable(False)
        sc.setStyleSheet(f"QScrollArea {{ background: transparent; border: none; }}" + _scrollbar_style(6))
        self._grid = GridPanel()
        self._grid.data_changed.connect(self._on_data_changed)
        sc.setWidget(self._grid)
        self._scroll = sc
        root.addWidget(sc, 1)

        desktop_safe_top = 0
        if self._parent_main and self._parent_main._grids:
            desktop_safe_top = self._parent_main._grids[0]._safe_margin_top

        for cd in self._panel_data.components:
            self._grid.add_component(cd)
        if desktop_safe_top > 0:
            for w in self._grid.components:
                w.data.y = max(0, w.data.y - desktop_safe_top)
                w.move(w.data.x, w.data.y)
        self._desktop_safe_top = desktop_safe_top

        groups = {}
        for w in self._grid.components:
            gid = getattr(w.data, '_group_id', None)
            if gid:
                groups.setdefault(gid, []).append(w.data.id)
                w.setProperty("locked", True)
        self._grid._groups = groups
        self._grid._update_overlay()
        self._cnt.setText(f"{len(self._grid.components)} 个组件")

    def _apply_style(self):
        self.setStyleSheet(f"""
            QMainWindow {{ background: {C['crust']}; }}
            #toolbar {{ background: {C['mantle']}; border-bottom: 1px solid {C['surface0']}; }}
            #logo {{ color: {C['blue']}; font-size: 13px; font-weight: bold; letter-spacing: 1px; }}
            #countLabel {{ color: {C['overlay0']}; font-size: 11px; margin-right: 8px; }}
            #gridBtn, #lockBtn {{
                background: {C['surface1']}; color: {C['text']};
                border: none; border-radius: 6px; padding: 4px 8px; font-size: 13px;
            }}
            #gridBtn:hover, #lockBtn:hover {{ background: {C['surface2']}; }}
            #winMinBtn, #winMaxBtn {{ background: transparent; color: {C['subtext0']}; border: none; border-radius: 6px; font-size: 14px; }}
            #winMinBtn:hover, #winMaxBtn:hover {{ background: {C['surface1']}; }}
            #winCloseBtn {{ background: transparent; color: {C['subtext0']}; border: none; border-radius: 6px; font-size: 14px; }}
            #winCloseBtn:hover {{ background: {C['red']}; color: {C['crust']}; }}
        """)

    def _toggle_grid(self):
        show = not self._grid._show_grid
        self._grid.set_show_grid(show)
        self._grid_btn.setProperty("active", show)
        self._grid_btn.style().unpolish(self._grid_btn)
        self._grid_btn.style().polish(self._grid_btn)

    def _toggle_lock(self):
        self._locked = not self._locked
        self._lock_btn.setText("🔒" if self._locked else "🔓")
        for w in self._grid.components:
            w.setProperty("locked", self._locked)

    def _toggle_max(self):
        if self._max_btn._is_restore:
            self.showNormal(); self._max_btn._is_restore = False
        else:
            self.showMaximized(); self._max_btn._is_restore = True
        self._max_btn.update()

    def _on_data_changed(self):
        self._cnt.setText(f"{len(self._grid.components)} 个组件")
        self._sync_back()

    def _sync_back(self):
        self._panel_data.components = [w.data for w in self._grid.components]
        if self._parent_main:
            self._parent_main._save_data()

    def _restore_desktop_offsets(self):
        if self._desktop_safe_top > 0:
            for w in self._grid.components:
                w.data.y = w.data.y + self._desktop_safe_top
                w.move(w.data.x, w.data.y)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        QTimer.singleShot(0, self._sync_size)

    def showEvent(self, e):
        super().showEvent(e)
        QTimer.singleShot(0, self._sync_size)

    def _sync_size(self):
        vp = self._scroll.viewport()
        self._grid.recalc_size(vp.width(), vp.height())

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            edge = self._hit_edge(e.pos())
            if edge:
                self._resizing = True; self._resize_edge = edge
                self._resize_origin = e.globalPos(); self._resize_geo = self.geometry()
            elif e.pos().y() < 32:
                self._tb_dragging = True; self._tb_offset = e.globalPos() - self.pos()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._resizing:
            self._do_resize(e.globalPos())
        elif self._tb_dragging:
            self.move(e.globalPos() - self._tb_offset)
        else:
            edge = self._hit_edge(e.pos())
            cursors = {1: Qt.SizeVerCursor, 2: Qt.SizeVerCursor, 4: Qt.SizeHorCursor, 8: Qt.SizeHorCursor,
                       5: Qt.SizeFDiagCursor, 6: Qt.SizeBDiagCursor, 9: Qt.SizeBDiagCursor, 10: Qt.SizeFDiagCursor}
            self.setCursor(cursors.get(edge, Qt.ArrowCursor))
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        self._tb_dragging = False; self._resizing = False
        super().mouseReleaseEvent(e)

    def mouseDoubleClickEvent(self, e):
        if e.pos().y() < 32:
            self._toggle_max()

    def _hit_edge(self, pos, m=6):
        w, h = self.width(), self.height()
        edge = 0
        if pos.y() >= h - m: edge |= 2
        if pos.x() <= m: edge |= 4
        if pos.x() >= w - m: edge |= 8
        return edge

    def _do_resize(self, gpos):
        dx = gpos.x() - self._resize_origin.x()
        dy = gpos.y() - self._resize_origin.y()
        g = QRect(self._resize_geo)
        e = self._resize_edge
        if e & 2: g.setBottom(g.bottom() + dy)
        if e & 4: g.setLeft(g.left() + dx)
        if e & 8: g.setRight(g.right() + dx)
        if g.width() >= 400 and g.height() >= 300:
            self.setGeometry(g)

    def closeEvent(self, e):
        self._restore_desktop_offsets()
        self._sync_back()
        self.closed.emit(self._panel_id)
        super().closeEvent(e)


# ---------------------------------------------------------------------------
# Main Window
# ---------------------------------------------------------------------------

