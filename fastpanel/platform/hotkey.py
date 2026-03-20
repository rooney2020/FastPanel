import sys
import threading
from PyQt5.QtCore import QObject, pyqtSignal

class _HotkeySignalBridge(QObject):
    triggered = pyqtSignal(str)

class _HotkeyManager:
    _instance = None

    def __init__(self):
        self._bindings: dict[str, callable] = {}
        self._running = False
        self._bridge = _HotkeySignalBridge()
        self._bridge.triggered.connect(self._fire)

    @classmethod
    def create(cls):
        if cls._instance:
            return cls._instance
        if sys.platform == "linux":
            try:
                inst = _X11HotkeyManager()
                cls._instance = inst
                return inst
            except Exception:
                pass
        inst = _HotkeyManager()
        cls._instance = inst
        return inst

    def register(self, key_str: str, callback: callable):
        self._bindings[key_str] = callback

    def unregister(self, key_str: str):
        self._bindings.pop(key_str, None)

    def start(self):
        pass

    def stop(self):
        self._running = False

    def _fire(self, key_str):
        cb = self._bindings.get(key_str)
        if cb:
            print(f"[Hotkey] Executing callback for: {key_str}", flush=True)
            cb()


class _X11HotkeyManager(_HotkeyManager):
    _MOD_MAP = {
        "ctrl": "control", "control": "control",
        "alt": "mod1", "mod1": "mod1",
        "shift": "shift",
        "super": "mod4", "win": "mod4", "mod4": "mod4",
    }

    def __init__(self):
        super().__init__()
        from Xlib import X, display as xdisplay, XK
        self._X = X
        self._XK = XK
        self._display = xdisplay.Display()
        self._display.set_error_handler(self._x_error_handler)
        self._root = self._display.screen().root
        self._grabbed_keys: list[tuple] = []
        self._thread = None
        self._grab_failures: list[str] = []

    @staticmethod
    def _x_error_handler(err, *args):
        pass

    def _parse_hotkey(self, key_str: str):
        from Xlib import X, XK
        parts = [p.strip().lower() for p in key_str.split("+")]
        mod_mask = 0
        keycode = 0
        mod_bits = {"control": X.ControlMask, "shift": X.ShiftMask,
                     "mod1": X.Mod1Mask, "mod4": X.Mod4Mask}
        for p in parts:
            mapped = self._MOD_MAP.get(p)
            if mapped and mapped in mod_bits:
                mod_mask |= mod_bits[mapped]
            else:
                keysym = XK.string_to_keysym(p.capitalize() if len(p) == 1 else p)
                if keysym == 0:
                    keysym = XK.string_to_keysym(p)
                if keysym == 0:
                    _sym_map = {
                        "f1": "F1", "f2": "F2", "f3": "F3", "f4": "F4",
                        "f5": "F5", "f6": "F6", "f7": "F7", "f8": "F8",
                        "f9": "F9", "f10": "F10", "f11": "F11", "f12": "F12",
                        "space": "space", "return": "Return", "enter": "Return",
                        "escape": "Escape", "esc": "Escape", "tab": "Tab",
                        "backspace": "BackSpace", "delete": "Delete",
                        "up": "Up", "down": "Down", "left": "Left", "right": "Right",
                        "home": "Home", "end": "End", "pageup": "Prior", "pagedown": "Next",
                    }
                    mapped_name = _sym_map.get(p, p)
                    keysym = XK.string_to_keysym(mapped_name)
                if keysym != 0:
                    keycode = self._display.keysym_to_keycode(keysym)
        return keycode, mod_mask

    def register(self, key_str: str, callback: callable):
        super().register(key_str, callback)
        keycode, mod_mask = self._parse_hotkey(key_str)
        if keycode == 0:
            self._grab_failures.append(key_str)
            print(f"[Hotkey] Failed to parse: {key_str}", flush=True)
            return
        from Xlib import X
        try:
            for extra in [0, X.Mod2Mask, X.LockMask, X.Mod2Mask | X.LockMask]:
                self._root.grab_key(keycode, mod_mask | extra, True,
                                    X.GrabModeAsync, X.GrabModeAsync)
            self._grabbed_keys.append((keycode, mod_mask, key_str))
            self._display.sync()
            print(f"[Hotkey] Registered: {key_str} (keycode={keycode}, mask={mod_mask})", flush=True)
        except Exception as e:
            self._grab_failures.append(key_str)
            print(f"[Hotkey] Grab failed for {key_str}: {e}", flush=True)

    def unregister(self, key_str: str):
        super().unregister(key_str)
        to_remove = [(kc, mm, ks) for kc, mm, ks in self._grabbed_keys if ks == key_str]
        from Xlib import X
        for kc, mm, _ks in to_remove:
            for extra in [0, X.Mod2Mask, X.LockMask, X.Mod2Mask | X.LockMask]:
                try:
                    self._root.ungrab_key(kc, mm | extra)
                except Exception:
                    pass
        self._grabbed_keys = [(kc, mm, ks) for kc, mm, ks in self._grabbed_keys if ks != key_str]
        self._display.flush()

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._event_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        from Xlib import X
        for kc, mm, _ks in self._grabbed_keys:
            for extra in [0, X.Mod2Mask, X.LockMask, X.Mod2Mask | X.LockMask]:
                try:
                    self._root.ungrab_key(kc, mm | extra)
                except Exception:
                    pass
        self._grabbed_keys.clear()
        self._display.flush()

    def _event_loop(self):
        from Xlib import X
        self._root.change_attributes(event_mask=X.KeyPressMask)
        while self._running:
            try:
                count = self._display.pending_events()
                if count == 0:
                    import time
                    time.sleep(0.05)
                    continue
                ev = self._display.next_event()
                if ev.type == X.KeyPress:
                    clean_mask = ev.state & ~(X.Mod2Mask | X.LockMask)
                    matched = False
                    for kc, mm, ks in self._grabbed_keys:
                        if ev.detail == kc and clean_mask == mm:
                            print(f"[Hotkey] Fired: {ks}", flush=True)
                            self._bridge.triggered.emit(ks)
                            matched = True
                            break
                    if not matched:
                        print(f"[Hotkey] Unmatched key event: detail={ev.detail} state={ev.state} clean={clean_mask}", flush=True)
            except Exception:
                if not self._running:
                    break
                import time
                time.sleep(0.1)



