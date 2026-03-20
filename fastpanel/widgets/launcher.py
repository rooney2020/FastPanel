import os
import re
import subprocess
import configparser
import glob as glob_mod
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QLineEdit
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFont, QColor, QIcon, QPixmap

from fastpanel.constants import GRID_SIZE
from fastpanel.settings import C, _settings
from fastpanel.theme import _comp_style, _bg, _scrollbar_style
from fastpanel.widgets.base import CompBase

class _DesktopEntry:
    __slots__ = ('name', 'generic_name', 'exec_cmd', 'icon', 'categories', 'keywords', 'no_display', 'terminal')

    def __init__(self, name='', generic_name='', exec_cmd='', icon='', categories='',
                 keywords='', no_display=False, terminal=False):
        self.name = name
        self.generic_name = generic_name
        self.exec_cmd = exec_cmd
        self.icon = icon
        self.categories = categories
        self.keywords = keywords
        self.no_display = no_display
        self.terminal = terminal

    def matches(self, query):
        q = query.lower()
        return (q in self.name.lower() or q in self.generic_name.lower()
                or q in self.categories.lower() or q in self.keywords.lower()
                or q in self.exec_cmd.lower())


def _scan_desktop_entries():
    dirs = []
    for d in ['/usr/share/applications', '/usr/local/share/applications',
              os.path.expanduser('~/.local/share/applications'), '/var/lib/flatpak/exports/share/applications',
              os.path.expanduser('~/.local/share/flatpak/exports/share/applications')]:
        if os.path.isdir(d):
            dirs.append(d)
    entries = []
    seen_names = set()
    cfg = configparser.ConfigParser(interpolation=None)
    for d in dirs:
        try:
            files = [f for f in os.listdir(d) if f.endswith('.desktop')]
        except OSError:
            continue
        for fname in files:
            fp = os.path.join(d, fname)
            try:
                cfg.clear()
                cfg.read(fp, encoding='utf-8')
                if not cfg.has_section('Desktop Entry'):
                    continue
                sec = cfg['Desktop Entry']
                etype = sec.get('Type', 'Application')
                if etype != 'Application':
                    continue
                nd = sec.get('NoDisplay', 'false').lower() == 'true'
                hidden = sec.get('Hidden', 'false').lower() == 'true'
                if nd or hidden:
                    continue
                name = sec.get('Name', fname)
                if name in seen_names:
                    continue
                seen_names.add(name)
                entries.append(_DesktopEntry(
                    name=name,
                    generic_name=sec.get('GenericName', ''),
                    exec_cmd=sec.get('Exec', ''),
                    icon=sec.get('Icon', ''),
                    categories=sec.get('Categories', ''),
                    keywords=sec.get('Keywords', ''),
                    no_display=nd,
                    terminal=sec.get('Terminal', 'false').lower() == 'true',
                ))
            except Exception:
                continue
    entries.sort(key=lambda e: e.name.lower())
    return entries


def _resolve_icon(icon_name, size=48):
    if not icon_name:
        return QIcon()
    if os.path.isabs(icon_name) and os.path.isfile(icon_name):
        return QIcon(icon_name)
    theme_icon = QIcon.fromTheme(icon_name)
    if not theme_icon.isNull():
        return theme_icon
    for ext in ('png', 'svg', 'xpm'):
        for base in [f'/usr/share/icons/hicolor/{size}x{size}/apps',
                     '/usr/share/pixmaps',
                     f'/usr/share/icons/hicolor/scalable/apps']:
            path = os.path.join(base, f'{icon_name}.{ext}')
            if os.path.isfile(path):
                return QIcon(path)
    return QIcon()


class _AppItemWidget(QFrame):
    clicked = pyqtSignal()

    def __init__(self, entry, parent=None):
        super().__init__(parent)
        self.entry = entry
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(40)
        self.setStyleSheet(f"""
            QFrame {{ background: transparent; border-radius: 6px; }}
            QFrame:hover {{ background: {C['surface0']}; }}
        """)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 4, 8, 4)
        lay.setSpacing(10)
        icon_lbl = QLabel()
        ic = _resolve_icon(entry.icon)
        if not ic.isNull():
            icon_lbl.setPixmap(ic.pixmap(24, 24))
        else:
            icon_lbl.setText("◆")
            icon_lbl.setStyleSheet(f"color: {C['blue']}; font-size: 16px;")
        icon_lbl.setFixedSize(28, 28)
        icon_lbl.setAlignment(Qt.AlignCenter)
        lay.addWidget(icon_lbl)
        name_lbl = QLabel(entry.name)
        name_lbl.setStyleSheet(f"color: {C['text']}; font-size: 13px; background: transparent;")
        lay.addWidget(name_lbl, 1)
        if entry.generic_name and entry.generic_name != entry.name:
            desc_lbl = QLabel(entry.generic_name)
            desc_lbl.setStyleSheet(f"color: {C['subtext0']}; font-size: 10px; background: transparent;")
            lay.addWidget(desc_lbl)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(e)


class LauncherWidget(CompBase):
    def __init__(self, data, parent=None):
        super().__init__(data, parent)
        self._entries = []
        self._filtered = []
        self._build_ui()
        self._load_entries()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(6)

        title_row = QHBoxLayout()
        title_lbl = QLabel("🔍  应用启动器")
        title_lbl.setStyleSheet(f"color: {C['text']}; font-size: 14px; font-weight: bold; background: transparent;")
        title_row.addWidget(title_lbl)
        title_row.addStretch()
        refresh_btn = QPushButton("↻")
        refresh_btn.setFixedSize(24, 24)
        refresh_btn.setCursor(Qt.PointingHandCursor)
        refresh_btn.setStyleSheet(f"""
            QPushButton {{ background: {_bg('surface0')}; color: {C['text']}; border: none; border-radius: 12px; font-size: 14px; }}
            QPushButton:hover {{ background: {_bg('surface1')}; }}
        """)
        refresh_btn.clicked.connect(self._load_entries)
        title_row.addWidget(refresh_btn)
        lay.addLayout(title_row)

        self._search = QLineEdit()
        self._search.setPlaceholderText("搜索应用…")
        self._search.setStyleSheet(f"""
            QLineEdit {{
                background: {_bg('surface0')}; color: {C['text']}; border: 1px solid {C['surface1']};
                border-radius: 8px; padding: 6px 12px; font-size: 13px;
            }}
            QLineEdit:focus {{ border-color: {C['blue']}; }}
        """)
        self._search.textChanged.connect(self._filter)
        lay.addWidget(self._search)

        self._count_lbl = QLabel()
        self._count_lbl.setStyleSheet(f"color: {C['subtext0']}; font-size: 10px; background: transparent;")
        lay.addWidget(self._count_lbl)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"QScrollArea {{ background: transparent; border: none; }}" + _scrollbar_style(6))
        self._list_container = QWidget()
        self._list_container.setStyleSheet("background: transparent;")
        self._list_layout = QVBoxLayout(self._list_container)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(2)
        self._list_layout.addStretch()
        scroll.setWidget(self._list_container)
        lay.addWidget(scroll, 1)

    def _load_entries(self):
        self._entries = _scan_desktop_entries()
        self._filter()

    def _filter(self):
        query = self._search.text().strip()
        if query:
            self._filtered = [e for e in self._entries if e.matches(query)]
        else:
            self._filtered = list(self._entries)
        self._rebuild_list()

    def _rebuild_list(self):
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        show = self._filtered[:100]
        for entry in show:
            item = _AppItemWidget(entry, self._list_container)
            item.clicked.connect(lambda e=entry: self._launch(e))
            self._list_layout.addWidget(item)
        self._list_layout.addStretch()
        total = len(self._filtered)
        self._count_lbl.setText(f"共 {total} 个应用" + (f"（显示前 100）" if total > 100 else ""))

    def _launch(self, entry):
        cmd = entry.exec_cmd
        cmd = re.sub(r'%[fFuUdDnNickvm]', '', cmd).strip()
        if not cmd:
            return
        try:
            if entry.terminal:
                terminal_cmds = ['x-terminal-emulator', 'gnome-terminal', 'xterm']
                for t in terminal_cmds:
                    if subprocess.run(['which', t], capture_output=True).returncode == 0:
                        subprocess.Popen([t, '-e', cmd])
                        return
            subprocess.Popen(cmd, shell=True, start_new_session=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass



