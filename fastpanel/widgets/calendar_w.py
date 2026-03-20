import calendar
import datetime
import os
import json
import urllib.request
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QGridLayout
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFont, QColor, QPainter

from fastpanel.constants import GRID_SIZE, _BASE_DIR
from fastpanel.settings import C, _settings
from fastpanel.theme import _comp_style, _bg
from fastpanel.widgets.base import CompBase

_HOLIDAY_CACHE = {}
_HOLIDAY_CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".holiday_cache")

def _load_holidays_for_year(year):
    if year in _HOLIDAY_CACHE:
        return _HOLIDAY_CACHE[year]
    os.makedirs(_HOLIDAY_CACHE_DIR, exist_ok=True)
    cache_file = os.path.join(_HOLIDAY_CACHE_DIR, f"{year}.json")
    data = None
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            pass
    if data is None:
        try:
            url = f"https://cdn.jsdelivr.net/npm/chinese-days/dist/years/{year}.json"
            req = urllib.request.Request(url, headers={"User-Agent": "FastPanel/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(data, ensure_ascii=False, indent=2, fp=f)
        except Exception:
            data = {}
    parsed = {"holidays": {}, "workdays": set()}
    for k, v in data.get("holidays", {}).items():
        parts = v.split(",")
        parsed["holidays"][k] = parts[1] if len(parts) >= 2 else parts[0]
    for k in data.get("workdays", {}):
        parsed["workdays"].add(k)
    _HOLIDAY_CACHE[year] = parsed
    return parsed



_LUNAR_INFO = [
    0x04bd8, 0x04ae0, 0x0a570, 0x054d5, 0x0d260, 0x0d950, 0x16554, 0x056a0, 0x09ad0, 0x055d2,
    0x04ae0, 0x0a5b6, 0x0a4d0, 0x0d250, 0x1d255, 0x0b540, 0x0d6a0, 0x0ada2, 0x095b0, 0x14977,
    0x04970, 0x0a4b0, 0x0b4b5, 0x06a50, 0x06d40, 0x1ab54, 0x02b60, 0x09570, 0x052f2, 0x04970,
    0x06566, 0x0d4a0, 0x0ea50, 0x06e95, 0x05ad0, 0x02b60, 0x186e3, 0x092e0, 0x1c8d7, 0x0c950,
    0x0d4a0, 0x1d8a6, 0x0b550, 0x056a0, 0x1a5b4, 0x025d0, 0x092d0, 0x0d2b2, 0x0a950, 0x0b557,
    0x06ca0, 0x0b550, 0x15355, 0x04da0, 0x0a5b0, 0x14573, 0x052b0, 0x0a9a8, 0x0e950, 0x06aa0,
    0x0aea6, 0x0ab50, 0x04b60, 0x0aae4, 0x0a570, 0x05260, 0x0f263, 0x0d950, 0x05b57, 0x056a0,
    0x096d0, 0x04dd5, 0x04ad0, 0x0a4d0, 0x0d4d4, 0x0d250, 0x0d558, 0x0b540, 0x0b6a0, 0x195a6,
    0x095b0, 0x049b0, 0x0a974, 0x0a4b0, 0x0b27a, 0x06a50, 0x06d40, 0x0af46, 0x0ab60, 0x09570,
    0x04af5, 0x04970, 0x064b0, 0x074a3, 0x0ea50, 0x06b58, 0x05ac0, 0x0ab60, 0x096d5, 0x092e0,
    0x0c960, 0x0d954, 0x0d4a0, 0x0da50, 0x07552, 0x056a0, 0x0abb7, 0x025d0, 0x092d0, 0x0cab5,
    0x0a950, 0x0b4a0, 0x0baa4, 0x0ad50, 0x055d9, 0x04ba0, 0x0a5b0, 0x15176, 0x052b0, 0x0a930,
    0x07954, 0x06aa0, 0x0ad50, 0x05b52, 0x04b60, 0x0a6e6, 0x0a4e0, 0x0d260, 0x0ea65, 0x0d530,
    0x05aa0, 0x076a3, 0x096d0, 0x04afb, 0x04ad0, 0x0a4d0, 0x1d0b6, 0x0d250, 0x0d520, 0x0dd45,
    0x0b5a0, 0x056d0, 0x055b2, 0x049b0, 0x0a577, 0x0a4b0, 0x0aa50, 0x1b255, 0x06d20, 0x0ada0,
    0x14b63, 0x09370, 0x049f8, 0x04970, 0x064b0, 0x168a6, 0x0ea50, 0x06b20, 0x1a6c4, 0x0aae0,
    0x092e0, 0x0d2e3, 0x0c960, 0x0d557, 0x0d4a0, 0x0da50, 0x05d55, 0x056a0, 0x0a6d0, 0x055d4,
    0x052d0, 0x0a9b8, 0x0a950, 0x0b4a0, 0x0b6a6, 0x0ad50, 0x055a0, 0x0aba4, 0x0a5b0, 0x052b0,
    0x0b273, 0x06930, 0x07337, 0x06aa0, 0x0ad50, 0x14b55, 0x04b60, 0x0a570, 0x054e4, 0x0d160,
    0x0e968, 0x0d520, 0x0daa0, 0x16aa6, 0x056d0, 0x04ae0, 0x0a9d4, 0x0a4d0, 0x0d150, 0x0f252,
    0x0d520,
]
_TIAN_GAN = "甲乙丙丁戊己庚辛壬癸"
_DI_ZHI = "子丑寅卯辰巳午未申酉戌亥"
_SHENG_XIAO = "鼠牛虎兔龙蛇马羊猴鸡狗猪"
_LUNAR_MON = ["正", "二", "三", "四", "五", "六", "七", "八", "九", "十", "冬", "腊"]
_LUNAR_DAY_STR = [
    "", "初一", "初二", "初三", "初四", "初五", "初六", "初七", "初八", "初九", "初十",
    "十一", "十二", "十三", "十四", "十五", "十六", "十七", "十八", "十九", "二十",
    "廿一", "廿二", "廿三", "廿四", "廿五", "廿六", "廿七", "廿八", "廿九", "三十",
]

def _lunar_year_days(y):
    idx = y - 1900
    if idx < 0 or idx >= len(_LUNAR_INFO): return 348
    s = 348
    for i in range(12):
        s += 30 if _LUNAR_INFO[idx] & (0x10000 >> i) else 29
    return s + _lunar_leap_days(y)

def _lunar_leap_month(y):
    idx = y - 1900
    if idx < 0 or idx >= len(_LUNAR_INFO): return 0
    return _LUNAR_INFO[idx] & 0xf

def _lunar_leap_days(y):
    lm = _lunar_leap_month(y)
    if not lm: return 0
    idx = y - 1900
    return 30 if _LUNAR_INFO[idx] & 0x10000 else 29

def _lunar_month_days(y, m):
    idx = y - 1900
    if idx < 0 or idx >= len(_LUNAR_INFO): return 29
    return 30 if _LUNAR_INFO[idx] & (0x10000 >> m) else 29

def _solar_to_lunar(year, month, day):
    base = datetime.date(1900, 1, 31)
    offset = (datetime.date(year, month, day) - base).days
    ly = 1900; lm = 1; ld = 1; leap = False
    while ly < 2101:
        ydays = _lunar_year_days(ly)
        if offset < ydays: break
        offset -= ydays; ly += 1
    lp = _lunar_leap_month(ly)
    for i in range(1, 14):
        if lp and i == lp + 1:
            mdays = _lunar_leap_days(ly); is_leap = True
        else:
            mi = i - (1 if i > lp and lp else 0)
            mdays = _lunar_month_days(ly, mi); is_leap = False
        if offset < mdays:
            lm = i - (1 if i > lp and lp else 0); ld = offset + 1; leap = is_leap; break
        offset -= mdays
    gan = _TIAN_GAN[(ly - 4) % 10]
    zhi = _DI_ZHI[(ly - 4) % 12]
    sx = _SHENG_XIAO[(ly - 4) % 12]
    return ly, lm, ld, leap, gan, zhi, sx



class _DayCell(QWidget):
    clicked = pyqtSignal(object)

    def __init__(self, date_obj, is_other, parent=None):
        super().__init__(parent)
        self.date_obj = date_obj
        self.is_other = is_other
        self.setCursor(Qt.PointingHandCursor)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit(self.date_obj)
        super().mousePressEvent(e)


class CalendarWidget(CompBase):
    def __init__(self, data, parent=None):
        super().__init__(data, parent)
        today = datetime.date.today()
        self._year = today.year
        self._month = today.month
        self._selected = None
        self._build()
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._auto_refresh)
        interval = max(data.refresh_interval, 10) * 1000
        self._refresh_timer.start(interval)

    def _auto_refresh(self):
        today = datetime.date.today()
        if today.year != self._year or today.month != self._month:
            pass
        self._refresh()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 8); root.setSpacing(4)

        nav = QHBoxLayout(); nav.setSpacing(4)
        pb = QPushButton("◀"); pb.setFixedSize(28, 28); pb.setCursor(Qt.PointingHandCursor)
        pb.setStyleSheet(f"background:{_bg('surface1')}; color:{C['text']}; border:none; border-radius:6px; font-size:12px;")
        pb.clicked.connect(self._prev_month); nav.addWidget(pb)
        self._month_lbl = QLabel(); self._month_lbl.setAlignment(Qt.AlignCenter)
        self._month_lbl.setStyleSheet(f"color:{C['text']}; font-size:14px; font-weight:bold;")
        nav.addWidget(self._month_lbl, 1)
        nb = QPushButton("▶"); nb.setFixedSize(28, 28); nb.setCursor(Qt.PointingHandCursor)
        nb.setStyleSheet(f"background:{_bg('surface1')}; color:{C['text']}; border:none; border-radius:6px; font-size:12px;")
        nb.clicked.connect(self._next_month); nav.addWidget(nb)
        tb = QPushButton("今天"); tb.setFixedHeight(28); tb.setCursor(Qt.PointingHandCursor)
        tb.setStyleSheet(f"background:{C['blue']}; color:{C['crust']}; border:none; border-radius:6px; font-size:11px; font-weight:bold; padding:0 10px;")
        tb.clicked.connect(self._go_today); nav.addWidget(tb)
        root.addLayout(nav)

        from PyQt5.QtWidgets import QGridLayout
        hdr = QHBoxLayout(); hdr.setSpacing(0)
        for i, d in enumerate(["一", "二", "三", "四", "五", "六", "日"]):
            l = QLabel(d); l.setAlignment(Qt.AlignCenter); l.setFixedHeight(20)
            clr = C['red'] if i >= 5 else C['subtext0']
            l.setStyleSheet(f"color:{clr}; font-size:11px; font-weight:bold;")
            hdr.addWidget(l, 1)
        root.addLayout(hdr)

        self._grid = QGridLayout(); self._grid.setSpacing(1)
        root.addLayout(self._grid, 1)

        self._lunar_lbl = QLabel(); self._lunar_lbl.setAlignment(Qt.AlignCenter)
        self._lunar_lbl.setStyleSheet(f"color:{C['subtext0']}; font-size:11px;")
        root.addWidget(self._lunar_lbl)

        self._refresh()

    def _prev_month(self):
        if self._month == 1: self._month = 12; self._year -= 1
        else: self._month -= 1
        self._refresh()

    def _next_month(self):
        if self._month == 12: self._month = 1; self._year += 1
        else: self._month += 1
        self._refresh()

    def _go_today(self):
        today = datetime.date.today()
        self._year = today.year; self._month = today.month
        self._selected = None
        self._refresh()

    def _refresh(self):
        self._month_lbl.setText(f"{self._year}年 {self._month}月")
        while self._grid.count():
            w = self._grid.takeAt(0).widget()
            if w: w.deleteLater()
        today = datetime.date.today()
        cal = calendar.monthcalendar(self._year, self._month)

        if self._month == 1:
            prev_y, prev_m = self._year - 1, 12
        else:
            prev_y, prev_m = self._year, self._month - 1
        prev_last = calendar.monthrange(prev_y, prev_m)[1]

        if self._month == 12:
            next_y, next_m = self._year + 1, 1
        else:
            next_y, next_m = self._year, self._month + 1

        years_needed = {self._year, prev_y, next_y}
        hol_data = {}
        for y in years_needed:
            hol_data[y] = _load_holidays_for_year(y)

        for r, week in enumerate(cal):
            for c, day in enumerate(week):
                is_other = False
                sy, sm, sd = self._year, self._month, day
                if day == 0:
                    is_other = True
                    if r == 0:
                        first_week = cal[0]
                        zeros = sum(1 for d in first_week if d == 0)
                        sd = prev_last - zeros + c + 1
                        sy, sm = prev_y, prev_m
                    else:
                        filled_before = sum(1 for d in week[:c] if d == 0)
                        sd = filled_before + 1
                        sy, sm = next_y, next_m
                try:
                    _, lm, ld, leap, _, _, _ = _solar_to_lunar(sy, sm, sd)
                    ltxt = _LUNAR_DAY_STR[ld] if ld <= 30 else ""
                except Exception:
                    ltxt = ""
                date_obj = datetime.date(sy, sm, sd)
                date_key = date_obj.strftime("%Y-%m-%d")
                yh = hol_data.get(sy, {"holidays": {}, "workdays": set()})
                holiday_name = yh["holidays"].get(date_key)
                is_workday = date_key in yh["workdays"]
                if holiday_name:
                    ltxt = holiday_name
                elif is_workday:
                    ltxt = "班"

                is_today = (date_obj == today)
                is_selected = (self._selected is not None and date_obj == self._selected)
                is_weekend = c >= 5
                w = _DayCell(date_obj, is_other); w.setFixedHeight(40)
                w.clicked.connect(self._on_day_click)
                vl = QVBoxLayout(w); vl.setContentsMargins(2, 1, 2, 1); vl.setSpacing(0)
                dl = QLabel(str(sd)); dl.setAlignment(Qt.AlignCenter)
                ll = QLabel(ltxt); ll.setAlignment(Qt.AlignCenter)
                if is_selected and is_today:
                    w.setStyleSheet(f"background:{C['blue']}; border-radius:6px; border:2px solid {C['lavender']};")
                    dl.setStyleSheet(f"color:{C['crust']}; font-size:13px; font-weight:bold;")
                    ll.setStyleSheet(f"color:{C['crust']}; font-size:8px;")
                elif is_today:
                    w.setStyleSheet(f"background:{C['blue']}; border-radius:6px;")
                    dl.setStyleSheet(f"color:{C['crust']}; font-size:13px; font-weight:bold;")
                    ll.setStyleSheet(f"color:{C['crust']}; font-size:8px;")
                elif is_selected:
                    w.setStyleSheet(f"background:{_bg('surface1')}; border-radius:6px; border:2px solid {C['blue']};")
                    dl.setStyleSheet(f"color:{C['text']}; font-size:13px; font-weight:bold;")
                    if holiday_name:
                        ll.setStyleSheet(f"color:{C['green']}; font-size:8px; font-weight:bold;")
                    elif is_workday:
                        ll.setStyleSheet(f"color:{C['peach']}; font-size:8px; font-weight:bold;")
                    else:
                        ll.setStyleSheet(f"color:{C['overlay0']}; font-size:8px;")
                elif is_other and holiday_name:
                    dl.setStyleSheet(f"color:{C['green']}; font-size:13px; opacity:0.7;")
                    ll.setStyleSheet(f"color:{C['green']}; font-size:8px; font-weight:bold;")
                elif is_other and is_workday:
                    dl.setStyleSheet(f"color:{C['peach']}; font-size:13px; opacity:0.7;")
                    ll.setStyleSheet(f"color:{C['peach']}; font-size:8px; font-weight:bold;")
                elif is_other:
                    dl.setStyleSheet(f"color:{C['surface2']}; font-size:13px;")
                    ll.setStyleSheet(f"color:{C['surface2']}; font-size:8px;")
                elif holiday_name:
                    dl.setStyleSheet(f"color:{C['green']}; font-size:13px; font-weight:bold;")
                    ll.setStyleSheet(f"color:{C['green']}; font-size:8px; font-weight:bold;")
                elif is_workday:
                    dl.setStyleSheet(f"color:{C['peach']}; font-size:13px; font-weight:bold;")
                    ll.setStyleSheet(f"color:{C['peach']}; font-size:8px; font-weight:bold;")
                elif is_weekend:
                    dl.setStyleSheet(f"color:{C['red']}; font-size:13px; font-weight:bold;")
                    ll.setStyleSheet(f"color:{C['overlay0']}; font-size:8px;")
                else:
                    dl.setStyleSheet(f"color:{C['text']}; font-size:13px; font-weight:bold;")
                    ll.setStyleSheet(f"color:{C['overlay0']}; font-size:8px;")
                vl.addWidget(dl); vl.addWidget(ll)
                self._grid.addWidget(w, r, c)

        ref_date = self._selected if self._selected else today
        try:
            _, lm, ld, leap, gan, zhi, sx = _solar_to_lunar(ref_date.year, ref_date.month, ref_date.day)
            lp = "闰" if leap else ""
            self._lunar_lbl.setText(f"{gan}{zhi}年（{sx}） {lp}{_LUNAR_MON[lm-1]}月{_LUNAR_DAY_STR[ld]}")
        except Exception:
            self._lunar_lbl.setText("")

    def _on_day_click(self, date_obj):
        if self._selected == date_obj:
            self._selected = None
        else:
            self._selected = date_obj
            if date_obj.year != self._year or date_obj.month != self._month:
                self._year = date_obj.year
                self._month = date_obj.month
        self._refresh()

    def update_from_data(self):
        pass


# ---------------------------------------------------------------------------
# Weather Component
# ---------------------------------------------------------------------------
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

