import json
import os
import re
import urllib.request
import urllib.parse
import datetime
import glob as glob_mod
import configparser
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea
)
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt5.QtGui import QFont, QColor, QPainter, QPen, QFontMetrics, QPixmap

from fastpanel.constants import GRID_SIZE
from fastpanel.settings import C, _settings
from fastpanel.dialogs.city import _CITY_DB
from fastpanel.theme import _comp_style, _bg
from fastpanel.widgets.base import CompBase

_WMO_DESC = {
    0: "晴", 1: "少云", 2: "多云", 3: "阴", 45: "雾", 48: "霜雾",
    51: "小毛毛雨", 53: "毛毛雨", 55: "大毛毛雨",
    61: "小雨", 63: "中雨", 65: "大雨", 66: "冻雨", 67: "大冻雨",
    71: "小雪", 73: "中雪", 75: "大雪", 77: "雪粒",
    80: "小阵雨", 81: "阵雨", 82: "大阵雨",
    85: "小阵雪", 86: "大阵雪", 95: "雷暴", 96: "冰雹雷暴", 99: "大冰雹雷暴",
}
_WMO_ICON = {
    0: ("☀", "#FFB300"), 1: ("⛅", "#FFB300"), 2: ("⛅", "#90A4AE"), 3: ("☁", "#78909C"),
    45: ("≋", "#B0BEC5"), 48: ("≋", "#B0BEC5"),
    51: ("🌧", "#90CAF9"), 53: ("🌧", "#64B5F6"), 55: ("🌧", "#42A5F5"),
    61: ("🌧", "#42A5F5"), 63: ("🌧", "#1E88E5"), 65: ("🌧", "#1565C0"),
    66: ("🌧", "#80DEEA"), 67: ("🌧", "#4DD0E1"),
    71: ("❆", "#B3E5FC"), 73: ("❆", "#81D4FA"), 75: ("❆", "#4FC3F7"), 77: ("❆", "#E0F7FA"),
    80: ("🌧", "#42A5F5"), 81: ("🌧", "#1E88E5"), 82: ("🌧", "#0D47A1"),
    85: ("❆", "#81D4FA"), 86: ("❆", "#4FC3F7"),
    95: ("⛈", "#6A1B9A"), 96: ("⛈", "#4A148C"), 99: ("⛈", "#311B92"),
}
def _wmo_icon(code): return _WMO_ICON.get(code, ("☁", "#90A4AE"))
def _wmo_desc(code): return _WMO_DESC.get(code, "未知")

def _wind_dir_from_deg(deg):
    dirs = ["北", "北偏东", "东北", "东偏北", "东", "东偏南", "东南", "南偏东",
            "南", "南偏西", "西南", "西偏南", "西", "西偏北", "西北", "北偏西"]
    return dirs[round(deg / 22.5) % 16]

_CN_WEATHER_ICON = {
    "晴": ("☀", "#FFA726"), "多云": ("⛅", "#78909C"), "阴": ("☁", "#90A4AE"),
    "雾": ("🌫", "#B0BEC5"), "霾": ("🌫", "#8D6E63"),
    "小雨": ("🌧", "#42A5F5"), "中雨": ("🌧", "#1E88E5"), "大雨": ("🌧", "#1565C0"),
    "暴雨": ("⛈", "#0D47A1"), "大暴雨": ("⛈", "#0D47A1"), "特大暴雨": ("⛈", "#0D47A1"),
    "阵雨": ("🌦", "#42A5F5"), "雷阵雨": ("⛈", "#7E57C2"),
    "小雪": ("❄", "#90CAF9"), "中雪": ("❄", "#64B5F6"), "大雪": ("❄", "#42A5F5"),
    "暴雪": ("❄", "#1E88E5"), "阵雪": ("❄", "#90CAF9"),
    "雨夹雪": ("🌨", "#78909C"), "冻雨": ("🌧", "#4FC3F7"),
    "浮尘": ("💨", "#BCAAA4"), "扬沙": ("💨", "#A1887F"), "沙尘暴": ("💨", "#795548"),
}

def _cn_weather_icon(text):
    for key, val in _CN_WEATHER_ICON.items():
        if key in text:
            return val
    return ("☁", "#90A4AE")

class _WeatherFetcher(QThread):
    result_ready = pyqtSignal(dict)

    def __init__(self, city_code, city_name=""):
        super().__init__()
        self._code = city_code
        self._name = city_name

    def run(self):
        try:
            url = f"http://t.weather.sojson.com/api/weather/city/{self._code}"
            req = urllib.request.Request(url, headers={"User-Agent": "FastPanel/1.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if data.get("status") != 200:
                self.result_ready.emit({"_error": data.get("message", "API返回错误")})
                return
            data["_city_name"] = self._name or data.get("cityInfo", {}).get("city", "")
            self.result_ready.emit(data)
        except Exception as e:
            self.result_ready.emit({"_error": str(e)})


class _TempChartWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._data = []
        self._hover_idx = -1
        self.setMinimumHeight(140)
        self.setMouseTracking(True)

    def set_data(self, data):
        self._data = data
        self._hover_idx = -1
        self.update()

    def _layout_params(self):
        w, h = self.width(), self.height()
        n = len(self._data)
        pad_l, pad_r = 20, 20
        pad_b = 52
        pad_t = max(22, (h - pad_b) // 3)
        cw = (w - pad_l - pad_r) / (n - 1) if n > 1 else 0
        all_temps = [d["max"] for d in self._data] + [d["min"] for d in self._data]
        t_min, t_max = min(all_temps) - 2, max(all_temps) + 2
        t_range = t_max - t_min if t_max != t_min else 1
        def tx(i): return pad_l + i * cw
        def ty(t): return pad_t + (1 - (t - t_min) / t_range) * (h - pad_t - pad_b)
        return n, w, h, cw, tx, ty

    def mouseMoveEvent(self, e):
        if len(self._data) < 2:
            self._hover_idx = -1; self.update(); return
        n, w, h, cw, tx, ty = self._layout_params()
        mx = e.x()
        best = -1; best_dist = 999999
        for i in range(n):
            d = abs(mx - tx(i))
            if d < best_dist and d < max(cw * 0.6, 20):
                best_dist = d; best = i
        if best != self._hover_idx:
            self._hover_idx = best
            self.update()

    def leaveEvent(self, e):
        self._hover_idx = -1; self.update()

    def paintEvent(self, e):
        if not self._data:
            return
        from PyQt5.QtGui import QPen, QFontMetrics
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        n, w, h, cw, tx, ty = self._layout_params()
        if n < 2:
            p.end(); return

        pen_max = QPen(QColor("#FF7043"), 2)
        p.setPen(pen_max)
        for i in range(n - 1):
            p.drawLine(int(tx(i)), int(ty(self._data[i]["max"])),
                       int(tx(i+1)), int(ty(self._data[i+1]["max"])))
        for i in range(n):
            p.setBrush(QColor("#FF7043")); p.setPen(Qt.NoPen)
            p.drawEllipse(int(tx(i))-3, int(ty(self._data[i]["max"]))-3, 6, 6)
            p.setPen(QColor("#FF7043"))
            f = p.font(); f.setPixelSize(10); p.setFont(f)
            p.drawText(int(tx(i))-10, int(ty(self._data[i]["max"]))-8, f'{self._data[i]["max"]}°')

        pen_min = QPen(QColor("#42A5F5"), 2)
        p.setPen(pen_min)
        for i in range(n - 1):
            p.drawLine(int(tx(i)), int(ty(self._data[i]["min"])),
                       int(tx(i+1)), int(ty(self._data[i+1]["min"])))
        for i in range(n):
            p.setBrush(QColor("#42A5F5")); p.setPen(Qt.NoPen)
            p.drawEllipse(int(tx(i))-3, int(ty(self._data[i]["min"]))-3, 6, 6)
            p.setPen(QColor("#42A5F5"))
            f = p.font(); f.setPixelSize(10); p.setFont(f)
            p.drawText(int(tx(i))-10, int(ty(self._data[i]["min"]))+16, f'{self._data[i]["min"]}°')

        today = datetime.date.today()
        for i, d in enumerate(self._data):
            dt = d.get("date"); wtype = d.get("type", "")
            if not dt:
                continue
            ic, ic_clr = _cn_weather_icon(wtype)
            if dt == today:
                date_str = "今天"
            else:
                date_str = f"{dt.month}/{dt.day}"
            f = p.font(); f.setPixelSize(13); p.setFont(f)
            p.setPen(QColor(ic_clr))
            p.drawText(int(tx(i)) - 8, h - 22, ic)
            f.setPixelSize(11); p.setFont(f)
            p.setPen(QColor(C['subtext0']))
            fm = QFontMetrics(f)
            tw = fm.horizontalAdvance(date_str)
            p.drawText(int(tx(i)) - tw // 2, h - 6, date_str)

        if 0 <= self._hover_idx < n:
            hi = self._hover_idx
            cx = int(tx(hi))
            p.setPen(QPen(QColor(C['overlay0']), 1, Qt.DashLine))
            p.drawLine(cx, 0, cx, h - 52)

            d = self._data[hi]
            dt = d.get("date")
            wtype = d.get("type", "")
            ic, ic_clr = _cn_weather_icon(wtype)
            weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
            if dt:
                if dt == today:
                    title = f"今天 ({dt.month}/{dt.day} {weekdays[dt.weekday()]})"
                else:
                    title = f"{dt.month}/{dt.day} {weekdays[dt.weekday()]}"
            else:
                title = "?"
            lines = [title, f"{ic} {wtype}"]
            lines.append(f"最高 {d['max']}°  最低 {d['min']}°")
            if d.get("fx"): lines.append(f"{d['fx']} {d.get('fl','')}")
            if d.get("aqi"): lines.append(f"AQI {d['aqi']}")
            if d.get("notice"): lines.append(d["notice"][:20])

            card_f = p.font(); card_f.setPixelSize(12); p.setFont(card_f)
            fm = QFontMetrics(card_f)
            line_h = fm.height() + 4
            card_w = max(fm.horizontalAdvance(l) for l in lines) + 20
            card_h = line_h * len(lines) + 16
            card_x = cx + 10
            if card_x + card_w > w - 5:
                card_x = cx - card_w - 10
            card_y = 8

            p.setPen(Qt.NoPen)
            p.setBrush(QColor(C['surface0']))
            p.drawRoundedRect(card_x, card_y, card_w, card_h, 6, 6)
            p.setPen(QPen(QColor(C['overlay0']), 1))
            p.drawRoundedRect(card_x, card_y, card_w, card_h, 6, 6)

            y_off = card_y + 14
            for j, line in enumerate(lines):
                if j == 0:
                    card_f.setBold(True); p.setFont(card_f)
                    p.setPen(QColor(C['text']))
                elif j == 1:
                    card_f.setBold(False); p.setFont(card_f)
                    p.setPen(QColor(ic_clr))
                else:
                    p.setPen(QColor(C['subtext0']))
                p.drawText(card_x + 10, y_off, line)
                y_off += line_h

        p.end()

    def refresh_theme(self):
        saved_year = self._year
        saved_month = self._month
        saved_selected = self._selected
        super().refresh_theme()
        self._year = saved_year
        self._month = saved_month
        self._selected = saved_selected
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._auto_refresh)
        self._refresh_timer.start(max(self.data.refresh_interval, 10) * 1000)
        self._refresh()


class WeatherWidget(CompBase):
    def __init__(self, data, parent=None):
        super().__init__(data, parent)
        self._fetcher = None
        self._has_data = False
        self._retry_count = 0
        self._max_retries = 3
        self._retry_delays = [5000, 15000, 30000]
        self._build()
        self._fetch_weather()
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._fetch_weather)
        interval = max(data.refresh_interval, 10) * 1000
        self._refresh_timer.start(interval)

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 10, 14, 8); root.setSpacing(2)

        top = QHBoxLayout(); top.setSpacing(6)
        self._city_lbl = QLabel(self.data.cmd.strip() or "大连")
        self._city_lbl.setStyleSheet(f"color:{C['text']}; font-size:13px; font-weight:bold;")
        top.addWidget(self._city_lbl)
        self._err_icon = QLabel("⚠")
        self._err_icon.setStyleSheet(f"color:{C['red']}; font-size:12px; background:transparent;")
        self._err_icon.setCursor(Qt.WhatsThisCursor)
        self._err_icon.hide()
        top.addWidget(self._err_icon)
        top.addStretch()
        rb = QPushButton("↻"); rb.setFixedSize(24, 24); rb.setCursor(Qt.PointingHandCursor)
        rb.setToolTip("刷新"); rb.setStyleSheet(f"background:transparent; color:{C['subtext0']}; border:none; font-size:16px; font-weight:bold;")
        rb.clicked.connect(self._fetch_weather); top.addWidget(rb)
        root.addLayout(top)

        cur_row = QHBoxLayout(); cur_row.setSpacing(8)
        self._temp_lbl = QLabel("--")
        self._temp_lbl.setStyleSheet(f"color:{C['text']}; font-size:36px; font-weight:bold;")
        cur_row.addWidget(self._temp_lbl)
        cur_info = QVBoxLayout(); cur_info.setSpacing(2)
        self._desc_lbl = QLabel("加载中…")
        self._desc_lbl.setStyleSheet(f"color:{C['text']}; font-size:13px;")
        cur_info.addWidget(self._desc_lbl)
        self._detail_lbl = QLabel("")
        self._detail_lbl.setStyleSheet(f"color:{C['subtext0']}; font-size:11px;")
        cur_info.addWidget(self._detail_lbl)
        cur_row.addLayout(cur_info, 1)
        self._icon_lbl = QLabel("")
        self._icon_lbl.setStyleSheet(f"font-size:36px;")
        self._icon_lbl.setAlignment(Qt.AlignCenter)
        cur_row.addWidget(self._icon_lbl)
        root.addLayout(cur_row)

        sep = QFrame(); sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"color:{C['surface1']};"); sep.setFixedHeight(1)
        root.addWidget(sep)

        fc_title = QLabel("未来15天预报")
        fc_title.setStyleSheet(f"color:{C['subtext0']}; font-size:10px; margin-top:2px;")
        root.addWidget(fc_title)

        self._chart = _TempChartWidget()
        root.addWidget(self._chart, 1)



    def _parse_city_cmd(self):
        raw = self.data.cmd.strip()
        if "|" in raw:
            code, name = raw.split("|", 1)
            return code.strip(), name.strip()
        for c in _CITY_DB:
            if c["name"] == raw or c["city"] == raw:
                return c["code"], c["name"]
        return "", raw or "大连"

    def _fetch_weather(self):
        code, name = self._parse_city_cmd()
        self._city_lbl.setText(name)
        if not code:
            if not self._has_data:
                self._desc_lbl.setText("请选择城市")
                self._desc_lbl.setStyleSheet(f"color:{C['peach']}; font-size:13px;")
            return
        if not self._has_data:
            self._desc_lbl.setText("加载中…")
            self._temp_lbl.setText("--")
            self._detail_lbl.setText("")
            self._icon_lbl.setText("")
            self._chart.set_data([])
        self._fetcher = _WeatherFetcher(code, name)
        self._fetcher.result_ready.connect(self._on_result)
        self._fetcher.start()

    def _on_result(self, data):
        if "_error" in data:
            err_msg = str(data["_error"])
            if self._has_data:
                self._err_icon.setToolTip(f"刷新失败: {err_msg}")
                self._err_icon.show()
            else:
                if self._retry_count < self._max_retries:
                    delay = self._retry_delays[min(self._retry_count, len(self._retry_delays)-1)]
                    self._retry_count += 1
                    self._desc_lbl.setText(f"加载失败，{delay//1000}秒后重试({self._retry_count}/{self._max_retries})…")
                    self._desc_lbl.setStyleSheet(f"color:{C['peach']}; font-size:13px;")
                    QTimer.singleShot(delay, self._fetch_weather)
                else:
                    self._desc_lbl.setText("获取失败")
                    self._detail_lbl.setText(err_msg)
                    self._desc_lbl.setStyleSheet(f"color:{C['red']}; font-size:13px;")
            return
        self._has_data = True
        self._retry_count = 0
        self._err_icon.hide()
        city_name = data.get("_city_name", "")
        if city_name:
            self._city_lbl.setText(city_name)

        d = data.get("data", {})
        temp = d.get("wendu", "?")
        humidity = d.get("shidu", "?")
        quality = d.get("quality", "")
        pm25 = d.get("pm25", "")
        ganmao = d.get("ganmao", "")

        forecast = d.get("forecast", [])
        today = forecast[0] if forecast else {}
        today_type = today.get("type", "")
        today_high = today.get("high", "").replace("高温 ", "").replace("℃", "")
        today_low = today.get("low", "").replace("低温 ", "").replace("℃", "")
        today_fx = today.get("fx", "")
        today_fl = today.get("fl", "")

        ic, ic_clr = _cn_weather_icon(today_type)
        today_range = f"  {today_low}~{today_high}°C" if today_high and today_low else ""

        self._temp_lbl.setText(f"{temp}°")
        self._temp_lbl.setStyleSheet(f"color:{C['text']}; font-size:36px; font-weight:bold;")
        self._desc_lbl.setText(f"{today_type}{today_range}")
        self._desc_lbl.setStyleSheet(f"color:{C['text']}; font-size:13px;")
        detail_parts = [f"湿度 {humidity}"]
        if today_fx: detail_parts.append(f"{today_fx}{today_fl}")
        if quality: detail_parts.append(f"空气{quality}")
        if pm25: detail_parts.append(f"PM2.5 {pm25}")
        self._detail_lbl.setText("  ".join(detail_parts))
        self._detail_lbl.setStyleSheet(f"color:{C['subtext0']}; font-size:11px;")
        self._icon_lbl.setText(ic)
        self._icon_lbl.setStyleSheet(f"font-size:36px; color:{ic_clr};")

        chart_data = []
        for item in forecast[:15]:
            try:
                dt = datetime.datetime.strptime(item.get("ymd", ""), "%Y-%m-%d").date()
            except Exception:
                dt = None
            hi = item.get("high", "").replace("高温 ", "").replace("℃", "")
            lo = item.get("low", "").replace("低温 ", "").replace("℃", "")
            try: hi_val = float(hi)
            except: hi_val = 0
            try: lo_val = float(lo)
            except: lo_val = 0
            chart_data.append({
                "date": dt, "max": hi_val, "min": lo_val,
                "type": item.get("type", ""), "fx": item.get("fx", ""),
                "fl": item.get("fl", ""), "aqi": item.get("aqi", ""),
                "notice": item.get("notice", "")
            })
        self._chart.set_data(chart_data)

    def update_from_data(self):
        _, name = self._parse_city_cmd()
        self._city_lbl.setText(name)
        self._has_data = False
        self._fetch_weather()

    def refresh_theme(self):
        super().refresh_theme()
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._fetch_weather)
        self._refresh_timer.start(max(self.data.refresh_interval, 10) * 1000)
        self._fetch_weather()


def _scan_desktop_apps():
    dirs = ["/usr/share/applications", os.path.expanduser("~/.local/share/applications")]
    apps = []
    for d in dirs:
        for fp in glob_mod.glob(os.path.join(d, "*.desktop")):
            try:
                cp = configparser.ConfigParser(interpolation=None)
                cp.read(fp, encoding="utf-8")
                sec = "Desktop Entry"
                if not cp.has_section(sec):
                    continue
                if cp.get(sec, "Type", fallback="") != "Application":
                    continue
                if cp.getboolean(sec, "NoDisplay", fallback=False):
                    continue
                name = cp.get(sec, "Name[zh_CN]", fallback="") or cp.get(sec, "Name", fallback="")
                exe = cp.get(sec, "Exec", fallback="")
                icon = cp.get(sec, "Icon", fallback="")
                if not name or not exe:
                    continue
                exe = re.sub(r'\s+%[fFuUdDnNickvm]', '', exe).strip()
                icon_path = ""
                if icon:
                    if os.path.isabs(icon) and os.path.isfile(icon):
                        icon_path = icon
                    else:
                        for base in ["/usr/share/icons/hicolor", "/usr/share/pixmaps"]:
                            for ext in [".png", ".svg", ".xpm"]:
                                for sz in ["128x128", "96x96", "64x64", "48x48", "scalable", "256x256"]:
                                    cand = os.path.join(base, sz, "apps", icon + ext)
                                    if os.path.isfile(cand):
                                        icon_path = cand; break
                                if icon_path: break
                            if icon_path: break
                        if not icon_path:
                            cand = os.path.join("/usr/share/pixmaps", icon + ".png")
                            if os.path.isfile(cand):
                                icon_path = cand
                            cand2 = os.path.join("/usr/share/pixmaps", icon + ".xpm")
                            if not icon_path and os.path.isfile(cand2):
                                icon_path = cand2
                apps.append({"name": name, "exec": exe, "icon": icon_path, "desktop": fp})
            except Exception:
                continue
    apps.sort(key=lambda a: a["name"].lower())
    return apps



