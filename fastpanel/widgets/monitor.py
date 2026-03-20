import time
import subprocess
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel
)
from PyQt5.QtCore import Qt, QTimer, QPointF, QPoint, QRect
from PyQt5.QtGui import QFont, QColor, QPainter, QPen, QPolygonF

from fastpanel.constants import GRID_SIZE, MONITOR_SUB_ALL, MONITOR_SUB_CPU, MONITOR_SUB_MEM, MONITOR_SUB_DISK, MONITOR_SUB_NET, MONITOR_SUB_LABELS
from fastpanel.settings import C, _settings
from fastpanel.theme import _comp_style, _bg
from fastpanel.widgets.base import CompBase

try:
    import psutil
except ImportError:
    psutil = None

class MonitorWidget(CompBase):
    def __init__(self, data, parent=None):
        super().__init__(data, parent)
        self._parse_monitor_cmd()
        self._history_len = 60
        self._cpu_history = [0.0] * self._history_len
        self._net_sent_history = [0.0] * self._history_len
        self._net_recv_history = [0.0] * self._history_len
        self._mem_history = [0.0] * self._history_len
        self._prev_net = None
        self._build()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(1500)
        self._tick()

    def refresh_theme(self):
        cpu_h = list(self._cpu_history)
        mem_h = list(self._mem_history)
        net_s = list(self._net_sent_history)
        net_r = list(self._net_recv_history)
        prev = self._prev_net
        super().refresh_theme()
        self._cpu_history = cpu_h
        self._mem_history = mem_h
        self._net_sent_history = net_s
        self._net_recv_history = net_r
        self._prev_net = prev
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(1500)

    def _parse_monitor_cmd(self):
        raw = self.data.cmd.strip()
        self._monitor_sub = raw if raw in MONITOR_SUB_LABELS else MONITOR_SUB_ALL

    def _build(self):
        self._canvas = QWidget(self)
        self._canvas.setAttribute(Qt.WA_TransparentForMouseEvents)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._canvas)

    _shared_cpu_val = 0.0
    _shared_cpu_ts = 0.0

    @classmethod
    def _get_shared_cpu(cls):
        import time, psutil
        now = time.monotonic()
        if now - cls._shared_cpu_ts > 0.5:
            cls._shared_cpu_val = psutil.cpu_percent(interval=0)
            cls._shared_cpu_ts = now
        return cls._shared_cpu_val

    def _tick(self):
        try:
            import psutil
            self._cpu_history.append(self._get_shared_cpu())
            self._cpu_history = self._cpu_history[-self._history_len:]
            mem = psutil.virtual_memory()
            self._mem_percent = mem.percent
            self._mem_used = mem.used
            self._mem_total = mem.total
            self._mem_history.append(mem.percent)
            self._mem_history = self._mem_history[-self._history_len:]
            parts = psutil.disk_partitions()
            self._disks = []
            seen = set()
            for p in parts:
                if p.mountpoint in seen:
                    continue
                seen.add(p.mountpoint)
                try:
                    u = psutil.disk_usage(p.mountpoint)
                    self._disks.append((p.mountpoint, u.used, u.total, u.percent))
                except Exception:
                    pass
            net = psutil.net_io_counters()
            if self._prev_net:
                dt = 1.5
                sent_speed = (net.bytes_sent - self._prev_net.bytes_sent) / dt
                recv_speed = (net.bytes_recv - self._prev_net.bytes_recv) / dt
            else:
                sent_speed = recv_speed = 0.0
            self._prev_net = net
            self._net_sent_history.append(sent_speed)
            self._net_recv_history.append(recv_speed)
            self._net_sent_history = self._net_sent_history[-self._history_len:]
            self._net_recv_history = self._net_recv_history[-self._history_len:]
            self._net_sent_speed = sent_speed
            self._net_recv_speed = recv_speed
        except Exception:
            pass
        self._canvas.update()

    def _fmt_bytes(self, b):
        for u in ['B', 'KB', 'MB', 'GB', 'TB']:
            if b < 1024:
                return f"{b:.1f}{u}"
            b /= 1024
        return f"{b:.1f}PB"

    def _fmt_speed(self, bps):
        for u in ['B/s', 'KB/s', 'MB/s', 'GB/s']:
            if bps < 1024:
                return f"{bps:.1f}{u}"
            bps /= 1024
        return f"{bps:.1f}TB/s"

    def paintEvent(self, e):
        super().paintEvent(e)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        sub = self._monitor_sub
        rect = self._canvas.geometry()
        pad = 12
        area = QRect(rect.x() + pad, rect.y() + pad, rect.width() - pad * 2, rect.height() - pad * 2)
        if sub == MONITOR_SUB_CPU:
            self._paint_cpu(p, area)
        elif sub == MONITOR_SUB_MEM:
            self._paint_mem(p, area)
        elif sub == MONITOR_SUB_DISK:
            self._paint_disk(p, area)
        elif sub == MONITOR_SUB_NET:
            self._paint_net(p, area)
        else:
            self._paint_all(p, area)
        p.end()

    def _draw_line_chart(self, p, rect, data, color, max_val=100.0, label="", cur_text=""):
        bg = QColor(C['surface0'])
        bg.setAlpha(60)
        p.setBrush(bg)
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(rect, 8, 8)

        if label:
            p.setPen(QColor(C['subtext0']))
            p.setFont(QFont("JetBrains Mono", 9))
            p.drawText(rect.adjusted(8, 4, 0, 0), Qt.AlignLeft | Qt.AlignTop, label)
        if cur_text:
            p.setPen(QColor(C['text']))
            p.setFont(QFont("JetBrains Mono", 10, QFont.Bold))
            p.drawText(rect.adjusted(0, 4, -8, 0), Qt.AlignRight | Qt.AlignTop, cur_text)

        chart_rect = QRect(rect.x() + 8, rect.y() + 24, rect.width() - 16, rect.height() - 32)
        if chart_rect.height() < 10 or chart_rect.width() < 10:
            return

        line_color = QColor(color)
        fill_color = QColor(color)
        fill_color.setAlpha(40)

        n = len(data)
        if n < 2 or max_val <= 0:
            return
        dx = chart_rect.width() / (n - 1) if n > 1 else 0

        points = []
        for i, v in enumerate(data):
            x = chart_rect.x() + i * dx
            ratio = min(v / max_val, 1.0)
            y = chart_rect.bottom() - ratio * chart_rect.height()
            points.append(QPoint(int(x), int(y)))

        from PyQt5.QtGui import QPolygonF, QPainterPath, QLinearGradient
        from PyQt5.QtCore import QPointF
        path = QPainterPath()
        path.moveTo(QPointF(points[0].x(), chart_rect.bottom()))
        for pt in points:
            path.lineTo(QPointF(pt.x(), pt.y()))
        path.lineTo(QPointF(points[-1].x(), chart_rect.bottom()))
        path.closeSubpath()

        grad = QLinearGradient(0, chart_rect.top(), 0, chart_rect.bottom())
        grad.setColorAt(0, fill_color)
        fc2 = QColor(color)
        fc2.setAlpha(5)
        grad.setColorAt(1, fc2)
        p.setBrush(grad)
        p.setPen(Qt.NoPen)
        p.drawPath(path)

        pen = QPen(line_color, 2)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        for i in range(len(points) - 1):
            p.drawLine(points[i], points[i + 1])

    def _paint_cpu(self, p, area):
        cur = self._cpu_history[-1] if self._cpu_history else 0
        self._draw_line_chart(p, area, self._cpu_history, C['green'],
                              max_val=100.0, label="CPU", cur_text=f"{cur:.0f}%")

    def _draw_ring(self, p, rect, percent, color, label="", detail=""):
        cx = rect.center().x()
        cy = rect.y() + min(rect.width(), rect.height() - 30) // 2 + 4
        radius = min(rect.width(), rect.height() - 30) // 2 - 8
        if radius < 15:
            return

        ring_w = max(8, radius // 4)
        ring_rect = QRect(cx - radius, cy - radius, radius * 2, radius * 2)

        track_color = QColor(C['surface1'])
        p.setPen(QPen(track_color, ring_w, Qt.SolidLine, Qt.RoundCap))
        p.setBrush(Qt.NoBrush)
        p.drawArc(ring_rect, 0, 360 * 16)

        arc_color = QColor(color)
        p.setPen(QPen(arc_color, ring_w, Qt.SolidLine, Qt.RoundCap))
        span = int(-percent / 100.0 * 360 * 16)
        p.drawArc(ring_rect, 90 * 16, span)

        p.setPen(QColor(C['text']))
        p.setFont(QFont("JetBrains Mono", max(10, radius // 3), QFont.Bold))
        p.drawText(ring_rect, Qt.AlignCenter, f"{percent:.0f}%")

        if detail:
            p.setPen(QColor(C['subtext0']))
            p.setFont(QFont("JetBrains Mono", 8))
            text_y = cy + radius + ring_w // 2 + 4
            p.drawText(QRect(rect.x(), text_y, rect.width(), 20), Qt.AlignCenter, detail)
        if label:
            p.setPen(QColor(C['subtext0']))
            p.setFont(QFont("JetBrains Mono", 9))
            p.drawText(QRect(rect.x(), rect.y(), rect.width(), 18), Qt.AlignCenter, label)

    def _paint_mem(self, p, area):
        pct = getattr(self, '_mem_percent', 0)
        used = getattr(self, '_mem_used', 0)
        total = getattr(self, '_mem_total', 1)
        detail = f"{self._fmt_bytes(used)} / {self._fmt_bytes(total)}"
        self._draw_ring(p, area, pct, C['blue'], label="内存", detail=detail)

    def _paint_disk(self, p, area):
        disks = getattr(self, '_disks', [])
        if not disks:
            p.setPen(QColor(C['subtext0']))
            p.setFont(QFont("JetBrains Mono", 10))
            p.drawText(area, Qt.AlignCenter, "无磁盘信息")
            return

        p.setPen(QColor(C['subtext0']))
        p.setFont(QFont("JetBrains Mono", 9))
        p.drawText(QRect(area.x(), area.y(), area.width(), 18), Qt.AlignLeft, "磁盘")

        bar_h = max(14, min(22, (area.height() - 24) // max(len(disks), 1) - 8))
        colors = [C['teal'], C['peach'], C['blue'], C['green'], C['mauve'], C['yellow']]
        y = area.y() + 24

        for i, (mount, used, total, pct) in enumerate(disks[:6]):
            color = colors[i % len(colors)]
            name = mount if len(mount) <= 12 else "…" + mount[-11:]
            detail = f"{self._fmt_bytes(used)}/{self._fmt_bytes(total)}"

            p.setPen(QColor(C['text']))
            p.setFont(QFont("JetBrains Mono", 8))
            p.drawText(QRect(area.x(), y, area.width(), bar_h), Qt.AlignLeft | Qt.AlignVCenter, name)

            bar_x = area.x() + min(100, area.width() // 3)
            bar_w = area.width() - min(100, area.width() // 3) - 80
            bar_rect = QRect(bar_x, y + 2, bar_w, bar_h - 4)

            track = QColor(C['surface1'])
            p.setBrush(track)
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(bar_rect, 4, 4)

            fill_w = int(bar_rect.width() * pct / 100.0)
            if fill_w > 0:
                fill_rect = QRect(bar_rect.x(), bar_rect.y(), fill_w, bar_rect.height())
                p.setBrush(QColor(color))
                p.drawRoundedRect(fill_rect, 4, 4)

            p.setPen(QColor(C['subtext0']))
            p.setFont(QFont("JetBrains Mono", 8))
            text_rect = QRect(bar_rect.right() + 6, y, 74, bar_h)
            p.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter, f"{pct:.0f}% {detail}")

            y += bar_h + 6
            if y + bar_h > area.bottom():
                break

    def _paint_net(self, p, area):
        max_s = max(max(self._net_sent_history, default=1), max(self._net_recv_history, default=1), 1024)
        h_half = area.height() // 2 - 4
        up_rect = QRect(area.x(), area.y(), area.width(), h_half)
        dn_rect = QRect(area.x(), area.y() + h_half + 8, area.width(), h_half)
        up_spd = self._fmt_speed(getattr(self, '_net_sent_speed', 0))
        dn_spd = self._fmt_speed(getattr(self, '_net_recv_speed', 0))
        self._draw_line_chart(p, up_rect, self._net_sent_history, C['peach'],
                              max_val=max_s, label="↑ 上传", cur_text=up_spd)
        self._draw_line_chart(p, dn_rect, self._net_recv_history, C['teal'],
                              max_val=max_s, label="↓ 下载", cur_text=dn_spd)

    def _paint_all(self, p, area):
        w_half = area.width() // 2 - 4
        h_half = area.height() // 2 - 4

        cpu_rect = QRect(area.x(), area.y(), w_half, h_half)
        cur_cpu = self._cpu_history[-1] if self._cpu_history else 0
        self._draw_line_chart(p, cpu_rect, self._cpu_history, C['green'],
                              max_val=100.0, label="CPU", cur_text=f"{cur_cpu:.0f}%")

        mem_rect = QRect(area.x() + w_half + 8, area.y(), w_half, h_half)
        pct = getattr(self, '_mem_percent', 0)
        used = getattr(self, '_mem_used', 0)
        total = getattr(self, '_mem_total', 1)
        self._draw_ring(p, mem_rect, pct, C['blue'], label="内存",
                        detail=f"{self._fmt_bytes(used)}/{self._fmt_bytes(total)}")

        disk_rect = QRect(area.x(), area.y() + h_half + 8, w_half, h_half)
        self._paint_disk_mini(p, disk_rect)

        net_rect = QRect(area.x() + w_half + 8, area.y() + h_half + 8, w_half, h_half)
        max_s = max(max(self._net_sent_history, default=1), max(self._net_recv_history, default=1), 1024)
        net_h = net_rect.height() // 2 - 2
        up_r = QRect(net_rect.x(), net_rect.y(), net_rect.width(), net_h)
        dn_r = QRect(net_rect.x(), net_rect.y() + net_h + 4, net_rect.width(), net_h)
        up_spd = self._fmt_speed(getattr(self, '_net_sent_speed', 0))
        dn_spd = self._fmt_speed(getattr(self, '_net_recv_speed', 0))
        self._draw_line_chart(p, up_r, self._net_sent_history, C['peach'],
                              max_val=max_s, label="↑", cur_text=up_spd)
        self._draw_line_chart(p, dn_r, self._net_recv_history, C['teal'],
                              max_val=max_s, label="↓", cur_text=dn_spd)

    def _paint_disk_mini(self, p, area):
        disks = getattr(self, '_disks', [])
        if not disks:
            p.setPen(QColor(C['subtext0']))
            p.setFont(QFont("JetBrains Mono", 8))
            p.drawText(area, Qt.AlignCenter, "磁盘: N/A")
            return
        p.setPen(QColor(C['subtext0']))
        p.setFont(QFont("JetBrains Mono", 8))
        p.drawText(QRect(area.x(), area.y(), area.width(), 14), Qt.AlignLeft, "磁盘")
        bar_h = max(10, min(16, (area.height() - 18) // max(len(disks), 1) - 4))
        colors = [C['teal'], C['peach'], C['blue'], C['green']]
        y = area.y() + 18
        for i, (mount, used, total, pct) in enumerate(disks[:4]):
            color = colors[i % len(colors)]
            name = mount if len(mount) <= 8 else "…" + mount[-7:]
            p.setPen(QColor(C['text']))
            p.setFont(QFont("JetBrains Mono", 7))
            p.drawText(QRect(area.x(), y, 60, bar_h), Qt.AlignLeft | Qt.AlignVCenter, name)
            bx = area.x() + 64
            bw = area.width() - 64 - 36
            br = QRect(bx, y + 1, max(bw, 10), bar_h - 2)
            p.setBrush(QColor(C['surface1']))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(br, 3, 3)
            fw = int(br.width() * pct / 100.0)
            if fw > 0:
                p.setBrush(QColor(color))
                p.drawRoundedRect(QRect(br.x(), br.y(), fw, br.height()), 3, 3)
            p.setPen(QColor(C['subtext0']))
            p.setFont(QFont("JetBrains Mono", 7))
            p.drawText(QRect(br.right() + 4, y, 32, bar_h), Qt.AlignLeft | Qt.AlignVCenter, f"{pct:.0f}%")
            y += bar_h + 3
            if y + bar_h > area.bottom():
                break



