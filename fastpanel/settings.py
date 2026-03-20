import os
import json
from fastpanel.constants import _BASE_DIR, THEMES

SETTINGS_FILE = os.path.join(_BASE_DIR, "settings.json")

def _load_settings():
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _save_settings(s):
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(s, ensure_ascii=False, indent=2, fp=f)
    except Exception:
        pass

_settings = _load_settings()
C = dict(THEMES.get(_settings.get("theme", "Catppuccin Mocha"), THEMES["Catppuccin Mocha"]))
