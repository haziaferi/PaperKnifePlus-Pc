"""
paperknife.qt.home
The Home page: quick actions and the recent-files grid.

Thumbnails are rendered here with PyMuPDF (paperknife.recent.get_thumb
returns a CTkImage, which Qt cannot use) on a worker thread: the file is
looked at and rendered into a QImage there, and the QPixmap is made on the
UI thread, so a file on an offline share or a huge scan never holds the
window while the stat or the render runs.
"""
from __future__ import annotations

import os
import threading
from pathlib import Path

import pymupdf as fitz
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget
from qfluentwidgets import BodyLabel, CardWidget, FlowLayout, PushButton, TransparentPushButton

from . import bridge, dialogs
from . import theme
from .pages import ToolPage, group_title, muted_caption
from ..recent import RECENT, time_ago

try:
    from shiboken6 import isValid as _is_valid
except ImportError:                     # pragma: no cover
    def _is_valid(obj) -> bool:
        return True

THUMB_BOX = (100, 130)
QUICK_ACTIONS = ("ReaderTool", "MergeTool", "SplitTool", "PasswordTool", "CompressTool",
                 "AnnotateTool", "OCRTool")

_THUMB_CACHE: dict[tuple, QPixmap | None] = {}
_THUMB_CACHE_MAX = 64


def _thumb_key(path: str, box=THUMB_BOX) -> tuple | None:
    """The cache key of *path* (it changes with the file); None when the file
    cannot be reached.  Safe on a worker thread."""
    try:
        mtime = os.stat(path).st_mtime_ns
    except OSError:
        return None
    return (path, tuple(box), mtime)


def _render_image(path: str, box=THUMB_BOX) -> QImage | None:
    """The first page fitted into *box* (logical px) at 2x, as a QImage (no
    QPixmap: this runs on a worker thread); None when it cannot be read."""
    try:
        with fitz.open(path) as doc:
            if doc.is_encrypted or len(doc) == 0:
                return None
            page = doc[0]
            zoom = 2 * min(box[0] / page.rect.width, box[1] / page.rect.height)
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
            return QImage(pix.samples, pix.width, pix.height, pix.stride,
                          QImage.Format_RGB888).copy()
    except Exception:
        return None


def _cache_pixmap(key: tuple, img: QImage | None) -> QPixmap | None:
    """UI thread: the QPixmap for *img*, remembered under *key*."""
    pm = None
    if img is not None:
        pm = QPixmap.fromImage(img)
        pm.setDevicePixelRatio(2.0)
    if len(_THUMB_CACHE) >= _THUMB_CACHE_MAX:
        _THUMB_CACHE.pop(next(iter(_THUMB_CACHE)))
    _THUMB_CACHE[key] = pm
    return pm


def render_thumb(path: str, box=THUMB_BOX) -> QPixmap | None:
    """The first page of *path* fitted into *box* (logical px), rendered at
    2x for sharpness at 200 % scaling; None when it cannot be read.
    UI thread, blocking (HomePage renders on a worker instead)."""
    key = _thumb_key(path, box)
    if key is None:
        return None
    if key in _THUMB_CACHE:
        return _THUMB_CACHE[key]
    return _cache_pixmap(key, _render_image(path, box))


def _framed(pm: QPixmap) -> QPixmap:
    """The page with a hairline border, so a white page reads on a white card."""
    from PySide6.QtGui import QPainter
    out = QPixmap(pm)
    p = QPainter(out)
    p.setPen(theme.color("thumb_border"))
    r = out.rect()
    p.drawRect(r.adjusted(0, 0, -1, -1))
    p.end()
    return out


def _short(name: str, n: int = 22) -> str:
    return name if len(name) <= n else name[:n - 3] + "…"


def _thumb_worker(jobs, stop: threading.Event) -> None:
    """Worker: stat and render each recent file, posting the result to the UI
    thread one card at a time; stops when a newer refresh started."""
    for card, path in jobs:
        if stop.is_set():
            return
        key = _thumb_key(path)
        if key is None:
            bridge.post(_show_thumb, stop, card, None, None, False)
        elif key in _THUMB_CACHE:
            bridge.post(_show_thumb, stop, card, key, None, True)
        else:
            bridge.post(_show_thumb, stop, card, key, _render_image(path), False)


def _show_thumb(stop, card, key, img, cached) -> None:
    """UI thread: put a worker's thumbnail on its card (if it still exists)."""
    if stop.is_set() or not _is_valid(card):
        return
    if key is None:
        pm = None
    elif cached and key in _THUMB_CACHE:
        pm = _THUMB_CACHE[key]
    elif cached:                         # evicted meanwhile: render it here
        pm = render_thumb(card.path)
    else:
        pm = _cache_pixmap(key, img)
    card.show_thumb(pm)


class RecentCard(CardWidget):
    """One recent file: thumbnail, name, pages / size / time ago."""

    def __init__(self, entry: dict, on_open, parent=None):
        super().__init__(parent)
        self.path = entry["path"]
        self.setFixedWidth(THUMB_BOX[0] + 40)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(self.path)
        v = QVBoxLayout(self)
        v.setContentsMargins(12, 12, 12, 10)
        v.setSpacing(4)
        self.thumb = QLabel(self)
        self.thumb.setFixedSize(QSize(*THUMB_BOX))
        self.thumb.setAlignment(Qt.AlignCenter)
        self.thumb.setObjectName("recentThumb")
        v.addWidget(self.thumb, 0, Qt.AlignHCenter)
        name = entry.get("name") or Path(self.path).name
        self.name_label = BodyLabel(_short(name), self)
        v.addWidget(self.name_label)
        meta = []
        if entry.get("pages"):
            meta.append(f"{entry['pages']} pp")
        if entry.get("size_kb"):
            meta.append(f"{entry['size_kb']} KB")
        ago = time_ago(entry.get("accessed", ""))
        if ago:
            meta.append(ago)
        self.meta_label = muted_caption("  ·  ".join(meta), self)
        v.addWidget(self.meta_label)
        self.clicked.connect(lambda: on_open(self.path))

    def load_thumb(self):
        self.show_thumb(render_thumb(self.path))

    def show_thumb(self, pm: QPixmap | None):
        if pm is not None:
            self.thumb.setPixmap(_framed(pm))
        else:
            self.thumb.setPixmap(theme.glyph_icon(0xE8A5, 40, "muted").pixmap(40, 40))


class HomePage(ToolPage):
    def __init__(self, window=None):
        super().__init__("PaperKnife+ PC", "100 % local  ·  no cloud  ·  no tracking",
                         window=window)
        self.setObjectName("home")
        self._thumb_stop = threading.Event()      # set: the running thumbnail pass is stale

        # Quick actions
        self.body.addWidget(group_title("Quick actions"))
        qa = QWidget(self.content)
        self.quick = FlowLayout(qa, needAni=False)
        self.quick.setContentsMargins(0, 0, 0, 0)
        self.quick.setHorizontalSpacing(8)
        self.quick.setVerticalSpacing(8)
        self.quick_buttons: dict[str, PushButton] = {}
        self.body.addWidget(qa)

        # Recent files
        head = QHBoxLayout()
        head.addWidget(group_title("Recent files"))
        head.addStretch(1)
        self.clear_button = TransparentPushButton("Clear history", self.content)
        self.clear_button.clicked.connect(self.clear_history)
        head.addWidget(self.clear_button, 0, Qt.AlignBottom)
        self.body.addLayout(head)
        self.empty_label = muted_caption("Open a PDF with any tool to see it here.")
        self.body.addWidget(self.empty_label)
        grid_host = QWidget(self.content)
        self.grid = FlowLayout(grid_host, needAni=False)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(12)
        self.grid.setVerticalSpacing(12)
        self.body.addWidget(grid_host)
        self.body.addStretch(1)
        self.cards: list[RecentCard] = []

    # ── content ──
    def build_quick_actions(self, tools):
        """tools: the registry; a button for each QUICK_ACTIONS tool present."""
        from .shell import NAV_GLYPH
        from .pages import plain_label
        by_name = {type(t).__name__: t for t in tools}
        for cls in QUICK_ACTIONS:
            t = by_name.get(cls)
            if t is None or cls in self.quick_buttons:
                continue
            b = PushButton(theme.Glyph(NAV_GLYPH.get(cls, 0xE8A5)), plain_label(t.label))
            b.setMinimumHeight(40)
            b.clicked.connect(lambda _=False, c=cls: self._open_tool(c))
            self.quick.addWidget(b)
            self.quick_buttons[cls] = b

    def _open_tool(self, cls: str, path: str | None = None):
        if self.window_ is not None:
            self.window_.open_tool(cls, path)

    def refresh(self):
        """Rebuild the grid from RECENT; thumbnails follow one per loop turn."""
        for c in self.cards:
            self.grid.removeWidget(c)
            c.deleteLater()
        self.cards = []
        entries = RECENT.all()
        self.empty_label.setVisible(not entries)
        self.clear_button.setVisible(bool(entries))
        for e in entries:
            c = RecentCard(e, lambda p: self._open_tool("ReaderTool", p), self.content)
            self.grid.addWidget(c)
            self.cards.append(c)
        self._thumb_stop.set()
        self._thumb_stop = stop = threading.Event()
        jobs = [(c, c.path) for c in self.cards]
        if jobs:
            threading.Thread(target=_thumb_worker, args=(jobs, stop),
                             name="home-thumbs", daemon=True).start()

    def clear_history(self):
        if dialogs.ask_yes_no("Clear history", "Remove all recent file entries?"):
            RECENT.clear()
            self.refresh()

    # ── shell hooks ──
    def activate(self):
        self.refresh()

    def accept_drop(self, path: str) -> bool:
        """A PDF dropped on Home opens in the Reader."""
        if Path(path).suffix.lower() == ".pdf" and os.path.isfile(path):
            self._open_tool("ReaderTool", path)
            return True
        return False
