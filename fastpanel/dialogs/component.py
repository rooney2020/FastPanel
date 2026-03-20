import os
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QCheckBox, QTextEdit, QFormLayout,
    QSpinBox, QFileDialog, QFrame, QScrollArea, QWidget
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QColor, QIntValidator

from fastpanel.constants import (
    GRID_SIZE, TYPE_CMD, TYPE_CMD_WINDOW, TYPE_SHORTCUT, TYPE_CALENDAR,
    TYPE_WEATHER, TYPE_DOCK, TYPE_TODO, TYPE_CLOCK, TYPE_MONITOR,
    TYPE_LAUNCHER, TYPE_NOTE, TYPE_QUICKACTION, TYPE_MEDIA,
    TYPE_CLIPBOARD, TYPE_TIMER, TYPE_GALLERY, TYPE_SYSINFO,
    TYPE_BOOKMARK, TYPE_CALC, TYPE_TRASH, TYPE_RSS, TYPE_LABELS,
    MONITOR_SUB_LABELS, MONITOR_SUB_ALL,
    CLOCK_SUB_LABELS, CLOCK_SUB_CLOCK, CLOCK_SUB_WORLD, CLOCK_SUB_ALARM,
    SUB_LABELS, SUB_APP, PARAM_PATTERN,
    CHECK_PATH, ARROW_PATH
)
from fastpanel.settings import C, _settings
from fastpanel.theme import _dialog_style, _scrollbar_style, _bg, _style_combobox
from fastpanel.data import ComponentData
from fastpanel.utils import _prepare_dialog, count_params

def _build_comp_dialog(dialog, heading_text, ok_text, data=None):
    dialog.setStyleSheet(_dialog_style())
    lay = QVBoxLayout(dialog)
    lay.setContentsMargins(28, 24, 28, 24)
    lay.setSpacing(16)

    heading = QLabel(heading_text)
    heading.setObjectName("heading")
    lay.addWidget(heading)

    form = QFormLayout()
    form.setLabelAlignment(Qt.AlignRight)
    form.setSpacing(12)

    dialog.cat = QComboBox()
    for k, v in TYPE_LABELS.items():
        dialog.cat.addItem(v, k)
    _style_combobox(dialog.cat)
    form.addRow("类  别", dialog.cat)

    dialog.name_edit = QLineEdit(data.name if data else "")
    dialog.name_edit.setPlaceholderText("组件名称")
    form.addRow("名  称", dialog.name_edit)

    # --- CMD fields ---
    dialog.cmd_edit = QLineEdit(data.cmd if data else "")
    dialog.cmd_edit.setPlaceholderText("例如：curl ($) | grep ($)")
    form.addRow("命  令", dialog.cmd_edit)

    dialog._hint = QLabel('提示：使用 ($) 作为动态参数占位符')
    dialog._hint.setStyleSheet(f"color:{C['overlay0']}; font-size:11px;")
    form.addRow("", dialog._hint)

    dialog._param_container = QWidget()
    dialog._param_layout = QVBoxLayout(dialog._param_container)
    dialog._param_layout.setContentsMargins(0, 0, 0, 0)
    dialog._param_layout.setSpacing(6)
    dialog._param_hint_edits = []
    dialog._param_default_edits = []
    dialog._param_rows = []
    form.addRow("", dialog._param_container)

    def _update_param_hints():
        n = count_params(dialog.cmd_edit.text())
        old_hints = [e.text() for e in dialog._param_hint_edits]
        old_defaults = [e.text() for e in dialog._param_default_edits]
        for row_w in dialog._param_rows:
            dialog._param_layout.removeWidget(row_w); row_w.deleteLater()
        dialog._param_hint_edits.clear()
        dialog._param_default_edits.clear()
        dialog._param_rows.clear()
        ph = data.param_hints if data else []
        pd = data.param_defaults if data else []
        for i in range(n):
            row_w = QWidget()
            rl = QHBoxLayout(row_w); rl.setContentsMargins(0, 0, 0, 0); rl.setSpacing(6)
            lbl = QLabel(f"参数{i+1}"); lbl.setFixedWidth(40)
            lbl.setStyleSheet(f"color:{C['subtext0']}; font-size:11px;")
            rl.addWidget(lbl)
            hint_e = QLineEdit()
            hint_e.setPlaceholderText("说明")
            if i < len(old_hints) and old_hints[i]:
                hint_e.setText(old_hints[i])
            elif i < len(ph) and ph[i]:
                hint_e.setText(ph[i])
            rl.addWidget(hint_e)
            def_e = QLineEdit()
            def_e.setPlaceholderText("默认值")
            if i < len(old_defaults) and old_defaults[i]:
                def_e.setText(old_defaults[i])
            elif i < len(pd) and pd[i]:
                def_e.setText(pd[i])
            rl.addWidget(def_e)
            dialog._param_layout.addWidget(row_w)
            dialog._param_hint_edits.append(hint_e)
            dialog._param_default_edits.append(def_e)
            dialog._param_rows.append(row_w)
        dialog._param_container.setVisible(n > 0 and dialog.cat.currentData() == TYPE_CMD)

    dialog.cmd_edit.textChanged.connect(_update_param_hints)
    dialog._update_param_hints = _update_param_hints

    dialog.output_chk = QCheckBox("显示命令输出结果")
    if data:
        dialog.output_chk.setChecked(data.show_output)
    form.addRow("", dialog.output_chk)

    # --- CMD Window fields ---
    dialog._cmdwin_hint = QLabel("CMD窗口只需填写名称即可，启动后可交互")
    dialog._cmdwin_hint.setStyleSheet(f"color:{C['overlay0']}; font-size:12px;")
    form.addRow("", dialog._cmdwin_hint)

    dialog.pre_cmd_edit = QTextEdit()
    dialog.pre_cmd_edit.setPlaceholderText("启动后自动执行的命令，每行一条（可选）")
    dialog.pre_cmd_edit.setFixedHeight(80)
    if data and data.pre_cmd:
        dialog.pre_cmd_edit.setPlainText(data.pre_cmd)
    form.addRow("预命令", dialog.pre_cmd_edit)

    # --- Shortcut fields ---
    dialog._shortcut_import_btn = QPushButton("📦 从系统导入应用")
    dialog._shortcut_import_btn.setCursor(Qt.PointingHandCursor)
    dialog._shortcut_import_btn.setStyleSheet(f"""
        QPushButton {{ background:{C['surface1']}; color:{C['text']}; border:none; border-radius:8px; padding:6px; font-size:11px; }}
        QPushButton:hover {{ background:{C['surface2']}; }}
    """)
    def _import_sys_shortcut():
        from fastpanel.widgets.dock import _SystemAppDialog
        dlg = _SystemAppDialog(dialog)
        if dlg.exec_() == QDialog.Accepted:
            app = dlg.selected_app()
            if app:
                dialog.name_edit.setText(app["name"])
                dialog.icon_edit.setText(app.get("icon", ""))
                dialog.path_edit.setText(app.get("exec", ""))
                dialog.sub_type_combo.setCurrentIndex(0)
    dialog._shortcut_import_btn.clicked.connect(_import_sys_shortcut)
    form.addRow("", dialog._shortcut_import_btn)

    dialog.sub_type_combo = QComboBox()
    for k, v in SUB_LABELS.items():
        dialog.sub_type_combo.addItem(v, k)
    if data and data.sub_type in SUB_LABELS:
        idx_st = list(SUB_LABELS.keys()).index(data.sub_type)
        dialog.sub_type_combo.setCurrentIndex(idx_st)
    _style_combobox(dialog.sub_type_combo)
    form.addRow("类  型", dialog.sub_type_combo)

    icon_w = QWidget()
    icon_lay = QHBoxLayout(icon_w)
    icon_lay.setContentsMargins(0, 0, 0, 0)
    icon_lay.setSpacing(6)
    dialog.icon_edit = QLineEdit(data.icon if data else "")
    dialog.icon_edit.setPlaceholderText("图标文件路径（可选）")
    icon_lay.addWidget(dialog.icon_edit)
    ib = QPushButton("…")
    ib.setFixedWidth(36)
    ib.setStyleSheet(f"background:{C['surface1']}; color:{C['text']}; border:none; border-radius:6px;")
    ib.clicked.connect(lambda: _dlg_browse(dialog, dialog.icon_edit, "图标", "图片 (*.png *.svg *.ico *.jpg)"))
    icon_lay.addWidget(ib)
    dialog._icon_widget = icon_w
    form.addRow("图  标", icon_w)

    path_w = QWidget()
    path_lay = QHBoxLayout(path_w)
    path_lay.setContentsMargins(0, 0, 0, 0)
    path_lay.setSpacing(6)
    dialog.path_edit = QLineEdit(data.path if data else "")
    dialog.path_edit.setPlaceholderText("程序/文件/脚本路径")
    path_lay.addWidget(dialog.path_edit)
    pb = QPushButton("…")
    pb.setFixedWidth(36)
    pb.setStyleSheet(f"background:{C['surface1']}; color:{C['text']}; border:none; border-radius:6px;")
    pb.clicked.connect(lambda: _dlg_browse(dialog, dialog.path_edit, "选择", "所有文件 (*)"))
    path_lay.addWidget(pb)
    dialog._path_widget = path_w
    form.addRow("路  径", path_w)

    # --- Dock hint ---
    dialog._dock_hint = QLabel("Dock栏只需填写名称，创建后右键添加快捷方式项目")
    dialog._dock_hint.setStyleSheet(f"color:{C['overlay0']}; font-size:12px;")
    form.addRow("", dialog._dock_hint)

    # --- Todo hint ---
    dialog._todo_hint = QLabel("待办组件只需填写名称，创建后可添加待办事项")
    dialog._todo_hint.setStyleSheet(f"color:{C['overlay0']}; font-size:12px;")
    form.addRow("", dialog._todo_hint)

    # --- Calendar hint ---
    dialog._cal_hint = QLabel("自动显示当月日历和农历")
    dialog._cal_hint.setStyleSheet(f"color:{C['overlay0']}; font-size:12px;")
    form.addRow("", dialog._cal_hint)

    # --- Refresh interval (shared by calendar & weather) ---
    from PyQt5.QtWidgets import QSpinBox
    dialog._refresh_spin = QSpinBox()
    dialog._refresh_spin.setRange(1, 1440)
    dialog._refresh_spin.setSuffix(" 分钟")
    dialog._refresh_spin.setValue(data.refresh_interval // 60 if data else 5)
    dialog._refresh_spin.setStyleSheet(f"background:{C['surface0']}; color:{C['text']}; border:1px solid {C['surface2']}; border-radius:6px; padding:4px;")
    form.addRow("刷新间隔", dialog._refresh_spin)

    # --- Weather fields ---
    dialog._weather_hint = QLabel("选择城市后获取天气信息")
    dialog._weather_hint.setStyleSheet(f"color:{C['overlay0']}; font-size:12px;")
    form.addRow("", dialog._weather_hint)
    _city_row = QHBoxLayout(); _city_row.setSpacing(6)
    _init_city_cmd = data.cmd if data and data.comp_type == TYPE_WEATHER else ""
    _init_code = _init_city_cmd.split("|")[0].strip() if "|" in _init_city_cmd else ""
    _init_name = _init_city_cmd.split("|")[1].strip() if "|" in _init_city_cmd else _init_city_cmd
    dialog.city_edit = QLineEdit(_init_name)
    dialog.city_edit.setPlaceholderText("点击右侧按钮选择城市")
    dialog.city_edit.setReadOnly(True)
    dialog._city_code = _init_code
    _city_row.addWidget(dialog.city_edit)
    _city_pick_btn = QPushButton("选择城市"); _city_pick_btn.setCursor(Qt.PointingHandCursor)
    _city_pick_btn.setStyleSheet(f"background:{C['surface1']}; color:{C['text']}; border:none; border-radius:6px; padding:6px 12px; font-size:12px;")
    def _open_city_dlg():
        from fastpanel.dialogs.city import CitySelectDialog
        d = CitySelectDialog(getattr(dialog, '_city_code', ''), dialog)
        if d.exec_() == QDialog.Accepted:
            dialog._city_code = d.selected_code()
            dialog.city_edit.setText(d.selected_city())
    _city_pick_btn.clicked.connect(_open_city_dlg)
    _city_row.addWidget(_city_pick_btn)
    dialog._city_w = QWidget(); dialog._city_w.setLayout(_city_row)
    form.addRow("城  市", dialog._city_w)

    # --- Clock fields ---
    dialog._clock_sub_combo = QComboBox()
    for k, v in CLOCK_SUB_LABELS.items():
        dialog._clock_sub_combo.addItem(v, k)
    _style_combobox(dialog._clock_sub_combo)
    form.addRow("时钟类型", dialog._clock_sub_combo)

    from fastpanel.widgets.clock import _WORLD_TIMEZONES
    dialog._clock_world_combo = QComboBox()
    for name, tz_id, offset in _WORLD_TIMEZONES:
        sign = "+" if offset >= 0 else ""
        dialog._clock_world_combo.addItem(f"{name} (UTC{sign}{offset})", tz_id)
    _style_combobox(dialog._clock_world_combo)
    form.addRow("时  区", dialog._clock_world_combo)

    dialog._clock_date_fmt = QComboBox()
    for fmt, desc in [("%H:%M:%S", "24小时制 (14:30:00)"), ("%I:%M:%S %p", "12小时制 (02:30:00 PM)")]:
        dialog._clock_date_fmt.addItem(desc, fmt)
    _style_combobox(dialog._clock_date_fmt)
    form.addRow("时间格式", dialog._clock_date_fmt)

    def _on_clock_sub_changed(_=0):
        sub = dialog._clock_sub_combo.currentData()
        for w in dialog._clock_world_fields:
            if w: w.setVisible(sub == CLOCK_SUB_WORLD)
        for w in dialog._clock_fmt_fields:
            if w: w.setVisible(sub == CLOCK_SUB_CLOCK)

    dialog._clock_sub_combo.currentIndexChanged.connect(_on_clock_sub_changed)

    # --- Monitor fields ---
    dialog._monitor_sub_combo = QComboBox()
    for k, v in MONITOR_SUB_LABELS.items():
        dialog._monitor_sub_combo.addItem(v, k)
    _style_combobox(dialog._monitor_sub_combo)
    form.addRow("监控类型", dialog._monitor_sub_combo)

    if data and data.comp_type == TYPE_MONITOR:
        msub = data.cmd.strip() if data.cmd else MONITOR_SUB_ALL
        idx = list(MONITOR_SUB_LABELS.keys()).index(msub) if msub in MONITOR_SUB_LABELS else list(MONITOR_SUB_LABELS.keys()).index(MONITOR_SUB_ALL)
        dialog._monitor_sub_combo.setCurrentIndex(idx)

    # --- Launcher fields ---
    dialog._launcher_hint = QLabel("自动扫描系统已安装应用，提供搜索和快速启动")
    dialog._launcher_hint.setStyleSheet(f"color:{C['overlay0']}; font-size:12px;")
    form.addRow("", dialog._launcher_hint)

    # --- Note fields ---
    dialog._note_hint = QLabel("桌面便签，支持多种颜色，文字自动保存")
    dialog._note_hint.setStyleSheet(f"color:{C['overlay0']}; font-size:12px;")
    form.addRow("", dialog._note_hint)

    # --- QuickAction fields ---
    dialog._quickaction_hint = QLabel("系统快捷操作：锁屏、关机、重启、音量控制等")
    dialog._quickaction_hint.setStyleSheet(f"color:{C['overlay0']}; font-size:12px;")
    form.addRow("", dialog._quickaction_hint)

    if data and data.comp_type == TYPE_CLOCK:
        parts = data.cmd.split("|", 1)
        sub = parts[0] if parts else CLOCK_SUB_CLOCK
        param = parts[1] if len(parts) > 1 else ""
        idx = list(CLOCK_SUB_LABELS.keys()).index(sub) if sub in CLOCK_SUB_LABELS else 0
        dialog._clock_sub_combo.setCurrentIndex(idx)
        if sub == CLOCK_SUB_WORLD:
            for i in range(dialog._clock_world_combo.count()):
                if dialog._clock_world_combo.itemData(i) == param:
                    dialog._clock_world_combo.setCurrentIndex(i); break
        elif sub == CLOCK_SUB_CLOCK and param:
            for i in range(dialog._clock_date_fmt.count()):
                if dialog._clock_date_fmt.itemData(i) == param:
                    dialog._clock_date_fmt.setCurrentIndex(i); break

    lay.addLayout(form)
    lay.addStretch()

    btns = QHBoxLayout()
    btns.addStretch()
    cancel = QPushButton("取消")
    cancel.setObjectName("cancelBtn")
    cancel.setCursor(Qt.PointingHandCursor)
    cancel.clicked.connect(dialog.reject)
    btns.addWidget(cancel)
    ok = QPushButton(ok_text)
    ok.setObjectName("okBtn")
    ok.setCursor(Qt.PointingHandCursor)
    ok.clicked.connect(dialog._validate)
    btns.addWidget(ok)
    lay.addLayout(btns)

    _lbl = form.labelForField
    dialog._cmd_fields = [_lbl(dialog.cmd_edit), dialog.cmd_edit,
                          _lbl(dialog._hint), dialog._hint,
                          _lbl(dialog._param_container), dialog._param_container,
                          _lbl(dialog.output_chk), dialog.output_chk]
    dialog._cmdwin_fields = [_lbl(dialog._cmdwin_hint), dialog._cmdwin_hint,
                             _lbl(dialog.pre_cmd_edit), dialog.pre_cmd_edit]
    dialog._shortcut_fields = [_lbl(dialog._shortcut_import_btn), dialog._shortcut_import_btn,
                               _lbl(dialog.sub_type_combo), dialog.sub_type_combo,
                               _lbl(icon_w), dialog._icon_widget,
                               _lbl(path_w), dialog._path_widget]
    dialog._dock_fields = [_lbl(dialog._dock_hint), dialog._dock_hint]
    dialog._todo_fields = [_lbl(dialog._todo_hint), dialog._todo_hint]
    dialog._refresh_fields = [_lbl(dialog._refresh_spin), dialog._refresh_spin]
    dialog._cal_fields = [_lbl(dialog._cal_hint), dialog._cal_hint]
    dialog._weather_fields = [_lbl(dialog._weather_hint), dialog._weather_hint,
                              _lbl(dialog._city_w), dialog._city_w]
    dialog._clock_fields = [_lbl(dialog._clock_sub_combo), dialog._clock_sub_combo]
    dialog._clock_world_fields = [_lbl(dialog._clock_world_combo), dialog._clock_world_combo]
    dialog._clock_fmt_fields = [_lbl(dialog._clock_date_fmt), dialog._clock_date_fmt]
    dialog._monitor_fields = [_lbl(dialog._monitor_sub_combo), dialog._monitor_sub_combo]
    dialog._launcher_fields = [_lbl(dialog._launcher_hint), dialog._launcher_hint]
    dialog._note_fields = [_lbl(dialog._note_hint), dialog._note_hint]
    dialog._quickaction_fields = [_lbl(dialog._quickaction_hint), dialog._quickaction_hint]

    dialog._name_fields = [_lbl(dialog.name_edit), dialog.name_edit]
    _NO_NAME_TYPES = {TYPE_CALENDAR, TYPE_WEATHER, TYPE_DOCK, TYPE_TODO, TYPE_CLOCK, TYPE_MONITOR, TYPE_LAUNCHER, TYPE_QUICKACTION}

    def on_type_changed(_=0):
        t = dialog.cat.currentData()
        for w in dialog._name_fields:
            if w: w.setVisible(t not in _NO_NAME_TYPES)
        for w in dialog._cmd_fields:
            if w: w.setVisible(t == TYPE_CMD)
        for w in dialog._cmdwin_fields:
            if w: w.setVisible(t == TYPE_CMD_WINDOW)
        for w in dialog._shortcut_fields:
            if w: w.setVisible(t == TYPE_SHORTCUT)
        for w in dialog._dock_fields:
            if w: w.setVisible(t == TYPE_DOCK)
        for w in dialog._todo_fields:
            if w: w.setVisible(t == TYPE_TODO)
        for w in dialog._refresh_fields:
            if w: w.setVisible(t in (TYPE_CALENDAR, TYPE_WEATHER))
        for w in dialog._cal_fields:
            if w: w.setVisible(t == TYPE_CALENDAR)
        for w in dialog._weather_fields:
            if w: w.setVisible(t == TYPE_WEATHER)
        for w in dialog._clock_fields:
            if w: w.setVisible(t == TYPE_CLOCK)
        for w in dialog._clock_world_fields:
            if w: w.setVisible(t == TYPE_CLOCK and dialog._clock_sub_combo.currentData() == CLOCK_SUB_WORLD)
        for w in dialog._clock_fmt_fields:
            if w: w.setVisible(t == TYPE_CLOCK and dialog._clock_sub_combo.currentData() == CLOCK_SUB_CLOCK)
        for w in dialog._monitor_fields:
            if w: w.setVisible(t == TYPE_MONITOR)
        for w in dialog._launcher_fields:
            if w: w.setVisible(t == TYPE_LAUNCHER)
        for w in dialog._note_fields:
            if w: w.setVisible(t == TYPE_NOTE)
        for w in dialog._quickaction_fields:
            if w: w.setVisible(t == TYPE_QUICKACTION)
        dialog._update_param_hints()

    dialog.cat.currentIndexChanged.connect(on_type_changed)

    if data:
        idx = list(TYPE_LABELS.keys()).index(data.comp_type)
        dialog.cat.setCurrentIndex(idx)

    on_type_changed()


def _dlg_browse(dialog, edit, title, filt):
    from fastpanel.utils import _open_file
    p, _ = _open_file(dialog, title, os.path.expanduser("~"), filt)
    if p:
        edit.setText(p)


def _dlg_validate(dialog):
    t = dialog.cat.currentData()
    _no_name = {TYPE_CALENDAR, TYPE_WEATHER, TYPE_DOCK, TYPE_TODO, TYPE_CLOCK, TYPE_MONITOR, TYPE_LAUNCHER, TYPE_QUICKACTION}
    if t not in _no_name and not dialog.name_edit.text().strip():
        dialog.name_edit.setFocus(); return False
    if t == TYPE_CMD and not dialog.cmd_edit.text().strip():
        dialog.cmd_edit.setFocus(); return False
    if t == TYPE_SHORTCUT and not dialog.path_edit.text().strip():
        dialog.path_edit.setFocus(); return False
    return True


def _dlg_get_data(dialog):
    t = dialog.cat.currentData()
    st = dialog.sub_type_combo.currentData() if t == TYPE_SHORTCUT else SUB_APP
    hints = [e.text().strip() for e in dialog._param_hint_edits] if hasattr(dialog, '_param_hint_edits') else []
    defaults = [e.text().strip() for e in dialog._param_default_edits] if hasattr(dialog, '_param_default_edits') else []
    pre = dialog.pre_cmd_edit.toPlainText().strip() if t == TYPE_CMD_WINDOW else ""
    cmd = dialog.cmd_edit.text().strip()
    if t == TYPE_WEATHER:
        city_code = getattr(dialog, '_city_code', '')
        city_name = dialog.city_edit.text().strip()
        cmd = f"{city_code}|{city_name}" if city_code else city_name or "大连"
    elif t == TYPE_CLOCK:
        clock_sub = dialog._clock_sub_combo.currentData()
        if clock_sub == CLOCK_SUB_WORLD:
            cmd = f"{clock_sub}|{dialog._clock_world_combo.currentData()}"
        elif clock_sub == CLOCK_SUB_CLOCK:
            cmd = f"{clock_sub}|{dialog._clock_date_fmt.currentData()}"
        elif clock_sub == CLOCK_SUB_ALARM:
            existing = getattr(dialog, '_data', None)
            if existing and existing.cmd.startswith(CLOCK_SUB_ALARM + "|"):
                cmd = existing.cmd
            else:
                cmd = f"{clock_sub}|[]"
        else:
            cmd = clock_sub
    if t == TYPE_MONITOR:
        cmd = dialog._monitor_sub_combo.currentData()
    if t == TYPE_NOTE:
        existing = getattr(dialog, '_data', None)
        if existing and existing.comp_type == TYPE_NOTE:
            cmd = existing.cmd
        else:
            cmd = "0|"
    name = dialog.name_edit.text().strip()
    if not name:
        _defaults = {TYPE_CALENDAR: "日历", TYPE_WEATHER: "天气", TYPE_DOCK: "Dock栏", TYPE_TODO: "待办",
                     TYPE_CLOCK: "时钟", TYPE_MONITOR: "系统监控", TYPE_LAUNCHER: "应用启动器",
                     TYPE_NOTE: "便签", TYPE_QUICKACTION: "快捷操作"}
        name = _defaults.get(t, t)
    ri = dialog._refresh_spin.value() * 60 if t in (TYPE_CALENDAR, TYPE_WEATHER) else 300
    return ComponentData(
        name=name, comp_type=t, sub_type=st,
        cmd=cmd, show_output=dialog.output_chk.isChecked(),
        icon=dialog.icon_edit.text().strip(), path=dialog.path_edit.text().strip(),
        param_hints=hints, param_defaults=defaults, pre_cmd=pre, refresh_interval=ri,
    )


class CreateDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        _prepare_dialog(self)
        self.setWindowTitle("创建组件")
        self.setFixedWidth(440)
        _build_comp_dialog(self, "✦  创建新组件", "创  建")

    def _validate(self):
        if _dlg_validate(self):
            self.accept()

    def get_data(self):
        return _dlg_get_data(self)


class EditDialog(QDialog):
    def __init__(self, data: ComponentData, parent=None):
        super().__init__(parent)
        _prepare_dialog(self)
        self.setWindowTitle("修改组件")
        self.setFixedWidth(440)
        self._data = data
        _build_comp_dialog(self, "✎  修改组件", "保  存", data)

    def _validate(self):
        if _dlg_validate(self):
            self.accept()

    def get_data(self):
        return _dlg_get_data(self)


# ---------------------------------------------------------------------------
# Export Dialog
# ---------------------------------------------------------------------------

