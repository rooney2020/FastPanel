from PyQt5.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QMenu
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont, QColor

from fastpanel.settings import C

class PanelTabBar(QFrame):
    tab_clicked = pyqtSignal(int)
    add_clicked = pyqtSignal()
    rename_requested = pyqtSignal(int)
    delete_requested = pyqtSignal(int)
    copy_requested = pyqtSignal(int)
    autohide_toggled = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent); self.setFixedHeight(42); self.setObjectName("panelTabBar")
        self._tabs = []; self._active = -1
        self._layout = QHBoxLayout(self); self._layout.setContentsMargins(8,4,8,4); self._layout.setSpacing(4)
        self._add_btn = QPushButton("＋"); self._add_btn.setObjectName("tabAddBtn")
        self._add_btn.setFixedSize(32,32); self._add_btn.setCursor(Qt.PointingHandCursor)
        self._add_btn.clicked.connect(self.add_clicked.emit); self._layout.addWidget(self._add_btn)
        self._layout.addStretch()
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._bar_menu)

    def _bar_menu(self, pos):
        menu = QMenu(self); menu.setStyleSheet(f"""
            QMenu {{ background:{C['base']}; border:1px solid {C['surface0']}; border-radius:6px; padding:4px 0; }}
            QMenu::item {{ color:{C['text']}; padding:6px 24px 6px 12px; font-size:12px; }}
            QMenu::item:selected {{ background:{C['surface1']}; }}
        """)
        ah = menu.addAction("📌  自动隐藏")
        a = menu.exec_(self.mapToGlobal(pos))
        if a == ah:
            self.autohide_toggled.emit()

    def add_tab(self, name):
        btn = QPushButton(name); btn.setObjectName("tabBtn"); btn.setCursor(Qt.PointingHandCursor)
        btn.setCheckable(True); idx = len(self._tabs)
        btn.clicked.connect(lambda _,i=idx: self._on_click(i))
        btn.setContextMenuPolicy(Qt.CustomContextMenu)
        btn.customContextMenuRequested.connect(lambda pos,i=idx: self._tab_menu(i, pos))
        self._tabs.append(btn); self._layout.insertWidget(self._layout.count()-1, btn)
        return idx

    def set_active(self, idx):
        self._active = idx
        for i, b in enumerate(self._tabs): b.setChecked(i==idx)

    def rename_tab(self, idx, name):
        if 0<=idx<len(self._tabs): self._tabs[idx].setText(name)

    def remove_tab(self, idx):
        if 0<=idx<len(self._tabs):
            b = self._tabs.pop(idx); self._layout.removeWidget(b); b.deleteLater()
            for i, b in enumerate(self._tabs):
                b.clicked.disconnect(); b.clicked.connect(lambda _,ii=i: self._on_click(ii))
                b.customContextMenuRequested.disconnect()
                b.customContextMenuRequested.connect(lambda pos,ii=i: self._tab_menu(ii, pos))

    def _on_click(self, idx): self.set_active(idx); self.tab_clicked.emit(idx)

    def _tab_menu(self, idx, pos):
        menu = QMenu(self); menu.setStyleSheet(f"""
            QMenu {{ background:{C['base']}; border:1px solid {C['surface0']}; border-radius:6px; padding:4px 0; }}
            QMenu::item {{ color:{C['text']}; padding:6px 24px 6px 12px; font-size:12px; }}
            QMenu::item:selected {{ background:{C['surface1']}; }}
            QMenu::separator {{ height:1px; background:{C['surface0']}; margin:3px 6px; }}
        """)
        ra = menu.addAction("✏  重命名"); ca = menu.addAction("📋  复制")
        menu.addSeparator(); da = menu.addAction("🗑  删除")
        a = menu.exec_(self._tabs[idx].mapToGlobal(pos))
        if a == ra: self.rename_requested.emit(idx)
        elif a == ca: self.copy_requested.emit(idx)
        elif a == da: self.delete_requested.emit(idx)


# ---------------------------------------------------------------------------
# Windowed Panel (launched from desktop mode)
# ---------------------------------------------------------------------------

