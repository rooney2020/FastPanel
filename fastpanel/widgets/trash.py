import os
import subprocess
import shutil
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QColor

from fastpanel.constants import GRID_SIZE
from fastpanel.settings import C, _settings
from fastpanel.theme import _comp_style, _bg, _scrollbar_style
from fastpanel.widgets.base import CompBase
from fastpanel.utils import _confirm_dialog

class TrashWidget(CompBase):
    _VIRTUAL_FS = frozenset([
        'proc', 'sysfs', 'devtmpfs', 'tmpfs', 'securityfs', 'cgroup', 'cgroup2',
        'pstore', 'debugfs', 'hugetlbfs', 'mqueue', 'fusectl', 'configfs',
        'binfmt_misc', 'autofs', 'efivarfs', 'tracefs', 'fuse.portal',
        'fuse.gvfsd-fuse', 'overlay', 'squashfs', 'nsfs', 'ramfs',
    ])

    def __init__(self, data, parent=None):
        super().__init__(data, parent)
        self._uid = os.getuid()
        self._home_trash = os.path.expanduser("~/.local/share/Trash")
        self._count = 0
        self._size = 0
        self._build_ui()
        self._timer = QTimer(self); self._timer.timeout.connect(self._refresh); self._timer.start(5000)
        QTimer.singleShot(100, self._refresh)

    def _build_ui(self):
        lay = QVBoxLayout(self); lay.setContentsMargins(16, 12, 16, 12); lay.setSpacing(6)
        top = QHBoxLayout()
        from fastpanel.theme import svg_pixmap as _sp
        self._icon_lbl = QLabel()
        _pm = _sp("trash", C['text'], 36)
        if not _pm.isNull():
            self._icon_lbl.setPixmap(_pm)
        self._icon_lbl.setStyleSheet("font-size:32px;background:transparent;")
        top.addWidget(self._icon_lbl)
        info = QVBoxLayout(); info.setSpacing(2)
        self._count_lbl = QLabel("0 个文件")
        self._count_lbl.setStyleSheet(f"color:{C['text']};font-size:14px;font-weight:bold;background:transparent;")
        self._size_lbl = QLabel("0 B")
        self._size_lbl.setStyleSheet(f"color:{C['subtext0']};font-size:11px;background:transparent;")
        info.addWidget(self._count_lbl); info.addWidget(self._size_lbl)
        top.addLayout(info); top.addStretch()
        lay.addLayout(top)
        btns = QHBoxLayout(); btns.addStretch()
        open_btn = QPushButton("打开回收站"); open_btn.setCursor(Qt.PointingHandCursor)
        open_btn.setStyleSheet(f"background:{_bg('surface1')};color:{C['text']};border:none;"
                               f"border-radius:8px;padding:6px 16px;font-size:13px;")
        open_btn.clicked.connect(self._open_trash)
        btns.addWidget(open_btn)
        empty_btn = QPushButton("清空"); empty_btn.setCursor(Qt.PointingHandCursor)
        empty_btn.setStyleSheet(f"background:{C['red']};color:{C['crust']};border:none;"
                                f"border-radius:8px;padding:6px 16px;font-size:13px;font-weight:bold;")
        empty_btn.clicked.connect(self._empty_trash)
        btns.addWidget(empty_btn)
        btns.addStretch()
        lay.addLayout(btns); lay.addStretch()

    def _get_all_trash_dirs(self):
        """Return a list of all trash 'files' directories across mount points."""
        dirs = []
        home_files = os.path.join(self._home_trash, "files")
        if os.path.isdir(home_files):
            dirs.append(home_files)
        try:
            with open("/proc/mounts") as f:
                for line in f:
                    parts = line.split()
                    if len(parts) < 3:
                        continue
                    mountpoint, fstype = parts[1], parts[2]
                    if fstype in self._VIRTUAL_FS:
                        continue
                    trash_files = os.path.join(mountpoint, f".Trash-{self._uid}", "files")
                    if trash_files != home_files and os.path.isdir(trash_files):
                        dirs.append(trash_files)
        except OSError:
            pass
        return dirs

    @staticmethod
    def _scan_dir_size(files_dir):
        count = 0
        total = 0
        try:
            items = os.listdir(files_dir)
        except OSError:
            return 0, 0
        count = len(items)
        for item in items:
            p = os.path.join(files_dir, item)
            try:
                if os.path.isfile(p):
                    total += os.path.getsize(p)
                elif os.path.isdir(p):
                    for root, _dirs, fs in os.walk(p):
                        for f in fs:
                            try:
                                total += os.path.getsize(os.path.join(root, f))
                            except OSError:
                                pass
            except OSError:
                pass
        return count, total

    def _refresh(self):
        all_count, all_size = 0, 0
        for d in self._get_all_trash_dirs():
            c, s = self._scan_dir_size(d)
            all_count += c
            all_size += s
        self._count = all_count
        self._size = all_size
        self._count_lbl.setText(f"{self._count} 个文件")
        self._size_lbl.setText(self._fmt_size(self._size))

    @staticmethod
    def _fmt_size(b):
        for unit in ['B', 'KB', 'MB', 'GB']:
            if b < 1024:
                return f"{b:.1f} {unit}"
            b /= 1024
        return f"{b:.1f} TB"

    def _open_trash(self):
        try:
            subprocess.Popen(["xdg-open", f"trash:///"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

    def _empty_trash(self):
        if not _confirm_dialog(self, "清空回收站", f"确定要永久删除 {self._count} 个文件吗？\n此操作不可撤销！"):
            return
        try:
            subprocess.run(["gio", "trash", "--empty"], timeout=30, capture_output=True)
        except Exception:
            for files_dir in self._get_all_trash_dirs():
                trash_root = os.path.dirname(files_dir)
                for sub in ["files", "info"]:
                    d = os.path.join(trash_root, sub)
                    if os.path.isdir(d):
                        for item in os.listdir(d):
                            p = os.path.join(d, item)
                            try:
                                if os.path.isdir(p):
                                    shutil.rmtree(p)
                                else:
                                    os.remove(p)
                            except Exception:
                                pass
        self._refresh()

    def refresh_theme(self):
        super().refresh_theme()
        self._timer = QTimer(self); self._timer.timeout.connect(self._refresh); self._timer.start(5000)
        QTimer.singleShot(100, self._refresh)


# ---------------------------------------------------------------------------
# RSS Reader Widget
# ---------------------------------------------------------------------------

