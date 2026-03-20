import os
from fastpanel.constants import _BASE_DIR

_AUTOSTART_DIR = os.path.expanduser("~/.config/autostart")
_AUTOSTART_FILE = os.path.join(_AUTOSTART_DIR, "fastpanel.desktop")
_APP_DESKTOP_DIR = os.path.expanduser("~/.local/share/applications")
_APP_DESKTOP_FILE = os.path.join(_APP_DESKTOP_DIR, "fastpanel.desktop")

def _desktop_entry_content(autostart=False):
    main_py = os.path.abspath(__file__)
    icon = os.path.join(os.path.dirname(main_py), "fastpanel.svg")
    entry = f"""[Desktop Entry]
Type=Application
Name=FastPanel
Comment=Desktop widget engine
Exec=python3 {main_py} --desktop
Icon={icon}
Terminal=false
Categories=Utility;
StartupNotify=false
"""
    if autostart:
        entry += "X-GNOME-Autostart-enabled=true\n"
    return entry

def _is_autostart_enabled():
    return os.path.isfile(_AUTOSTART_FILE)

def _set_autostart(enabled: bool):
    if enabled:
        os.makedirs(_AUTOSTART_DIR, exist_ok=True)
        with open(_AUTOSTART_FILE, "w") as f:
            f.write(_desktop_entry_content(autostart=True))
    else:
        if os.path.isfile(_AUTOSTART_FILE):
            os.remove(_AUTOSTART_FILE)

def _install_desktop_entry():
    os.makedirs(_APP_DESKTOP_DIR, exist_ok=True)
    with open(_APP_DESKTOP_FILE, "w") as f:
        f.write(_desktop_entry_content())

# ---------------------------------------------------------------------------
# Global Hotkey Manager (X11 via python-xlib, fallback: noop)
# ---------------------------------------------------------------------------

