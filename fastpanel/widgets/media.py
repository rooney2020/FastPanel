import subprocess
import json
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QColor, QIcon, QPixmap

from fastpanel.constants import GRID_SIZE
from fastpanel.settings import C, _settings
from fastpanel.theme import _comp_style, _bg
from fastpanel.widgets.base import CompBase

class MediaWidget(CompBase):
    def __init__(self, data, parent=None):
        super().__init__(data, parent)
        self._title = ""; self._artist = ""; self._album = ""
        self._playing = False; self._art_pixmap = None
        self._timer = QTimer(self); self._timer.timeout.connect(self._tick); self._timer.start(1500)
        self._build_ui()
        QTimer.singleShot(100, self._tick)

    def _build_ui(self):
        lay = QVBoxLayout(self); lay.setContentsMargins(16, 12, 16, 12); lay.setSpacing(6)
        top = QHBoxLayout(); top.setSpacing(12)
        self._art_label = QLabel(); self._art_label.setFixedSize(60, 60)
        self._art_label.setStyleSheet(f"background: {_bg('surface1')}; border-radius: 8px;")
        self._art_label.setAlignment(Qt.AlignCenter)
        top.addWidget(self._art_label)
        info = QVBoxLayout(); info.setSpacing(2)
        self._title_lbl = QLabel("无媒体播放")
        self._title_lbl.setStyleSheet(f"color:{C['text']};font-size:14px;font-weight:bold;background:transparent;")
        self._artist_lbl = QLabel("")
        self._artist_lbl.setStyleSheet(f"color:{C['subtext0']};font-size:11px;background:transparent;")
        self._album_lbl = QLabel("")
        self._album_lbl.setStyleSheet(f"color:{C['overlay0']};font-size:10px;background:transparent;")
        info.addWidget(self._title_lbl); info.addWidget(self._artist_lbl); info.addWidget(self._album_lbl)
        info.addStretch()
        top.addLayout(info); top.addStretch()
        lay.addLayout(top)
        btns = QHBoxLayout(); btns.setSpacing(12); btns.addStretch()
        _media_icons = [
            ("media-skip-backward", "Previous", 36),
            ("media-playback-start", "PlayPause", 44),
            ("media-skip-forward", "Next", 36),
        ]
        self._play_btn = None
        for icon_name, cmd, sz in _media_icons:
            b = QPushButton(); b.setFixedSize(sz, sz); b.setCursor(Qt.PointingHandCursor)
            qicon = QIcon.fromTheme(icon_name)
            if not qicon.isNull():
                b.setIcon(qicon)
                b.setIconSize(b.size() * 0.55)
            else:
                fallback = {"Previous": "◂◂", "PlayPause": "▶", "Next": "▸▸"}
                b.setText(fallback.get(cmd, "?"))
            is_main = (cmd == "PlayPause")
            if is_main:
                b.setStyleSheet(f"""QPushButton {{background:{C['blue']};color:{C['crust']};
                    border:none;border-radius:{sz // 2}px;}}
                    QPushButton:hover {{background:{C['lavender']};}}""")
                self._play_btn = b
            else:
                b.setStyleSheet(f"""QPushButton {{background:{_bg('surface1')};color:{C['text']};
                    border:none;border-radius:{sz // 2}px;}}
                    QPushButton:hover {{background:{C['surface2']};}}""")
            b.clicked.connect(lambda _, c=cmd: self._mpris_cmd(c))
            btns.addWidget(b)
        btns.addStretch()
        lay.addLayout(btns)

    def _mpris_cmd(self, method):
        try:
            subprocess.Popen(
                ["dbus-send", "--print-reply", "--dest=org.mpris.MediaPlayer2.*",
                 "/org/mpris/MediaPlayer2", f"org.mpris.MediaPlayer2.Player.{method}"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            players = self._get_players()
            if players:
                try:
                    subprocess.Popen(
                        ["dbus-send", "--print-reply", f"--dest={players[0]}",
                         "/org/mpris/MediaPlayer2", f"org.mpris.MediaPlayer2.Player.{method}"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                except Exception:
                    pass

    def _get_players(self):
        try:
            out = subprocess.check_output(
                ["dbus-send", "--session", "--dest=org.freedesktop.DBus",
                 "--type=method_call", "--print-reply",
                 "/org/freedesktop/DBus", "org.freedesktop.DBus.ListNames"],
                timeout=2, stderr=subprocess.DEVNULL).decode()
            return [line.strip().strip('"') for line in out.split('\n')
                    if 'org.mpris.MediaPlayer2.' in line]
        except Exception:
            return []

    def _tick(self):
        players = self._get_players()
        if not players:
            self._title_lbl.setText("无媒体播放"); self._artist_lbl.setText(""); self._album_lbl.setText("")
            return
        player = players[0]
        try:
            out = subprocess.check_output(
                ["dbus-send", "--session", "--print-reply", f"--dest={player}",
                 "/org/mpris/MediaPlayer2",
                 "org.freedesktop.DBus.Properties.Get",
                 "string:org.mpris.MediaPlayer2.Player", "string:Metadata"],
                timeout=2, stderr=subprocess.DEVNULL).decode()
            title = self._extract_meta(out, "xesam:title")
            artist = self._extract_meta(out, "xesam:artist")
            album = self._extract_meta(out, "xesam:album")
            self._title_lbl.setText(title or "未知曲目")
            self._artist_lbl.setText(artist or "")
            self._album_lbl.setText(album or "")
        except Exception:
            pass

    def refresh_theme(self):
        super().refresh_theme()
        self._timer = QTimer(self); self._timer.timeout.connect(self._tick); self._timer.start(1500)
        QTimer.singleShot(100, self._tick)

    @staticmethod
    def _extract_meta(raw, key):
        idx = raw.find(key)
        if idx < 0:
            return ""
        sub = raw[idx:]
        for marker in ['string "', 'variant       string "']:
            si = sub.find(marker)
            if si >= 0:
                start = si + len(marker)
                end = sub.find('"', start)
                if end > start:
                    return sub[start:end]
        return ""


# ---------------------------------------------------------------------------
# Clipboard Manager Widget
# ---------------------------------------------------------------------------

