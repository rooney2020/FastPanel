import os
import json
import uuid
import subprocess
import traceback
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFrame, QScrollArea, QMenu, QAction,
    QStackedWidget, QSystemTrayIcon, QFileDialog, QDialog, QFormLayout,
    QLineEdit, QComboBox, QCheckBox, QGraphicsDropShadowEffect
)
from PyQt5.QtCore import Qt, QPoint, QRect, QTimer, pyqtSignal
from PyQt5.QtGui import QPainter, QColor, QFont, QPixmap, QIcon, QPen, QCursor

import fastpanel.constants as _const
from fastpanel.constants import (
    GRID_SIZE, MIN_W, MIN_H, PANEL_PADDING, _DESKTOP_MODE, THEMES,
    TYPE_CMD, TYPE_CMD_WINDOW, TYPE_SHORTCUT, TYPE_CALENDAR,
    TYPE_WEATHER, TYPE_DOCK, TYPE_TODO, TYPE_CLOCK, TYPE_MONITOR,
    TYPE_LAUNCHER, TYPE_NOTE, TYPE_QUICKACTION, TYPE_MEDIA,
    TYPE_CLIPBOARD, TYPE_TIMER, TYPE_GALLERY, TYPE_SYSINFO,
    TYPE_BOOKMARK, TYPE_CALC, TYPE_TRASH, TYPE_RSS, TYPE_LABELS,
    MONITOR_SUB_LABELS, MONITOR_SUB_ALL, MONITOR_SUB_DISK,
    CLOCK_SUB_LABELS, CLOCK_SUB_CLOCK, CLOCK_SUB_ALARM,
    CLOCK_SUB_STOPWATCH, CLOCK_SUB_TIMER,
    DATA_FILE, _BASE_DIR
)
from fastpanel.settings import C, _settings, _save_settings, SETTINGS_FILE
from fastpanel.theme import _comp_style, _bg, _dialog_style, _scrollbar_style
from fastpanel.data import ComponentData, PanelData
from fastpanel.utils import snap, count_params, _confirm_dialog, _input_dialog, _prepare_dialog, _open_file, _save_file, _open_dir
from fastpanel.platform.backend import DesktopBackend, _X11DesktopBackend
from fastpanel.platform.hotkey import _HotkeyManager
from fastpanel.platform.autostart import _set_autostart
from fastpanel.panels.grid import GridPanel
from fastpanel.panels.tab_bar import PanelTabBar
from fastpanel.dialogs.component import CreateDialog, EditDialog, _build_comp_dialog, _dlg_get_data
from fastpanel.dialogs.export import ExportDialog
from fastpanel.dialogs.settings_dlg import SettingsDialog
from fastpanel.widgets.clipboard import _ClipboardPopup, _ClipboardMonitor
from fastpanel.windows.panel_window import _PanelWindow
from fastpanel.platform.voice_input import VoiceInputController
from fastpanel.widgets.voice_indicator import VoiceIndicator

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._desktop_mode = _DESKTOP_MODE
        self._desktop_backend = None
        self.setWindowTitle("FastPanel")
        _icon_path = os.path.join(_BASE_DIR, "fastpanel.svg")
        if os.path.isfile(_icon_path):
            self.setWindowIcon(QIcon(_icon_path))
        self._panels_data = []; self._grids = []; self._scrolls = []; self._active = 0
        self._per_monitor_active = False
        self._locked = False
        self._panel_windows = {}
        self._tb_dragging = False; self._tb_offset = QPoint()
        _ClipboardMonitor.ensure_running()

        if self._desktop_mode:
            self._desktop_backend = DesktopBackend.create()
            self._desktop_backend.setup_window(self)
        else:
            self.setWindowFlags(Qt.FramelessWindowHint)
            self.setMinimumSize(960, 640); self.resize(1200, 800)

        self._build_ui(); self._apply_style(); self._load_data()
        if not self._panels_data:
            self._first_launch_setup()
        elif self._desktop_mode and len(QApplication.screens()) > 1 and not _settings.get("_monitor_mode_chosen"):
            self._ask_monitor_mode()
        elif self._desktop_mode and _settings.get("monitor_mode") == "per_monitor":
            self._apply_per_monitor_panels()
        self._voice_ctrl = None
        self._voice_indicator = None
        if self._desktop_mode:
            self._setup_tray()
            self._setup_hotkeys()
            self._setup_voice_input()
            if _settings.get("monitor_mode") == "per_monitor":
                self._mon_switch_timer = QTimer(self)
                self._mon_switch_timer.timeout.connect(self._auto_switch_monitor_panel)
                self._mon_switch_timer.start(500)

    def _build_ui(self):
        cw = QWidget(); self.setCentralWidget(cw)
        root = QVBoxLayout(cw); root.setContentsMargins(0,0,0,0); root.setSpacing(0)

        # Toolbar (hidden in desktop mode)
        tb = QFrame(); tb.setObjectName("toolbar"); tb.setFixedHeight(48)
        self._toolbar = tb
        tl = QHBoxLayout(tb); tl.setContentsMargins(16,0,8,0); tl.setSpacing(8)
        logo = QLabel("⚡ FastPanel"); logo.setObjectName("logo"); tl.addWidget(logo)
        tl.addStretch()
        self._cnt = QLabel("0 个组件"); self._cnt.setObjectName("countLabel"); tl.addWidget(self._cnt)
        for txt, slot in [("📥 导入", self._on_import), ("📤 导出", self._on_export)]:
            b = QPushButton(txt); b.setObjectName("ioBtn"); b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(slot); tl.addWidget(b)
        self._grid_btn = QPushButton("▦"); self._grid_btn.setObjectName("gridBtn")
        self._grid_btn.setCursor(Qt.PointingHandCursor); self._grid_btn.setToolTip("显示/隐藏网格")
        self._grid_btn.setProperty("active", _settings.get("show_grid", True))
        self._grid_btn.clicked.connect(self._toggle_grid); tl.addWidget(self._grid_btn)
        self._lock_btn = QPushButton("🔓"); self._lock_btn.setObjectName("lockBtn")
        self._lock_btn.setCursor(Qt.PointingHandCursor); self._lock_btn.setToolTip("锁定/解锁布局")
        self._lock_btn.clicked.connect(self._toggle_lock); tl.addWidget(self._lock_btn)
        sb = QPushButton("⚙"); sb.setObjectName("settingsBtn")
        sb.setCursor(Qt.PointingHandCursor); sb.setToolTip("设置")
        sb.clicked.connect(self._on_settings); tl.addWidget(sb)
        ab = QPushButton("＋  新建组件"); ab.setObjectName("addBtn"); ab.setCursor(Qt.PointingHandCursor)
        ab.clicked.connect(self._on_add); tl.addWidget(ab)

        self._max_btn = None
        if not self._desktop_mode:
            for txt, oid, slot in [("—", "winMinBtn", self.showMinimized),
                                    ("", "winMaxBtn", self._toggle_max),
                                    ("✕", "winCloseBtn", self.close)]:
                b = QPushButton(txt); b.setObjectName(oid); b.setFixedSize(36, 28)
                b.setCursor(Qt.PointingHandCursor); b.clicked.connect(slot); tl.addWidget(b)
                if oid == "winMaxBtn": self._max_btn = b
            self._max_btn._is_restore = False
            _orig_paint = self._max_btn.paintEvent
            def _max_paint(event):
                _orig_paint(event)
                pp = QPainter(self._max_btn)
                pp.setRenderHint(QPainter.Antialiasing)
                pen = QPen(QColor(C['subtext0']), 1.2)
                pp.setPen(pen); pp.setBrush(Qt.NoBrush)
                if self._max_btn._is_restore:
                    pp.drawRect(15, 6, 10, 10)
                    pp.drawRect(11, 11, 10, 10)
                else:
                    pp.drawRect(12, 8, 12, 12)
                pp.end()
            self._max_btn.paintEvent = _max_paint

        if self._desktop_mode:
            tb.hide()
        else:
            root.addWidget(tb)

        self._stack = QStackedWidget(); root.addWidget(self._stack, 1)

        self._tab_bar_container = QWidget()
        self._tab_bar_container.setFixedHeight(42)
        tcl = QVBoxLayout(self._tab_bar_container)
        tcl.setContentsMargins(0, 0, 0, 0); tcl.setSpacing(0)
        self._tab_bar = PanelTabBar()
        self._tab_bar.add_clicked.connect(self._on_add_panel)
        self._tab_bar.tab_clicked.connect(self._switch_panel)
        self._tab_bar.rename_requested.connect(self._on_rename_panel)
        self._tab_bar.delete_requested.connect(self._on_delete_panel)
        self._tab_bar.copy_requested.connect(self._on_copy_panel)
        self._tab_bar.autohide_toggled.connect(self._toggle_tab_autohide)
        tcl.addWidget(self._tab_bar)

        if self._desktop_mode:
            self._tab_bar_container.hide()
        else:
            root.addWidget(self._tab_bar_container)

        self._tab_autohide = self._desktop_mode
        self._tab_hover_zone = QWidget(cw)
        self._tab_hover_zone.setFixedHeight(4)
        self._tab_hover_zone.setStyleSheet(f"background: {C['surface0']};")
        self._tab_hover_zone.hide()
        self._tab_hover_zone.setMouseTracking(True)
        self._tab_hover_zone.installEventFilter(self)
        self._tab_bar_container.installEventFilter(self)

    def _apply_style(self):
        self.setStyleSheet(f"""
            QMainWindow {{ background: {C['crust']}; }}
            #toolbar {{ background: {C['mantle']}; border-bottom: 1px solid {C['surface0']}; }}
            #logo {{ color: {C['blue']}; font-size: 22px; font-weight: bold; letter-spacing: 1px; }}
            #countLabel {{ color: {C['overlay0']}; font-size: 12px; margin-right: 16px; }}
            #addBtn {{
                background: {C['blue']}; color: {C['crust']};
                border: none; border-radius: 10px; padding: 10px 22px;
                font-size: 13px; font-weight: bold;
            }}
            #addBtn:hover {{ background: {C['lavender']}; }}
            #ioBtn {{
                background: {C['surface1']}; color: {C['text']};
                border: none; border-radius: 8px; padding: 8px 16px;
                font-size: 12px; margin-right: 4px;
            }}
            #ioBtn:hover {{ background: {C['surface2']}; }}
            #gridBtn {{
                background: {C['surface1']}; color: {C['text']};
                border: none; border-radius: 8px; padding: 8px 12px;
                font-size: 18px; margin-right: 4px;
            }}
            #gridBtn:hover {{ background: {C['surface2']}; }}
            #gridBtn[active="true"] {{
                background: {C['blue']}; color: {C['crust']};
            }}
            #gridBtn[active="true"]:hover {{ background: {C['lavender']}; color: {C['crust']}; }}
            #lockBtn {{
                background: {C['surface1']}; color: {C['text']};
                border: none; border-radius: 8px; padding: 8px 12px;
                font-size: 18px; margin-right: 4px;
            }}
            #lockBtn:hover {{ background: {C['surface2']}; }}
            #lockBtn[locked="true"] {{
                background: {C['red']}; color: {C['crust']};
            }}
            #lockBtn[locked="true"]:hover {{ background: {C['peach']}; color: {C['crust']}; }}
            #settingsBtn {{
                background: {C['surface1']}; color: {C['text']};
                border: none; border-radius: 8px; padding: 8px 12px;
                font-size: 18px; margin-right: 4px;
            }}
            #settingsBtn:hover {{ background: {C['surface2']}; }}
            QScrollArea {{ border: none; background: {C['crust']}; }}
            QScrollBar:vertical {{
                background: {C['mantle']}; width: 8px; border-radius: 4px;
            }}
            QScrollBar::handle:vertical {{
                background: {C['surface1']}; border-radius: 4px; min-height: 40px;
            }}
            QScrollBar::handle:vertical:hover {{ background: {C['surface2']}; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            #panelTabBar {{ background: {C['mantle']}; border-top: 1px solid {C['surface0']}; }}
            #tabAddBtn {{
                background: {C['surface1']}; color: {C['text']};
                border: none; border-radius: 8px; font-size: 16px; font-weight: bold;
            }}
            #tabAddBtn:hover {{ background: {C['blue']}; color: {C['crust']}; }}
            #tabBtn {{
                background: {C['surface0']}; color: {C['subtext0']};
                border: none; border-radius: 8px; padding: 6px 18px; font-size: 12px;
            }}
            #tabBtn:hover {{ background: {C['surface1']}; }}
            #tabBtn:checked {{ background: {C['blue']}; color: {C['crust']}; font-weight: bold; }}
            #winMinBtn, #winMaxBtn {{
                background: transparent; color: {C['subtext0']};
                border: none; border-radius: 4px; font-size: 14px;
            }}
            #winMinBtn:hover, #winMaxBtn:hover {{ background: {C['surface1']}; color: {C['text']}; }}
            #winCloseBtn {{
                background: transparent; color: {C['subtext0']};
                border: none; border-radius: 4px; font-size: 14px;
            }}
            #winCloseBtn:hover {{ background: {C['red']}; color: {C['crust']}; }}
        """)

    # ---- System Tray (desktop mode) ----
    def _setup_tray(self):
        self._tray = QSystemTrayIcon(self)
        _icon_path = os.path.join(_BASE_DIR, "fastpanel.svg")
        if os.path.isfile(_icon_path):
            self._tray.setIcon(QIcon(_icon_path))
        else:
            self._tray.setIcon(self.style().standardIcon(self.style().SP_ComputerIcon))
        tray_menu = QMenu()
        tray_menu.setStyleSheet(self._ctx_menu_style())
        show_act = tray_menu.addAction("显示/隐藏桌面")
        show_act.triggered.connect(self._toggle_visibility)
        tray_menu.addSeparator()
        add_act = tray_menu.addAction("新建组件")
        add_act.triggered.connect(self._on_add)
        settings_act = tray_menu.addAction("设置")
        settings_act.triggered.connect(self._on_settings)
        tray_menu.addSeparator()
        lock_act = tray_menu.addAction("锁定布局" if not self._locked else "解锁布局")
        lock_act.triggered.connect(self._toggle_lock)
        self._tray_lock_act = lock_act
        tray_menu.addSeparator()
        quit_act = tray_menu.addAction("退出 FastPanel")
        quit_act.triggered.connect(self._quit_app)
        self._tray.setContextMenu(tray_menu)
        self._tray.activated.connect(self._on_tray_activated)
        self._tray.show()

    def _setup_hotkeys(self):
        self._hotkey_mgr = _HotkeyManager.create()
        hotkeys = _settings.get("hotkeys", {})
        toggle_key = hotkeys.get("toggle_visibility", "")
        add_key = hotkeys.get("add_component", "")
        lock_key = hotkeys.get("toggle_lock", "")
        settings_key = hotkeys.get("open_settings", "")
        if toggle_key:
            self._hotkey_mgr.register(toggle_key, self._toggle_visibility)
        if add_key:
            self._hotkey_mgr.register(add_key, self._on_add)
        if lock_key:
            self._hotkey_mgr.register(lock_key, self._toggle_lock)
        if settings_key:
            self._hotkey_mgr.register(settings_key, self._on_settings)
        clip_key = hotkeys.get("clipboard_popup", "")
        if clip_key:
            self._hotkey_mgr.register(clip_key, self._show_clipboard_popup)
        voice_key = hotkeys.get("voice_input", "")
        if voice_key:
            self._hotkey_mgr.register(voice_key, self._toggle_voice_input)
        self._hotkey_mgr.start()

    def _stop_hotkeys(self):
        if hasattr(self, '_hotkey_mgr'):
            self._hotkey_mgr.stop()

    def _show_clipboard_popup(self):
        print(f"[Clipboard] popup requested", flush=True)
        try:
            popup = _ClipboardPopup.get_or_create(None)
            popup.show_at_cursor()
            print(f"[Clipboard] popup shown at {popup.pos()}, visible={popup.isVisible()}", flush=True)
        except Exception as e:
            print(f"[Clipboard] ERROR: {e}", flush=True)
            import traceback; traceback.print_exc()

    def _setup_voice_input(self):
        self._voice_ctrl = VoiceInputController(self)
        self._voice_indicator = VoiceIndicator()
        self._voice_ctrl.state_changed.connect(self._on_voice_state)
        self._voice_ctrl.partial_text.connect(self._on_voice_partial)
        self._voice_ctrl.final_text.connect(self._on_voice_final)
        self._voice_ctrl.download_progress.connect(self._on_voice_dl_progress)
        self._voice_ctrl.error.connect(self._on_voice_error)

    def _toggle_voice_input(self):
        print("[Voice] toggle requested", flush=True)
        if self._voice_ctrl:
            self._voice_ctrl.toggle()

    def _on_voice_state(self, state: str):
        print(f"[Voice] state → {state}", flush=True)
        if not self._voice_indicator:
            return
        if state == "downloading":
            self._voice_indicator.show_downloading(0)
        elif state == "recording":
            self._voice_indicator.show_recording()
        elif state == "finalizing":
            self._voice_indicator.show_finalizing()
        elif state == "idle":
            self._voice_indicator.hide()

    def _on_voice_dl_progress(self, pct: int):
        if self._voice_indicator:
            self._voice_indicator.show_downloading(pct)

    def _on_voice_partial(self, _text: str):
        pass

    def _on_voice_final(self, text: str):
        print(f"[Voice] result: {text}", flush=True)

    def _on_voice_error(self, msg: str):
        print(f"[Voice] error: {msg}", flush=True)
        if self._voice_indicator:
            self._voice_indicator.show_error(msg)

    def _toggle_visibility(self):
        if self.isVisible():
            self.hide()
        else:
            self.show()
            if self._desktop_mode and self._desktop_backend:
                self._desktop_backend.setup_window(self)

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self._toggle_visibility()

    def _launch_panel_window(self, panel_idx):
        if 0 <= panel_idx < len(self._panels_data):
            pd = self._panels_data[panel_idx]
            if pd.id in self._panel_windows:
                win = self._panel_windows[pd.id]
                win.raise_()
                win.activateWindow()
                return
            win = _PanelWindow(pd, self)
            win.closed.connect(self._on_panel_window_closed)
            self._panel_windows[pd.id] = win
            win.show()

    def _on_panel_window_closed(self, panel_id):
        self._panel_windows.pop(panel_id, None)

    def _quit_app(self):
        self._save_data()
        self._stop_hotkeys()
        if self._voice_ctrl:
            self._voice_ctrl.cleanup()
        for win in list(self._panel_windows.values()):
            win.close()
        self._panel_windows.clear()
        if hasattr(self, '_tray'):
            self._tray.hide()
        _X11DesktopBackend.restore_gnome_desktop()
        QApplication.instance().quit()

    # ---- Desktop right-click context menu ----
    def _ctx_menu_style(self):
        return f"""
            QMenu {{
                background: {C['surface0']}; color: {C['text']};
                border: 1px solid {C['surface1']}; border-radius: 8px;
                padding: 6px 4px; font-size: 13px;
            }}
            QMenu::item {{
                padding: 8px 28px 8px 16px; border-radius: 4px; margin: 2px 4px;
            }}
            QMenu::item:selected {{ background: {C['blue']}; color: {C['crust']}; }}
            QMenu::separator {{ height: 1px; background: {C['surface1']}; margin: 4px 8px; }}
        """

    def _quick_add(self, comp_type, cmd=""):
        _DEFAULT_NAMES = {TYPE_CALENDAR: "日历", TYPE_WEATHER: "天气", TYPE_DOCK: "Dock栏",
                          TYPE_TODO: "待办", TYPE_CLOCK: "时钟", TYPE_MONITOR: "系统监控",
                          TYPE_LAUNCHER: "应用启动器", TYPE_QUICKACTION: "快捷操作",
                          TYPE_NOTE: "便签", TYPE_MEDIA: "媒体控制", TYPE_CLIPBOARD: "剪贴板",
                          TYPE_TIMER: "计时器", TYPE_GALLERY: "相册", TYPE_SYSINFO: "系统信息",
                          TYPE_BOOKMARK: "书签", TYPE_CALC: "计算器", TYPE_TRASH: "回收站",
                          TYPE_RSS: "RSS"}
        _NEEDS_DIALOG = {TYPE_CMD, TYPE_CMD_WINDOW, TYPE_SHORTCUT}
        if comp_type in _NEEDS_DIALOG:
            self._on_add_with_type(comp_type)
            return
        if comp_type == TYPE_WEATHER:
            self._on_add_with_type(comp_type)
            return
        name = _DEFAULT_NAMES.get(comp_type, comp_type)
        d = ComponentData(name=name, comp_type=comp_type, cmd=cmd)
        if comp_type == TYPE_NOTE:
            d.cmd = "0|"
        elif comp_type == TYPE_CLOCK and cmd in (CLOCK_SUB_ALARM,):
            d.cmd = f"{cmd}|[]"
        d.x, d.y = self._next_pos()
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
        grid = self._cg()
        safe_top = grid._safe_margin_top
        safe_bot = grid._safe_margin_bottom
        avail_h = grid.height() - safe_top - safe_bot
        if d.w > grid.width() or d.h > avail_h:
            _confirm_dialog(self, "提示", "布局空间不足，请先调整布局")
            return
        free = self._find_free_pos(grid, d.w, d.h, safe_top, safe_bot)
        if free is None:
            _confirm_dialog(self, "提示", "布局空间不足，请先调整布局")
            return
        d.x, d.y = free
        grid.add_component(d)
        self._panels_data[self._active].components.append(d)
        self._update_count(); self._sync_sizes()

    def _on_add_with_type(self, comp_type):
        dlg = CreateDialog(self)
        idx = list(TYPE_LABELS.keys()).index(comp_type) if comp_type in TYPE_LABELS else 0
        dlg.cat.setCurrentIndex(idx)
        if dlg.exec_() == QDialog.Accepted:
            d = dlg.get_data()
            d.x, d.y = self._next_pos()
            self._apply_default_size(d)
            grid = self._cg()
            safe_top = grid._safe_margin_top
            safe_bot = grid._safe_margin_bottom
            avail_h = grid.height() - safe_top - safe_bot
            if d.w > grid.width() or d.h > avail_h:
                _confirm_dialog(self, "提示", "布局空间不足，请先调整布局")
                return
            free = self._find_free_pos(grid, d.w, d.h, safe_top, safe_bot)
            if free is None:
                _confirm_dialog(self, "提示", "布局空间不足，请先调整布局")
                return
            d.x, d.y = free
            grid.add_component(d)
            self._panels_data[self._active].components.append(d)
            self._update_count(); self._sync_sizes()

    def _show_desktop_ctx_menu(self, pos):
        menu = QMenu(self)
        menu.setStyleSheet(self._ctx_menu_style())

        add_menu = menu.addMenu("＋  新建组件")
        add_menu.setStyleSheet(self._ctx_menu_style())
        _style = self._ctx_menu_style()

        _simple = [
            ("📋 剪贴板", TYPE_CLIPBOARD, ""),
            ("📝 便签", TYPE_NOTE, ""),
            ("✅ 待办", TYPE_TODO, ""),
            ("🎛 快捷操作", TYPE_QUICKACTION, ""),
            ("📅 日历", TYPE_CALENDAR, ""),
            ("🔢 计算器", TYPE_CALC, ""),
            ("🔖 书签", TYPE_BOOKMARK, ""),
            ("🗑 回收站", TYPE_TRASH, ""),
            ("🚀 应用启动器", TYPE_LAUNCHER, ""),
            ("🎵 媒体控制", TYPE_MEDIA, ""),
            ("🖼 相册", TYPE_GALLERY, ""),
            ("💻 系统信息", TYPE_SYSINFO, ""),
            ("📰 RSS", TYPE_RSS, ""),
            ("📌 Dock栏", TYPE_DOCK, ""),
        ]
        for label, t, cmd in _simple:
            act = add_menu.addAction(label)
            act.triggered.connect(lambda _, tp=t, c=cmd: self._quick_add(tp, c))

        add_menu.addSeparator()

        clock_sub = add_menu.addMenu("🕐 时钟")
        clock_sub.setStyleSheet(_style)
        for sub_id, sub_name in CLOCK_SUB_LABELS.items():
            act = clock_sub.addAction(sub_name)
            act.triggered.connect(lambda _, s=sub_id: self._quick_add(TYPE_CLOCK, s))

        mon_sub = add_menu.addMenu("📊 系统监控")
        mon_sub.setStyleSheet(_style)
        for sub_id, sub_name in MONITOR_SUB_LABELS.items():
            act = mon_sub.addAction(sub_name)
            act.triggered.connect(lambda _, s=sub_id: self._quick_add(TYPE_MONITOR, s))

        weather_act = add_menu.addAction("🌤 天气")
        weather_act.triggered.connect(lambda: self._quick_add(TYPE_WEATHER))

        add_menu.addSeparator()
        cmd_act = add_menu.addAction("⌨ CMD 命令")
        cmd_act.triggered.connect(lambda: self._quick_add(TYPE_CMD))
        cmdwin_act = add_menu.addAction("🖥 CMD 窗口")
        cmdwin_act.triggered.connect(lambda: self._quick_add(TYPE_CMD_WINDOW))
        shortcut_act = add_menu.addAction("🔗 快捷方式")
        shortcut_act.triggered.connect(lambda: self._quick_add(TYPE_SHORTCUT))

        menu.addSeparator()

        panel_menu = menu.addMenu("面板")
        panel_menu.setStyleSheet(self._ctx_menu_style())
        _is_per_mon = _settings.get("monitor_mode") == "per_monitor"
        _mpm = _settings.get("monitor_panel_map", {})
        _cur_screen = QApplication.screenAt(pos)
        _cur_screen_name = _cur_screen.name() if _cur_screen else ""
        _cur_panel_idx = _mpm.get(_cur_screen_name, self._active) if _is_per_mon else self._active
        for i, pd in enumerate(self._panels_data):
            is_cur = (i == _cur_panel_idx) if _is_per_mon else (i == self._active)
            label = ("● " if is_cur else "    ") + pd.name
            if _is_per_mon:
                tags = []
                for sn, pi in _mpm.items():
                    if pi == i:
                        if sn == _cur_screen_name:
                            tags.append("当前显示器")
                        else:
                            tags.append(sn)
                if tags:
                    label += "  (" + ", ".join(tags) + ")"
            act = panel_menu.addAction(label)
            if _is_per_mon and _cur_screen_name:
                act.triggered.connect(lambda checked, idx=i, scr=_cur_screen_name: self._assign_panel_to_monitor(scr, idx))
            else:
                act.triggered.connect(lambda checked, idx=i: self._switch_panel(idx))
        panel_menu.addSeparator()
        add_panel_act = panel_menu.addAction("＋  新建面板")
        add_panel_act.triggered.connect(self._on_add_panel)
        if len(self._panels_data) > 1:
            _can_delete = True
            if _is_per_mon and len(self._panels_data) <= len(QApplication.screens()):
                _can_delete = False
            rename_act = panel_menu.addAction("✏  重命名当前面板")
            rename_act.triggered.connect(lambda: self._on_rename_panel(self._active))
            if _can_delete:
                del_act = panel_menu.addAction("🗑  删除当前面板")
                del_act.triggered.connect(lambda: self._on_delete_panel(self._active))
        copy_act = panel_menu.addAction("📋  复制当前面板")
        copy_act.triggered.connect(lambda: self._on_copy_panel(self._active))

        menu.addSeparator()
        win_menu = menu.addMenu("🪟  启动窗口级面板")
        win_menu.setStyleSheet(self._ctx_menu_style())
        for i, pd in enumerate(self._panels_data):
            is_open = pd.id in self._panel_windows
            label = ("✔ " if is_open else "    ") + pd.name
            act = win_menu.addAction(label)
            act.triggered.connect(lambda checked, idx=i: self._launch_panel_window(idx))

        menu.addSeparator()
        grid_act = menu.addAction("隐藏网格" if _settings.get("show_grid", True) else "显示网格")
        grid_act.triggered.connect(self._toggle_grid)
        lock_act = menu.addAction("解锁布局" if self._locked else "锁定布局")
        lock_act.triggered.connect(self._toggle_lock)

        menu.addSeparator()
        imp_act = menu.addAction("📥  导入")
        imp_act.triggered.connect(self._on_import)
        exp_act = menu.addAction("📤  导出")
        exp_act.triggered.connect(self._on_export)

        menu.addSeparator()
        settings_act = menu.addAction("⚙  设置")
        settings_act.triggered.connect(self._on_settings)

        menu.addSeparator()
        quit_act = menu.addAction("退出 FastPanel")
        quit_act.triggered.connect(self._quit_app)

        menu.exec_(pos)

    def _create_panel(self, name, pd=None):
        pd = pd or PanelData(name=name); self._panels_data.append(pd)
        sc = QScrollArea(); sc.setWidgetResizable(False)
        sc.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        if _DESKTOP_MODE:
            sc.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        g = GridPanel(); g.data_changed.connect(self._on_data_changed)
        if self._desktop_mode:
            g.desktop_ctx_menu_requested.connect(self._show_desktop_ctx_menu)
            if self._desktop_backend:
                avail = self._desktop_backend.get_available_geometry()
                full = self._desktop_backend.get_full_geometry()
                safe_t = avail.y() - full.y()
                safe_b = (full.y() + full.height()) - (avail.y() + avail.height())
                g.set_safe_margins(safe_t, safe_b)
        sc.setWidget(g)
        self._grids.append(g); self._scrolls.append(sc); self._stack.addWidget(sc)
        idx = self._tab_bar.add_tab(name)
        for cd in pd.components: g.add_component(cd)
        groups: dict[str, list[str]] = {}
        for w in g.components:
            gid = getattr(w.data, '_group_id', None)
            if gid:
                groups.setdefault(gid, []).append(w.data.id)
                w.setProperty("locked", True)
        g._groups = groups
        g._update_overlay()
        return idx

    def _switch_panel(self, idx):
        if 0<=idx<len(self._panels_data):
            self._active = idx; self._stack.setCurrentIndex(idx)
            self._tab_bar.set_active(idx); self._update_count()
            QTimer.singleShot(0, self._sync_sizes)

    def _on_add_panel(self):
        ok, name = _input_dialog(self, "新建 Panel", "名称：", "新面板")
        if ok:
            n = name.strip() or "新面板"
            idx = self._create_panel(n); self._switch_panel(idx); self._save_data()

    def _on_rename_panel(self, idx):
        if 0<=idx<len(self._panels_data):
            ok, name = _input_dialog(self, "重命名", "新名称：", self._panels_data[idx].name)
            if ok:
                n = name.strip()
                if n: self._panels_data[idx].name = n; self._tab_bar.rename_tab(idx, n); self._save_data()

    def _on_copy_panel(self, idx):
        if 0 <= idx < len(self._panels_data):
            src = self._panels_data[idx]
            ok, name = _input_dialog(self, "复制面板", "新面板名称：", src.name + " - 副本")
            if ok:
                n = name.strip() or src.name + " - 副本"
                new_pd = PanelData(name=n, components=[
                    ComponentData(
                        name=c.name, comp_type=c.comp_type, sub_type=c.sub_type,
                        cmd=c.cmd, show_output=c.show_output,
                        icon=c.icon, path=c.path,
                        x=c.x, y=c.y, w=c.w, h=c.h,
                        param_hints=list(c.param_hints),
                        param_defaults=list(c.param_defaults),
                    ) for c in src.components
                ])
                new_idx = self._create_panel(n)
                grid = self._grids[new_idx]
                for c in new_pd.components:
                    grid.add_component(c)
                self._switch_panel(new_idx)
                self._save_data()

    def _on_delete_panel(self, idx):
        if len(self._panels_data) <= 1: return
        if _settings.get("monitor_mode") == "per_monitor":
            n_screens = len(QApplication.screens())
            if len(self._panels_data) <= n_screens:
                _confirm_dialog(self, "无法删除",
                    f"当前为「每个显示器独立面板」模式，面板数量（{len(self._panels_data)}）"
                    f"不能少于显示器数量（{n_screens}）。")
                return
        if not _confirm_dialog(self, "确认", f"删除面板「{self._panels_data[idx].name}」？"): return
        self._panels_data.pop(idx); g = self._grids.pop(idx); s = self._scrolls.pop(idx)
        g.clear_all(); s.deleteLater(); self._tab_bar.remove_tab(idx)
        if _settings.get("monitor_mode") == "per_monitor":
            mpm = _settings.get("monitor_panel_map", {})
            new_mpm = {}
            for sn, pi in mpm.items():
                if pi == idx:
                    new_mpm[sn] = -1
                elif pi > idx:
                    new_mpm[sn] = pi - 1
                else:
                    new_mpm[sn] = pi
            used = set(v for v in new_mpm.values() if v >= 0)
            for sn in list(new_mpm.keys()):
                if new_mpm[sn] < 0:
                    for i in range(len(self._panels_data)):
                        if i not in used:
                            new_mpm[sn] = i
                            used.add(i)
                            break
                    else:
                        new_mpm[sn] = 0
            _settings["monitor_panel_map"] = new_mpm
            _save_settings(_settings)
            self._enter_per_monitor_mode()
        else:
            self._switch_panel(min(idx, len(self._panels_data)-1))
        self._save_data()

    def _assign_panel_to_monitor(self, screen_name, panel_idx):
        mpm = _settings.get("monitor_panel_map", {})
        old_panel = mpm.get(screen_name)
        for sn, pi in list(mpm.items()):
            if pi == panel_idx and sn != screen_name:
                if old_panel is not None:
                    mpm[sn] = old_panel
                break
        mpm[screen_name] = panel_idx
        _settings["monitor_panel_map"] = mpm
        _save_settings(_settings)
        if getattr(self, '_per_monitor_active', False):
            self._enter_per_monitor_mode()
        else:
            self._switch_panel(panel_idx)

    def _enter_per_monitor_mode(self):
        if not self._desktop_mode:
            return
        mpm = _settings.get("monitor_panel_map", {})
        if not mpm:
            return
        self._per_monitor_active = True
        self._stack.hide()
        cw = self.centralWidget()
        full_geo = self._desktop_backend.get_full_geometry() if self._desktop_backend else QApplication.primaryScreen().virtualGeometry()
        for sc in self._scrolls:
            sc.hide()
        shown_panels = set()
        for screen in QApplication.screens():
            sn = screen.name()
            pi = mpm.get(sn, 0)
            if 0 <= pi < len(self._scrolls) and pi not in shown_panels:
                shown_panels.add(pi)
                sc = self._scrolls[pi]
                if sc.parent() != cw:
                    sc.setParent(cw)
                geo = screen.geometry()
                x = geo.x() - full_geo.x()
                y = geo.y() - full_geo.y()
                sc.setGeometry(x, y, geo.width(), geo.height())
                sc.show()
                sc.raise_()
                g = self._grids[pi]
                g.recalc_size(geo.width(), geo.height())
        cur_screen = QApplication.screenAt(QCursor.pos())
        if cur_screen and cur_screen.name() in mpm:
            self._active = mpm[cur_screen.name()]
            self._tab_bar.set_active(self._active)
            self._update_count()

    def _exit_per_monitor_mode(self):
        self._per_monitor_active = False
        for sc in self._scrolls:
            sc.setParent(self._stack)
            self._stack.addWidget(sc)
        self._stack.show()
        self._switch_panel(self._active)

    def _auto_switch_monitor_panel(self):
        if not self._desktop_mode or _settings.get("monitor_mode") != "per_monitor":
            return
        mpm = _settings.get("monitor_panel_map", {})
        cur_screen = QApplication.screenAt(QCursor.pos())
        if cur_screen and cur_screen.name() in mpm:
            target = mpm[cur_screen.name()]
            if target != self._active and 0 <= target < len(self._panels_data):
                self._active = target
                self._tab_bar.set_active(target)
                self._update_count()

    def _cg(self):
        if self._active >= len(self._grids):
            self._active = max(0, len(self._grids) - 1)
        return self._grids[self._active] if self._grids else None
    def _cs(self):
        if self._active >= len(self._scrolls):
            self._active = max(0, len(self._scrolls) - 1)
        return self._scrolls[self._active] if self._scrolls else None

    def resizeEvent(self, e):
        super().resizeEvent(e); self._sync_sizes()
        if self._tab_autohide:
            self._position_hover_zone()
    def showEvent(self, e): super().showEvent(e); QTimer.singleShot(0, self._sync_sizes)
    def _sync_sizes(self):
        if getattr(self, '_per_monitor_active', False):
            self._enter_per_monitor_mode()
            return
        for s, g in zip(self._scrolls, self._grids):
            vp = s.viewport(); g.recalc_size(vp.width(), vp.height())
    def _update_count(self):
        g = self._cg()
        self._cnt.setText(f"{len(g.components)} 个组件" if g else "0 个组件")

    def _next_pos(self):
        cs = self._cg().components
        safe_top = self._cg()._safe_margin_top
        start_y = max(40, safe_top + GRID_SIZE)
        if not cs: return 40, snap(start_y)
        vw = self._cs().viewport().width(); mr, ry, rb = 0, 0, 0
        for c in cs:
            r = c.data.x+c.data.w; b = c.data.y+c.data.h
            if r > mr: mr, ry = r, c.data.y
            if b > rb: rb = b
        x, y = mr+GRID_SIZE, ry
        if x+320 > vw: x, y = 40, rb+GRID_SIZE
        return snap(x), snap(y)

    def _find_free_pos(self, grid, w, h, safe_top, safe_bot):
        gw = grid.width()
        gh = grid.height()
        occupied = [(c.data.x, c.data.y, c.data.w, c.data.h) for c in grid.components]
        start_y = ((safe_top + GRID_SIZE - 1) // GRID_SIZE) * GRID_SIZE
        max_y = gh - safe_bot - h

        def overlaps(nx, ny):
            for ox, oy, ow, oh in occupied:
                if nx < ox + ow and nx + w > ox and ny < oy + oh and ny + h > oy:
                    return True
            return False

        for y in range(start_y, max_y + 1, GRID_SIZE):
            for x in range(0, gw - w + 1, GRID_SIZE):
                if not overlaps(x, y):
                    return (x, y)
        return None

    def _apply_default_size(self, d):
        """Set default w/h for a ComponentData based on its type."""
        t = d.comp_type
        if t == TYPE_CMD:
            np = count_params(d.cmd)
            if d.show_output:
                d.w = 320; d.h = max(160 + np * 38 + 120, 300)
            elif np > 0:
                d.w = 320; d.h = GRID_SIZE * 2 + np * 38
            else:
                d.w = GRID_SIZE * 13; d.h = GRID_SIZE * 2
        elif t == TYPE_CMD_WINDOW:
            d.w = 320; d.h = 340
        elif t == TYPE_SHORTCUT:
            d.w = GRID_SIZE * 4; d.h = GRID_SIZE * 4
        elif t == TYPE_CALENDAR:
            d.w = GRID_SIZE * 16; d.h = GRID_SIZE * 16
        elif t == TYPE_WEATHER:
            d.w = GRID_SIZE * 14; d.h = GRID_SIZE * 12
        elif t == TYPE_DOCK:
            d.w = GRID_SIZE * 20; d.h = GRID_SIZE * 5
        elif t == TYPE_TODO:
            d.w = GRID_SIZE * 14; d.h = GRID_SIZE * 12
        elif t == TYPE_CLOCK:
            sub = d.cmd.split("|")[0] if d.cmd else CLOCK_SUB_CLOCK
            if sub == CLOCK_SUB_STOPWATCH:
                d.w = GRID_SIZE * 12; d.h = GRID_SIZE * 12
            elif sub == CLOCK_SUB_TIMER:
                d.w = GRID_SIZE * 12; d.h = GRID_SIZE * 10
            else:
                d.w = GRID_SIZE * 10; d.h = GRID_SIZE * 8
        elif t == TYPE_MONITOR:
            sub = d.cmd.strip() if d.cmd else MONITOR_SUB_ALL
            if sub == MONITOR_SUB_ALL:
                d.w = GRID_SIZE * 22; d.h = GRID_SIZE * 18
            elif sub == MONITOR_SUB_DISK:
                d.w = GRID_SIZE * 18; d.h = GRID_SIZE * 10
            else:
                d.w = GRID_SIZE * 14; d.h = GRID_SIZE * 10
        else:
            _sizes = {
                TYPE_LAUNCHER: (16, 20), TYPE_NOTE: (12, 10), TYPE_QUICKACTION: (18, 12),
                TYPE_MEDIA: (16, 7), TYPE_CLIPBOARD: (14, 14), TYPE_TIMER: (12, 10),
                TYPE_GALLERY: (14, 12), TYPE_SYSINFO: (16, 14), TYPE_BOOKMARK: (14, 12),
                TYPE_CALC: (14, 16), TYPE_TRASH: (10, 8), TYPE_RSS: (16, 16),
            }
            gw, gh = _sizes.get(t, (10, 8))
            d.w = GRID_SIZE * gw; d.h = GRID_SIZE * gh

    def _on_add(self):
        dlg = CreateDialog(self)
        if dlg.exec_()==QDialog.Accepted:
            d = dlg.get_data()
            d.x, d.y = self._next_pos()
            if d.comp_type == TYPE_CMD:
                np = count_params(d.cmd)
                if d.show_output:
                    d.w = 320; d.h = max(160 + np * 38 + 120, 300)
                elif np > 0:
                    d.w = 320; d.h = GRID_SIZE * 2 + np * 38
                else:
                    d.w = GRID_SIZE * 13; d.h = GRID_SIZE * 2
            elif d.comp_type == TYPE_CMD_WINDOW:
                d.w = 320; d.h = 340
            elif d.comp_type == TYPE_SHORTCUT:
                d.w = GRID_SIZE * 4; d.h = GRID_SIZE * 4
            elif d.comp_type == TYPE_CALENDAR:
                d.w = GRID_SIZE * 16; d.h = GRID_SIZE * 16
            elif d.comp_type == TYPE_WEATHER:
                d.w = GRID_SIZE * 14; d.h = GRID_SIZE * 12
            elif d.comp_type == TYPE_DOCK:
                d.w = GRID_SIZE * 20; d.h = GRID_SIZE * 5
            elif d.comp_type == TYPE_TODO:
                d.w = GRID_SIZE * 14; d.h = GRID_SIZE * 12
            elif d.comp_type == TYPE_CLOCK:
                sub = d.cmd.split("|")[0] if d.cmd else CLOCK_SUB_CLOCK
                if sub == CLOCK_SUB_STOPWATCH:
                    d.w = GRID_SIZE * 12; d.h = GRID_SIZE * 12
                elif sub == CLOCK_SUB_TIMER:
                    d.w = GRID_SIZE * 12; d.h = GRID_SIZE * 10
                else:
                    d.w = GRID_SIZE * 10; d.h = GRID_SIZE * 8
            elif d.comp_type == TYPE_MONITOR:
                sub = d.cmd.strip() if d.cmd else MONITOR_SUB_ALL
                if sub == MONITOR_SUB_ALL:
                    d.w = GRID_SIZE * 22; d.h = GRID_SIZE * 18
                elif sub == MONITOR_SUB_DISK:
                    d.w = GRID_SIZE * 18; d.h = GRID_SIZE * 10
                else:
                    d.w = GRID_SIZE * 14; d.h = GRID_SIZE * 10
            elif d.comp_type == TYPE_LAUNCHER:
                d.w = GRID_SIZE * 16; d.h = GRID_SIZE * 20
            elif d.comp_type == TYPE_NOTE:
                d.w = GRID_SIZE * 12; d.h = GRID_SIZE * 10
            elif d.comp_type == TYPE_QUICKACTION:
                d.w = GRID_SIZE * 18; d.h = GRID_SIZE * 12
            elif d.comp_type == TYPE_MEDIA:
                d.w = GRID_SIZE * 16; d.h = GRID_SIZE * 7
            elif d.comp_type == TYPE_CLIPBOARD:
                d.w = GRID_SIZE * 14; d.h = GRID_SIZE * 14
            elif d.comp_type == TYPE_TIMER:
                d.w = GRID_SIZE * 12; d.h = GRID_SIZE * 10
            elif d.comp_type == TYPE_GALLERY:
                d.w = GRID_SIZE * 14; d.h = GRID_SIZE * 12
            elif d.comp_type == TYPE_SYSINFO:
                d.w = GRID_SIZE * 16; d.h = GRID_SIZE * 14
            elif d.comp_type == TYPE_BOOKMARK:
                d.w = GRID_SIZE * 14; d.h = GRID_SIZE * 12
            elif d.comp_type == TYPE_CALC:
                d.w = GRID_SIZE * 14; d.h = GRID_SIZE * 16
            elif d.comp_type == TYPE_TRASH:
                d.w = GRID_SIZE * 12; d.h = GRID_SIZE * 7
            elif d.comp_type == TYPE_RSS:
                d.w = GRID_SIZE * 16; d.h = GRID_SIZE * 16
            else:
                d.w = 320; d.h = 200
            grid = self._cg()
            gw = grid.width()
            safe_top = grid._safe_margin_top
            safe_bot = grid._safe_margin_bottom
            gh = grid.height() - safe_top - safe_bot
            if d.w > gw or d.h > gh:
                _confirm_dialog(self, "提示", "布局空间不足，请先调整布局")
                return
            pos = self._find_free_pos(grid, d.w, d.h, safe_top, safe_bot)
            if pos is None:
                _confirm_dialog(self, "提示", "布局空间不足，请先调整布局")
                return
            d.x, d.y = pos
            grid.add_component(d)
            self._panels_data[self._active].components.append(d)
            self._update_count(); self._sync_sizes()

    def _on_data_changed(self):
        self._update_count(); self._sync_data(); self._save_data()

    def _sync_data(self):
        for i, g in enumerate(self._grids):
            self._panels_data[i].components = [w.data for w in g.components]

    def _save_data(self):
        self._sync_data()
        try:
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump({"active": self._active, "panels": [p.to_dict() for p in self._panels_data]},
                          f, ensure_ascii=False, indent=2)
        except Exception: pass

    def _load_data(self):
        if not os.path.exists(DATA_FILE): return
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f: obj = json.load(f)
            if isinstance(obj, list):
                pd = PanelData(name="默认", components=[ComponentData.from_dict(d) for d in obj])
                self._create_panel("默认", pd); self._switch_panel(0); return
            for p in obj.get("panels", []): self._create_panel(PanelData.from_dict(p).name, PanelData.from_dict(p))
            if self._panels_data: self._switch_panel(min(obj.get("active", 0), len(self._panels_data)-1))
        except Exception: pass

    def _first_launch_setup(self):
        screens = QApplication.screens()
        if self._desktop_mode and len(screens) > 1 and not _settings.get("_monitor_mode_chosen"):
            from PyQt5.QtWidgets import QDialogButtonBox
            dlg = QDialog(self)
            _prepare_dialog(dlg)
            dlg.setWindowTitle("多显示器设置")
            dlg.setFixedWidth(420)
            dlg.setStyleSheet(_dialog_style())
            lay = QVBoxLayout(dlg); lay.setSpacing(16); lay.setContentsMargins(28, 24, 28, 24)
            h = QLabel("🖥  检测到多个显示器"); h.setObjectName("heading"); lay.addWidget(h)
            info = QLabel(f"当前有 {len(screens)} 个显示器，请选择布局方式：")
            info.setStyleSheet(f"color:{C['subtext0']};font-size:13px;")
            info.setWordWrap(True); lay.addWidget(info)

            opt1 = QPushButton("📐 所有显示器共用一个面板")
            opt1.setStyleSheet(f"QPushButton{{background:{C['surface0']};color:{C['text']};border:1px solid {C['surface2']};"
                               f"border-radius:10px;padding:14px;font-size:13px;text-align:left;}}"
                               f"QPushButton:hover{{border-color:{C['blue']};background:{C['surface1']};}}")
            opt1.setCursor(Qt.PointingHandCursor)
            lay.addWidget(opt1)

            opt2 = QPushButton("🖥 每个显示器独立面板")
            opt2.setStyleSheet(f"QPushButton{{background:{C['surface0']};color:{C['text']};border:1px solid {C['surface2']};"
                               f"border-radius:10px;padding:14px;font-size:13px;text-align:left;}}"
                               f"QPushButton:hover{{border-color:{C['blue']};background:{C['surface1']};}}")
            opt2.setCursor(Qt.PointingHandCursor)
            lay.addWidget(opt2)

            choice = [None]
            opt1.clicked.connect(lambda: (choice.__setitem__(0, "single"), dlg.accept()))
            opt2.clicked.connect(lambda: (choice.__setitem__(0, "per_monitor"), dlg.accept()))
            dlg.exec_()

            _settings["_monitor_mode_chosen"] = True
            _settings["monitor_mode"] = choice[0] or "single"
            _save_settings(_settings)

            if choice[0] == "per_monitor":
                for s in screens:
                    self._create_panel(s.name())
                self._switch_panel(0)
                return

        self._create_panel("默认"); self._switch_panel(0)

    def _ask_monitor_mode(self):
        screens = QApplication.screens()
        dlg = QDialog(self)
        _prepare_dialog(dlg)
        dlg.setWindowTitle("多显示器设置")
        dlg.setFixedWidth(420)
        dlg.setStyleSheet(_dialog_style())
        lay = QVBoxLayout(dlg); lay.setSpacing(16); lay.setContentsMargins(28, 24, 28, 24)
        h = QLabel("🖥  检测到多个显示器"); h.setObjectName("heading"); lay.addWidget(h)
        info = QLabel(f"当前有 {len(screens)} 个显示器，请选择布局方式：")
        info.setStyleSheet(f"color:{C['subtext0']};font-size:13px;")
        info.setWordWrap(True); lay.addWidget(info)

        opt1 = QPushButton("📐 所有显示器共用一个面板")
        opt1.setStyleSheet(f"QPushButton{{background:{C['surface0']};color:{C['text']};border:1px solid {C['surface2']};"
                           f"border-radius:10px;padding:14px;font-size:13px;text-align:left;}}"
                           f"QPushButton:hover{{border-color:{C['blue']};background:{C['surface1']};}}")
        opt1.setCursor(Qt.PointingHandCursor); lay.addWidget(opt1)

        opt2 = QPushButton("🖥 每个显示器独立面板")
        opt2.setStyleSheet(f"QPushButton{{background:{C['surface0']};color:{C['text']};border:1px solid {C['surface2']};"
                           f"border-radius:10px;padding:14px;font-size:13px;text-align:left;}}"
                           f"QPushButton:hover{{border-color:{C['blue']};background:{C['surface1']};}}")
        opt2.setCursor(Qt.PointingHandCursor); lay.addWidget(opt2)

        choice = [None]
        opt1.clicked.connect(lambda: (choice.__setitem__(0, "single"), dlg.accept()))
        opt2.clicked.connect(lambda: (choice.__setitem__(0, "per_monitor"), dlg.accept()))
        dlg.exec_()

        _settings["_monitor_mode_chosen"] = True
        _settings["monitor_mode"] = choice[0] or "single"
        _save_settings(_settings)

        if choice[0] == "per_monitor":
            self._apply_per_monitor_panels()

    def _apply_per_monitor_panels(self):
        screens = QApplication.screens()
        needed = len(screens) - len(self._panels_data)
        if needed > 0:
            existing_names = {p.name for p in self._panels_data}
            idx = 1
            for _ in range(needed):
                name = f"面板{idx}"
                while name in existing_names:
                    idx += 1
                    name = f"面板{idx}"
                existing_names.add(name)
                self._create_panel(name)
                idx += 1
        n_panels = len(self._panels_data)
        mpm = _settings.get("monitor_panel_map", {})
        for sn in list(mpm.keys()):
            if mpm[sn] >= n_panels:
                mpm[sn] = min(mpm[sn], n_panels - 1)
        for i, s in enumerate(screens):
            if s.name() not in mpm:
                mpm[s.name()] = min(i, n_panels - 1)
        _settings["monitor_panel_map"] = mpm
        _save_settings(_settings)
        self._enter_per_monitor_mode()
        self._save_data()

    def _on_export(self):
        dlg = ExportDialog(self._panels_data, self)
        if dlg.exec_() != QDialog.Accepted:
            return
        data = dlg.get_export_data()
        if not data:
            return
        p, _ = _save_file(self, "导出", os.path.expanduser("~/fastpanel_export.json"), "JSON (*.json)")
        if p:
            try:
                with open(p, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            except Exception:
                pass

    def _on_import(self):
        p, _ = _open_file(self, "导入", os.path.expanduser("~"), "JSON (*.json)")
        if not p: return
        try:
            with open(p, "r", encoding="utf-8") as f: obj = json.load(f)
        except Exception:
            return
        if not isinstance(obj, list) or not obj:
            return
        has_existing = any(len(pd.components) > 0 for pd in self._panels_data)
        mode = "direct"
        if has_existing:
            dlg = QDialog(self)
            _prepare_dialog(dlg)
            dlg.setWindowTitle("导入方式")
            dlg.setFixedWidth(340)
            dlg.setStyleSheet(_dialog_style())
            dl = QVBoxLayout(dlg); dl.setContentsMargins(24, 20, 24, 20); dl.setSpacing(12)
            lbl = QLabel("检测到当前已有组件，请选择导入方式：")
            lbl.setStyleSheet(f"color:{C['text']}; font-size:13px;")
            dl.addWidget(lbl)
            overwrite_btn = QPushButton("覆盖 — 替换所有现有数据")
            overwrite_btn.setStyleSheet(f"""
                QPushButton {{ background:{C['red']}; color:{C['crust']}; border:none; border-radius:8px; padding:10px 16px; font-size:13px; font-weight:bold; }}
                QPushButton:hover {{ background:{C['peach']}; }}
                QPushButton:pressed {{ background:{C['yellow']}; }}
            """)
            overwrite_btn.setCursor(Qt.PointingHandCursor)
            overwrite_btn.clicked.connect(lambda: (setattr(dlg, '_mode', 'overwrite'), dlg.accept()))
            dl.addWidget(overwrite_btn)
            append_btn = QPushButton("新增 — 导入到新面板，保留现有数据")
            append_btn.setStyleSheet(f"""
                QPushButton {{ background:{C['blue']}; color:{C['crust']}; border:none; border-radius:8px; padding:10px 16px; font-size:13px; font-weight:bold; }}
                QPushButton:hover {{ background:{C['lavender']}; }}
                QPushButton:pressed {{ background:{C['sky']}; }}
            """)
            append_btn.setCursor(Qt.PointingHandCursor)
            append_btn.clicked.connect(lambda: (setattr(dlg, '_mode', 'append'), dlg.accept()))
            dl.addWidget(append_btn)
            cancel_btn = QPushButton("取消")
            cancel_btn.setStyleSheet(f"""
                QPushButton {{ background:{C['surface0']}; color:{C['text']}; border:none; border-radius:8px; padding:8px 16px; font-size:13px; }}
                QPushButton:hover {{ background:{C['surface1']}; }}
                QPushButton:pressed {{ background:{C['surface2']}; }}
            """)
            cancel_btn.setCursor(Qt.PointingHandCursor)
            cancel_btn.clicked.connect(dlg.reject)
            dl.addWidget(cancel_btn)
            if dlg.exec_() != QDialog.Accepted:
                return
            mode = getattr(dlg, '_mode', 'append')

        is_panel_format = obj and isinstance(obj[0], dict) and "components" in obj[0]

        if mode == "overwrite":
            if getattr(self, '_per_monitor_active', False):
                self._exit_per_monitor_mode()
            while len(self._panels_data) > 0:
                idx = len(self._panels_data) - 1
                self._panels_data.pop(idx)
                g = self._grids.pop(idx); s = self._scrolls.pop(idx)
                g.clear_all(); self._stack.removeWidget(s); s.deleteLater()
            while self._tab_bar._tabs:
                self._tab_bar.remove_tab(0)
            self._active = 0
            _settings.pop("monitor_panel_map", None)
            _save_settings(_settings)

        if is_panel_format:
            for panel_d in obj:
                name = panel_d.get("name", "导入面板")
                comps = [ComponentData.from_dict(c) for c in panel_d.get("components", [])]
                for c in comps: c.id = str(uuid.uuid4())
                pd = PanelData(name=name, components=comps)
                self._create_panel(name, pd)
        else:
            if not self._panels_data:
                self._create_panel("默认")
            for d in obj:
                data = ComponentData.from_dict(d); data.id = str(uuid.uuid4())
                self._cg().add_component(data)

        if self._panels_data:
            self._tab_bar.set_active(0)
            self._switch_panel(0)
            self._stack.show()
        if self._desktop_mode and _settings.get("monitor_mode") == "per_monitor":
            self._apply_per_monitor_panels()
        self._update_count(); self._sync_sizes(); self._save_data()

    def eventFilter(self, obj, event):
        if obj == self._tab_hover_zone and event.type() == event.Enter:
            if self._tab_autohide:
                self._tab_bar_container.show()
                self._tab_hover_zone.hide()
            return False
        if obj == self._tab_bar_container and event.type() == event.Leave:
            if self._tab_autohide:
                self._tab_bar_container.hide()
                self._tab_hover_zone.show()
                self._position_hover_zone()
            return False
        return super().eventFilter(obj, event)

    def _position_hover_zone(self):
        cw = self.centralWidget()
        if cw:
            self._tab_hover_zone.setGeometry(0, cw.height() - 4, cw.width(), 4)

    def _toggle_tab_autohide(self):
        self._tab_autohide = not self._tab_autohide
        if self._tab_autohide:
            self._tab_bar_container.hide()
            self._tab_hover_zone.show()
            self._position_hover_zone()
        else:
            self._tab_bar_container.show()
            self._tab_hover_zone.hide()

    def _toggle_max(self):
        if self._desktop_mode:
            return
        if self.isMaximized():
            self.showNormal()
            if self._max_btn: self._max_btn._is_restore = False
        else:
            self.showMaximized()
            if self._max_btn: self._max_btn._is_restore = True
        if self._max_btn: self._max_btn.update()

    def _toggle_grid(self):
        show = not _settings.get("show_grid", True)
        _settings["show_grid"] = show
        self._grid_btn.setProperty("active", show)
        self._grid_btn.style().unpolish(self._grid_btn)
        self._grid_btn.style().polish(self._grid_btn)
        for g in self._grids:
            g.set_show_grid(show)
            g.update()
        _save_settings(_settings)

    def _toggle_lock(self):
        self._locked = not self._locked
        if not self._desktop_mode:
            self._lock_btn.setText("🔒" if self._locked else "🔓")
            self._lock_btn.setProperty("locked", self._locked)
            self._lock_btn.style().unpolish(self._lock_btn)
            self._lock_btn.style().polish(self._lock_btn)
        if hasattr(self, '_tray_lock_act'):
            self._tray_lock_act.setText("解锁布局" if self._locked else "锁定布局")
        for g in self._grids:
            for w in g.components:
                w.setProperty("locked", self._locked)

    def _on_settings(self):
        if hasattr(self, '_settings_dlg') and self._settings_dlg is not None:
            try:
                if self._settings_dlg.isVisible():
                    self._settings_dlg.raise_()
                    self._settings_dlg.activateWindow()
                    return
            except RuntimeError:
                self._settings_dlg = None
        dlg = SettingsDialog(self)
        self._settings_dlg = dlg
        if self._voice_ctrl and hasattr(dlg, '_voice_model_status'):
            from fastpanel.platform.voice_input import VoiceState
            if self._voice_ctrl.state == VoiceState.DOWNLOADING:
                self._voice_ctrl.download_progress.connect(dlg._on_voice_dl_progress)
                self._voice_ctrl.stt_engine.model_ready.connect(dlg._on_voice_dl_done)
                self._voice_ctrl.stt_engine.model_error.connect(dlg._on_voice_dl_error)
        if dlg.exec_() == QDialog.Accepted:
            global C, _settings
            s = dlg.get_settings()
            _settings.update(s)
            _save_settings(_settings)
            C.update(THEMES.get(s["theme"], THEMES["Catppuccin Mocha"]))
            self._apply_style()
            cs = _comp_style()
            for g in self._grids:
                pal = g.palette(); pal.setColor(pal.Window, QColor(C["crust"])); g.setPalette(pal)
                g.set_bg_image(s.get("bg_image", ""), s.get("bg_opacity", 30))
                g.set_bg_gradient(s.get("bg_gradient", ""))
                g.set_bg_mode(s.get("bg_mode", "tile"))
                g.set_per_monitor_bg(s.get("bg_per_monitor", {}))
                g.set_bg_slideshow(s.get("bg_slideshow_dir", ""), s.get("bg_slideshow_interval", 300))
                g.set_show_grid(_settings.get("show_grid", True))
                for w in g.components:
                    w.setStyleSheet(cs)
                    w.refresh_theme()
                g.update()
            
            if self._desktop_mode and "hotkeys" in s:
                self._stop_hotkeys()
                self._setup_hotkeys()
            if "_autostart" in s:
                _set_autostart(s["_autostart"])
                s.pop("_autostart", None)
            if _settings.get("monitor_mode") == "per_monitor":
                self._apply_per_monitor_panels()
                if not hasattr(self, '_mon_switch_timer') or self._mon_switch_timer is None:
                    self._mon_switch_timer = QTimer(self)
                    self._mon_switch_timer.timeout.connect(self._auto_switch_monitor_panel)
                    self._mon_switch_timer.start(500)
            else:
                if hasattr(self, '_mon_switch_timer') and self._mon_switch_timer is not None:
                    self._mon_switch_timer.stop()
                    self._mon_switch_timer = None
                if getattr(self, '_per_monitor_active', False):
                    self._exit_per_monitor_mode()

    def mousePressEvent(self, e):
        if self._desktop_mode:
            super().mousePressEvent(e); return
        if e.button() == Qt.LeftButton and self._toolbar.geometry().contains(e.pos()):
            self._tb_dragging = True
            self._tb_offset = e.globalPos() - self.frameGeometry().topLeft()
            e.accept()
        else:
            super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._desktop_mode:
            super().mouseMoveEvent(e); return
        if self._tb_dragging:
            if self.isMaximized():
                ratio = e.pos().x() / self.width()
                self.showNormal()
                if self._max_btn:
                    self._max_btn._is_restore = False; self._max_btn.update()
                new_x = int(self.width() * ratio)
                self._tb_offset = QPoint(new_x, e.pos().y())
            self.move(e.globalPos() - self._tb_offset)
            e.accept()
        else:
            super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        self._tb_dragging = False
        super().mouseReleaseEvent(e)

    def mouseDoubleClickEvent(self, e):
        if self._desktop_mode:
            super().mouseDoubleClickEvent(e); return
        if self._toolbar.geometry().contains(e.pos()):
            self._toggle_max()
        else:
            super().mouseDoubleClickEvent(e)

    def closeEvent(self, e):
        self._save_data()
        if hasattr(self, '_tray'):
            self._tray.hide()
        super().closeEvent(e)



