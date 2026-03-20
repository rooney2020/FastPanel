import os
import platform
import socket
import subprocess
import datetime
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QFrame, QScrollArea
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QColor

from fastpanel.constants import GRID_SIZE
from fastpanel.settings import C, _settings
from fastpanel.theme import _comp_style, _bg, _scrollbar_style
from fastpanel.widgets.base import CompBase

try:
    import psutil
except ImportError:
    psutil = None

class SysInfoWidget(CompBase):
    def __init__(self, data, parent=None):
        super().__init__(data, parent)
        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self); lay.setContentsMargins(16, 12, 16, 12); lay.setSpacing(6)
        title = QLabel("💻 系统信息")
        title.setStyleSheet(f"color:{C['text']};font-size:14px;font-weight:bold;background:transparent;")
        lay.addWidget(title)
        import platform
        import socket
        info_items = []
        info_items.append(("主机名", socket.gethostname()))
        info_items.append(("用  户", os.environ.get("USER", "unknown")))
        info_items.append(("系  统", f"{platform.system()} {platform.release()}"))
        info_items.append(("发行版", platform.freedesktop_os_release().get("PRETTY_NAME", "N/A")
                           if hasattr(platform, 'freedesktop_os_release') else platform.platform()))
        info_items.append(("架  构", platform.machine()))
        info_items.append(("Python", platform.python_version()))
        try:
            info_items.append(("CPU", self._cpu_model()))
        except Exception:
            pass
        try:
            import psutil
            mem = psutil.virtual_memory()
            info_items.append(("内  存", f"{mem.total / (1024**3):.1f} GB"))
        except Exception:
            pass
        try:
            ips = self._get_ips()
            for name, ip in ips:
                info_items.append((name, ip))
        except Exception:
            pass
        try:
            info_items.append(("桌面环境", os.environ.get("XDG_CURRENT_DESKTOP", "N/A")))
            info_items.append(("显示协议", os.environ.get("XDG_SESSION_TYPE", "N/A")))
        except Exception:
            pass
        try:
            uptime = self._uptime()
            if uptime:
                info_items.append(("运行时间", uptime))
        except Exception:
            pass

        for label, value in info_items:
            row = QHBoxLayout(); row.setSpacing(8)
            lbl = QLabel(label)
            lbl.setStyleSheet(f"color:{C['subtext0']};font-size:11px;background:transparent;min-width:60px;")
            val = QLabel(str(value))
            val.setStyleSheet(f"color:{C['text']};font-size:11px;background:transparent;")
            val.setTextInteractionFlags(Qt.TextSelectableByMouse)
            row.addWidget(lbl); row.addWidget(val); row.addStretch()
            lay.addLayout(row)
        lay.addStretch()

    @staticmethod
    def _cpu_model():
        try:
            with open("/proc/cpuinfo") as f:
                for line in f:
                    if "model name" in line:
                        return line.split(":")[1].strip()
        except Exception:
            pass
        import platform
        return platform.processor() or "N/A"

    @staticmethod
    def _get_ips():
        result = []
        try:
            import psutil
            for name, addrs in psutil.net_if_addrs().items():
                if name == "lo":
                    continue
                for addr in addrs:
                    if addr.family == 2:
                        result.append((name, addr.address))
        except Exception:
            import socket
            result.append(("IP", socket.gethostbyname(socket.gethostname())))
        return result

    @staticmethod
    def _uptime():
        try:
            with open("/proc/uptime") as f:
                secs = float(f.read().split()[0])
            days = int(secs // 86400)
            hours = int((secs % 86400) // 3600)
            mins = int((secs % 3600) // 60)
            parts = []
            if days:
                parts.append(f"{days}天")
            parts.append(f"{hours}时{mins}分")
            return " ".join(parts)
        except Exception:
            return None


# ---------------------------------------------------------------------------
# Bookmark Manager Widget
# ---------------------------------------------------------------------------

