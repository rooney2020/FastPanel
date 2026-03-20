import os
import json
import re
import subprocess
import configparser
import glob as glob_mod
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QDialog, QFormLayout, QLineEdit, QMenu,
    QFileDialog, QGraphicsDropShadowEffect, QCheckBox, QComboBox
)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer, QRect
from PyQt5.QtGui import QFont, QColor, QIcon, QPixmap, QPainter, QPen

from fastpanel.constants import GRID_SIZE, SUB_LABELS, SUB_APP, SUB_FILE, SUB_SCRIPT
from fastpanel.settings import C, _settings
from fastpanel.theme import _comp_style, _bg, _dialog_style, _scrollbar_style, _style_combobox
from fastpanel.widgets.base import CompBase
from fastpanel.widgets.cmd import _LaunchThread

def _scan_desktop_apps():
    dirs = ["/usr/share/applications", os.path.expanduser("~/.local/share/applications")]
    apps = []
    for d in dirs:
        for fp in glob_mod.glob(os.path.join(d, "*.desktop")):
            try:
                cp = configparser.ConfigParser(interpolation=None)
                cp.read(fp, encoding="utf-8")
                sec = "Desktop Entry"
                if not cp.has_section(sec):
                    continue
                if cp.get(sec, "Type", fallback="") != "Application":
                    continue
                if cp.getboolean(sec, "NoDisplay", fallback=False):
                    continue
                name = cp.get(sec, "Name[zh_CN]", fallback="") or cp.get(sec, "Name", fallback="")
                exe = cp.get(sec, "Exec", fallback="")
                icon = cp.get(sec, "Icon", fallback="")
                if not name or not exe:
                    continue
                exe = re.sub(r'\s+%[fFuUdDnNickvm]', '', exe).strip()
                icon_path = ""
                if icon:
                    if os.path.isabs(icon) and os.path.isfile(icon):
                        icon_path = icon
                    else:
                        for base in ["/usr/share/icons/hicolor", "/usr/share/pixmaps"]:
                            for ext in [".png", ".svg", ".xpm"]:
                                for sz in ["128x128", "96x96", "64x64", "48x48", "scalable", "256x256"]:
                                    cand = os.path.join(base, sz, "apps", icon + ext)
                                    if os.path.isfile(cand):
                                        icon_path = cand; break
                                if icon_path: break
                            if icon_path: break
                        if not icon_path:
                            cand = os.path.join("/usr/share/pixmaps", icon + ".png")
                            if os.path.isfile(cand):
                                icon_path = cand
                            cand2 = os.path.join("/usr/share/pixmaps", icon + ".xpm")
                            if not icon_path and os.path.isfile(cand2):
                                icon_path = cand2
                apps.append({"name": name, "exec": exe, "icon": icon_path, "desktop": fp})
            except Exception:
                continue
    apps.sort(key=lambda a: a["name"].lower())
    return apps



class _SystemAppDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        from fastpanel.utils import _prepare_dialog
        _prepare_dialog(self)
        self.setWindowTitle("选择系统应用")
        self.setFixedSize(520, 480)
        self.setStyleSheet(f"""
            QDialog {{ background: {C['base']}; color: {C['text']}; }}
            QLabel {{ color: {C['text']}; background: transparent; }}
            QLineEdit {{ background: {C['surface0']}; color: {C['text']}; border: 1px solid {C['surface2']};
                         border-radius: 6px; padding: 6px; font-size: 12px; }}
            QScrollArea {{ border: none; background: {C['base']}; }}
            {_scrollbar_style(8)}
        """)
        self._selected = None
        lay = QVBoxLayout(self)
        self._search = QLineEdit()
        self._search.setPlaceholderText("搜索应用…")
        self._search.textChanged.connect(self._filter)
        lay.addWidget(self._search)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._container = QWidget()
        self._container.setStyleSheet(f"background: {C['base']};")
        self._grid = QVBoxLayout(self._container)
        self._grid.setSpacing(2)
        self._grid.setContentsMargins(4, 4, 4, 4)
        self._scroll.setWidget(self._container)
        lay.addWidget(self._scroll, 1)

        self._apps = _scan_desktop_apps()
        self._buttons = []
        self._build_list(self._apps)

    def _build_list(self, apps):
        while self._grid.count():
            item = self._grid.takeAt(0)
            w = item.widget()
            if w: w.deleteLater()
        self._buttons.clear()
        for app in apps:
            btn = QPushButton()
            btn.setCursor(Qt.PointingHandCursor)
            hl = QHBoxLayout(btn)
            hl.setContentsMargins(8, 4, 8, 4)
            hl.setSpacing(10)
            icon_lbl = QLabel()
            icon_lbl.setFixedSize(28, 28)
            icon_lbl.setStyleSheet("background:transparent; border:none;")
            if app["icon"] and os.path.isfile(app["icon"]):
                pm = QPixmap(app["icon"]).scaled(28, 28, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                icon_lbl.setPixmap(pm)
            else:
                icon_lbl.setText("🖥️")
                icon_lbl.setStyleSheet("font-size:18px; background:transparent; border:none;")
            icon_lbl.setAlignment(Qt.AlignCenter)
            hl.addWidget(icon_lbl)
            name_lbl = QLabel(app["name"])
            name_lbl.setStyleSheet(f"color:{C['text']}; font-size:13px;")
            hl.addWidget(name_lbl, 1)
            btn.setStyleSheet(f"""
                QPushButton {{ background: transparent; border: none; border-radius: 6px; text-align: left; padding: 4px; }}
                QPushButton:hover {{ background: {C['surface1']}; }}
            """)
            btn.clicked.connect(lambda _, a=app: self._select(a))
            self._grid.addWidget(btn)
            self._buttons.append((btn, app))
        self._grid.addStretch()

    def _filter(self, text):
        ft = text.strip().lower()
        for btn, app in self._buttons:
            btn.setVisible(not ft or ft in app["name"].lower())

    def _select(self, app):
        self._selected = app
        self.accept()

    def selected_app(self):
        return self._selected


class _DockItemDialog(QDialog):
    def __init__(self, item=None, parent=None):
        super().__init__(parent)
        from fastpanel.utils import _prepare_dialog
        _prepare_dialog(self)
        self.setWindowTitle("编辑Dock项" if item else "添加Dock项")
        self.setFixedWidth(380)
        self.setStyleSheet(f"""
            QDialog {{ background: {C['base']}; color: {C['text']}; }}
            QLabel {{ color: {C['text']}; font-size: 13px; }}
            QLineEdit {{ background: {C['surface0']}; color: {C['text']}; border: 1px solid {C['surface2']};
                         border-radius: 6px; padding: 6px; font-size: 12px; }}
        """)
        lay = QVBoxLayout(self)

        imp_btn = QPushButton("📦 从系统导入应用")
        imp_btn.setCursor(Qt.PointingHandCursor)
        imp_btn.setStyleSheet(f"""
            QPushButton {{ background:{C['surface1']}; color:{C['text']}; border:none; border-radius:8px; padding:8px; font-size:12px; }}
            QPushButton:hover {{ background:{C['surface2']}; }}
        """)
        imp_btn.clicked.connect(self._import_sys_app)
        lay.addWidget(imp_btn)

        form = QFormLayout(); form.setSpacing(10)

        self._name_edit = QLineEdit(item.get("name", "") if item else "")
        self._name_edit.setPlaceholderText("显示名称")
        form.addRow("名称", self._name_edit)

        self._type_combo = QComboBox()
        for k, v in SUB_LABELS.items():
            self._type_combo.addItem(v, k)
        if item:
            idx = list(SUB_LABELS.keys()).index(item.get("sub_type", SUB_APP))
            self._type_combo.setCurrentIndex(idx)
        _style_combobox(self._type_combo)
        form.addRow("类型", self._type_combo)

        icon_w = QWidget()
        icon_lay = QHBoxLayout(icon_w); icon_lay.setContentsMargins(0, 0, 0, 0); icon_lay.setSpacing(6)
        self._icon_edit = QLineEdit(item.get("icon", "") if item else "")
        self._icon_edit.setPlaceholderText("图标路径（可选）")
        icon_lay.addWidget(self._icon_edit)
        ib = QPushButton("…"); ib.setFixedWidth(36)
        ib.setStyleSheet(f"background:{C['surface1']}; color:{C['text']}; border:none; border-radius:6px;")
        ib.clicked.connect(self._browse_icon)
        icon_lay.addWidget(ib)
        form.addRow("图标", icon_w)

        path_w = QWidget()
        path_lay = QHBoxLayout(path_w); path_lay.setContentsMargins(0, 0, 0, 0); path_lay.setSpacing(6)
        self._path_edit = QLineEdit(item.get("path", "") if item else "")
        self._path_edit.setPlaceholderText("程序/文件/脚本路径")
        path_lay.addWidget(self._path_edit)
        pb = QPushButton("…"); pb.setFixedWidth(36)
        pb.setStyleSheet(f"background:{C['surface1']}; color:{C['text']}; border:none; border-radius:6px;")
        pb.clicked.connect(self._browse_path)
        path_lay.addWidget(pb)
        form.addRow("路径", path_w)

        lay.addLayout(form)
        lay.addStretch()

        btns = QHBoxLayout(); btns.addStretch()
        cancel = QPushButton("取消")
        cancel.setStyleSheet(f"background:{C['surface1']}; color:{C['text']}; border:none; border-radius:8px; padding:8px 20px; font-size:13px;")
        cancel.setCursor(Qt.PointingHandCursor)
        cancel.clicked.connect(self.reject); btns.addWidget(cancel)
        ok = QPushButton("确定")
        ok.setStyleSheet(f"background:{C['blue']}; color:{C['crust']}; border:none; border-radius:8px; padding:8px 20px; font-size:13px; font-weight:bold;")
        ok.setCursor(Qt.PointingHandCursor)
        ok.clicked.connect(self._validate); btns.addWidget(ok)
        lay.addLayout(btns)

    def _browse_icon(self):
        from fastpanel.utils import _open_file
        p, _ = _open_file(self, "选择图标", "", "图片 (*.png *.svg *.ico *.jpg)")
        if p: self._icon_edit.setText(p)

    def _browse_path(self):
        from fastpanel.utils import _open_file
        p, _ = _open_file(self, "选择文件", "", "所有文件 (*)")
        if p: self._path_edit.setText(p)

    def _import_sys_app(self):
        dlg = _SystemAppDialog(self)
        if dlg.exec_() == QDialog.Accepted:
            app = dlg.selected_app()
            if app:
                self._name_edit.setText(app["name"])
                self._icon_edit.setText(app.get("icon", ""))
                self._path_edit.setText(app.get("exec", ""))
                self._type_combo.setCurrentIndex(0)

    def _validate(self):
        if not self._name_edit.text().strip():
            return
        if not self._path_edit.text().strip():
            return
        self.accept()

    def get_item(self):
        return {
            "name": self._name_edit.text().strip(),
            "sub_type": self._type_combo.currentData(),
            "icon": self._icon_edit.text().strip(),
            "path": self._path_edit.text().strip(),
        }


class DockWidget(CompBase):
    def __init__(self, data, parent=None):
        super().__init__(data, parent)
        self._items = []
        self._load_items()
        self._threads = {}
        self._build()

    def _load_items(self):
        try:
            self._items = json.loads(self.data.cmd) if self.data.cmd else []
        except Exception:
            self._items = []

    def _save_items(self):
        self.data.cmd = json.dumps(self._items, ensure_ascii=False)

    def _build(self):
        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(6, 4, 6, 6)
        self._root.setSpacing(2)

        self._title_lbl = None

        self._dock_area = QWidget()
        self._dock_area.setStyleSheet("background:transparent; border:none;")
        self._dock_layout = QHBoxLayout(self._dock_area)
        self._dock_layout.setContentsMargins(4, 0, 4, 0)
        self._dock_layout.setSpacing(0)
        self._dock_layout.setAlignment(Qt.AlignCenter)
        self._root.addWidget(self._dock_area, 1)

        self._rebuild_icons()

    def _rebuild_icons(self):
        while self._dock_layout.count():
            item = self._dock_layout.takeAt(0)
            w = item.widget()
            if w: w.deleteLater()

        for i, it in enumerate(self._items):
            icon_w = _DockIcon(it, i, self)
            icon_w.launched.connect(self._launch_item)
            icon_w.edit_requested.connect(self._edit_item)
            icon_w.remove_requested.connect(self._remove_item)
            self._dock_layout.addWidget(icon_w, alignment=Qt.AlignVCenter)

        add_btn = QPushButton("+")
        add_btn.setFixedSize(48, 48)
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.setStyleSheet(f"""
            QPushButton {{
                background: {_bg('surface0')}; color: {C['overlay0']}; border: 2px dashed {C['surface2']};
                border-radius: 12px; font-size: 22px; font-weight: bold;
            }}
            QPushButton:hover {{ background: {_bg('surface1')}; color: {C['text']}; border-color: {C['overlay0']}; }}
        """)
        add_btn.setToolTip("添加项目")
        add_btn.clicked.connect(self._add_item)
        self._dock_layout.addWidget(add_btn, alignment=Qt.AlignVCenter)

    def _add_item(self):
        dlg = _DockItemDialog(parent=self)
        if dlg.exec_() == QDialog.Accepted:
            self._items.append(dlg.get_item())
            self._save_items()
            self._rebuild_icons()
            self._save_to_parent()

    def _edit_item(self, idx):
        if 0 <= idx < len(self._items):
            dlg = _DockItemDialog(self._items[idx], self)
            if dlg.exec_() == QDialog.Accepted:
                self._items[idx] = dlg.get_item()
                self._save_items()
                self._rebuild_icons()
                self._save_to_parent()

    def _remove_item(self, idx):
        if 0 <= idx < len(self._items):
            self._items.pop(idx)
            self._save_items()
            self._rebuild_icons()
            self._save_to_parent()

    def _launch_item(self, idx):
        if idx in self._threads and self._threads[idx].isRunning():
            return
        if 0 <= idx < len(self._items):
            it = self._items[idx]
            t = _LaunchThread(it.get("path", ""), it.get("sub_type", SUB_APP))
            t.finished.connect(lambda ok, msg, i=idx: self._on_launch_done(i, ok, msg))
            self._threads[idx] = t
            t.start()

    def _on_launch_done(self, idx, ok, msg):
        pass

    def _save_to_parent(self):
        w = self.window()
        if w and hasattr(w, '_save_data'):
            w._save_data()

    def update_from_data(self):
        self._load_items()
        self._rebuild_icons()

    def contextMenuEvent(self, e):
        from PyQt5.QtWidgets import QMenu
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{ background: {_bg('surface0')}; color: {C['text']}; border: 1px solid {C['surface2']}; border-radius: 6px; padding: 4px; }}
            QMenu::item {{ padding: 6px 20px; border-radius: 4px; }}
            QMenu::item:selected {{ background: {_bg('surface1')}; }}
        """)
        add_act = menu.addAction("➕ 添加项目")
        menu.addSeparator()
        edit_act = menu.addAction("✏️ 修改")
        del_act = menu.addAction("🗑️ 删除")
        if self._group_id:
            menu.addSeparator()
            ungrp_act = menu.addAction("📤 解除组合")
        else:
            ungrp_act = None
        act = menu.exec_(e.globalPos())
        if act == add_act:
            self._add_item()
        elif act == edit_act:
            grid = self.parent()
            if grid and hasattr(grid, '_edit'):
                grid._edit(self)
        elif act == del_act:
            grid = self.parent()
            if grid and hasattr(grid, '_delete'):
                grid._delete(self)
        elif ungrp_act and act == ungrp_act:
            grid = self.parent()
            if grid and hasattr(grid, '_ungroup'):
                grid._ungroup(self._group_id)


class _DockIcon(QWidget):
    launched = pyqtSignal(int)
    edit_requested = pyqtSignal(int)
    remove_requested = pyqtSignal(int)

    def __init__(self, item_data, idx, parent=None):
        super().__init__(parent)
        self._item = item_data
        self._idx = idx
        self._scale = 1.0
        self._target_scale = 1.0
        self._base_size = 48
        self.setFixedSize(self._base_size + 16, self._base_size + 16)
        self.setCursor(Qt.PointingHandCursor)
        self.setMouseTracking(True)

        self.setToolTip(item_data.get("name", ""))

        self._pm = None
        icon_path = item_data.get("icon", "")
        if icon_path and os.path.isfile(icon_path):
            self._pm = QPixmap(icon_path)

        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(16)
        self._anim_timer.timeout.connect(self._animate_step)

    def _animate_step(self):
        diff = self._target_scale - self._scale
        if abs(diff) < 0.02:
            self._scale = self._target_scale
            self._anim_timer.stop()
        else:
            self._scale += diff * 0.3
        self.update()

    def enterEvent(self, e):
        self._target_scale = 1.35
        if not self._anim_timer.isActive():
            self._anim_timer.start()

    def leaveEvent(self, e):
        self._target_scale = 1.0
        if not self._anim_timer.isActive():
            self._anim_timer.start()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.launched.emit(self._idx)

    def contextMenuEvent(self, e):
        from PyQt5.QtWidgets import QMenu
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{ background: {C['surface0']}; color: {C['text']}; border: 1px solid {C['surface2']}; border-radius: 6px; padding: 4px; }}
            QMenu::item {{ padding: 6px 16px; border-radius: 4px; }}
            QMenu::item:selected {{ background: {C['surface1']}; }}
        """)
        edit_act = menu.addAction("✏️ 编辑")
        del_act = menu.addAction("🗑️ 移除")
        act = menu.exec_(e.globalPos())
        if act == edit_act:
            self.edit_requested.emit(self._idx)
        elif act == del_act:
            self.remove_requested.emit(self._idx)
        e.accept()

    def paintEvent(self, e):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        s = int(self._base_size * self._scale)
        cx, cy = w // 2, h // 2

        if self._pm:
            scaled = self._pm.scaled(s, s, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            p.drawPixmap(cx - scaled.width() // 2, cy - scaled.height() // 2, scaled)
        else:
            sub_icons = {SUB_APP: "🖥️", SUB_SCRIPT: "📜", SUB_FILE: "📄"}
            icon_ch = sub_icons.get(self._item.get("sub_type", SUB_APP), "🔗")
            f = p.font()
            f.setPixelSize(int(24 * self._scale))
            p.setFont(f)
            p.setPen(QColor(C['text']))
            p.drawText(QRect(0, cy - s // 2, w, s), Qt.AlignCenter, icon_ch)

        pass  # name shown via tooltip

        p.end()



