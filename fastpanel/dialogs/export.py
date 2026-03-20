import os
import uuid
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QCheckBox, QFileDialog, QFrame, QScrollArea, QWidget
)
from PyQt5.QtCore import Qt, QRect
from PyQt5.QtGui import QFont, QColor, QPixmap, QPainter

from fastpanel.settings import C
from fastpanel.constants import TYPE_LABELS
from fastpanel.theme import _dialog_style, _scrollbar_style

class ExportDialog(QDialog):
    def __init__(self, panels_data, parent=None):
        super().__init__(parent)
        from fastpanel.utils import _prepare_dialog
        _prepare_dialog(self)
        self.setWindowTitle("导出")
        self.setFixedWidth(460)
        self.setStyleSheet(_dialog_style())
        self._panels_data = panels_data

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20); lay.setSpacing(12)

        heading = QLabel("📤  选择导出内容")
        heading.setObjectName("heading")
        lay.addWidget(heading)

        self._all_chk = QCheckBox("全选")
        self._all_chk.setChecked(True)
        self._all_chk.stateChanged.connect(self._on_all_changed)
        lay.addWidget(self._all_chk)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(360)
        scroll.setStyleSheet(
            f"QScrollArea {{ border: 1px solid {C['surface1']}; border-radius: 8px; background: {C['base']}; }}"
            + _scrollbar_style(6)
        )
        content = QWidget()
        content.setStyleSheet(f"background: {C['base']};");
        self._tree_layout = QVBoxLayout(content)
        self._tree_layout.setContentsMargins(8, 8, 8, 8)
        self._tree_layout.setSpacing(4)

        self._panel_chks = []
        self._comp_chks = []
        for pi, pd in enumerate(panels_data):
            p_chk = QCheckBox(f"📁 {pd.name}")
            p_chk.setChecked(True)
            p_chk.setStyleSheet(f"font-weight: bold; color: {C['text']};")
            self._tree_layout.addWidget(p_chk)
            self._panel_chks.append(p_chk)
            comp_list = []
            for ci, cd in enumerate(pd.components):
                c_chk = QCheckBox(f"    {TYPE_LABELS.get(cd.comp_type, '')} {cd.name}")
                c_chk.setChecked(True)
                self._tree_layout.addWidget(c_chk)
                comp_list.append(c_chk)
            self._comp_chks.append(comp_list)
            p_chk.stateChanged.connect(lambda state, idx=pi: self._on_panel_changed(idx, state))

        self._tree_layout.addStretch()
        scroll.setWidget(content)
        lay.addWidget(scroll)

        btns = QHBoxLayout(); btns.addStretch()
        cancel = QPushButton("取消"); cancel.setObjectName("cancelBtn")
        cancel.setCursor(Qt.PointingHandCursor); cancel.clicked.connect(self.reject)
        btns.addWidget(cancel)
        ok = QPushButton("导  出"); ok.setObjectName("okBtn")
        ok.setCursor(Qt.PointingHandCursor); ok.clicked.connect(self.accept)
        btns.addWidget(ok)
        lay.addLayout(btns)

    def _on_all_changed(self, state):
        checked = state == Qt.Checked
        for p_chk in self._panel_chks:
            p_chk.blockSignals(True); p_chk.setChecked(checked); p_chk.blockSignals(False)
        for comp_list in self._comp_chks:
            for c_chk in comp_list:
                c_chk.setChecked(checked)

    def _on_panel_changed(self, idx, state):
        checked = state == Qt.Checked
        for c_chk in self._comp_chks[idx]:
            c_chk.setChecked(checked)

    def get_export_data(self):
        result = []
        for pi, pd in enumerate(self._panels_data):
            comps = []
            for ci, cd in enumerate(pd.components):
                if self._comp_chks[pi][ci].isChecked():
                    comps.append(cd.to_dict())
            if comps:
                result.append({"name": pd.name, "components": comps})
        return result


# ---------------------------------------------------------------------------
# Settings Dialog
# ---------------------------------------------------------------------------
class _CropView(QWidget):
    def __init__(self, pixmap, parent=None):
        super().__init__(parent)
        self._src = pixmap
        sw, sh = pixmap.width(), pixmap.height()
        max_w, max_h = 640, 480
        scale = min(max_w / sw, max_h / sh, 1.0)
        self._dw = int(sw * scale)
        self._dh = int(sh * scale)
        self._scale = scale
        self._disp = pixmap.scaled(self._dw, self._dh, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.setFixedSize(self._dw, self._dh)
        self._crop = QRect(0, 0, self._dw, self._dh)
        self._drag = None
        self._drag_edge = None

    def paintEvent(self, e):
        p = QPainter(self)
        p.drawPixmap(0, 0, self._disp)
        dim = QColor(0, 0, 0, 120)
        cr = self._crop
        p.fillRect(QRect(0, 0, self._dw, cr.top()), dim)
        p.fillRect(QRect(0, cr.bottom(), self._dw, self._dh - cr.bottom()), dim)
        p.fillRect(QRect(0, cr.top(), cr.left(), cr.height()), dim)
        p.fillRect(QRect(cr.right(), cr.top(), self._dw - cr.right(), cr.height()), dim)
        p.setPen(QColor(255, 255, 255))
        p.drawRect(cr)
        p.setPen(QColor(255, 255, 255, 100))
        tw = cr.width() / 3; th = cr.height() / 3
        for i in range(1, 3):
            p.drawLine(int(cr.left() + tw * i), cr.top(), int(cr.left() + tw * i), cr.bottom())
            p.drawLine(cr.left(), int(cr.top() + th * i), cr.right(), int(cr.top() + th * i))
        p.end()

    def _edge_at(self, pos):
        cr = self._crop; m = 8
        edges = []
        if abs(pos.y() - cr.top()) < m: edges.append("t")
        if abs(pos.y() - cr.bottom()) < m: edges.append("b")
        if abs(pos.x() - cr.left()) < m: edges.append("l")
        if abs(pos.x() - cr.right()) < m: edges.append("r")
        if not edges and cr.contains(pos): return "move"
        return "".join(edges) if edges else None

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag_edge = self._edge_at(e.pos())
            self._drag = e.pos()

    def mouseMoveEvent(self, e):
        if not self._drag:
            edge = self._edge_at(e.pos())
            cursors = {"t": Qt.SizeVerCursor, "b": Qt.SizeVerCursor, "l": Qt.SizeHorCursor, "r": Qt.SizeHorCursor,
                       "tl": Qt.SizeFDiagCursor, "br": Qt.SizeFDiagCursor, "tr": Qt.SizeBDiagCursor, "bl": Qt.SizeBDiagCursor, "move": Qt.SizeAllCursor}
            self.setCursor(cursors.get(edge, Qt.ArrowCursor))
            return
        dx = e.pos().x() - self._drag.x()
        dy = e.pos().y() - self._drag.y()
        cr = QRect(self._crop)
        de = self._drag_edge
        if de == "move":
            cr.translate(dx, dy)
            if cr.left() < 0: cr.moveLeft(0)
            if cr.top() < 0: cr.moveTop(0)
            if cr.right() > self._dw: cr.moveRight(self._dw)
            if cr.bottom() > self._dh: cr.moveBottom(self._dh)
        else:
            if de and "t" in de: cr.setTop(max(0, min(cr.bottom() - 20, cr.top() + dy)))
            if de and "b" in de: cr.setBottom(min(self._dh, max(cr.top() + 20, cr.bottom() + dy)))
            if de and "l" in de: cr.setLeft(max(0, min(cr.right() - 20, cr.left() + dx)))
            if de and "r" in de: cr.setRight(min(self._dw, max(cr.left() + 20, cr.right() + dx)))
        self._crop = cr
        self._drag = e.pos()
        self.update()

    def mouseReleaseEvent(self, e):
        self._drag = None; self._drag_edge = None

    def get_crop_rect(self):
        s = 1 / self._scale
        return QRect(int(self._crop.left() * s), int(self._crop.top() * s),
                     int(self._crop.width() * s), int(self._crop.height() * s))


class ImageCropDialog(QDialog):
    def __init__(self, image_path, parent=None):
        super().__init__(parent)
        from fastpanel.utils import _prepare_dialog
        _prepare_dialog(self)
        self.setWindowTitle("裁剪壁纸")
        self.setStyleSheet(f"QDialog {{ background: {C['base']}; }} QLabel {{ color: {C['text']}; }}")
        self._path = image_path
        self._src = QPixmap(image_path)
        self._cropped_path = None
        lay = QVBoxLayout(self); lay.setSpacing(12); lay.setContentsMargins(16, 16, 16, 16)
        hint = QLabel("拖动白色边框调整裁剪区域")
        hint.setStyleSheet(f"color:{C['subtext0']}; font-size:12px;")
        hint.setAlignment(Qt.AlignCenter); lay.addWidget(hint)
        self._view = _CropView(self._src, self)
        lay.addWidget(self._view, 0, Qt.AlignCenter)
        btns = QHBoxLayout(); btns.addStretch()
        cb = QPushButton("取消"); cb.setStyleSheet(f"background:{C['surface1']}; color:{C['text']}; border:none; border-radius:8px; padding:8px 24px; font-size:13px;")
        cb.setCursor(Qt.PointingHandCursor); cb.clicked.connect(self.reject); btns.addWidget(cb)
        ob = QPushButton("确认裁剪"); ob.setStyleSheet(f"background:{C['blue']}; color:{C['crust']}; border:none; border-radius:8px; padding:8px 24px; font-size:13px; font-weight:bold;")
        ob.setCursor(Qt.PointingHandCursor); ob.clicked.connect(self._do_crop); btns.addWidget(ob)
        lay.addLayout(btns)
        self.adjustSize()

    def _do_crop(self):
        r = self._view.get_crop_rect()
        cropped = self._src.copy(r)
        out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".wallpaper")
        os.makedirs(out_dir, exist_ok=True)
        self._cropped_path = os.path.join(out_dir, f"cropped_{uuid.uuid4().hex[:8]}.png")
        cropped.save(self._cropped_path, "PNG")
        self.accept()

    def cropped_path(self):
        return self._cropped_path



