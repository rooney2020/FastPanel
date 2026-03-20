import json
import os
import re
import subprocess
import urllib.request
import threading
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QDialog, QFormLayout, QLineEdit
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFont, QColor

from fastpanel.constants import GRID_SIZE, _BASE_DIR
from fastpanel.settings import C, _settings
from fastpanel.utils import _input_dialog
from fastpanel.theme import _comp_style, _bg, _dialog_style, _scrollbar_style
from fastpanel.widgets.base import CompBase

class RSSWidget(CompBase):
    def __init__(self, data, parent=None):
        super().__init__(data, parent)
        self._feeds: list[dict] = []
        self._items: list[dict] = []
        self._load_feeds()
        self._build_ui()
        QTimer.singleShot(500, self._fetch_all)

    def _load_feeds(self):
        try:
            if self.data.cmd:
                self._feeds = json.loads(self.data.cmd)
        except Exception:
            self._feeds = [{"name": "Hacker News", "url": "https://hnrss.org/frontpage?count=10"}]

    def _save_feeds(self):
        self.data.cmd = json.dumps(self._feeds, ensure_ascii=False)

    def _build_ui(self):
        lay = QVBoxLayout(self); lay.setContentsMargins(12, 10, 12, 10); lay.setSpacing(6)
        hdr = QHBoxLayout()
        title = QLabel("📰 RSS 阅读器")
        title.setStyleSheet(f"color:{C['text']};font-size:14px;font-weight:bold;background:transparent;")
        hdr.addWidget(title); hdr.addStretch()
        add_btn = QPushButton("＋"); add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.setStyleSheet(f"background:{C['blue']};color:{C['crust']};border:none;border-radius:8px;"
                              f"font-size:14px;padding:4px 12px;font-weight:bold;")
        add_btn.clicked.connect(self._add_feed)
        hdr.addWidget(add_btn)
        refresh_btn = QPushButton("↻"); refresh_btn.setCursor(Qt.PointingHandCursor)
        refresh_btn.setStyleSheet(f"background:{_bg('surface1')};color:{C['text']};border:none;border-radius:8px;"
                                  f"font-size:14px;padding:4px 12px;")
        refresh_btn.clicked.connect(self._fetch_all)
        hdr.addWidget(refresh_btn)
        lay.addLayout(hdr)
        self._status = QLabel("")
        self._status.setStyleSheet(f"color:{C['subtext0']};font-size:10px;background:transparent;")
        lay.addWidget(self._status)
        sc = QScrollArea(); sc.setWidgetResizable(True)
        sc.setStyleSheet(f"QScrollArea{{background:transparent;border:none;}}QScrollArea > QWidget{{background:transparent;}}{_scrollbar_style(6)}")
        sc.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._list_w = QWidget()
        self._list_w.setStyleSheet("background:transparent;")
        self._list_lay = QVBoxLayout(self._list_w); self._list_lay.setContentsMargins(0, 0, 0, 0)
        self._list_lay.setSpacing(4); self._list_lay.addStretch()
        sc.setWidget(self._list_w)
        lay.addWidget(sc)

    def _add_feed(self):
        ok, url = _input_dialog(self, "添加 RSS 源", "RSS URL：", "https://")
        if not ok or not url:
            return
        ok2, name = _input_dialog(self, "添加 RSS 源", "名称（可选）：")
        self._feeds.append({"name": name or (url.split("/")[2] if len(url.split("/")) > 2 else "Feed"), "url": url})
        self._save_feeds()
        self._fetch_all()

    def _fetch_all(self):
        self._status.setText("加载中...")
        self._items = []
        t = threading.Thread(target=self._fetch_worker, daemon=True)
        t.start()

    def _fetch_worker(self):
        items = []
        for feed in self._feeds:
            try:
                req = urllib.request.Request(feed["url"], headers={"User-Agent": "FastPanel/1.0"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = resp.read().decode("utf-8", errors="replace")
                items.extend(self._parse_rss(data, feed.get("name", "")))
            except Exception:
                pass
        self._items = items[:30]
        QTimer.singleShot(0, self._rebuild)

    @staticmethod
    def _parse_rss(xml_text, source=""):
        items = []
        import re
        for m in re.finditer(r'<item>(.*?)</item>', xml_text, re.DOTALL):
            block = m.group(1)
            title_m = re.search(r'<title>(.*?)</title>', block, re.DOTALL)
            link_m = re.search(r'<link>(.*?)</link>', block, re.DOTALL)
            if title_m:
                title = title_m.group(1).strip()
                title = re.sub(r'<!\[CDATA\[(.*?)\]\]>', r'\1', title)
                link = link_m.group(1).strip() if link_m else ""
                link = re.sub(r'<!\[CDATA\[(.*?)\]\]>', r'\1', link)
                items.append({"title": title, "link": link, "source": source})
        return items

    def _rebuild(self):
        while self._list_lay.count() > 1:
            item = self._list_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._status.setText(f"{len(self._items)} 条 · {len(self._feeds)} 个源")
        for i, item in enumerate(self._items):
            row = QFrame()
            row.setStyleSheet(f"QFrame{{background:{_bg('surface0')};border-radius:6px;}}"
                              f"QFrame:hover{{background:{_bg('surface1')};}}")
            rl = QVBoxLayout(row); rl.setContentsMargins(8, 6, 8, 6); rl.setSpacing(2)
            title = QLabel(item["title"])
            title.setWordWrap(True); title.setCursor(Qt.PointingHandCursor)
            title.setStyleSheet(f"color:{C['text']};font-size:11px;background:transparent;")
            title.mousePressEvent = lambda e, url=item.get("link", ""): self._open(url)
            rl.addWidget(title)
            if item.get("source"):
                src = QLabel(item["source"])
                src.setStyleSheet(f"color:{C['overlay0']};font-size:9px;background:transparent;")
                rl.addWidget(src)
            self._list_lay.insertWidget(i, row)

    def _open(self, url):
        if url:
            try:
                subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass

    def refresh_theme(self):
        saved_items = list(self._items)
        super().refresh_theme()
        self._items = saved_items
        if self._items:
            self._rebuild()
        else:
            QTimer.singleShot(500, self._fetch_all)



