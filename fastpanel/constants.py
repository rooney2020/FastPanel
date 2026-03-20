import os
import re

GRID_SIZE = 20
MIN_W = 260
MIN_H = 140
PANEL_PADDING = 60
PARAM_PATTERN = re.compile(r'\(\$\)')

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_FILE = os.path.join(_BASE_DIR, "data.json")
ARROW_PATH = os.path.join(_BASE_DIR, "arrow_down.png")
CHECK_PATH = os.path.join(_BASE_DIR, "check.svg")

_DESKTOP_MODE = False

TYPE_CMD = "cmd"
TYPE_CMD_WINDOW = "cmd_window"
TYPE_SHORTCUT = "shortcut"
TYPE_CALENDAR = "calendar"
TYPE_WEATHER = "weather"
TYPE_DOCK = "dock"
TYPE_TODO = "todo"
TYPE_CLOCK = "clock"
TYPE_MONITOR = "monitor"
TYPE_LAUNCHER = "launcher"
TYPE_NOTE = "note"
TYPE_QUICKACTION = "quickaction"
TYPE_MEDIA = "media"
TYPE_CLIPBOARD = "clipboard"
TYPE_TIMER = "timer"
TYPE_GALLERY = "gallery"
TYPE_SYSINFO = "sysinfo"
TYPE_BOOKMARK = "bookmark"
TYPE_CALC = "calc"
TYPE_TRASH = "trash"
TYPE_RSS = "rss"
TYPE_LABELS = {TYPE_CMD: "CMD", TYPE_CMD_WINDOW: "CMD窗口", TYPE_SHORTCUT: "快捷方式",
               TYPE_CALENDAR: "日历", TYPE_WEATHER: "天气", TYPE_DOCK: "Dock栏", TYPE_TODO: "待办",
               TYPE_CLOCK: "时钟", TYPE_MONITOR: "系统监控", TYPE_LAUNCHER: "应用启动器",
               TYPE_NOTE: "便签", TYPE_QUICKACTION: "快捷操作",
               TYPE_MEDIA: "媒体控制", TYPE_CLIPBOARD: "剪贴板", TYPE_TIMER: "计时器",
               TYPE_GALLERY: "相册", TYPE_SYSINFO: "系统信息",
               TYPE_BOOKMARK: "书签", TYPE_CALC: "计算器", TYPE_TRASH: "回收站",
               TYPE_RSS: "RSS"}

MONITOR_SUB_CPU = "cpu"
MONITOR_SUB_MEM = "memory"
MONITOR_SUB_DISK = "disk"
MONITOR_SUB_NET = "network"
MONITOR_SUB_ALL = "all"
MONITOR_SUB_LABELS = {
    MONITOR_SUB_CPU: "CPU", MONITOR_SUB_MEM: "内存",
    MONITOR_SUB_DISK: "磁盘", MONITOR_SUB_NET: "网络",
    MONITOR_SUB_ALL: "综合概览",
}

CLOCK_SUB_CLOCK = "clock"
CLOCK_SUB_WORLD = "world"
CLOCK_SUB_STOPWATCH = "stopwatch"
CLOCK_SUB_TIMER = "timer"
CLOCK_SUB_ALARM = "alarm"
CLOCK_SUB_LABELS = {CLOCK_SUB_CLOCK: "时钟", CLOCK_SUB_WORLD: "世界时钟",
                    CLOCK_SUB_STOPWATCH: "秒表", CLOCK_SUB_TIMER: "计时器",
                    CLOCK_SUB_ALARM: "闹钟"}

SUB_APP = "application"
SUB_FILE = "file"
SUB_SCRIPT = "script"
SUB_LABELS = {SUB_APP: "应用程序", SUB_FILE: "文件", SUB_SCRIPT: "脚本"}

THEMES = {
    "Catppuccin Mocha": {
        "base": "#1e1e2e", "mantle": "#181825", "crust": "#11111b",
        "surface0": "#313244", "surface1": "#45475a", "surface2": "#585b70",
        "overlay0": "#6c7086", "text": "#cdd6f4", "subtext0": "#a6adc8",
        "blue": "#89b4fa", "sky": "#89dceb", "teal": "#94e2d5",
        "green": "#a6e3a1", "red": "#f38ba8", "peach": "#fab387",
        "lavender": "#b4befe", "yellow": "#f9e2af", "mauve": "#cba6f7",
    },
    "Catppuccin Latte": {
        "base": "#eff1f5", "mantle": "#e6e9ef", "crust": "#dce0e8",
        "surface0": "#ccd0da", "surface1": "#bcc0cc", "surface2": "#acb0be",
        "overlay0": "#9ca0b0", "text": "#4c4f69", "subtext0": "#6c6f85",
        "blue": "#1e66f5", "sky": "#04a5e5", "teal": "#179299",
        "green": "#40a02b", "red": "#d20f39", "peach": "#fe640b",
        "lavender": "#7287fd", "yellow": "#df8e1d", "mauve": "#8839ef",
    },
    "Nord": {
        "base": "#2e3440", "mantle": "#242933", "crust": "#1d2128",
        "surface0": "#3b4252", "surface1": "#434c5e", "surface2": "#4c566a",
        "overlay0": "#616e88", "text": "#eceff4", "subtext0": "#d8dee9",
        "blue": "#81a1c1", "sky": "#88c0d0", "teal": "#8fbcbb",
        "green": "#a3be8c", "red": "#bf616a", "peach": "#d08770",
        "lavender": "#b48ead", "yellow": "#ebcb8b", "mauve": "#b48ead",
    },
    "Dracula": {
        "base": "#282a36", "mantle": "#21222c", "crust": "#191a21",
        "surface0": "#343746", "surface1": "#44475a", "surface2": "#585b6e",
        "overlay0": "#6272a4", "text": "#f8f8f2", "subtext0": "#bfbfbf",
        "blue": "#8be9fd", "sky": "#8be9fd", "teal": "#8be9fd",
        "green": "#50fa7b", "red": "#ff5555", "peach": "#ffb86c",
        "lavender": "#bd93f9", "yellow": "#f1fa8c", "mauve": "#bd93f9",
    },
    "One Dark": {
        "base": "#282c34", "mantle": "#21252b", "crust": "#1b1f27",
        "surface0": "#31353f", "surface1": "#3e4451", "surface2": "#4b5263",
        "overlay0": "#636d83", "text": "#abb2bf", "subtext0": "#828997",
        "blue": "#61afef", "sky": "#56b6c2", "teal": "#56b6c2",
        "green": "#98c379", "red": "#e06c75", "peach": "#d19a66",
        "lavender": "#c678dd", "yellow": "#e5c07b", "mauve": "#c678dd",
    },
}

