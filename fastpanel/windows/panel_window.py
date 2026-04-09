import os
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QMenu, QDialog
)
from PyQt5.QtCore import Qt, QPoint, QRect, QTimer, pyqtSignal, QEvent
from PyQt5.QtGui import QPainter, QColor, QPen, QIcon

from fastpanel.constants import (
    GRID_SIZE, _BASE_DIR,
    TYPE_CMD, TYPE_CMD_WINDOW, TYPE_SHORTCUT, TYPE_CALENDAR,
    TYPE_WEATHER, TYPE_DOCK, TYPE_TODO, TYPE_CLOCK, TYPE_MONITOR,
    TYPE_LAUNCHER, TYPE_NOTE, TYPE_QUICKACTION, TYPE_MEDIA,
    TYPE_CLIPBOARD, TYPE_TIMER, TYPE_GALLERY, TYPE_SYSINFO,
    TYPE_BOOKMARK, TYPE_CALC, TYPE_TRASH, TYPE_RSS, TYPE_LABELS,
    MONITOR_SUB_LABELS, MONITOR_SUB_ALL, MONITOR_SUB_DISK,
    CLOCK_SUB_LABELS, CLOCK_SUB_ALARM, CLOCK_SUB_STOPWATCH, CLOCK_SUB_TIMER,
)
from fastpanel.settings import C
from fastpanel.theme import _scrollbar_style
from fastpanel.panels.grid import GridPanel
from fastpanel.data import ComponentData
from fastpanel.dialogs.component import CreateDialog
from fastpanel.utils import snap, _confirm_dialog

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
        self._edge_cursor_set = False
        self._build_ui()
        self._apply_style()

    def _build_ui(self):
        self.setMouseTracking(True)
        cw = QWidget(); cw.setMouseTracking(True); self.setCentralWidget(cw)
        _edge = 5
        root = QVBoxLayout(cw); root.setContentsMargins(_edge, 0, _edge, _edge); root.setSpacing(0)

        tb = QFrame(); tb.setObjectName("toolbar"); tb.setFixedHeight(32)
        tl = QHBoxLayout(tb); tl.setContentsMargins(12, 0, 4, 0); tl.setSpacing(6)
        logo = QLabel(self._panel_data.name)
        logo.setObjectName("logo"); tl.addWidget(logo)
        tl.addStretch()
        self._cnt = QLabel("0 个组件"); self._cnt.setObjectName("countLabel"); tl.addWidget(self._cnt)

        self._grid_btn = QPushButton("▦"); self._grid_btn.setObjectName("gridBtn")
        self._grid_btn.setCursor(Qt.PointingHandCursor); self._grid_btn.setToolTip("显示/隐藏网格")
        self._grid_btn.setProperty("active", True)
        self._grid_btn.clicked.connect(self._toggle_grid); tl.addWidget(self._grid_btn)

        from fastpanel.theme import svg_icon as _si
        self._lock_btn = QPushButton(); self._lock_btn.setObjectName("lockBtn")
        self._lock_btn.setIcon(_si("unlock", C['text'], 16))
        self._lock_btn.setCursor(Qt.PointingHandCursor); self._lock_btn.setToolTip("锁定/解锁布局")
        self._lock_btn.clicked.connect(self._toggle_lock); tl.addWidget(self._lock_btn)

        sb = QPushButton(); sb.setObjectName("settingsBtn")
        sb.setIcon(_si("settings", C['text'], 16))
        sb.setCursor(Qt.PointingHandCursor); sb.setToolTip("设置")
        sb.clicked.connect(self._on_settings); tl.addWidget(sb)

        ab = QPushButton("＋  新建组件"); ab.setObjectName("addBtn"); ab.setCursor(Qt.PointingHandCursor)
        ab.clicked.connect(self._on_add); tl.addWidget(ab)

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
        self._grid.desktop_ctx_menu_requested.connect(self._show_ctx_menu)
        sc.setWidget(self._grid)
        self._scroll = sc
        root.addWidget(sc, 1)

        cw.installEventFilter(self)
        sc.installEventFilter(self)
        sc.viewport().setMouseTracking(True)
        sc.viewport().installEventFilter(self)

        self._edge_timer = QTimer(self)
        self._edge_timer.timeout.connect(self._check_edge_cursor)
        self._edge_timer.start(80)

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
        from fastpanel.theme import svg_icon as _si2
        self._lock_btn.setIcon(_si2("lock" if self._locked else "unlock", C['text'], 16))
        for w in self._grid.components:
            w.setProperty("locked", self._locked)

    def _toggle_max(self):
        if self._max_btn._is_restore:
            self.showNormal()
            if hasattr(self, '_normal_geo'):
                self.setGeometry(self._normal_geo)
            self._max_btn._is_restore = False
        else:
            self._normal_geo = self.geometry()
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

    def _map_to_win(self, obj, pos):
        """Map a position from any child widget to window coordinates."""
        if obj is self:
            return pos
        return obj.mapTo(self, pos)

    def _check_edge_cursor(self):
        if self._resizing or self._tb_dragging or self._max_btn._is_restore:
            if self._edge_cursor_set:
                from PyQt5.QtWidgets import QApplication as _App
                _App.restoreOverrideCursor()
                self._edge_cursor_set = False
            return
        from PyQt5.QtGui import QCursor
        from PyQt5.QtWidgets import QApplication as _App
        win_pos = self.mapFromGlobal(QCursor.pos())
        _cursors = {2: Qt.SizeVerCursor, 4: Qt.SizeHorCursor, 8: Qt.SizeHorCursor,
                    6: Qt.SizeBDiagCursor, 10: Qt.SizeFDiagCursor}
        edge = self._hit_edge(win_pos) if self.rect().contains(win_pos) else 0
        if edge in _cursors:
            if not self._edge_cursor_set:
                _App.setOverrideCursor(_cursors[edge])
                self._edge_cursor_set = True
        else:
            if self._edge_cursor_set:
                _App.restoreOverrideCursor()
                self._edge_cursor_set = False

    def _start_resize_if_edge(self, win_pos, global_pos):
        if self._max_btn._is_restore:
            return False
        edge = self._hit_edge(win_pos)
        if edge:
            self._resizing = True; self._resize_edge = edge
            self._resize_origin = global_pos; self._resize_geo = self.geometry()
            return True
        return False

    def eventFilter(self, obj, event):
        if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
            win_pos = self._map_to_win(obj, event.pos())
            if self._start_resize_if_edge(win_pos, event.globalPos()):
                return True
        return super().eventFilter(obj, event)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            if not self._start_resize_if_edge(e.pos(), e.globalPos()):
                if e.pos().y() < 32:
                    self._tb_dragging = True; self._tb_offset = e.globalPos() - self.pos()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._resizing:
            self._do_resize(e.globalPos())
        elif self._tb_dragging:
            if self._max_btn._is_restore:
                old_w = self.width()
                ratio = e.pos().x() / max(1, old_w)
                normal_w = self._normal_geo.width() if hasattr(self, '_normal_geo') else 1000
                normal_h = self._normal_geo.height() if hasattr(self, '_normal_geo') else 700
                self.showNormal()
                self._max_btn._is_restore = False
                self._max_btn.update()
                new_x = int(e.globalPos().x() - normal_w * ratio)
                new_y = e.globalPos().y() - 16
                self.setGeometry(new_x, new_y, normal_w, normal_h)
                self._tb_offset = e.globalPos() - self.pos()
            self.move(e.globalPos() - self._tb_offset)
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
        self._edge_timer.stop()
        if self._edge_cursor_set:
            from PyQt5.QtWidgets import QApplication as _App
            _App.restoreOverrideCursor()
            self._edge_cursor_set = False
        self._restore_desktop_offsets()
        self._sync_back()
        self.closed.emit(self._panel_id)
        super().closeEvent(e)

    # --- right-click menu for adding components ---

    def _on_add(self):
        menu = QMenu(self)
        _style = self._ctx_menu_style()
        menu.setStyleSheet(_style)

        _simple = [
            ("剪贴板", TYPE_CLIPBOARD, ""), ("便签", TYPE_NOTE, ""),
            ("待办", TYPE_TODO, ""), ("快捷操作", TYPE_QUICKACTION, ""),
            ("日历", TYPE_CALENDAR, ""), ("计算器", TYPE_CALC, ""),
            ("书签", TYPE_BOOKMARK, ""), ("回收站", TYPE_TRASH, ""),
            ("应用启动器", TYPE_LAUNCHER, ""), ("媒体控制", TYPE_MEDIA, ""),
            ("相册", TYPE_GALLERY, ""), ("系统信息", TYPE_SYSINFO, ""),
            ("RSS", TYPE_RSS, ""), ("Dock栏", TYPE_DOCK, ""),
        ]
        for label, t, cmd in _simple:
            act = menu.addAction(label)
            act.triggered.connect(lambda _, tp=t, c=cmd: self._quick_add(tp, c))

        menu.addSeparator()

        clock_sub = menu.addMenu("时钟")
        clock_sub.setStyleSheet(_style)
        for sub_id, sub_name in CLOCK_SUB_LABELS.items():
            act = clock_sub.addAction(sub_name)
            act.triggered.connect(lambda _, s=sub_id: self._quick_add(TYPE_CLOCK, s))

        mon_sub = menu.addMenu("系统监控")
        mon_sub.setStyleSheet(_style)
        for sub_id, sub_name in MONITOR_SUB_LABELS.items():
            act = mon_sub.addAction(sub_name)
            act.triggered.connect(lambda _, s=sub_id: self._quick_add(TYPE_MONITOR, s))

        weather_act = menu.addAction("天气")
        weather_act.triggered.connect(lambda: self._quick_add(TYPE_WEATHER))

        menu.addSeparator()
        for label, t in [("CMD 命令", TYPE_CMD), ("CMD 窗口", TYPE_CMD_WINDOW), ("快捷方式", TYPE_SHORTCUT)]:
            act = menu.addAction(label)
            act.triggered.connect(lambda _, tp=t: self._quick_add(tp))

        btn = self.sender()
        if btn:
            menu.exec_(btn.mapToGlobal(btn.rect().bottomLeft()))
        else:
            menu.exec_(self.cursor().pos())

    def _on_settings(self):
        from fastpanel.dialogs.settings_dlg import SettingsDialog
        dlg = SettingsDialog(self)
        dlg.exec_()

    def _ctx_menu_style(self):
        return f"""
            QMenu {{ background: {C['mantle']}; color: {C['text']}; border: 1px solid {C['surface1']}; border-radius: 8px; padding: 6px; }}
            QMenu::item {{ padding: 6px 18px; border-radius: 4px; }}
            QMenu::item:selected {{ background: {C['blue']}; color: {C['crust']}; }}
            QMenu::separator {{ height: 1px; background: {C['surface1']}; margin: 4px 8px; }}
        """

    def _show_ctx_menu(self, pos):
        menu = QMenu(self)
        _style = self._ctx_menu_style()
        menu.setStyleSheet(_style)

        add_menu = menu.addMenu("＋  新建组件")
        add_menu.setStyleSheet(_style)

        _simple = [
            ("剪贴板", TYPE_CLIPBOARD, ""), ("便签", TYPE_NOTE, ""),
            ("待办", TYPE_TODO, ""), ("快捷操作", TYPE_QUICKACTION, ""),
            ("日历", TYPE_CALENDAR, ""), ("计算器", TYPE_CALC, ""),
            ("书签", TYPE_BOOKMARK, ""), ("回收站", TYPE_TRASH, ""),
            ("应用启动器", TYPE_LAUNCHER, ""), ("媒体控制", TYPE_MEDIA, ""),
            ("相册", TYPE_GALLERY, ""), ("系统信息", TYPE_SYSINFO, ""),
            ("RSS", TYPE_RSS, ""), ("Dock栏", TYPE_DOCK, ""),
        ]
        for label, t, cmd in _simple:
            act = add_menu.addAction(label)
            act.triggered.connect(lambda _, tp=t, c=cmd: self._quick_add(tp, c))

        add_menu.addSeparator()

        clock_sub = add_menu.addMenu("时钟")
        clock_sub.setStyleSheet(_style)
        for sub_id, sub_name in CLOCK_SUB_LABELS.items():
            act = clock_sub.addAction(sub_name)
            act.triggered.connect(lambda _, s=sub_id: self._quick_add(TYPE_CLOCK, s))

        mon_sub = add_menu.addMenu("系统监控")
        mon_sub.setStyleSheet(_style)
        for sub_id, sub_name in MONITOR_SUB_LABELS.items():
            act = mon_sub.addAction(sub_name)
            act.triggered.connect(lambda _, s=sub_id: self._quick_add(TYPE_MONITOR, s))

        weather_act = add_menu.addAction("天气")
        weather_act.triggered.connect(lambda: self._quick_add(TYPE_WEATHER))

        add_menu.addSeparator()
        for label, t in [("CMD 命令", TYPE_CMD), ("CMD 窗口", TYPE_CMD_WINDOW), ("快捷方式", TYPE_SHORTCUT)]:
            act = add_menu.addAction(label)
            act.triggered.connect(lambda _, tp=t: self._quick_add(tp))

        menu.exec_(pos)

    def _quick_add(self, comp_type, cmd=""):
        _DEFAULT_NAMES = {
            TYPE_CALENDAR: "日历", TYPE_WEATHER: "天气", TYPE_DOCK: "Dock栏",
            TYPE_TODO: "待办", TYPE_CLOCK: "时钟", TYPE_MONITOR: "系统监控",
            TYPE_LAUNCHER: "应用启动器", TYPE_QUICKACTION: "快捷操作",
            TYPE_NOTE: "便签", TYPE_MEDIA: "媒体控制", TYPE_CLIPBOARD: "剪贴板",
            TYPE_TIMER: "计时器", TYPE_GALLERY: "相册", TYPE_SYSINFO: "系统信息",
            TYPE_BOOKMARK: "书签", TYPE_CALC: "计算器", TYPE_TRASH: "回收站",
            TYPE_RSS: "RSS",
        }
        _NEEDS_DIALOG = {TYPE_CMD, TYPE_CMD_WINDOW, TYPE_SHORTCUT, TYPE_WEATHER}
        if comp_type in _NEEDS_DIALOG:
            self._on_add_with_type(comp_type)
            return

        name = _DEFAULT_NAMES.get(comp_type, comp_type)
        d = ComponentData(name=name, comp_type=comp_type, cmd=cmd)
        if comp_type == TYPE_NOTE:
            d.cmd = "0|"
        elif comp_type == TYPE_CLOCK and cmd in (CLOCK_SUB_ALARM,):
            d.cmd = f"{cmd}|[]"

        size_map = {
            TYPE_CALENDAR: (16, 16), TYPE_DOCK: (20, 5), TYPE_TODO: (14, 12),
            TYPE_LAUNCHER: (16, 20), TYPE_QUICKACTION: (18, 12), TYPE_NOTE: (12, 10),
            TYPE_MEDIA: (16, 7), TYPE_CLIPBOARD: (14, 14), TYPE_TIMER: (12, 10),
            TYPE_GALLERY: (14, 12), TYPE_SYSINFO: (16, 14), TYPE_BOOKMARK: (14, 12),
            TYPE_CALC: (14, 16), TYPE_TRASH: (10, 8), TYPE_RSS: (16, 16),
            TYPE_CLOCK: (10, 8), TYPE_WEATHER: (14, 12),
        }
        if comp_type == TYPE_MONITOR:
            mon_sizes = {MONITOR_SUB_ALL: (22, 18), MONITOR_SUB_DISK: (18, 10)}
            gw, gh = mon_sizes.get(cmd, (14, 10))
        elif comp_type == TYPE_CLOCK:
            clk_sizes = {CLOCK_SUB_STOPWATCH: (12, 12), CLOCK_SUB_TIMER: (12, 10)}
            gw, gh = clk_sizes.get(cmd, (10, 8))
        else:
            gw, gh = size_map.get(comp_type, (10, 8))
        d.w = GRID_SIZE * gw; d.h = GRID_SIZE * gh

        self._place_and_add(d)

    def _on_add_with_type(self, comp_type):
        dlg = CreateDialog(self)
        idx = list(TYPE_LABELS.keys()).index(comp_type) if comp_type in TYPE_LABELS else 0
        dlg.cat.setCurrentIndex(idx)
        if dlg.exec_() == QDialog.Accepted:
            d = dlg.get_data()
            if self._parent_main:
                self._parent_main._apply_default_size(d)
            else:
                d.w = max(d.w, GRID_SIZE * 10); d.h = max(d.h, GRID_SIZE * 8)
            self._place_and_add(d)

    def _place_and_add(self, d):
        grid = self._grid
        free = self._find_free_pos(grid, d.w, d.h)
        if free is None:
            _confirm_dialog(self, "提示", "布局空间不足，请先调整布局")
            return
        d.x, d.y = free
        grid.add_component(d)
        self._panel_data.components.append(d)
        self._cnt.setText(f"{len(grid.components)} 个组件")
        self._sync_back()

    @staticmethod
    def _find_free_pos(grid, w, h):
        gw, gh = grid.width(), grid.height()
        occupied = [(c.data.x, c.data.y, c.data.w, c.data.h) for c in grid.components]
        def overlaps(nx, ny):
            for ox, oy, ow, oh in occupied:
                if nx < ox + ow and nx + w > ox and ny < oy + oh and ny + h > oy:
                    return True
            return False
        for y in range(0, max(1, gh - h + 1), GRID_SIZE):
            for x in range(0, max(1, gw - w + 1), GRID_SIZE):
                if not overlaps(x, y):
                    return (x, y)
        return None


# ---------------------------------------------------------------------------
# Main Window
# ---------------------------------------------------------------------------

