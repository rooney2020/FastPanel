from fastpanel.settings import C, _settings
from fastpanel.constants import ARROW_PATH, CHECK_PATH

def _hex_to_rgba(hex_color, alpha):
    h = hex_color.lstrip('#')
    return f"rgba({int(h[:2],16)},{int(h[2:4],16)},{int(h[4:6],16)},{alpha})"

def _bg(color_key):
    """Get a background color with component opacity applied."""
    opa = _settings.get("comp_opacity", 90) / 100.0
    a = int(opa * 255)
    return _hex_to_rgba(C[color_key], a)

def _comp_style():
    opa = _settings.get("comp_opacity", 90) / 100.0
    a = int(opa * 255)
    bg = _hex_to_rgba(C['base'], a)
    crust_bg = _hex_to_rgba(C['crust'], a)
    s0_bg = _hex_to_rgba(C['surface0'], a)
    s1_bg = _hex_to_rgba(C['surface1'], a)
    border = _hex_to_rgba(C['surface0'], min(a + 30, 255))
    hover = _hex_to_rgba(C['surface2'], min(a + 50, 255))
    return f"""
    QFrame[compWidget="true"] {{
        background: {bg}; border: 1px solid {border}; border-radius: 12px;
    }}
    QFrame[compWidget="true"]:hover {{ border: 1px solid {hover}; }}
    #badge {{
        background: {C['blue']}; color: {C['crust']};
        border-radius: 4px; font-size: 10px; font-weight: bold; padding: 0 8px;
    }}
    #badgeCmdWin {{
        background: {C['mauve']}; color: {C['crust']};
        border-radius: 4px; font-size: 9px; font-weight: bold; padding: 0 6px;
    }}
    #badgeShortcut {{
        background: {C['peach']}; color: {C['crust']};
        border-radius: 4px; font-size: 9px; font-weight: bold; padding: 0 6px;
    }}
    #title {{ color: {C['text']}; font-size: 14px; font-weight: bold; }}
    #runBtn {{
        background: {C['green']}; color: {C['crust']};
        border: none; border-radius: 6px; padding: 0 14px;
        font-weight: bold; font-size: 12px;
    }}
    #runBtn:hover {{ background: {C['teal']}; }}
    #runBtn[running="true"] {{ background: {C['red']}; }}
    #runBtn[running="true"]:hover {{ background: {C['peach']}; }}
    #cmdFrame {{
        background: {crust_bg}; border-radius: 8px;
    }}
    #prompt {{
        color: {C['green']};
        font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace;
        font-size: 12px; font-weight: bold;
    }}
    #cmdText {{
        color: {C['subtext0']};
        font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace;
        font-size: 12px;
    }}
    #paramInput {{
        background: {crust_bg}; color: {C['yellow']};
        border: 1px solid {border}; border-radius: 6px;
        padding: 5px 10px;
        font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace;
        font-size: 12px;
    }}
    #paramInput:focus {{ border: 1px solid {C['yellow']}; }}
    #output {{
        background: {crust_bg}; color: {C['green']};
        border: 1px solid {border}; border-radius: 8px;
        font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace;
        font-size: 11px; padding: 8px;
    }}
    #stdinInput {{
        background: {crust_bg}; color: {C['text']};
        border: 1px solid {border}; border-radius: 6px;
        padding: 4px 8px;
        font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace;
        font-size: 11px;
    }}
    #stdinInput:focus {{ border: 1px solid {C['sky']}; }}
    #stdinInput:disabled {{ color: {C['overlay0']}; }}
    #sendBtn {{
        background: {C['sky']}; color: {C['crust']};
        border: none; border-radius: 6px; font-size: 11px;
        font-weight: bold; padding: 4px;
    }}
    #sendBtn:hover {{ background: {C['teal']}; }}
    #sendBtn:disabled {{ background: {s1_bg}; color: {C['overlay0']}; }}
    #launchBtn {{
        background: {C['peach']}; color: {C['crust']};
        border: none; border-radius: 8px; padding: 10px 24px;
        font-size: 14px; font-weight: bold;
    }}
    #launchBtn:hover {{ background: {C['yellow']}; }}
    #iconLabel {{ background: transparent; }}
    #pathLabel {{
        color: {C['subtext0']};
        font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace;
        font-size: 11px;
    }}
    """


# ---------------------------------------------------------------------------
# Process runner (pty-based)
# ---------------------------------------------------------------------------

def _dialog_style():
    return f"""
        QDialog {{ background: {C['base']}; }}
        #heading {{ color: {C['lavender']}; font-size: 18px; font-weight: bold; }}
        QLabel {{ color: {C['subtext0']}; font-size: 13px; }}
        QLineEdit {{
            background: {C['surface0']}; color: {C['text']};
            border: 1px solid {C['surface1']}; border-radius: 8px;
            padding: 8px 14px; font-size: 13px;
            selection-background-color: {C['blue']};
        }}
        QLineEdit:focus {{ border: 1px solid {C['blue']}; }}
        QComboBox {{
            background: {C['surface0']}; color: {C['text']};
            border: 1px solid {C['surface1']}; border-radius: 8px;
            padding: 8px 14px; font-size: 13px;
        }}
        QComboBox::drop-down {{
            subcontrol-origin: padding; subcontrol-position: center right;
            width: 28px; border: none; background: transparent;
        }}
        QComboBox::down-arrow {{ image: url({ARROW_PATH}); width: 12px; height: 8px; }}
        QComboBox QAbstractItemView {{
            background: {C['surface0']}; color: {C['text']};
            selection-background-color: {C['surface1']};
            border: 1px solid {C['surface1']}; outline: none;
        }}
        QCheckBox {{ color: {C['subtext0']}; font-size: 13px; spacing: 8px; }}
        QCheckBox::indicator {{
            width: 18px; height: 18px; border-radius: 4px;
            border: 2px solid {C['surface2']}; background: transparent;
        }}
        QCheckBox::indicator:hover {{ border-color: {C['blue']}; }}
        QCheckBox::indicator:checked {{
            border: 2px solid {C['blue']}; background: transparent;
            image: url({CHECK_PATH});
        }}
        #cancelBtn {{
            background: {C['surface1']}; color: {C['text']};
            border: none; border-radius: 8px; padding: 8px 24px; font-size: 13px;
        }}
        #cancelBtn:hover {{ background: {C['surface2']}; }}
        #okBtn {{
            background: {C['blue']}; color: {C['crust']};
            border: none; border-radius: 8px; padding: 8px 28px;
            font-size: 13px; font-weight: bold;
        }}
        #okBtn:hover {{ background: {C['lavender']}; }}
    """


def _combobox_popup_style():
    return f"""
        QAbstractItemView {{
            background: {C['surface0']}; color: {C['text']};
            border: 1px solid {C['surface1']}; border-radius: 6px;
            selection-background-color: {C['surface1']};
            selection-color: {C['text']};
            outline: none; padding: 4px;
        }}
        QAbstractItemView::item {{
            padding: 6px 12px; border-radius: 4px; min-height: 22px;
        }}
        QAbstractItemView::item:hover {{ background: {C['surface1']}; }}
        QAbstractItemView::item:selected {{ background: {C['surface1']}; }}
    """


def _style_combobox(combo):
    """Apply full styling to a QComboBox including its popup container QPalette."""
    from PyQt5.QtWidgets import QComboBox as _QCB
    from PyQt5.QtGui import QPalette, QColor
    from PyQt5.QtCore import QTimer

    combo.setStyleSheet(f"""
        QComboBox {{
            background: {C['surface0']}; color: {C['text']};
            border: 1px solid {C['surface1']}; border-radius: 8px;
            padding: 6px 30px 6px 12px; font-size: 13px; min-height: 20px;
        }}
        QComboBox:hover {{ border-color: {C['surface2']}; }}
        QComboBox:focus {{ border-color: {C['blue']}; }}
        QComboBox::drop-down {{
            subcontrol-origin: padding; subcontrol-position: center right;
            width: 28px; border: none;
        }}
        QComboBox::down-arrow {{ image: url({ARROW_PATH}); width: 12px; height: 8px; }}
        QComboBox QAbstractItemView {{
            background: {C['surface0']}; color: {C['text']};
            border: 1px solid {C['surface1']}; border-radius: 6px;
            selection-background-color: {C['surface1']};
            selection-color: {C['text']};
            outline: none; padding: 4px;
        }}
        QComboBox QAbstractItemView::item {{
            padding: 6px 12px; min-height: 22px;
        }}
        QComboBox QAbstractItemView::item:hover {{ background: {C['surface1']}; }}
        QComboBox QAbstractItemView::item:selected {{ background: {C['surface1']}; }}
        QComboBox QFrame {{
            background: {C['surface0']};
            border: 1px solid {C['surface1']};
            border-radius: 6px;
        }}
    """)
    if combo.view():
        combo.view().setStyleSheet(_combobox_popup_style())

    def _apply_popup_style():
        view = combo.view()
        if not view:
            return
        container = view.parent()
        if container and container is not combo:
            bg = QColor(C['surface0'])
            fg = QColor(C['text'])
            pal = container.palette()
            for role in (QPalette.Window, QPalette.Base, QPalette.AlternateBase,
                         QPalette.Button):
                pal.setColor(QPalette.Active, role, bg)
                pal.setColor(QPalette.Inactive, role, bg)
            for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
                pal.setColor(QPalette.Active, role, fg)
                pal.setColor(QPalette.Inactive, role, fg)
            pal.setColor(QPalette.Highlight, QColor(C['surface1']))
            pal.setColor(QPalette.HighlightedText, fg)
            container.setPalette(pal)
            container.setAutoFillBackground(True)
            container.setStyleSheet(
                f"QFrame {{ background: {C['surface0']}; border: 1px solid {C['surface1']}; border-radius: 6px; }}"
            )
            view.setPalette(pal)
            view.setAutoFillBackground(True)
            view.setStyleSheet(_combobox_popup_style())

    _cls_name = f"_StyledCB_{id(combo)}"
    _styled_cls = type(_cls_name, (_QCB,), {
        'showPopup': lambda self: (
            _QCB.showPopup(self),
            QTimer.singleShot(0, _apply_popup_style),
        )
    })
    combo.__class__ = _styled_cls


def _scrollbar_style(width=6):
    return f"""
        QScrollBar:vertical {{
            width: {width}px; background: transparent; border: none; margin: 0;
        }}
        QScrollBar::handle:vertical {{
            background: {C['surface1']}; border-radius: {width // 2}px; min-height: 20px;
        }}
        QScrollBar::handle:vertical:hover {{ background: {C['surface2']}; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
        QScrollBar:horizontal {{
            height: {width}px; background: transparent; border: none; margin: 0;
        }}
        QScrollBar::handle:horizontal {{
            background: {C['surface1']}; border-radius: {width // 2}px; min-width: 20px;
        }}
        QScrollBar::handle:horizontal:hover {{ background: {C['surface2']}; }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
        QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: transparent; }}
    """


def _file_dialog_style():
    """Full stylesheet for non-native QFileDialog in desktop mode."""
    sel_bg = _hex_to_rgba(C["blue"], 0.2)
    return f"""
        QFileDialog {{ background: {C['base']}; color: {C['text']}; }}
        QLabel {{ color: {C['text']}; font-size: 13px; }}
        QLineEdit {{
            background: {C['surface0']}; color: {C['text']};
            border: 1px solid {C['surface1']}; border-radius: 8px;
            padding: 6px 12px; font-size: 13px;
            selection-background-color: {C['blue']};
            selection-color: {C['crust']};
        }}
        QLineEdit:focus {{ border-color: {C['blue']}; }}
        QComboBox {{
            background: {C['surface0']}; color: {C['text']};
            border: 1px solid {C['surface1']}; border-radius: 8px;
            padding: 6px 12px; font-size: 13px; min-height: 20px;
        }}
        QComboBox:hover {{ border-color: {C['surface2']}; }}
        QComboBox::drop-down {{
            subcontrol-origin: padding; subcontrol-position: top right;
            width: 28px; border: none; border-radius: 8px;
        }}
        QComboBox::down-arrow {{ image: url({ARROW_PATH}); width: 12px; height: 8px; }}
        QComboBox QAbstractItemView {{
            background: {C['surface0']}; color: {C['text']};
            border: 1px solid {C['surface1']}; border-radius: 8px;
            selection-background-color: {C['surface1']};
            selection-color: {C['text']};
            outline: none; padding: 4px;
        }}
        QComboBox QAbstractItemView::item {{
            padding: 6px 12px; border-radius: 4px; margin: 1px;
        }}
        QComboBox QAbstractItemView::item:hover {{ background: {C['surface1']}; }}
        QTreeView, QListView, QTableView {{
            background: {C['base']}; color: {C['text']};
            border: 1px solid {C['surface0']}; border-radius: 8px;
            outline: none; font-size: 13px;
            selection-background-color: {sel_bg};
            selection-color: {C['text']};
        }}
        QTreeView::item, QListView::item {{
            padding: 4px 8px; border-radius: 4px;
        }}
        QTreeView::item:hover, QListView::item:hover {{ background: {C['surface0']}; }}
        QTreeView::item:selected, QListView::item:selected {{
            background: {sel_bg}; color: {C['text']};
        }}
        QHeaderView {{ background: {C['mantle']}; }}
        QHeaderView::section {{
            background: {C['mantle']}; color: {C['subtext0']};
            border: none; border-bottom: 1px solid {C['surface0']};
            padding: 6px 10px; font-size: 12px; font-weight: bold;
        }}
        QTableCornerButton::section {{ background: {C['mantle']}; border: none; }}
        QToolButton {{
            background: {C['surface0']}; color: {C['text']};
            border: none; border-radius: 6px;
            padding: 4px; min-width: 28px; min-height: 28px;
        }}
        QToolButton:hover {{ background: {C['surface1']}; }}
        QToolButton:pressed {{ background: {C['surface2']}; }}
        QPushButton {{
            background: {C['blue']}; color: {C['crust']};
            border: none; border-radius: 8px;
            padding: 8px 20px; font-size: 13px; font-weight: bold;
        }}
        QPushButton:hover {{ background: {C['lavender']}; }}
        QPushButton:pressed {{ background: {C['sky']}; }}
        QPushButton:disabled {{ background: {C['surface1']}; color: {C['overlay0']}; }}
        QSplitter::handle {{ background: {C['surface0']}; }}
        QFrame {{ color: {C['text']}; }}
        {_scrollbar_style(6)}
    """



