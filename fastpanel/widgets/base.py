import os
import subprocess
from PyQt5.QtWidgets import (
    QFrame, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QLineEdit, QMenu, QScrollArea, QGraphicsDropShadowEffect, QGraphicsOpacityEffect
)
from PyQt5.QtCore import Qt, QPoint, QRect, pyqtSignal, QTimer, QPropertyAnimation, QEasingCurve
from PyQt5.QtGui import QPainter, QColor, QFont, QPixmap, QPen

from fastpanel.constants import (
    GRID_SIZE, MIN_W, MIN_H, _DESKTOP_MODE, TYPE_LABELS, TYPE_CMD, TYPE_CMD_WINDOW,
    TYPE_SHORTCUT, TYPE_CALENDAR, TYPE_WEATHER, TYPE_DOCK, TYPE_TODO, TYPE_CLOCK,
    TYPE_MONITOR, MONITOR_SUB_ALL, MONITOR_SUB_DISK, TYPE_LAUNCHER, TYPE_NOTE,
    TYPE_QUICKACTION, TYPE_MEDIA, TYPE_CLIPBOARD, TYPE_TIMER, TYPE_GALLERY,
    TYPE_SYSINFO, TYPE_BOOKMARK, TYPE_CALC, TYPE_TRASH, TYPE_RSS
)
from fastpanel.settings import C, _settings
from fastpanel.theme import _comp_style, _bg, _hex_to_rgba, _scrollbar_style
from fastpanel.data import ComponentData
from fastpanel.utils import count_params, snap

class DragResizeMixin:
    EDGE_MARGIN = 8

    def init_drag(self):
        self._dragging = False
        self._resizing = False
        self._drag_offset = QPoint()
        self._resize_origin = QPoint()
        self._resize_geo = QRect()
        self._edges = []

    def _detect_edges(self, pos):
        m = self.EDGE_MARGIN
        edges = []
        if pos.x() >= self.width() - m: edges.append("r")
        if pos.y() >= self.height() - m: edges.append("b")
        if pos.x() <= m: edges.append("l")
        if pos.y() <= m: edges.append("t")
        return edges

    def _edge_cursor(self, edges):
        s = set(edges)
        if s == {"r","b"} or s == {"l","t"}: return Qt.SizeFDiagCursor
        if s == {"r","t"} or s == {"l","b"}: return Qt.SizeBDiagCursor
        if s & {"r","l"}: return Qt.SizeHorCursor
        if s & {"t","b"}: return Qt.SizeVerCursor
        return None

    def handle_press(self, e):
        if e.button() != Qt.LeftButton: return False
        if self.property("locked"):
            return False
        edges = self._detect_edges(e.pos())
        if edges:
            self._resizing = True
            self._edges = edges
            self._resize_origin = e.globalPos()
            self._resize_geo = self.geometry()
            return True
        if e.pos().y() < 44:
            self._dragging = True
            self._drag_offset = e.globalPos() - self.pos()
            self._drag_origin = QPoint(self.x(), self.y())
            return True
        return False

    def handle_move(self, e):
        if self._resizing:
            d = e.globalPos() - self._resize_origin
            g = QRect(self._resize_geo)
            pw = self.parent().width() if self.parent() else 9999
            mw, mh = self.minimumWidth(), self.minimumHeight()
            if "r" in self._edges: g.setWidth(min(max(mw, g.width()+d.x()), pw-g.x()))
            if "b" in self._edges: g.setHeight(max(mh, g.height()+d.y()))
            if "l" in self._edges:
                nw = g.width()-d.x()
                if nw >= mw: g.setLeft(max(0, self._resize_geo.left()+d.x()))
            if "t" in self._edges:
                nh = g.height()-d.y()
                if nh >= mh: g.setTop(self._resize_geo.top()+d.y())
            self.setGeometry(g)
            return True
        if self._dragging:
            p = e.globalPos() - self._drag_offset
            par = self.parent()
            pw = par.width() if par else 9999
            safe_top = getattr(par, '_safe_margin_top', 0) if par else 0
            safe_bottom = getattr(par, '_safe_margin_bottom', 0) if par else 0
            ph = par.height() if par else 9999
            p.setX(max(0, min(p.x(), pw-self.width())))
            p.setY(max(safe_top, min(p.y(), ph - safe_bottom - self.height())))
            self.move(p)
            return True
        edges = self._detect_edges(e.pos())
        cur = self._edge_cursor(edges)
        if cur: self.setCursor(cur)
        elif e.pos().y() < 44: self.setCursor(Qt.OpenHandCursor)
        else: self.setCursor(Qt.ArrowCursor)
        return False

    def handle_release(self, e, data):
        if self._dragging:
            x, y = snap(self.x()), snap(self.y())
            par = self.parent()
            pw = par.width() if par else 9999
            safe_top = getattr(par, '_safe_margin_top', 0) if par else 0
            safe_bottom = getattr(par, '_safe_margin_bottom', 0) if par else 0
            ph = par.height() if par else 9999
            x = max(0, min(x, pw-self.width()))
            y = max(safe_top, min(y, ph - safe_bottom - self.height()))
            self.move(x, y)
            data.x, data.y = x, y
            self._dragging = False
            return True
        if self._resizing:
            g = self.geometry()
            mw, mh = self.minimumWidth(), self.minimumHeight()
            g = QRect(snap(g.x()), snap(g.y()), max(mw, snap(g.width())), max(mh, snap(g.height())))
            self.setGeometry(g)
            data.x, data.y = g.x(), g.y()
            data.w, data.h = g.width(), g.height()
            self._resizing = False
            self._edges = []
            return True
        return False


# ---------------------------------------------------------------------------
# Component base
# ---------------------------------------------------------------------------
class CompBase(QFrame, DragResizeMixin):
    delete_requested = pyqtSignal(object)
    edit_requested = pyqtSignal(object)
    copy_requested = pyqtSignal(object)
    geometry_changed = pyqtSignal()

    def __init__(self, data: ComponentData, parent=None):
        super().__init__(parent)
        self.data = data
        self.init_drag()
        self.setProperty("compWidget", "true")
        self.setGeometry(data.x, data.y, data.w, data.h)
        if data.comp_type == TYPE_SHORTCUT:
            self.setMinimumSize(GRID_SIZE * 4, GRID_SIZE * 4)
        elif data.comp_type == TYPE_CALENDAR:
            self.setMinimumSize(GRID_SIZE * 14, GRID_SIZE * 14)
        elif data.comp_type == TYPE_WEATHER:
            self.setMinimumSize(GRID_SIZE * 12, GRID_SIZE * 10)
        elif data.comp_type == TYPE_DOCK:
            self.setMinimumSize(GRID_SIZE * 6, GRID_SIZE * 4)
        elif data.comp_type == TYPE_TODO:
            self.setMinimumSize(GRID_SIZE * 10, GRID_SIZE * 8)
        elif data.comp_type == TYPE_CLOCK:
            self.setMinimumSize(GRID_SIZE * 8, GRID_SIZE * 6)
        elif data.comp_type == TYPE_MONITOR:
            sub = data.cmd.strip() if data.cmd else MONITOR_SUB_ALL
            if sub == MONITOR_SUB_ALL:
                self.setMinimumSize(GRID_SIZE * 20, GRID_SIZE * 16)
            elif sub == MONITOR_SUB_DISK:
                self.setMinimumSize(GRID_SIZE * 16, GRID_SIZE * 8)
            else:
                self.setMinimumSize(GRID_SIZE * 12, GRID_SIZE * 8)
        elif data.comp_type == TYPE_LAUNCHER:
            self.setMinimumSize(GRID_SIZE * 14, GRID_SIZE * 16)
        elif data.comp_type == TYPE_NOTE:
            self.setMinimumSize(GRID_SIZE * 10, GRID_SIZE * 8)
        elif data.comp_type == TYPE_QUICKACTION:
            self.setMinimumSize(GRID_SIZE * 16, GRID_SIZE * 10)
        elif data.comp_type == TYPE_MEDIA:
            self.setMinimumSize(GRID_SIZE * 14, GRID_SIZE * 6)
        elif data.comp_type == TYPE_CLIPBOARD:
            self.setMinimumSize(GRID_SIZE * 12, GRID_SIZE * 10)
        elif data.comp_type == TYPE_TIMER:
            self.setMinimumSize(GRID_SIZE * 10, GRID_SIZE * 8)
        elif data.comp_type == TYPE_GALLERY:
            self.setMinimumSize(GRID_SIZE * 12, GRID_SIZE * 10)
        elif data.comp_type == TYPE_SYSINFO:
            self.setMinimumSize(GRID_SIZE * 14, GRID_SIZE * 10)
        elif data.comp_type == TYPE_BOOKMARK:
            self.setMinimumSize(GRID_SIZE * 12, GRID_SIZE * 10)
        elif data.comp_type == TYPE_CALC:
            self.setMinimumSize(GRID_SIZE * 12, GRID_SIZE * 14)
        elif data.comp_type == TYPE_TRASH:
            self.setMinimumSize(GRID_SIZE * 10, GRID_SIZE * 6)
        elif data.comp_type == TYPE_RSS:
            self.setMinimumSize(GRID_SIZE * 14, GRID_SIZE * 14)
        elif data.comp_type == TYPE_CMD and not data.show_output:
            np = count_params(data.cmd)
            mh = GRID_SIZE * (2 + np * 2) if np > 0 else GRID_SIZE * 2
            self.setMinimumSize(GRID_SIZE * 13, mh)
        else:
            self.setMinimumSize(MIN_W, MIN_H)
        self.setMouseTracking(True)
        self.setStyleSheet(_comp_style())
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._ctx_menu)
        self._apply_opacity_effect()

    def _apply_opacity_effect(self):
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24); shadow.setOffset(0, 4); shadow.setColor(QColor(0, 0, 0, 100))
        self.setGraphicsEffect(shadow)

    def refresh_theme(self):
        for timer in self.findChildren(QTimer):
            timer.stop()
        old_layout = self.layout()
        if old_layout:
            self._clear_layout_recursive(old_layout)
            QWidget().setLayout(old_layout)
        build_fn = getattr(self, '_build_ui', None) or getattr(self, '_build', None)
        if build_fn:
            build_fn()

    @staticmethod
    def _clear_layout_recursive(layout):
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
            elif item.layout():
                CompBase._clear_layout_recursive(item.layout())

    def _get_grid(self):
        from fastpanel.panels.grid import GridPanel
        p = self.parent()
        return p if isinstance(p, GridPanel) else None

    def _get_batch(self):
        """Return the set of widgets that should move together (selection or group)."""
        grid = self._get_grid()
        if not grid:
            return [self]
        if self in grid._selected and len(grid._selected) > 1:
            return list(grid._selected)
        gid = getattr(self.data, '_group_id', None)
        if gid:
            return [w for w in grid._components if getattr(w.data, '_group_id', None) == gid]
        return [self]

    def _ctx_menu(self, pos):
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{ background:{C['base']}; border:1px solid {C['surface0']}; border-radius:8px; padding:6px 0; }}
            QMenu::item {{ color:{C['text']}; padding:8px 28px 8px 16px; font-size:12px; }}
            QMenu::item:selected {{ background:{_bg('surface1')}; }}
            QMenu::separator {{ height:1px; background:{_bg('surface0')}; margin:4px 8px; }}
        """)

        grid = self._get_grid()
        in_selection = grid and self in grid._selected and len(grid._selected) > 1
        gid = getattr(self.data, '_group_id', None)

        ea = ca = ga = ua = da = None
        if in_selection:
            ga = menu.addAction("🔗  组合")
            menu.addSeparator()
        ea = menu.addAction("✏  修改"); ca = menu.addAction("📋  复制")
        if gid:
            menu.addSeparator()
            ua = menu.addAction("🔓  解除组合")
        menu.addSeparator(); da = menu.addAction("🗑  删除")
        a = menu.exec_(self.mapToGlobal(pos))
        if a is None: return
        if a == ea: self.edit_requested.emit(self)
        elif a == ca: self.copy_requested.emit(self)
        elif a == da: self.delete_requested.emit(self)
        elif ga and a == ga and grid:
            grid._group_selected()
        elif ua and a == ua and grid:
            grid._ungroup(gid)

    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton:
            super().mousePressEvent(e); return
        grid = self._get_grid()
        batch = self._get_batch()
        if len(batch) > 1 and not self._detect_edges(e.pos()):
            self._batch_dragging = True
            self._batch_drag_origin = e.globalPos()
            self._batch_offsets = [(w, QPoint(w.x(), w.y())) for w in batch]
            for w in batch:
                w.raise_()
            grid = self._get_grid()
            if grid:
                grid._overlay.raise_()
            return
        if grid and grid._selected and self not in grid._selected:
            grid._clear_selection()
        self._batch_dragging = False
        self.handle_press(e); self.raise_()

    def mouseMoveEvent(self, e):
        if getattr(self, '_batch_dragging', False):
            delta = e.globalPos() - self._batch_drag_origin
            par = self.parent()
            pw = par.width() if par else 9999
            ph = par.height() if par else 9999
            safe_top = getattr(par, '_safe_margin_top', 0) if par else 0
            safe_bottom = getattr(par, '_safe_margin_bottom', 0) if par else 0
            min_x = min(orig.x() for _, orig in self._batch_offsets)
            min_y = min(orig.y() for _, orig in self._batch_offsets)
            max_r = max(orig.x() + w.width() for w, orig in self._batch_offsets)
            max_b = max(orig.y() + w.height() for w, orig in self._batch_offsets)
            dx, dy = delta.x(), delta.y()
            if min_x + dx < 0: dx = -min_x
            if min_y + dy < safe_top: dy = safe_top - min_y
            if max_r + dx > pw: dx = pw - max_r
            if max_b + dy > ph - safe_bottom: dy = ph - safe_bottom - max_b
            for w, orig in self._batch_offsets:
                w.move(orig.x() + dx, orig.y() + dy)
            grid = self._get_grid()
            if grid:
                grid._update_overlay()
            return
        self.handle_move(e)

    def mouseReleaseEvent(self, e):
        if getattr(self, '_batch_dragging', False):
            self._batch_dragging = False
            par = self.parent()
            pw = par.width() if par else 9999
            ph = par.height() if par else 9999
            safe_top = getattr(par, '_safe_margin_top', 0) if par else 0
            safe_bottom = getattr(par, '_safe_margin_bottom', 0) if par else 0
            grid = self._get_grid()
            all_snapshot = [(w, w.data.x, w.data.y) for w in grid._components] if grid else []
            batch_origins = list(self._batch_offsets)
            for w, _ in self._batch_offsets:
                x, y = snap(w.x()), snap(w.y())
                x = max(0, min(x, pw - w.width()))
                y = max(safe_top, min(y, ph - safe_bottom - w.height()))
                w.move(x, y); w.data.x, w.data.y = x, y
            if grid:
                for w, _ in self._batch_offsets:
                    grid._resolve_overlaps(w)
                if grid._layout_overflow():
                    for w, ox, oy in all_snapshot:
                        w.move(ox, oy)
                        w.data.x, w.data.y = ox, oy
                    grid._show_toast("⚠ 布局空间不足，组件已回到原位")
                grid._update_overlay()
            self.geometry_changed.emit()
            return
        if self.handle_release(e, self.data): self.geometry_changed.emit()


# ---------------------------------------------------------------------------
# Fullscreen Output Dialog
# ---------------------------------------------------------------------------
class _ExpandBtn(QPushButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(28, 28)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("全屏查看输出")

    def paintEvent(self, e):
        from PyQt5.QtGui import QPen
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        bg = QColor(C['surface1'])
        p.setBrush(bg); p.setPen(Qt.NoPen)
        p.drawRoundedRect(0, 0, self.width(), self.height(), 6, 6)
        pen = QPen(QColor(C['subtext0']), 2)
        p.setPen(pen); p.setBrush(Qt.NoBrush)
        m = 7; w, h = self.width(), self.height()
        p.drawLine(w - m, m, w - m - 5, m)
        p.drawLine(w - m, m, w - m, m + 5)
        p.drawLine(w - m, m, w - m - 4, m + 4)
        p.drawLine(m, h - m, m + 5, h - m)
        p.drawLine(m, h - m, m, h - m - 5)
        p.drawLine(m, h - m, m + 4, h - m - 4)
        p.end()


class FullscreenOutputOverlay(QWidget):
    run_toggled = pyqtSignal()
    closed = pyqtSignal()

    def __init__(self, title, comp_type=TYPE_CMD, parent=None):
        super().__init__(parent)
        self._start_label = "启动" if comp_type == TYPE_CMD_WINDOW else "执行"
        self._stop_label = "停止"
        self.setAutoFillBackground(True)
        lay = QVBoxLayout(self); lay.setContentsMargins(16, 12, 16, 12); lay.setSpacing(8)
        h = QHBoxLayout(); h.setSpacing(8)
        lbl = QLabel(title)
        lbl.setStyleSheet(f"color:{C['text']}; font-size:16px; font-weight:bold;")
        h.addWidget(lbl)
        h.addStretch()
        self._run_btn = QPushButton(f"▶  {self._start_label}")
        self._run_btn.setStyleSheet(f"background:{C['green']}; color:{C['crust']}; border:none; border-radius:6px; padding:6px 16px; font-weight:bold; font-size:12px;")
        self._run_btn.setCursor(Qt.PointingHandCursor); self._run_btn.clicked.connect(self.run_toggled.emit)
        h.addWidget(self._run_btn)
        close_btn = QPushButton("↙↗ 退出全屏")
        close_btn.setStyleSheet(f"background:{C['surface1']}; color:{C['text']}; border:none; border-radius:6px; padding:6px 16px; font-size:12px;")
        close_btn.setCursor(Qt.PointingHandCursor); close_btn.clicked.connect(self._close)
        h.addWidget(close_btn)
        lay.addLayout(h)
        self._output = QTextEdit(); self._output.setReadOnly(True)
        self._output.setStyleSheet(f"background:{C['crust']}; color:{C['green']}; border:1px solid {C['surface0']}; border-radius:8px; font-family:'JetBrains Mono','Consolas',monospace; font-size:12px; padding:8px;")
        lay.addWidget(self._output, 1)
        ir = QHBoxLayout(); ir.setSpacing(6)
        self._stdin = QLineEdit(); self._stdin.setPlaceholderText("输入内容（回车发送）…")
        self._stdin.setStyleSheet(f"background:{C['crust']}; color:{C['text']}; border:1px solid {C['surface0']}; border-radius:6px; padding:6px 10px; font-family:'JetBrains Mono','Consolas',monospace; font-size:12px;")
        ir.addWidget(self._stdin)
        self._send_btn = QPushButton("发送")
        self._send_btn.setStyleSheet(f"background:{C['sky']}; color:{C['crust']}; border:none; border-radius:6px; font-size:12px; font-weight:bold; padding:6px 16px;")
        self._send_btn.setCursor(Qt.PointingHandCursor)
        ir.addWidget(self._send_btn)
        lay.addLayout(ir)
        self._write_fn = None
        self._connected = False

    def set_write_fn(self, fn):
        self._write_fn = fn
        if not self._connected:
            self._stdin.returnPressed.connect(self._do_send)
            self._send_btn.clicked.connect(self._do_send)
            self._connected = True

    def set_running(self, running):
        if running:
            self._run_btn.setText(f"■  {self._stop_label}")
            self._run_btn.setStyleSheet(f"background:{C['red']}; color:{C['crust']}; border:none; border-radius:6px; padding:6px 16px; font-weight:bold; font-size:12px;")
        else:
            self._run_btn.setText(f"▶  {self._start_label}")
            self._run_btn.setStyleSheet(f"background:{C['green']}; color:{C['crust']}; border:none; border-radius:6px; padding:6px 16px; font-weight:bold; font-size:12px;")

    def set_input_enabled(self, enabled):
        self._stdin.setEnabled(enabled)
        self._send_btn.setEnabled(enabled)

    def _do_send(self):
        if self._write_fn:
            self._write_fn(self._stdin.text())
            self._stdin.clear()

    def append_line(self, html):
        self._output.append(html)

    def sync_content(self, source: QTextEdit):
        self._output.setHtml(source.toHtml())

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(C['base']))
        p.end()

    def _close(self):
        self.hide()
        self.closed.emit()

    def sync_content(self, source: QTextEdit):
        self._output.setHtml(source.toHtml())
        sb = self._output.verticalScrollBar()
        sb.setValue(sb.maximum())


# ---------------------------------------------------------------------------
# CMD Component
# ---------------------------------------------------------------------------

