import os
import uuid
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QMenu, QGraphicsDropShadowEffect
)
from PyQt5.QtCore import Qt, QPoint, QRect, QTimer, pyqtSignal
from PyQt5.QtGui import QPainter, QColor, QFont, QPixmap, QPen, QLinearGradient

from fastpanel.constants import GRID_SIZE, MIN_W, MIN_H, PANEL_PADDING, _DESKTOP_MODE, _BASE_DIR
from fastpanel.settings import C, _settings
from fastpanel.theme import _comp_style, _bg, _scrollbar_style
from fastpanel.widgets.factory import create_widget
from fastpanel.data import ComponentData
from fastpanel.utils import snap, _confirm_dialog

class _SelectionOverlay(QWidget):
    """Transparent overlay drawn above components for selection / group frames."""
    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.sel_rect = QRect()
        self.selecting = False
        self.bounding = QRect()
        self.group_bounds = []

    def paintEvent(self, e):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)

        for gr in self.group_bounds:
            p.setBrush(Qt.NoBrush)
            pen = QColor(C['peach']); pen.setAlpha(120)
            p.setPen(pen)
            p.drawRoundedRect(gr.adjusted(-4, -4, 4, 4), 14, 14)

        if not self.bounding.isNull():
            sc = QColor(C['blue']); sc.setAlpha(25)
            p.setBrush(sc)
            pen = QColor(C['blue']); pen.setAlpha(160)
            p.setPen(pen)
            p.drawRoundedRect(self.bounding.adjusted(-4, -4, 4, 4), 14, 14)

        if self.selecting and not self.sel_rect.isNull():
            sc = QColor(C['blue']); sc.setAlpha(30)
            p.setBrush(sc)
            p.setPen(QColor(C['blue']))
            p.drawRect(self.sel_rect)
        p.end()


class GridPanel(QWidget):
    data_changed = pyqtSignal()
    desktop_ctx_menu_requested = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._components: list = []
        self._selected: list = []
        self._groups: dict = {}
        self._selecting = False
        self._sel_origin = QPoint()
        self._multi_dragging = False
        self._multi_drag_origin = QPoint()
        self._multi_drag_offsets = []
        self._bg_pixmap = None
        self._bg_opacity = 30
        self._bg_slideshow_dir = ""
        self._bg_slideshow_interval = 300
        self._bg_slideshow_files = []
        self._bg_slideshow_idx = 0
        self._bg_slideshow_timer = QTimer(self)
        self._bg_slideshow_timer.timeout.connect(self._next_slideshow)
        self._bg_gradient = ""
        self._bg_mode = _settings.get("bg_mode", "tile")
        self._bg_per_monitor = {}
        per_mon = _settings.get("bg_per_monitor", {})
        for name, path in per_mon.items():
            if path and os.path.isfile(path):
                self._bg_per_monitor[name] = QPixmap(path)
        self._show_grid = _settings.get("show_grid", True)
        self._safe_margin_top = 0
        self._safe_margin_bottom = 0
        self.setAutoFillBackground(True)
        self.setMouseTracking(True)
        pal = self.palette(); pal.setColor(pal.Window, QColor(C["crust"])); self.setPalette(pal)
        self._overlay = _SelectionOverlay(self)
        self._overlay.show()
        bg = _settings.get("bg_image", "")
        if bg and os.path.isfile(bg):
            self._bg_pixmap = QPixmap(bg)
        self._bg_opacity = _settings.get("bg_opacity", 30)
        grad = _settings.get("bg_gradient", "")
        if grad:
            self._bg_gradient = grad
        ss_dir = _settings.get("bg_slideshow_dir", "")
        if ss_dir:
            self.set_bg_slideshow(ss_dir, _settings.get("bg_slideshow_interval", 300))

    def set_bg_image(self, path, opacity=30):
        if path and os.path.isfile(path):
            self._bg_pixmap = QPixmap(path)
        else:
            self._bg_pixmap = None
        self._bg_opacity = opacity

    def set_bg_gradient(self, gradient_str):
        self._bg_gradient = gradient_str
        self.update()

    def set_bg_mode(self, mode):
        self._bg_mode = mode
        self.update()

    def set_per_monitor_bg(self, mapping):
        self._bg_per_monitor = {}
        for name, path in mapping.items():
            if path and os.path.isfile(path):
                self._bg_per_monitor[name] = QPixmap(path)
        self.update()

    def set_bg_slideshow(self, directory, interval=300):
        self._bg_slideshow_dir = directory
        self._bg_slideshow_interval = max(10, interval)
        self._bg_slideshow_timer.stop()
        self._bg_slideshow_files = []
        self._bg_slideshow_idx = 0
        if directory and os.path.isdir(directory):
            exts = {'.png', '.jpg', '.jpeg', '.bmp', '.webp'}
            self._bg_slideshow_files = sorted(
                [os.path.join(directory, f) for f in os.listdir(directory)
                 if os.path.splitext(f)[1].lower() in exts])
            if self._bg_slideshow_files:
                self._bg_pixmap = QPixmap(self._bg_slideshow_files[0])
                self._bg_slideshow_timer.start(interval * 1000)
                self.update()

    def _next_slideshow(self):
        if not self._bg_slideshow_files:
            return
        self._bg_slideshow_idx = (self._bg_slideshow_idx + 1) % len(self._bg_slideshow_files)
        path = self._bg_slideshow_files[self._bg_slideshow_idx]
        if os.path.isfile(path):
            self._bg_pixmap = QPixmap(path)
            self.update()

    def set_safe_margins(self, top, bottom):
        self._safe_margin_top = ((top + GRID_SIZE - 1) // GRID_SIZE) * GRID_SIZE
        self._safe_margin_bottom = ((bottom + GRID_SIZE - 1) // GRID_SIZE) * GRID_SIZE

    def set_show_grid(self, show):
        self._show_grid = show

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._overlay.setGeometry(0, 0, self.width(), self.height())
        self._overlay.raise_()

    def paintEvent(self, e):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(e.rect(), QColor(C["crust"]))
        if self._bg_gradient:
            from PyQt5.QtGui import QLinearGradient
            parts = self._bg_gradient.split(",")
            if len(parts) >= 2:
                grad = QLinearGradient(0, 0, self.width(), self.height())
                for i, color_str in enumerate(parts):
                    stop = i / max(len(parts) - 1, 1)
                    grad.setColorAt(stop, QColor(color_str.strip()))
                p.setOpacity(self._bg_opacity / 100.0)
                p.fillRect(e.rect(), grad)
                p.setOpacity(1.0)
        if self._bg_pixmap and not self._bg_pixmap.isNull():
            p.setOpacity(self._bg_opacity / 100.0)
            if self._bg_mode == "clone":
                screens = QApplication.screens()
                win = self.window()
                win_pos = win.pos() if win else QPoint(0, 0)
                for s in screens:
                    sg = s.geometry()
                    local_rect = QRect(sg.x() - win_pos.x(), sg.y() - win_pos.y(), sg.width(), sg.height())
                    scaled = self._bg_pixmap.scaled(local_rect.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                    ox = local_rect.x() + (local_rect.width() - scaled.width()) // 2
                    oy = local_rect.y() + (local_rect.height() - scaled.height()) // 2
                    p.setClipRect(local_rect)
                    p.drawPixmap(ox, oy, scaled)
                p.setClipping(False)
            elif self._bg_mode == "per_monitor" and self._bg_per_monitor:
                screens = QApplication.screens()
                win = self.window()
                win_pos = win.pos() if win else QPoint(0, 0)
                for s in screens:
                    sg = s.geometry()
                    local_rect = QRect(sg.x() - win_pos.x(), sg.y() - win_pos.y(), sg.width(), sg.height())
                    pm = self._bg_per_monitor.get(s.name())
                    if pm is None:
                        pm = self._bg_pixmap
                    if pm and not pm.isNull():
                        scaled = pm.scaled(local_rect.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                        ox = local_rect.x() + (local_rect.width() - scaled.width()) // 2
                        oy = local_rect.y() + (local_rect.height() - scaled.height()) // 2
                        p.setClipRect(local_rect)
                        p.drawPixmap(ox, oy, scaled)
                p.setClipping(False)
            else:
                scaled = self._bg_pixmap.scaled(self.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                x = (self.width() - scaled.width()) // 2
                y = (self.height() - scaled.height()) // 2
                p.drawPixmap(x, y, scaled)
            p.setOpacity(1.0)
        safe_top = self._safe_margin_top
        safe_bot = self._safe_margin_bottom
        if self._show_grid:
            dc = QColor(C["overlay0"]); dc.setAlpha(80); p.setPen(Qt.NoPen); p.setBrush(dc)
            grid_top = ((safe_top + GRID_SIZE - 1) // GRID_SIZE) * GRID_SIZE
            grid_bottom = ((self.height() - safe_bot) // GRID_SIZE) * GRID_SIZE
            r = e.rect(); x0 = (r.left()//GRID_SIZE)*GRID_SIZE
            for x in range(x0, r.right()+1, GRID_SIZE):
                for y in range(grid_top, min(r.bottom()+1, grid_bottom + 1), GRID_SIZE):
                    p.drawEllipse(x-1, y-1, 2, 2)
        if safe_top > 0 or safe_bot > 0:
            boundary_color = QColor(C['surface1']); boundary_color.setAlpha(60)
            pen = QPen(boundary_color, 1, Qt.DashLine)
            p.setPen(pen)
            if safe_top > 0:
                p.drawLine(0, safe_top, self.width(), safe_top)
            if safe_bot > 0:
                p.drawLine(0, self.height() - safe_bot, self.width(), self.height() - safe_bot)
        p.end()

    def _sel_bounding(self):
        if not self._selected:
            return QRect()
        rects = [w.geometry() for w in self._selected]
        r = rects[0]
        for rr in rects[1:]:
            r = r.united(rr)
        return r

    def _group_bounding(self, gid):
        members = [w for w in self._components if getattr(w.data, '_group_id', None) == gid]
        if not members:
            return QRect()
        r = members[0].geometry()
        for w in members[1:]:
            r = r.united(w.geometry())
        return r

    def _update_overlay(self):
        if self._selecting:
            self._overlay.sel_rect = QRect(self._sel_origin, self._sel_origin).normalized()
            self._overlay.selecting = True
        else:
            self._overlay.selecting = False
            self._overlay.sel_rect = QRect()
        self._overlay.bounding = self._sel_bounding()
        seen = set()
        gbs = []
        for gid, _ in self._groups.items():
            if gid not in seen:
                seen.add(gid)
                gb = self._group_bounding(gid)
                if not gb.isNull():
                    gbs.append(gb)
        self._overlay.group_bounds = gbs
        self._overlay.raise_()
        self._overlay.update()

    def contextMenuEvent(self, e):
        child = self.childAt(e.pos())
        comp = self._find_comp(child) if child and child is not self._overlay else None
        if comp is None and _DESKTOP_MODE:
            self.desktop_ctx_menu_requested.emit(e.globalPos())
            e.accept()
            return
        super().contextMenuEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            child = self.childAt(e.pos())
            if child is None or child is self._overlay:
                if self._selected:
                    self._clear_selection()
                self._selecting = True
                self._sel_origin = e.pos()
                self._overlay.selecting = True
                self._overlay.sel_rect = QRect(e.pos(), e.pos())
                self._overlay.raise_()
                self._overlay.update()

    def mouseMoveEvent(self, e):
        if self._selecting:
            self._overlay.sel_rect = QRect(self._sel_origin, e.pos()).normalized()
            self._overlay.update()

    def mouseReleaseEvent(self, e):
        if self._selecting:
            self._selecting = False
            sr = self._overlay.sel_rect
            self._selected = [w for w in self._components if sr.intersects(w.geometry())]
            self._update_overlay()

    def _find_comp(self, widget):
        from fastpanel.widgets.base import CompBase
        w = widget
        while w and w is not self:
            if isinstance(w, CompBase):
                return w
            w = w.parent()
        return None

    def _clear_selection(self):
        self._selected.clear()
        self._update_overlay()

    def _group_selected(self):
        if len(self._selected) < 2:
            return
        gid = str(uuid.uuid4())
        self._groups[gid] = [w.data.id for w in self._selected]
        for w in self._selected:
            w.data._group_id = gid
            w.setProperty("locked", True)
        self._clear_selection()
        self._update_overlay()
        self.data_changed.emit()

    def _ungroup(self, gid):
        if gid in self._groups:
            for w in self._components:
                if getattr(w.data, '_group_id', None) == gid:
                    w.data._group_id = None
                    w.setProperty("locked", False)
            del self._groups[gid]
        self._clear_selection()
        self._update_overlay()
        self.data_changed.emit()

    def _get_group_of(self, w):
        return getattr(w.data, '_group_id', None)

    def recalc_size(self, vw, vh):
        if _DESKTOP_MODE:
            self.setFixedSize(vw, vh)
            return
        mb = vh
        for c in self._components:
            b = c.data.y + c.data.h + PANEL_PADDING
            if b > mb: mb = b
        self.setFixedSize(vw, max(vh, mb))

    def add_component(self, data):
        w = create_widget(data, self)
        w.delete_requested.connect(self._remove)
        w.edit_requested.connect(self._edit)
        w.copy_requested.connect(self._copy)
        w.geometry_changed.connect(self._child_moved)
        w.show(); self._components.append(w); self.data_changed.emit()
        return w

    def _show_toast(self, text, duration=2500):
        toast = QLabel(text, self)
        toast.setAlignment(Qt.AlignCenter)
        toast.setStyleSheet(f"""
            QLabel {{
                background: {C['red']}; color: {C['crust']};
                font-size: 16px; font-weight: bold;
                padding: 16px 32px; border-radius: 10px;
            }}
        """)
        toast.adjustSize()
        cursor_pos = self.mapFromGlobal(QApplication.desktop().cursor().pos())
        screen = QApplication.screenAt(QApplication.desktop().cursor().pos())
        if screen:
            sg = screen.geometry()
            local_center_x = self.mapFromGlobal(QPoint(sg.center().x(), sg.y())).x()
            local_top_y = self.mapFromGlobal(QPoint(0, sg.y())).y()
            toast.move(local_center_x - toast.width() // 2, local_top_y + self._safe_margin_top + 40)
        else:
            toast.move((self.width() - toast.width()) // 2, self._safe_margin_top + 40)
        toast.show()
        toast.raise_()
        shadow = QGraphicsDropShadowEffect(toast)
        shadow.setBlurRadius(20); shadow.setOffset(0, 4); shadow.setColor(QColor(0, 0, 0, 120))
        toast.setGraphicsEffect(shadow)
        QTimer.singleShot(duration, toast.deleteLater)

    def _child_moved(self):
        mover = self.sender()
        if mover:
            mover_origin = getattr(mover, '_drag_origin', None)
            snapshot = [(w, w.data.x, w.data.y) for w in self._components if w is not mover]
            self._resolve_overlaps(mover)
            if self._layout_overflow():
                for w, ox, oy in snapshot:
                    w.move(ox, oy)
                    w.data.x, w.data.y = ox, oy
                if mover_origin:
                    mover.move(mover_origin)
                    mover.data.x, mover.data.y = mover_origin.x(), mover_origin.y()
                self._show_toast("⚠ 布局空间不足，组件已回到原位")
        par = self.parent()
        if par:
            vp = par.viewport() if hasattr(par, 'viewport') else par
            self.recalc_size(vp.width(), vp.height())
        self._update_overlay()
        self.data_changed.emit()

    def _layout_overflow(self):
        if not _DESKTOP_MODE:
            return False
        safe_bot = self._safe_margin_bottom
        max_bottom = self.height() - safe_bot
        for w in self._components:
            if w.data.y + w.data.h > max_bottom:
                return True
            if w.data.x + w.data.w > self.width():
                return True
        return False

    def _resolve_overlaps(self, mover):
        mover_gid = getattr(mover.data, '_group_id', None)
        if mover_gid:
            mr = self._group_bounding(mover_gid)
            skip_ids = set(self._groups.get(mover_gid, []))
        else:
            mr = mover.geometry()
            skip_ids = {mover.data.id}
        for w in self._components:
            if w.data.id in skip_ids:
                continue
            w_gid = getattr(w.data, '_group_id', None)
            if w_gid and w_gid == mover_gid:
                continue
            wr = w.geometry()
            if mr.intersects(wr):
                ny = snap(mr.bottom() + GRID_SIZE)
                dy = ny - wr.y()
                if w_gid:
                    for gw in self._components:
                        if getattr(gw.data, '_group_id', None) == w_gid:
                            gw.move(gw.x(), gw.y() + dy)
                            gw.data.y = gw.y()
                    self._resolve_overlaps(w)
                else:
                    w.move(wr.x(), ny)
                    w.data.x, w.data.y = wr.x(), ny
                    self._resolve_overlaps(w)

    def _remove(self, w):
        if _confirm_dialog(self, "确认删除", f"确定删除组件「{w.data.name}」？"):
            self._components.remove(w)
            w.setParent(None)
            w.deleteLater()
            self.update()
            self.data_changed.emit()

    def _edit(self, w):
        from PyQt5.QtWidgets import QDialog
        from fastpanel.dialogs.component import EditDialog
        from fastpanel.utils import count_params
        dlg = EditDialog(w.data, self)
        if dlg.exec_() == QDialog.Accepted:
            new = dlg.get_data()
            need_rebuild = (
                w.data.comp_type != new.comp_type
                or w.data.sub_type != new.sub_type
                or w.data.show_output != new.show_output
                or count_params(w.data.cmd) != count_params(new.cmd)
                or w.data.param_hints != new.param_hints
                or w.data.param_defaults != new.param_defaults
            )
            if need_rebuild:
                geo = w.geometry()
                self._components.remove(w); w.deleteLater()
                nd = ComponentData(
                    name=new.name, comp_type=new.comp_type, sub_type=new.sub_type,
                    cmd=new.cmd, show_output=new.show_output,
                    icon=new.icon, path=new.path,
                    x=geo.x(), y=geo.y(), w=geo.width(), h=geo.height(), uid=w.data.id,
                    param_hints=new.param_hints, param_defaults=new.param_defaults,
                    pre_cmd=new.pre_cmd,
                )
                self.add_component(nd)
            else:
                w.data.name = new.name; w.data.cmd = new.cmd
                w.data.show_output = new.show_output
                w.data.sub_type = new.sub_type
                w.data.icon = new.icon; w.data.path = new.path
                w.data.param_hints = new.param_hints
                w.data.param_defaults = new.param_defaults
                w.data.pre_cmd = new.pre_cmd
                w.update_from_data()
            self.data_changed.emit()

    def _copy(self, w):
        from PyQt5.QtWidgets import QDialog
        from fastpanel.dialogs.component import EditDialog
        copy_data = ComponentData(
            name=w.data.name, comp_type=w.data.comp_type, sub_type=w.data.sub_type,
            cmd=w.data.cmd, show_output=w.data.show_output,
            icon=w.data.icon, path=w.data.path,
            param_hints=list(w.data.param_hints),
            param_defaults=list(w.data.param_defaults),
            pre_cmd=w.data.pre_cmd,
        )
        dlg = EditDialog(copy_data, self)
        dlg.setWindowTitle("复制组件")
        if dlg.exec_() == QDialog.Accepted:
            nd = dlg.get_data()
            nd.x = w.data.x + GRID_SIZE * 2
            nd.y = w.data.y + GRID_SIZE * 2
            nd.w = w.data.w
            nd.h = w.data.h
            self.add_component(nd)
            self.data_changed.emit()

    def clear_all(self):
        for w in self._components: w.deleteLater()
        self._components.clear()

    @property
    def components(self):
        return list(self._components)



