from fastpanel.data import ComponentData
from fastpanel.widgets.base import CompBase
from fastpanel.constants import (
    TYPE_CMD, TYPE_CMD_WINDOW, TYPE_SHORTCUT, TYPE_CALENDAR,
    TYPE_WEATHER, TYPE_DOCK, TYPE_TODO, TYPE_CLOCK, TYPE_MONITOR,
    TYPE_LAUNCHER, TYPE_NOTE, TYPE_QUICKACTION, TYPE_MEDIA,
    TYPE_CLIPBOARD, TYPE_TIMER, TYPE_GALLERY, TYPE_SYSINFO,
    TYPE_BOOKMARK, TYPE_CALC, TYPE_TRASH, TYPE_RSS
)
from fastpanel.widgets.cmd import CmdWidget, CmdWindowWidget, ShortcutWidget
from fastpanel.widgets.calendar_w import CalendarWidget
from fastpanel.widgets.weather import WeatherWidget
from fastpanel.widgets.dock import DockWidget
from fastpanel.widgets.todo import TodoWidget
from fastpanel.widgets.clock import ClockWidget
from fastpanel.widgets.monitor import MonitorWidget
from fastpanel.widgets.launcher import LauncherWidget
from fastpanel.widgets.note import NoteWidget
from fastpanel.widgets.quick_action import QuickActionWidget
from fastpanel.widgets.media import MediaWidget
from fastpanel.widgets.clipboard import ClipboardWidget
from fastpanel.widgets.timer import TimerWidget
from fastpanel.widgets.gallery import GalleryWidget
from fastpanel.widgets.sysinfo import SysInfoWidget
from fastpanel.widgets.bookmark import BookmarkWidget
from fastpanel.widgets.calc import CalcWidget
from fastpanel.widgets.trash import TrashWidget
from fastpanel.widgets.rss import RSSWidget

def create_widget(data: ComponentData, parent=None) -> CompBase:
    if data.comp_type == TYPE_CMD_WINDOW:
        return CmdWindowWidget(data, parent)
    if data.comp_type == TYPE_SHORTCUT:
        return ShortcutWidget(data, parent)
    if data.comp_type == TYPE_CALENDAR:
        return CalendarWidget(data, parent)
    if data.comp_type == TYPE_WEATHER:
        return WeatherWidget(data, parent)
    if data.comp_type == TYPE_DOCK:
        return DockWidget(data, parent)
    if data.comp_type == TYPE_TODO:
        return TodoWidget(data, parent)
    if data.comp_type == TYPE_CLOCK:
        return ClockWidget(data, parent)
    if data.comp_type == TYPE_MONITOR:
        return MonitorWidget(data, parent)
    if data.comp_type == TYPE_LAUNCHER:
        return LauncherWidget(data, parent)
    if data.comp_type == TYPE_NOTE:
        return NoteWidget(data, parent)
    if data.comp_type == TYPE_QUICKACTION:
        return QuickActionWidget(data, parent)
    if data.comp_type == TYPE_MEDIA:
        return MediaWidget(data, parent)
    if data.comp_type == TYPE_CLIPBOARD:
        return ClipboardWidget(data, parent)
    if data.comp_type == TYPE_TIMER:
        return TimerWidget(data, parent)
    if data.comp_type == TYPE_GALLERY:
        return GalleryWidget(data, parent)
    if data.comp_type == TYPE_SYSINFO:
        return SysInfoWidget(data, parent)
    if data.comp_type == TYPE_BOOKMARK:
        return BookmarkWidget(data, parent)
    if data.comp_type == TYPE_CALC:
        return CalcWidget(data, parent)
    if data.comp_type == TYPE_TRASH:
        return TrashWidget(data, parent)
    if data.comp_type == TYPE_RSS:
        return RSSWidget(data, parent)
    return CmdWidget(data, parent)


# ---------------------------------------------------------------------------
# Grid Panel
# ---------------------------------------------------------------------------

