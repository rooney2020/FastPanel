import os
import subprocess
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QLineEdit, QScrollArea, QMenu, QSizePolicy, QGraphicsOpacityEffect,
    QDialog
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QThread, QPropertyAnimation, QEasingCurve
from PyQt5.QtGui import QFont, QColor, QPixmap, QPainter

from fastpanel.constants import GRID_SIZE, PARAM_PATTERN, SUB_APP, SUB_FILE, SUB_SCRIPT, TYPE_CMD, TYPE_CMD_WINDOW
from fastpanel.settings import C, _settings
from fastpanel.theme import _comp_style, _bg, _scrollbar_style, svg_icon
from fastpanel.platform.pty import PtyRunner, _ansi_to_html, _SGR_RE
from fastpanel.widgets.base import CompBase, _ExpandBtn, FullscreenOutputOverlay, _calc_fs_rect
from fastpanel.utils import count_params


def _send_desktop_notification(title, body):
    try:
        subprocess.Popen(
            ["notify-send", "-i", "terminal", title, body],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
    except Exception:
        pass


class _NotifyBtn(QPushButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(28, 28)
        self.setCursor(Qt.PointingHandCursor)
        self.setCheckable(True)
        self.setToolTip("命令完成时通知")
        self._update_style()
        self.toggled.connect(lambda: self._update_style())

    def _update_style(self):
        if self.isChecked():
            self.setStyleSheet(
                f"background:{C['yellow']}; border:none; border-radius:6px;")
            self.setIcon(svg_icon("bell", C['crust'], 16))
        else:
            self.setStyleSheet(
                f"background:{_bg('surface1')}; border:none; border-radius:6px;")
            self.setIcon(svg_icon("bell", C['subtext0'], 16))


class _WindowBtn(QPushButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(28, 28)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("窗口模式")
        self.setStyleSheet(
            f"background:{_bg('surface1')}; border:none; border-radius:6px;")
        self.setIcon(svg_icon("external-link", C['subtext0'], 16))


class _DetachedWindow(QDialog):
    """Detached window for CMD output with full session support."""
    run_toggled = pyqtSignal()
    closed = pyqtSignal()

    def __init__(self, title, comp_type=TYPE_CMD, parent=None):
        super().__init__(parent, Qt.Window | Qt.WindowMinMaxButtonsHint | Qt.WindowCloseButtonHint)
        self.setWindowTitle(title)
        self.resize(800, 500)
        self._start_label = "启动" if comp_type == TYPE_CMD_WINDOW else "执行"
        self._stop_label = "停止"

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 10)
        lay.setSpacing(6)

        h = QHBoxLayout()
        h.setSpacing(8)
        lbl = QLabel(title)
        lbl.setStyleSheet(f"color:{C['text']}; font-size:14px; font-weight:bold;")
        h.addWidget(lbl)
        h.addStretch()
        self._run_btn = QPushButton(f"▶  {self._start_label}")
        self._run_btn.setStyleSheet(
            f"background:{C['green']}; color:{C['crust']}; border:none; "
            f"border-radius:6px; padding:6px 14px; font-weight:bold; font-size:12px;")
        self._run_btn.setCursor(Qt.PointingHandCursor)
        self._run_btn.clicked.connect(self.run_toggled.emit)
        h.addWidget(self._run_btn)
        lay.addLayout(h)

        self._output = QTextEdit()
        self._output.setReadOnly(True)
        self._output.setStyleSheet(
            f"background:{C['crust']}; color:{C['green']}; border:1px solid {C['surface0']}; "
            f"border-radius:8px; font-family:'JetBrains Mono','Consolas',monospace; "
            f"font-size:12px; padding:8px;")
        lay.addWidget(self._output, 1)

        ir = QHBoxLayout()
        ir.setSpacing(6)
        self._stdin = QLineEdit()
        self._stdin.setPlaceholderText("输入内容（回车发送）…")
        self._stdin.setStyleSheet(
            f"background:{C['crust']}; color:{C['text']}; border:1px solid {C['surface0']}; "
            f"border-radius:6px; padding:6px 10px; "
            f"font-family:'JetBrains Mono','Consolas',monospace; font-size:12px;")
        ir.addWidget(self._stdin)
        self._send_btn = QPushButton("发送")
        self._send_btn.setStyleSheet(
            f"background:{C['sky']}; color:{C['crust']}; border:none; "
            f"border-radius:6px; font-size:12px; font-weight:bold; padding:6px 16px;")
        self._send_btn.setCursor(Qt.PointingHandCursor)
        ir.addWidget(self._send_btn)
        lay.addLayout(ir)

        self._write_fn = None
        self._connected = False

        pal = self.palette()
        pal.setColor(pal.Window, QColor(C['base']))
        self.setPalette(pal)

    def set_write_fn(self, fn):
        self._write_fn = fn
        if not self._connected:
            self._stdin.returnPressed.connect(self._do_send)
            self._send_btn.clicked.connect(self._do_send)
            self._connected = True

    def set_running(self, running):
        if running:
            self._run_btn.setText(f"■  {self._stop_label}")
            self._run_btn.setStyleSheet(
                f"background:{C['red']}; color:{C['crust']}; border:none; "
                f"border-radius:6px; padding:6px 14px; font-weight:bold; font-size:12px;")
        else:
            self._run_btn.setText(f"▶  {self._start_label}")
            self._run_btn.setStyleSheet(
                f"background:{C['green']}; color:{C['crust']}; border:none; "
                f"border-radius:6px; padding:6px 14px; font-weight:bold; font-size:12px;")

    def set_input_enabled(self, enabled):
        self._stdin.setEnabled(enabled)
        self._send_btn.setEnabled(enabled)

    def _do_send(self):
        if self._write_fn:
            self._write_fn(self._stdin.text())
            self._stdin.clear()

    def append_line(self, html):
        self._output.append(html)

    def sync_content(self, source: QTextEdit):
        self._output.setHtml(source.toHtml())
        sb = self._output.verticalScrollBar()
        sb.setValue(sb.maximum())

    def closeEvent(self, e):
        self.closed.emit()
        super().closeEvent(e)

class CmdWidget(CompBase):
    def __init__(self, data, parent=None):
        super().__init__(data, parent)
        self._runner = None
        self._param_inputs = []
        self._fs_dlg = None
        self._win_dlg = None
        self._notify = False
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 6, 10, 6); root.setSpacing(4)

        h = QHBoxLayout(); h.setSpacing(6)
        badge = QLabel("CMD"); badge.setObjectName("badge"); badge.setFixedHeight(22); badge.setAlignment(Qt.AlignCenter)
        h.addWidget(badge)
        self._title = QLabel(self.data.name); self._title.setObjectName("title")
        self._title.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._title.setToolTip(self.data.name)
        self._title.setMinimumWidth(0)
        h.addWidget(self._title)
        cmd_q = QLabel("?"); cmd_q.setFixedSize(18, 18); cmd_q.setAlignment(Qt.AlignCenter)
        cmd_q.setStyleSheet(f"background:{_bg('surface1')}; color:{C['subtext0']}; border-radius:9px; font-size:11px; font-weight:bold;")
        cmd_q.setToolTip(self.data.cmd)
        h.addWidget(cmd_q)
        if self.data.show_output:
            self._notify_btn = _NotifyBtn()
            self._notify_btn.toggled.connect(lambda c: setattr(self, '_notify', c))
            h.addWidget(self._notify_btn)
            win_btn = _WindowBtn()
            win_btn.clicked.connect(self._open_window); h.addWidget(win_btn)
            fs = _ExpandBtn()
            fs.clicked.connect(self._open_fullscreen); h.addWidget(fs)
        self._run_btn = QPushButton("▶  执行"); self._run_btn.setObjectName("runBtn")
        self._run_btn.setCursor(Qt.PointingHandCursor); self._run_btn.setFixedHeight(28)
        self._run_btn.clicked.connect(self._toggle); h.addWidget(self._run_btn)
        root.addLayout(h)

        for i in range(count_params(self.data.cmd)):
            row = QHBoxLayout(); row.setSpacing(4)
            inp = QLineEdit(); inp.setObjectName("paramInput")
            hint = self.data.param_hints[i] if i < len(self.data.param_hints) and self.data.param_hints[i] else ""
            inp.setPlaceholderText(hint or f"参数 {i+1}")
            default = self.data.param_defaults[i] if i < len(self.data.param_defaults) and self.data.param_defaults[i] else ""
            if default:
                inp.setText(default)
            row.addWidget(inp); self._param_inputs.append(inp)
            if hint:
                q = QLabel("?"); q.setFixedSize(18, 18); q.setAlignment(Qt.AlignCenter)
                q.setStyleSheet(f"background:{_bg('surface1')}; color:{C['subtext0']}; border-radius:9px; font-size:11px; font-weight:bold;")
                q.setToolTip(hint)
                row.addWidget(q)
            root.addLayout(row)

        if self.data.show_output:
            self._output = QTextEdit(); self._output.setObjectName("output")
            self._output.setReadOnly(True); self._output.setPlaceholderText("点击「执行」查看输出…")
            root.addWidget(self._output, 1)
            ir = QHBoxLayout(); ir.setSpacing(6)
            self._stdin = QLineEdit(); self._stdin.setObjectName("stdinInput")
            self._stdin.setPlaceholderText("输入内容（回车发送）…"); self._stdin.setEnabled(False)
            self._stdin.returnPressed.connect(self._send); ir.addWidget(self._stdin)
            self._send_btn = QPushButton("发送"); self._send_btn.setObjectName("sendBtn")
            self._send_btn.setFixedWidth(52); self._send_btn.setEnabled(False)
            self._send_btn.setCursor(Qt.PointingHandCursor); self._send_btn.clicked.connect(self._send)
            ir.addWidget(self._send_btn); root.addLayout(ir)
        else:
            self._output = None; self._stdin = None; self._send_btn = None
            root.addStretch()

    def _build_cmd(self):
        cmd = self.data.cmd
        for inp in self._param_inputs:
            cmd = PARAM_PATTERN.sub(inp.text(), cmd, count=1)
        return cmd

    def _send(self):
        if self._runner and self._stdin:
            self._runner.write_stdin(self._stdin.text()); self._stdin.clear()

    def _toggle(self):
        if self._runner and self._runner.isRunning(): self._runner.stop()
        else: self._execute()

    def _execute(self):
        self._run_btn.setText("■  停止"); self._run_btn.setProperty("running", True)
        self._run_btn.style().unpolish(self._run_btn); self._run_btn.style().polish(self._run_btn)
        if self._output: self._output.clear()
        if self._stdin: self._stdin.setEnabled(True)
        if self._send_btn: self._send_btn.setEnabled(True)
        self._runner = PtyRunner(self._build_cmd())
        self._runner.line_ready.connect(self._on_line); self._runner.done.connect(self._on_done)
        self._runner.start()
        if self._fs_dlg:
            self._fs_dlg.set_write_fn(self._runner.write_stdin)
            self._fs_dlg.set_input_enabled(True)
            self._fs_dlg.set_running(True)
        if self._win_dlg:
            self._win_dlg.set_write_fn(self._runner.write_stdin)
            self._win_dlg.set_input_enabled(True)
            self._win_dlg.set_running(True)

    def _open_window(self):
        if not self._win_dlg:
            self._win_dlg = _DetachedWindow(self.data.name, TYPE_CMD)
            self._win_dlg.run_toggled.connect(self._toggle)
            self._win_dlg.closed.connect(self._on_win_closed)
        running = self._runner and self._runner.isRunning()
        if running:
            self._win_dlg.set_write_fn(self._runner.write_stdin)
            self._win_dlg.set_input_enabled(True)
        else:
            self._win_dlg.set_write_fn(None)
            self._win_dlg.set_input_enabled(False)
        self._win_dlg.set_running(running)
        if self._output:
            self._win_dlg.sync_content(self._output)
        self._win_dlg.show()
        self._win_dlg.raise_()
        self._win_dlg.activateWindow()

    def _on_win_closed(self):
        self._win_dlg = None

    def _open_fullscreen(self):
        grid = self.parentWidget()
        if not grid:
            return
        if not self._fs_dlg:
            self._fs_dlg = FullscreenOutputOverlay(self.data.name, TYPE_CMD, grid)
            self._fs_dlg.run_toggled.connect(self._toggle)
            self._fs_dlg.closed.connect(self._on_fs_closed)
        running = self._runner and self._runner.isRunning()
        if running:
            self._fs_dlg.set_write_fn(self._runner.write_stdin)
            self._fs_dlg.set_input_enabled(True)
        else:
            self._fs_dlg.set_write_fn(None)
            self._fs_dlg.set_input_enabled(False)
        self._fs_dlg.set_running(running)
        if self._output:
            self._fs_dlg.sync_content(self._output)
        self._fs_dlg.setGeometry(_calc_fs_rect(self))
        self._fs_dlg.raise_()
        self._fs_dlg.show()

    def _on_fs_closed(self):
        self._fs_dlg = None

    def _on_line(self, t):
        plain = _SGR_RE.sub("", t)
        if self._output: self._output.append(plain)
        if self._fs_dlg: self._fs_dlg.append_line(plain)
        if self._win_dlg: self._win_dlg.append_line(plain)

    def _on_done(self, code):
        self._run_btn.setProperty("running", False)
        self._run_btn.style().unpolish(self._run_btn)
        self._run_btn.style().polish(self._run_btn)
        if self._stdin:
            self._stdin.setEnabled(False)
        if self._send_btn:
            self._send_btn.setEnabled(False)
        if self._fs_dlg:
            self._fs_dlg.set_input_enabled(False)
            self._fs_dlg.set_running(False)
        if self._win_dlg:
            self._win_dlg.set_input_enabled(False)
            self._win_dlg.set_running(False)
        if self._notify and code != -15:
            status = "成功" if code == 0 else f"失败（退出码 {code}）"
            _send_desktop_notification(f"CMD: {self.data.name}", f"执行{status}")
        if self._output:
            if code == -15:
                msg, c = "--- 已停止 ---", C['peach']
            else:
                msg, c = f"--- 退出码 {code} ---", C['green'] if code == 0 else C['red']
            html = f'<span style="color:{c}; font-weight:bold;">{msg}</span>'
            self._output.append(html)
            if self._fs_dlg: self._fs_dlg.append_line(html)
            if self._win_dlg: self._win_dlg.append_line(html)
            self._run_btn.setText("▶  执行")
        else:
            if code == -15:
                self._run_btn.setText("⏹ 已停止")
                self._run_btn.setStyleSheet(f"background:{_bg('surface1')}; color:{C['text']}; border:none; border-radius:6px; padding:0 14px; font-weight:bold; font-size:12px;")
            elif code == 0:
                self._run_btn.setText("✓ 完成")
                self._run_btn.setStyleSheet(f"background:{_bg('surface0')}; color:{C['green']}; border:none; border-radius:6px; padding:0 14px; font-weight:bold; font-size:12px;")
            else:
                self._run_btn.setText(f"✗ 失败({code})")
                self._run_btn.setStyleSheet(f"background:{_bg('surface0')}; color:{C['red']}; border:none; border-radius:6px; padding:0 14px; font-weight:bold; font-size:12px;")
            QTimer.singleShot(2000, self._reset_btn)

    def _reset_btn(self):
        self._run_btn.setText("▶  执行")
        self._run_btn.setStyleSheet("")
        self._run_btn.style().unpolish(self._run_btn)
        self._run_btn.style().polish(self._run_btn)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        fm = self._title.fontMetrics()
        elided = fm.elidedText(self.data.name, Qt.ElideRight, self._title.width())
        self._title.setText(elided)

    def update_from_data(self):
        self._title.setText(self.data.name)
        self._title.setToolTip(self.data.name)


# ---------------------------------------------------------------------------
# CMD Window Component
# ---------------------------------------------------------------------------
class CmdWindowWidget(CompBase):
    def __init__(self, data, parent=None):
        super().__init__(data, parent)
        self._runner = None
        self._fs_dlg = None
        self._win_dlg = None
        self._notify = False
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14,10,14,14); root.setSpacing(8)

        h = QHBoxLayout(); h.setSpacing(8)
        badge = QLabel("CMD窗口"); badge.setObjectName("badgeCmdWin"); badge.setFixedHeight(22); badge.setAlignment(Qt.AlignCenter)
        h.addWidget(badge)
        self._title = QLabel(self.data.name); self._title.setObjectName("title")
        self._title.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred); h.addWidget(self._title)
        exp_btn = QPushButton(); exp_btn.setFixedSize(28, 28); exp_btn.setCursor(Qt.PointingHandCursor)
        exp_btn.setIcon(svg_icon("clipboard", C['text'], 16))
        exp_btn.setToolTip("导出日志"); exp_btn.setStyleSheet(f"background:{_bg('surface1')}; color:{C['text']}; border:none; border-radius:6px; font-size:14px;")
        exp_btn.clicked.connect(self._export_log); h.addWidget(exp_btn)
        self._notify_btn = _NotifyBtn()
        self._notify_btn.toggled.connect(lambda c: setattr(self, '_notify', c))
        h.addWidget(self._notify_btn)
        win_btn = _WindowBtn()
        win_btn.clicked.connect(self._open_window); h.addWidget(win_btn)
        fs = _ExpandBtn()
        fs.clicked.connect(self._open_fullscreen); h.addWidget(fs)
        self._run_btn = QPushButton("▶  启动"); self._run_btn.setObjectName("runBtn")
        self._run_btn.setCursor(Qt.PointingHandCursor); self._run_btn.setFixedHeight(28)
        self._run_btn.clicked.connect(self._toggle); h.addWidget(self._run_btn)
        root.addLayout(h)

        self._output = QTextEdit(); self._output.setObjectName("output")
        self._output.setReadOnly(True); self._output.setPlaceholderText("启动后可在下方输入命令…")
        root.addWidget(self._output, 1)

        ir = QHBoxLayout(); ir.setSpacing(6)
        self._stdin = QLineEdit(); self._stdin.setObjectName("stdinInput")
        self._stdin.setPlaceholderText("输入命令（回车执行）…"); self._stdin.setEnabled(False)
        self._stdin.returnPressed.connect(self._send); ir.addWidget(self._stdin)
        self._send_btn = QPushButton("发送"); self._send_btn.setObjectName("sendBtn")
        self._send_btn.setFixedWidth(52); self._send_btn.setEnabled(False)
        self._send_btn.setCursor(Qt.PointingHandCursor); self._send_btn.clicked.connect(self._send)
        ir.addWidget(self._send_btn); root.addLayout(ir)

    def _send(self):
        if self._runner:
            self._runner.write_stdin(self._stdin.text()); self._stdin.clear()

    def _toggle(self):
        if self._runner and self._runner.isRunning(): self._runner.stop()
        else: self._start()

    def _start(self):
        self._run_btn.setText("■  停止"); self._run_btn.setProperty("running", True)
        self._run_btn.style().unpolish(self._run_btn); self._run_btn.style().polish(self._run_btn)
        self._output.clear(); self._stdin.setEnabled(True); self._send_btn.setEnabled(True)
        self._runner = PtyRunner("/bin/bash")
        self._runner.line_ready.connect(self._on_line); self._runner.done.connect(self._on_done)
        self._runner.start()
        if self._fs_dlg:
            self._fs_dlg.set_write_fn(self._runner.write_stdin)
            self._fs_dlg.set_input_enabled(True)
            self._fs_dlg.set_running(True)
        if self._win_dlg:
            self._win_dlg.set_write_fn(self._runner.write_stdin)
            self._win_dlg.set_input_enabled(True)
            self._win_dlg.set_running(True)
        if self.data.pre_cmd:
            lines = [l for l in self.data.pre_cmd.splitlines() if l.strip()]
            if lines:
                QTimer.singleShot(200, lambda: self._send_pre_cmds(lines, 0))

    def _send_pre_cmds(self, lines, idx):
        if idx < len(lines) and self._runner and self._runner.isRunning():
            self._runner.write_stdin(lines[idx])
            QTimer.singleShot(100, lambda: self._send_pre_cmds(lines, idx + 1))

    def _open_window(self):
        if not self._win_dlg:
            self._win_dlg = _DetachedWindow(self.data.name, TYPE_CMD_WINDOW)
            self._win_dlg.run_toggled.connect(self._toggle)
            self._win_dlg.closed.connect(self._on_win_closed)
        running = self._runner and self._runner.isRunning()
        if running:
            self._win_dlg.set_write_fn(self._runner.write_stdin)
            self._win_dlg.set_input_enabled(True)
        else:
            self._win_dlg.set_write_fn(None)
            self._win_dlg.set_input_enabled(False)
        self._win_dlg.set_running(running)
        self._win_dlg.sync_content(self._output)
        self._win_dlg.show()
        self._win_dlg.raise_()
        self._win_dlg.activateWindow()

    def _on_win_closed(self):
        self._win_dlg = None

    def _open_fullscreen(self):
        grid = self.parentWidget()
        if not grid:
            return
        if not self._fs_dlg:
            self._fs_dlg = FullscreenOutputOverlay(self.data.name, TYPE_CMD_WINDOW, grid)
            self._fs_dlg.run_toggled.connect(self._toggle)
            self._fs_dlg.closed.connect(self._on_fs_closed)
        running = self._runner and self._runner.isRunning()
        if running:
            self._fs_dlg.set_write_fn(self._runner.write_stdin)
            self._fs_dlg.set_input_enabled(True)
        else:
            self._fs_dlg.set_write_fn(None)
            self._fs_dlg.set_input_enabled(False)
        self._fs_dlg.set_running(running)
        self._fs_dlg.sync_content(self._output)
        self._fs_dlg.setGeometry(_calc_fs_rect(self))
        self._fs_dlg.raise_()
        self._fs_dlg.show()

    def _on_fs_closed(self):
        self._fs_dlg = None

    def _on_line(self, t):
        html = _ansi_to_html(t)
        self._output.append(html)
        if self._fs_dlg: self._fs_dlg.append_line(html)
        if self._win_dlg: self._win_dlg.append_line(html)

    def _on_done(self, code):
        self._run_btn.setText("▶  启动"); self._run_btn.setProperty("running", False)
        self._run_btn.style().unpolish(self._run_btn); self._run_btn.style().polish(self._run_btn)
        self._stdin.setEnabled(False); self._send_btn.setEnabled(False)
        if self._fs_dlg:
            self._fs_dlg.set_input_enabled(False)
            self._fs_dlg.set_running(False)
        if self._win_dlg:
            self._win_dlg.set_input_enabled(False)
            self._win_dlg.set_running(False)
        if self._notify and code != -15:
            _send_desktop_notification(f"CMD窗口: {self.data.name}", "会话已结束")
        c = C['peach'] if code == -15 else C['overlay0']
        html = f'<span style="color:{c}; font-weight:bold;">--- 会话结束 ---</span>'
        self._output.append(html)
        if self._fs_dlg: self._fs_dlg.append_line(html)
        if self._win_dlg: self._win_dlg.append_line(html)

    def _export_log(self):
        text = self._output.toPlainText()
        if not text.strip():
            return
        from fastpanel.utils import _save_file
        f, _ = _save_file(self, "导出日志", f"{self.data.name}_log.txt", "文本文件 (*.txt);;所有文件 (*)")
        if f:
            try:
                with open(f, "w", encoding="utf-8") as fp:
                    fp.write(text)
            except Exception:
                pass

    def update_from_data(self):
        self._title.setText(self.data.name)


# ---------------------------------------------------------------------------
# Shortcut Component
# ---------------------------------------------------------------------------
class _LaunchThread(QThread):
    finished = pyqtSignal(bool, str)

    def __init__(self, path, sub_type):
        super().__init__()
        self._path = path
        self._sub_type = sub_type

    def run(self):
        try:
            if self._sub_type == SUB_SCRIPT:
                sh = "bash" if self._path.endswith(".sh") else "python3" if self._path.endswith(".py") else "bash"
                proc = subprocess.Popen([sh, self._path], start_new_session=True,
                                        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
                _, err = proc.communicate(timeout=30)
                ok = proc.returncode == 0
                msg = "" if ok else err.decode("utf-8", errors="replace")[:200]
            elif self._sub_type == SUB_APP:
                subprocess.Popen([self._path], start_new_session=True,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                ok, msg = True, ""
            else:
                subprocess.Popen(["xdg-open", self._path], start_new_session=True,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                ok, msg = True, ""
            self.finished.emit(ok, msg)
        except Exception as e:
            self.finished.emit(False, str(e))


class ShortcutWidget(CompBase):
    def __init__(self, data, parent=None):
        super().__init__(data, parent)
        self._thread = None
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 2)
        root.setSpacing(2)

        self._icon_lbl = QLabel()
        self._icon_lbl.setAlignment(Qt.AlignCenter)
        self._icon_lbl.setStyleSheet("background: transparent; border: none;")
        self._icon_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._has_pixmap = False
        if self.data.icon and os.path.isfile(self.data.icon):
            self._orig_pm = QPixmap(self.data.icon)
            self._has_pixmap = True
        else:
            _sub_svg = {SUB_APP: "monitor", SUB_SCRIPT: "terminal", SUB_FILE: "file"}
            _svg_name = _sub_svg.get(self.data.sub_type, "link")
            from fastpanel.theme import svg_pixmap as _sp
            _pm = _sp(_svg_name, C['text'], 28)
            if not _pm.isNull():
                self._icon_lbl.setPixmap(_pm)
            else:
                self._icon_lbl.setText(_svg_name[:2])
            self._icon_lbl.setStyleSheet("background: transparent; border: none;")
            self._orig_pm = None
        root.addWidget(self._icon_lbl, 1)

        self._title = QLabel(self.data.name)
        self._title.setAlignment(Qt.AlignCenter)
        self._title.setWordWrap(True)
        self._title.setFixedHeight(18)
        self._title.setStyleSheet(f"color:{C['text']}; font-size:11px; background:transparent; border:none;")
        root.addWidget(self._title)

        self._hover_overlay = QWidget(self)
        self._hover_overlay.setStyleSheet("background: rgba(0,0,0,120); border-radius: 12px;")
        hover_lay = QVBoxLayout(self._hover_overlay)
        hover_lay.setAlignment(Qt.AlignCenter)
        btn_text = "▶ 打开" if self.data.sub_type == SUB_FILE else "▶ 启动"
        self._launch_btn = QPushButton(btn_text)
        self._launch_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C['green']}; color: {C['crust']};
                border: none; border-radius: 6px;
                font-size: 11px; font-weight: bold; padding: 4px 8px;
            }}
            QPushButton:hover {{ background: #b5e8b0; }}
        """)
        self._launch_btn.setCursor(Qt.PointingHandCursor)
        hover_lay.addWidget(self._launch_btn)
        self._launch_btn.clicked.connect(self._launch)
        self._hover_overlay.hide()

        self._result_overlay = QLabel(self)
        self._result_overlay.setAlignment(Qt.AlignCenter)
        self._result_overlay.hide()

        self._result_effect = QGraphicsOpacityEffect(self._result_overlay)
        self._result_overlay.setGraphicsEffect(self._result_effect)
        self._result_effect.setOpacity(1.0)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self._has_pixmap and self._orig_pm:
            avail = self._icon_lbl.size()
            s = min(avail.width(), avail.height(), 64)
            if s > 4:
                self._icon_lbl.setPixmap(
                    self._orig_pm.scaled(s, s, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self._hover_overlay.setGeometry(0, 0, self.width(), self.height())
        self._result_overlay.setGeometry(0, 0, self.width(), self.height())

    def enterEvent(self, e):
        super().enterEvent(e)
        if not (self._thread and self._thread.isRunning()):
            self._hover_overlay.show()
            self._hover_overlay.raise_()

    def leaveEvent(self, e):
        super().leaveEvent(e)
        self._hover_overlay.hide()

    def _launch(self):
        path = self.data.path
        if not path or (self._thread and self._thread.isRunning()):
            return
        self._hover_overlay.hide()
        self._thread = _LaunchThread(path, self.data.sub_type)
        self._thread.finished.connect(self._on_launch_done)
        self._thread.start()

    def _on_launch_done(self, ok, msg):
        if ok:
            self._show_result("✓ 已启动", C['green'])
        else:
            tip = msg[:30] if msg else "启动失败"
            self._show_result(f"✗ {tip}", C['red'])

    def _show_result(self, text, color):
        self._result_overlay.setText(text)
        self._result_overlay.setStyleSheet(
            f"background: rgba(0,0,0,140); color: {color}; font-size: 12px; "
            f"font-weight: bold; border-radius: 12px;")
        self._result_overlay.setGeometry(0, 0, self.width(), self.height())
        self._result_overlay.show()
        self._result_overlay.raise_()
        self._result_effect.setOpacity(1.0)

        anim = QPropertyAnimation(self._result_effect, b"opacity", self)
        anim.setDuration(1500)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.setEasingCurve(QEasingCurve.InQuad)
        anim.finished.connect(self._result_overlay.hide)
        anim.start()
        self._anim = anim

    def update_from_data(self):
        self._title.setText(self.data.name)


# ---------------------------------------------------------------------------
# Calendar Component
# ---------------------------------------------------------------------------

