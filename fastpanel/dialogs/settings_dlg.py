import os
from PyQt5.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QCheckBox, QFormLayout, QSpinBox,
    QFileDialog, QFrame, QScrollArea, QSlider, QWidget
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QColor

from fastpanel.constants import THEMES, _BASE_DIR, _DESKTOP_MODE
from fastpanel.settings import C, _settings
from fastpanel.theme import _dialog_style, _scrollbar_style, _bg, _style_combobox
from fastpanel.utils import _confirm_dialog
from fastpanel.dialogs.hotkey_dlg import _HotkeyEdit
from fastpanel.platform.autostart import _is_autostart_enabled

class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        from fastpanel.utils import _prepare_dialog
        _prepare_dialog(self)
        self.setWindowTitle("设置")
        self.setFixedWidth(480)
        self.setStyleSheet(_dialog_style())

        lay = QVBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(0)
        heading = QLabel("⚙  设置"); heading.setObjectName("heading")
        heading.setContentsMargins(28, 20, 28, 12)
        lay.addWidget(heading)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet(f"""
            QScrollArea {{ background: {C['base']}; border: none; }}
            QScrollArea > QWidget > QWidget {{ background: {C['base']}; }}
            {_scrollbar_style()}
        """)
        scroll_content = QWidget()
        scroll_content.setStyleSheet(f"background: {C['base']};")
        form = QFormLayout(scroll_content); form.setLabelAlignment(Qt.AlignRight); form.setSpacing(12)
        form.setContentsMargins(28, 0, 28, 16)

        self.theme_combo = QComboBox()
        for name in THEMES:
            self.theme_combo.addItem(name)
        cur = _settings.get("theme", "Catppuccin Mocha")
        if cur in THEMES:
            self.theme_combo.setCurrentText(cur)
        self.theme_combo.currentTextChanged.connect(self._preview_theme)
        _style_combobox(self.theme_combo)
        form.addRow("主  题", self.theme_combo)

        self._preview_bar = QWidget()
        self._preview_bar.setFixedHeight(28)
        self._update_preview_colors(cur)
        form.addRow("预  览", self._preview_bar)

        # --- Monitor mode ---
        screens = QApplication.screens()
        if len(screens) > 1:
            self._monitor_mode_combo = QComboBox()
            self._monitor_mode_combo.addItem("所有显示器共用一个面板", "single")
            self._monitor_mode_combo.addItem("每个显示器独立面板", "per_monitor")
            cur_mm = _settings.get("monitor_mode", "single")
            for i in range(self._monitor_mode_combo.count()):
                if self._monitor_mode_combo.itemData(i) == cur_mm:
                    self._monitor_mode_combo.setCurrentIndex(i); break
            _style_combobox(self._monitor_mode_combo)
            form.addRow("显示器模式", self._monitor_mode_combo)

        # --- Wallpaper mode selector (mutually exclusive) ---
        _WP_MODES = [
            ("theme", "随主题颜色"),
            ("image", "壁纸（单图）"),
            ("per_monitor", "每个显示器"),
            ("gradient", "渐变色"),
            ("slideshow", "壁纸轮播"),
        ]
        cur_wp = _settings.get("wp_mode", "")
        if not cur_wp:
            if _settings.get("bg_slideshow_dir", ""):
                cur_wp = "slideshow"
            elif _settings.get("bg_gradient", ""):
                cur_wp = "gradient"
            elif _settings.get("bg_per_monitor", {}):
                cur_wp = "per_monitor"
            elif _settings.get("bg_image", ""):
                cur_wp = "image"
            else:
                cur_wp = "theme"

        self._wp_mode_combo = QComboBox()
        for mode_id, mode_label in _WP_MODES:
            self._wp_mode_combo.addItem(mode_label, mode_id)
        for i in range(self._wp_mode_combo.count()):
            if self._wp_mode_combo.itemData(i) == cur_wp:
                self._wp_mode_combo.setCurrentIndex(i); break
        _style_combobox(self._wp_mode_combo)
        form.addRow("壁纸模式", self._wp_mode_combo)

        # -- Image mode settings --
        self._wp_image_w = QWidget()
        _img_lay = QVBoxLayout(self._wp_image_w); _img_lay.setContentsMargins(0, 0, 0, 0); _img_lay.setSpacing(6)
        bg_w = QWidget()
        bg_lay = QHBoxLayout(bg_w); bg_lay.setContentsMargins(0, 0, 0, 0); bg_lay.setSpacing(6)
        self.bg_edit = QLineEdit(_settings.get("bg_image", ""))
        self.bg_edit.setPlaceholderText("背景图片路径")
        bg_lay.addWidget(self.bg_edit)
        bb = QPushButton("…"); bb.setFixedWidth(36)
        bb.setStyleSheet(f"background:{C['surface1']}; color:{C['text']}; border:none; border-radius:6px;")
        bb.clicked.connect(self._browse_bg)
        bg_lay.addWidget(bb)
        clr = QPushButton("✕"); clr.setFixedWidth(36)
        clr.setStyleSheet(f"background:{C['surface1']}; color:{C['red']}; border:none; border-radius:6px;")
        clr.clicked.connect(lambda: self.bg_edit.clear())
        bg_lay.addWidget(clr)
        _img_lay.addWidget(bg_w)
        _img_mode_w = QWidget()
        _img_mode_lay = QHBoxLayout(_img_mode_w); _img_mode_lay.setContentsMargins(0, 0, 0, 0); _img_mode_lay.setSpacing(6)
        _img_mode_lay.addWidget(QLabel("显示方式"))
        self._bg_mode_combo = QComboBox()
        for mode_id, mode_label in [("tile", "平铺"), ("clone", "复制")]:
            self._bg_mode_combo.addItem(mode_label, mode_id)
        cur_mode = _settings.get("bg_mode", "tile")
        for i in range(self._bg_mode_combo.count()):
            if self._bg_mode_combo.itemData(i) == cur_mode:
                self._bg_mode_combo.setCurrentIndex(i); break
        _style_combobox(self._bg_mode_combo)
        _img_mode_lay.addWidget(self._bg_mode_combo)
        _img_lay.addWidget(_img_mode_w)
        form.addRow("", self._wp_image_w)

        # -- Opacity (shared for image/per_monitor/slideshow) --
        from PyQt5.QtWidgets import QSlider
        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(10, 100)
        self.opacity_slider.setValue(_settings.get("bg_opacity", 30))
        self._opa_label = QLabel(f"{self.opacity_slider.value()}%")
        self._opa_label.setFixedWidth(36)
        self.opacity_slider.valueChanged.connect(lambda v: self._opa_label.setText(f"{v}%"))
        self._wp_opa_w = QWidget()
        opa_lay = QHBoxLayout(self._wp_opa_w); opa_lay.setContentsMargins(0, 0, 0, 0); opa_lay.setSpacing(6)
        opa_lay.addWidget(self.opacity_slider); opa_lay.addWidget(self._opa_label)
        form.addRow("背景透明度", self._wp_opa_w)

        # -- Component opacity --
        self._comp_opa_slider = QSlider(Qt.Horizontal)
        self._comp_opa_slider.setRange(20, 100)
        self._comp_opa_slider.setValue(_settings.get("comp_opacity", 90))
        self._comp_opa_label = QLabel(f"{self._comp_opa_slider.value()}%")
        self._comp_opa_label.setFixedWidth(36)
        self._comp_opa_slider.valueChanged.connect(lambda v: self._comp_opa_label.setText(f"{v}%"))
        comp_opa_w = QWidget()
        comp_opa_lay = QHBoxLayout(comp_opa_w); comp_opa_lay.setContentsMargins(0, 0, 0, 0); comp_opa_lay.setSpacing(6)
        comp_opa_lay.addWidget(self._comp_opa_slider); comp_opa_lay.addWidget(self._comp_opa_label)
        form.addRow("组件透明度", comp_opa_w)

        # -- Per monitor settings --
        self._per_monitor_container = QWidget()
        self._per_monitor_lay = QVBoxLayout(self._per_monitor_container)
        self._per_monitor_lay.setContentsMargins(0, 0, 0, 0); self._per_monitor_lay.setSpacing(6)
        self._per_monitor_edits = {}
        screens = QApplication.screens()
        saved_per_mon = _settings.get("bg_per_monitor", {})
        for s in screens:
            row_w = QWidget()
            row_l = QHBoxLayout(row_w); row_l.setContentsMargins(0, 0, 0, 0); row_l.setSpacing(4)
            lbl = QLabel(f"{s.name()} ({s.geometry().width()}×{s.geometry().height()})")
            lbl.setFixedWidth(160)
            lbl.setStyleSheet(f"color:{C['subtext0']}; font-size:11px;")
            row_l.addWidget(lbl)
            edit = QLineEdit(saved_per_mon.get(s.name(), ""))
            edit.setPlaceholderText("壁纸路径")
            row_l.addWidget(edit)
            browse_btn = QPushButton("…"); browse_btn.setFixedWidth(28)
            browse_btn.setStyleSheet(f"background:{C['surface1']}; color:{C['text']}; border:none; border-radius:6px;")
            browse_btn.clicked.connect(lambda _, e=edit: self._browse_per_monitor(e))
            row_l.addWidget(browse_btn)
            self._per_monitor_lay.addWidget(row_w)
            self._per_monitor_edits[s.name()] = edit
        form.addRow("", self._per_monitor_container)

        # -- Gradient settings --
        self._wp_gradient_w = QWidget()
        _grad_lay = QVBoxLayout(self._wp_gradient_w); _grad_lay.setContentsMargins(0, 0, 0, 0); _grad_lay.setSpacing(6)
        self.gradient_edit = QLineEdit(_settings.get("bg_gradient", ""))
        self.gradient_edit.setPlaceholderText("渐变色，如: #1a1b26,#24283b,#414868")
        _grad_lay.addWidget(self.gradient_edit)
        _GRADIENT_PRESETS = [
            ("深空", "#0f0c29,#302b63,#24243e"),
            ("日落", "#ee9ca7,#ffdde1"),
            ("海洋", "#2193b0,#6dd5ed"),
            ("森林", "#134e5e,#71b280"),
            ("极光", "#00c9ff,#92fe9d"),
            ("暗夜", "#0f2027,#203a43,#2c5364"),
            ("火焰", "#f12711,#f5af19"),
        ]
        grad_preset_w = QWidget()
        grad_preset_lay = QHBoxLayout(grad_preset_w); grad_preset_lay.setContentsMargins(0, 0, 0, 0); grad_preset_lay.setSpacing(4)
        for name, val in _GRADIENT_PRESETS:
            pb = QPushButton(name); pb.setFixedHeight(24); pb.setCursor(Qt.PointingHandCursor)
            colors = val.split(",")
            if len(colors) >= 2:
                pb.setStyleSheet(f"""
                    QPushButton {{
                        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 {colors[0]},stop:1 {colors[-1]});
                        color: white; border: none; border-radius: 4px; font-size: 10px; padding: 2px 6px;
                    }}
                    QPushButton:hover {{ border: 1px solid white; }}
                """)
            pb.clicked.connect(lambda _, v=val: self.gradient_edit.setText(v))
            grad_preset_lay.addWidget(pb)
        grad_preset_lay.addStretch()
        _grad_lay.addWidget(grad_preset_w)
        form.addRow("", self._wp_gradient_w)

        # -- Slideshow settings --
        self._wp_slideshow_w = QWidget()
        _ss_lay = QVBoxLayout(self._wp_slideshow_w); _ss_lay.setContentsMargins(0, 0, 0, 0); _ss_lay.setSpacing(6)
        ss_row = QWidget()
        ss_hlay = QHBoxLayout(ss_row); ss_hlay.setContentsMargins(0, 0, 0, 0); ss_hlay.setSpacing(6)
        self.slideshow_dir = QLineEdit(_settings.get("bg_slideshow_dir", ""))
        self.slideshow_dir.setPlaceholderText("壁纸目录")
        ss_hlay.addWidget(self.slideshow_dir)
        ssb = QPushButton("…"); ssb.setFixedWidth(36)
        ssb.setStyleSheet(f"background:{C['surface1']}; color:{C['text']}; border:none; border-radius:6px;")
        ssb.clicked.connect(self._browse_slideshow)
        ss_hlay.addWidget(ssb)
        _ss_lay.addWidget(ss_row)
        int_row = QWidget()
        int_hlay = QHBoxLayout(int_row); int_hlay.setContentsMargins(0, 0, 0, 0); int_hlay.setSpacing(6)
        int_hlay.addWidget(QLabel("切换间隔"))
        self.slideshow_interval = QSpinBox()
        self.slideshow_interval.setRange(10, 3600)
        self.slideshow_interval.setSuffix(" 秒")
        self.slideshow_interval.setValue(_settings.get("bg_slideshow_interval", 300))
        int_hlay.addWidget(self.slideshow_interval)
        _ss_lay.addWidget(int_row)
        form.addRow("", self._wp_slideshow_w)

        # -- Mode switch handler --
        def _on_wp_mode_change(idx):
            mode = self._wp_mode_combo.itemData(idx)
            self._wp_image_w.setVisible(mode == "image")
            self._wp_opa_w.setVisible(mode in ("image", "per_monitor", "slideshow"))
            self._per_monitor_container.setVisible(mode == "per_monitor")
            self._wp_gradient_w.setVisible(mode == "gradient")
            self._wp_slideshow_w.setVisible(mode == "slideshow")
        self._wp_mode_combo.currentIndexChanged.connect(_on_wp_mode_change)
        _on_wp_mode_change(self._wp_mode_combo.currentIndex())

        if _DESKTOP_MODE:
            sep = QFrame(); sep.setFrameShape(QFrame.HLine)
            sep.setStyleSheet(f"color: {C['surface1']};")
            form.addRow(sep)
            hotkeys = _settings.get("hotkeys", {})
            self._autostart_cb = QCheckBox("开机自动启动 FastPanel（桌面模式）")
            self._autostart_cb.setChecked(_is_autostart_enabled())
            form.addRow("自启动", self._autostart_cb)

            sep2 = QFrame(); sep2.setFrameShape(QFrame.HLine)
            sep2.setStyleSheet(f"color: {C['surface1']};")
            form.addRow(sep2)
            hk_label = QLabel("快捷键  （点击输入框设置，×按钮清除）")
            hk_label.setStyleSheet(f"color: {C['subtext0']}; font-size: 11px; padding-top: 4px;")
            form.addRow("", hk_label)
            _hk_defs = [
                ("显示/隐藏", "toggle_visibility", "_hk_toggle"),
                ("新建组件", "add_component", "_hk_add"),
                ("锁定切换", "toggle_lock", "_hk_lock"),
                ("打开设置", "open_settings", "_hk_settings"),
                ("剪贴板弹出", "clipboard_popup", "_hk_clipboard"),
                ("语音输入", "voice_input", "_hk_voice"),
            ]
            for label_text, key, attr in _hk_defs:
                hk_edit = _HotkeyEdit(hotkeys.get(key, ""))
                setattr(self, attr, hk_edit)
                row = QHBoxLayout(); row.setSpacing(4)
                row.addWidget(hk_edit, 1)
                clr_btn = QPushButton("×")
                clr_btn.setFixedSize(28, 28)
                clr_btn.setCursor(Qt.PointingHandCursor)
                clr_btn.setStyleSheet(f"""
                    QPushButton {{ background: {C['surface1']}; color: {C['red']};
                        border: none; border-radius: 14px; font-size: 16px; font-weight: bold; }}
                    QPushButton:hover {{ background: {C['red']}; color: {C['crust']}; }}
                """)
                clr_btn.clicked.connect(lambda _, e=hk_edit: e.setText(""))
                row.addWidget(clr_btn)
                w = QWidget(); w.setLayout(row)
                form.addRow(label_text, w)

            sep3 = QFrame(); sep3.setFrameShape(QFrame.HLine)
            sep3.setStyleSheet(f"color: {C['surface1']};")
            form.addRow(sep3)
            voice_label = QLabel("语音输入  （Vosk 离线识别，需下载 ~1.2GB 中文模型）")
            voice_label.setStyleSheet(f"color: {C['subtext0']}; font-size: 11px; padding-top: 4px;")
            form.addRow("", voice_label)

            from fastpanel.platform.stt import SttEngine
            model_row = QWidget()
            model_lay = QHBoxLayout(model_row); model_lay.setContentsMargins(0, 0, 0, 0); model_lay.setSpacing(8)
            self._voice_model_status = QLabel()
            self._voice_model_status.setStyleSheet(f"font-size: 12px;")
            model_lay.addWidget(self._voice_model_status, 1)
            self._voice_dl_btn = QPushButton()
            self._voice_dl_btn.setCursor(Qt.PointingHandCursor)
            self._voice_dl_btn.setFixedHeight(28)
            model_lay.addWidget(self._voice_dl_btn)
            form.addRow("语音模型", model_row)

            self._stt_for_dl = SttEngine(self)
            self._stt_for_dl.model_progress.connect(self._on_voice_dl_progress)
            self._stt_for_dl.model_ready.connect(self._on_voice_dl_done)
            self._stt_for_dl.model_error.connect(self._on_voice_dl_error)
            self._update_voice_model_ui()

        scroll.setWidget(scroll_content)
        lay.addWidget(scroll, 1)

        btns_w = QWidget()
        btns_w.setContentsMargins(28, 8, 28, 16)
        btns = QHBoxLayout(btns_w); btns.addStretch()
        cancel = QPushButton("取消"); cancel.setObjectName("cancelBtn")
        cancel.setCursor(Qt.PointingHandCursor); cancel.clicked.connect(self.reject); btns.addWidget(cancel)
        ok = QPushButton("应  用"); ok.setObjectName("okBtn")
        ok.setCursor(Qt.PointingHandCursor); ok.clicked.connect(self.accept); btns.addWidget(ok)
        lay.addWidget(btns_w)

        max_h = int(QApplication.primaryScreen().availableGeometry().height() * 0.85)
        self.setMaximumHeight(max_h)

    def _preview_theme(self, name):
        self._update_preview_colors(name)

    def _update_preview_colors(self, name):
        t = THEMES.get(name, THEMES["Catppuccin Mocha"])
        colors = [t["base"], t["surface0"], t["blue"], t["green"], t["red"], t["peach"], t["mauve"], t["text"]]
        swatches = "".join(f'<span style="display:inline-block;width:24px;height:24px;background:{c};border-radius:4px;margin:0 2px;">&nbsp;</span>' for c in colors)
        self._preview_bar.setStyleSheet(
            f"background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            f"stop:0 {t['base']}, stop:0.25 {t['surface0']}, stop:0.5 {t['blue']}, stop:0.75 {t['green']}, stop:1 {t['peach']});"
            f"border-radius: 6px;"
        )

    def _browse_bg(self):
        from fastpanel.utils import _open_file
        f, _ = _open_file(self, "选择背景图片", "", "图片 (*.png *.jpg *.jpeg *.bmp *.webp)")
        if f:
            from fastpanel.dialogs.export import ImageCropDialog
            dlg = ImageCropDialog(f, self)
            if dlg.exec_() == QDialog.Accepted and dlg.cropped_path():
                self.bg_edit.setText(dlg.cropped_path())
            else:
                self.bg_edit.setText(f)

    def _browse_slideshow(self):
        from fastpanel.utils import _open_dir
        d = _open_dir(self, "选择壁纸目录", os.path.expanduser("~"))
        if d:
            self.slideshow_dir.setText(d)

    def _browse_per_monitor(self, edit):
        from fastpanel.utils import _open_file
        f, _ = _open_file(self, "选择壁纸", "", "图片 (*.png *.jpg *.jpeg *.bmp *.webp)")
        if f:
            edit.setText(f)

    def _update_voice_model_ui(self):
        if self._stt_for_dl.is_model_available():
            self._voice_model_status.setText("✓ 模型已就绪")
            self._voice_model_status.setStyleSheet(f"color: {C['green']}; font-size: 12px;")
            self._voice_dl_btn.setText("重新下载")
            self._voice_dl_btn.setStyleSheet(f"""
                QPushButton {{ background: {C['surface1']}; color: {C['text']};
                    border: none; border-radius: 6px; padding: 4px 12px; font-size: 12px; }}
                QPushButton:hover {{ background: {C['surface2']}; }}
            """)
        else:
            self._voice_model_status.setText("✗ 模型未下载")
            self._voice_model_status.setStyleSheet(f"color: {C['red']}; font-size: 12px;")
            self._voice_dl_btn.setText("下载模型 (~1.2GB)")
            self._voice_dl_btn.setStyleSheet(f"""
                QPushButton {{ background: {C['blue']}; color: {C['crust']};
                    border: none; border-radius: 6px; padding: 4px 12px; font-size: 12px; font-weight: bold; }}
                QPushButton:hover {{ background: {C['lavender']}; }}
            """)
        self._voice_dl_btn.setEnabled(True)
        try:
            self._voice_dl_btn.clicked.disconnect()
        except TypeError:
            pass
        self._voice_dl_btn.clicked.connect(self._on_voice_download)

    def _on_voice_download(self):
        self._voice_dl_btn.setEnabled(False)
        self._voice_dl_btn.setText("下载中...")
        self._voice_model_status.setText("正在下载...")
        self._voice_model_status.setStyleSheet(f"color: {C['blue']}; font-size: 12px;")
        self._stt_for_dl.download_model()

    def _on_voice_dl_progress(self, pct):
        self._voice_model_status.setText(f"下载中... {pct}%")
        self._voice_model_status.setStyleSheet(f"color: {C['blue']}; font-size: 12px;")
        self._voice_dl_btn.setEnabled(False)
        self._voice_dl_btn.setText("下载中...")

    def _on_voice_dl_done(self):
        self._update_voice_model_ui()

    def _on_voice_dl_error(self, msg):
        self._voice_model_status.setText(f"✗ {msg}")
        self._voice_model_status.setStyleSheet(f"color: {C['red']}; font-size: 12px;")
        self._voice_dl_btn.setEnabled(True)
        self._voice_dl_btn.setText("重试下载")

    def accept(self):
        if _DESKTOP_MODE and hasattr(self, '_hk_toggle'):
            hk_edits = {
                "显示/隐藏": self._hk_toggle, "新建组件": self._hk_add,
                "锁定切换": self._hk_lock, "打开设置": self._hk_settings,
                "剪贴板弹出": self._hk_clipboard, "语音输入": self._hk_voice,
            }
            used = {}
            for name, edit in hk_edits.items():
                key = edit.text().strip().lower()
                if key:
                    if key in used:
                        _confirm_dialog(self, "快捷键冲突",
                                        f"「{name}」与「{used[key]}」使用了相同的快捷键：{edit.text().strip()}\n请修改后重试。")
                        edit.setFocus()
                        return
                    used[key] = name
        super().accept()

    def get_settings(self):
        bg_mode = self._bg_mode_combo.itemData(self._bg_mode_combo.currentIndex())
        per_mon = {}
        for name, edit in self._per_monitor_edits.items():
            val = edit.text().strip()
            if val:
                per_mon[name] = val
        wp_mode = self._wp_mode_combo.itemData(self._wp_mode_combo.currentIndex())
        if hasattr(self, '_monitor_mode_combo'):
            _settings["monitor_mode"] = self._monitor_mode_combo.itemData(self._monitor_mode_combo.currentIndex())
            _settings["_monitor_mode_chosen"] = True
        s = {
            "theme": self.theme_combo.currentText(),
            "wp_mode": wp_mode,
            "bg_image": self.bg_edit.text().strip() if wp_mode == "image" else "",
            "bg_opacity": self.opacity_slider.value(),
            "comp_opacity": self._comp_opa_slider.value(),
            "bg_gradient": self.gradient_edit.text().strip() if wp_mode == "gradient" else "",
            "bg_slideshow_dir": self.slideshow_dir.text().strip() if wp_mode == "slideshow" else "",
            "bg_slideshow_interval": self.slideshow_interval.value(),
            "show_grid": _settings.get("show_grid", True),
            "bg_mode": bg_mode if wp_mode == "image" else "tile",
            "bg_per_monitor": per_mon if wp_mode == "per_monitor" else {},
        }
        if _DESKTOP_MODE and hasattr(self, '_hk_toggle'):
            s["hotkeys"] = {
                "toggle_visibility": self._hk_toggle.text().strip(),
                "add_component": self._hk_add.text().strip(),
                "toggle_lock": self._hk_lock.text().strip(),
                "open_settings": self._hk_settings.text().strip(),
                "clipboard_popup": self._hk_clipboard.text().strip(),
                "voice_input": self._hk_voice.text().strip(),
            }
        
        if hasattr(self, '_autostart_cb'):
            s["_autostart"] = self._autostart_cb.isChecked()
        return s


# ---------------------------------------------------------------------------
# Panel Tab Bar
# ---------------------------------------------------------------------------

