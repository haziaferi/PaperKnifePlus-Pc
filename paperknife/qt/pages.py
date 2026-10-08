"""
paperknife.qt.pages
The page frame every tool page uses, its building blocks, and the registry
the shell's page factory reads.

A tool's Qt page registers itself by the tool's class name:

    from paperknife.qt.pages import ToolPage, register_page

    @register_page("CompressTool")
    class CompressPage(ToolPage):
        def __init__(self, tool, window):
            super().__init__("Compress", "Reduce file size …", tool=tool, window=window)
            ...

and MainWindow.page_for(tool) builds it the first time the tool is opened.
A tool with no registered page gets a PlaceholderPage.

Optional hooks the shell calls when a page defines them:
    open() / save() / undo()     Ctrl+O / Ctrl+S / Ctrl+Z
    delete()                     Delete (not while a text field has focus)
    accept_drop(path) -> bool    a file dropped on the window (ToolPage
                                 forwards it to its file cards)
    activate() / deactivate()    the page is shown / left
    open_path(path)              open this file (a Home recent-file click)
"""
from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QFrame, QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget
from qfluentwidgets import (BodyLabel, CaptionLabel, IconWidget, PrimaryPushButton, PushButton,
                            SimpleCardWidget, SingleDirectionScrollArea, StrongBodyLabel,
                            TitleLabel, setCustomStyleSheet)

from . import dialogs
from . import theme

# ── Registry ──────────────────────────────────────────────────────────────────
QT_PAGES: dict[str, type] = {}


def register_page(class_name: str):
    """Class decorator: QT_PAGES[class_name] = the page class."""
    def deco(cls):
        QT_PAGES[class_name] = cls
        return cls
    return deco


def plain_label(label: str) -> str:
    """A tool's sidebar label without its leading emoji and spacing."""
    i = 0
    while i < len(label) and not label[i].isalnum():
        i += 1
    return label[i:].strip()


def action_placement() -> str:
    """Where the main action goes: "header" (top right, the default) or
    "bar" (a command bar at the bottom), from env PK_ACTION."""
    v = os.environ.get("PK_ACTION", "header").strip().lower()
    return v if v in ("header", "bar") else "header"


# Layout constants (4 px grid)
PAGE_MARGINS = (32, 20, 32, 16)
LABEL_COLUMN = 320          # setting rows: width of the name / description column
ROW_MIN_HEIGHT = 64
ACTION_SIZE = (160, 36)


# ── Small widgets ─────────────────────────────────────────────────────────────
class Divider(QWidget):
    """A 1 px line in the theme's divider colour (repainted on theme change)."""

    def __init__(self, vertical: bool = False, parent=None):
        super().__init__(parent)
        if vertical:
            self.setFixedWidth(1)
            self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        else:
            self.setFixedHeight(1)
            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.fillRect(self.rect(), theme.color("divider"))


def muted_caption(text: str = "", parent=None) -> CaptionLabel:
    lbl = CaptionLabel(text, parent)
    lbl.setTextColor(*theme.pair("muted"))
    return lbl


def card(padding: int = 16) -> SimpleCardWidget:
    """A plain card with a vertical layout (card.layout())."""
    c = SimpleCardWidget()
    v = QVBoxLayout(c)
    v.setContentsMargins(padding, padding, padding, padding)
    v.setSpacing(8 if padding else 0)
    return c


def group_title(text: str) -> StrongBodyLabel:
    """The heading above a card of setting rows."""
    lbl = StrongBodyLabel(text)
    lbl.setContentsMargins(0, 16, 0, 4)
    return lbl


def setting_row(group: QWidget, title: str, desc: str = "") -> QWidget:
    """Add a Windows 11 settings row to *group* (a card()) and return the
    container for its control: the name and description sit in a fixed-width
    column on the left, the control right-aligned, rows split by thin lines.

        row = setting_row(level_card, "Level", "How hard to compress")
        row.layout().addWidget(combo)
    """
    lay = group.layout()
    rows = int(group.property("pk_rows") or 0)
    if rows == 0:
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
    else:
        lay.addWidget(Divider())
    row = QWidget(group)
    row.setObjectName("settingRow")
    row.setMinimumHeight(ROW_MIN_HEIGHT)
    h = QHBoxLayout(row)
    h.setContentsMargins(16, 10, 16, 10)
    h.setSpacing(16)
    texts = QWidget(row)
    texts.setFixedWidth(LABEL_COLUMN)
    tv = QVBoxLayout(texts)
    tv.setContentsMargins(0, 0, 0, 0)
    tv.setSpacing(2)
    tv.addStretch(1)
    name = BodyLabel(title, texts)
    tv.addWidget(name)
    if desc:
        d = muted_caption(desc, texts)
        d.setWordWrap(True)
        tv.addWidget(d)
    tv.addStretch(1)
    h.addWidget(texts)
    h.addStretch(1)
    control = QWidget(row)
    control.setObjectName("settingControl")
    ch = QHBoxLayout(control)
    ch.setContentsMargins(0, 0, 0, 0)
    ch.setSpacing(8)
    ch.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    h.addWidget(control, 0, Qt.AlignRight | Qt.AlignVCenter)
    lay.addWidget(row)
    group.setProperty("pk_rows", rows + 1)
    row.title_label = name
    return control


def _fmt_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.0f} KB"
    return f"{n / (1024 * 1024):.1f} MB"


class FileCard(SimpleCardWidget):
    """The file a single-file tool works on.

    Empty: a drop-zone line and Choose file.  Filled: the name, size and
    folder, and Change.  accept_drop(path) takes a dropped file of one of
    *exts* (case-insensitive; empty = any file)."""

    def __init__(self, on_change=None, exts=(".pdf",), parent=None):
        super().__init__(parent)
        self.setObjectName("fileCard")
        self._on_change = on_change
        self.exts = tuple(e.lower() for e in (exts or ()))
        self._path = ""
        h = QHBoxLayout(self)
        h.setContentsMargins(16, 12, 16, 12)
        h.setSpacing(12)
        self.icon = IconWidget(theme.Glyph(0xE8A5), self)       # Document
        self.icon.setFixedSize(24, 24)
        h.addWidget(self.icon)
        texts = QVBoxLayout()
        texts.setSpacing(2)
        self.name_label = BodyLabel(self)
        self.meta_label = muted_caption("", self)
        texts.addWidget(self.name_label)
        texts.addWidget(self.meta_label)
        h.addLayout(texts, 1)
        self.button = PushButton("Choose file", self)
        self.button.clicked.connect(self.choose)
        h.addWidget(self.button, 0, Qt.AlignVCenter)
        self.setMinimumHeight(68)
        self._show_empty()

    # ── state ──
    def path(self) -> str:
        return self._path

    def _kind(self) -> str:
        if self.exts == (".pdf",):
            return "a PDF"
        if not self.exts:
            return "a file"
        return "a " + " / ".join(e.lstrip(".").upper() for e in self.exts) + " file"

    def _show_empty(self):
        self.name_label.setText(f"Drop {self._kind()} here")
        self.meta_label.setText("or choose one from a folder")
        self.button.setText("Choose file")

    def _show_file(self, path: str):
        p = Path(path)
        try:
            size = _fmt_size(p.stat().st_size)
        except OSError:
            size = "?"
        self.name_label.setText(p.name)
        self.meta_label.setText(f"{size}  ·  {p.parent}")
        self.meta_label.setToolTip(str(p))
        self.button.setText("Change")

    def set_path(self, path: str, notify: bool = True):
        self._path = str(path) if path else ""
        if self._path:
            self._show_file(self._path)
        else:
            self._show_empty()
        if notify and self._on_change is not None:
            self._on_change(self._path)

    def clear(self):
        self.set_path("", notify=False)

    def accepts(self, path: str) -> bool:
        return os.path.isfile(path) and (not self.exts or Path(path).suffix.lower() in self.exts)

    def accept_drop(self, path: str) -> bool:
        if not self.accepts(path):
            return False
        self.set_path(path)
        return True

    def choose(self):
        if self.exts:
            pats = " ".join(f"*{e}" for e in self.exts)
            label = "PDF" if self.exts == (".pdf",) else "Supported files"
            filters = [(label, pats)]
        else:
            filters = None
        p = dialogs.ask_open("Choose file", filters)
        if p:
            self.set_path(p)


def file_card(on_change=None, exts=(".pdf",)) -> FileCard:
    return FileCard(on_change, exts)


# ── The page frame ────────────────────────────────────────────────────────────
class ToolPage(QWidget):
    """Header (title 28 px semibold, subtitle 12 px muted, an actions area),
    the body, and the main action in ONE place set by env PK_ACTION:
    "header" puts it at the header's right, "bar" in a command bar at the
    bottom.  primary() / secondary() add buttons to that place.

    self.body is the QVBoxLayout tool content goes into; scroll=True wraps
    it in a vertical scroll area (single-file transforms), scroll=False
    gives the full height (workspaces)."""

    def __init__(self, title: str, subtitle: str = "", *, tool=None, window=None,
                 scroll: bool = True, parent=None):
        super().__init__(parent)
        self.tool = tool
        self.window_ = window
        self.placement = action_placement()
        self._compact = False
        self._buttons: list = []

        v = QVBoxLayout(self)
        v.setContentsMargins(*PAGE_MARGINS)
        v.setSpacing(0)

        # Header
        self.header = QWidget(self)
        self.header.setObjectName("pageHeader")
        hh = QHBoxLayout(self.header)
        hh.setContentsMargins(0, 0, 0, 16)
        hh.setSpacing(8)
        titles = QVBoxLayout()
        titles.setSpacing(0)
        self.title_label = TitleLabel(title, self.header)
        self.subtitle_label = muted_caption(subtitle, self.header)
        self.subtitle_label.setVisible(bool(subtitle))
        titles.addWidget(self.title_label)
        titles.addWidget(self.subtitle_label)
        hh.addLayout(titles)
        hh.addStretch(1)
        self.header_actions = QHBoxLayout()
        self.header_actions.setSpacing(8)
        hh.addLayout(self.header_actions)
        v.addWidget(self.header)

        # Body
        content = QWidget()
        content.setObjectName("pageBody")
        self.body = QVBoxLayout(content)
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(8)
        if scroll:
            area = SingleDirectionScrollArea(self, Qt.Vertical)
            area.setWidgetResizable(True)
            area.setWidget(content)
            area.enableTransparentBackground()
            area.setFrameShape(QFrame.NoFrame)
            content.setStyleSheet("QWidget#pageBody { background: transparent; }")
            self.scroll_area = area
            v.addWidget(area, 1)
        else:
            self.scroll_area = None
            v.addWidget(content, 1)
        self.content = content

        # Command bar (PK_ACTION=bar)
        self.command_bar = QWidget(self)
        self.command_bar.setObjectName("commandBar")
        cv = QVBoxLayout(self.command_bar)
        cv.setContentsMargins(0, 12, 0, 0)
        cv.setSpacing(12)
        cv.addWidget(Divider())
        self.bar_actions = QHBoxLayout()
        self.bar_actions.setSpacing(8)
        self.bar_actions.addStretch(1)
        cv.addLayout(self.bar_actions)
        self.command_bar.hide()
        v.addWidget(self.command_bar)

    # ── title ──
    def set_title(self, title: str, subtitle: str | None = None):
        self.title_label.setText(title)
        if subtitle is not None:
            self.subtitle_label.setText(subtitle)
            self.subtitle_label.setVisible(bool(subtitle))

    # ── actions ──
    def _action_layout(self) -> QHBoxLayout:
        if self.placement == "bar":
            self.command_bar.show()
            return self.bar_actions
        return self.header_actions

    def _place(self, btn, primary: bool):
        lay = self._action_layout()
        if primary:
            lay.addWidget(btn, 0, Qt.AlignTop if lay is self.header_actions else Qt.AlignVCenter)
        else:
            # secondary buttons go before (left of) the first primary one
            idx = next((lay.indexOf(b) for b in self._buttons
                        if getattr(b, "pk_primary", False) and lay.indexOf(b) >= 0), -1)
            if idx >= 0:
                lay.insertWidget(idx, btn, 0, Qt.AlignTop if lay is self.header_actions
                                 else Qt.AlignVCenter)
            else:
                lay.addWidget(btn, 0, Qt.AlignTop if lay is self.header_actions
                              else Qt.AlignVCenter)
        self._buttons.append(btn)

    def primary(self, text: str, slot=None, danger: bool = False) -> PrimaryPushButton:
        """The page's main action (one per page)."""
        btn = PrimaryPushButton(text, self)
        btn.setMinimumSize(*ACTION_SIZE)
        btn.pk_primary = True
        if danger:
            def qss(dark):
                bg, hv = theme.hex_color("danger", dark), theme.hex_color("danger_hover", dark)
                fg = theme.hex_color("on_accent", dark)
                return (f"PrimaryPushButton{{background-color:{bg};border:1px solid {bg};"
                        f"color:{fg};}}"
                        f"PrimaryPushButton:hover{{background-color:{hv};border-color:{hv};}}"
                        f"PrimaryPushButton:pressed{{background-color:{hv};}}")
            setCustomStyleSheet(btn, qss(False), qss(True))
        if slot is not None:
            btn.clicked.connect(slot)
        self._place(btn, True)
        return btn

    def secondary(self, text: str, slot=None) -> PushButton:
        btn = PushButton(text, self)
        btn.setMinimumHeight(ACTION_SIZE[1])
        btn.pk_primary = False
        if slot is not None:
            btn.clicked.connect(slot)
        self._place(btn, False)
        return btn

    def add_header_widget(self, w: QWidget):
        """Something for the header's actions area that is not an action
        (a file chip, a page counter); it stays in the header either way."""
        self.header_actions.insertWidget(0, w, 0, Qt.AlignTop)

    # ── drops ──
    def accept_drop(self, path: str) -> bool:
        """Give a dropped file to the first visible file card that takes it."""
        for fc in self.findChildren(FileCard):
            if fc.isVisibleTo(self) and fc.accept_drop(path):
                return True
        return False

    # ── window modes (the shell calls these) ──
    def set_compact(self, on: bool):
        """Compact Mode: the header and any context panel are hidden."""
        self._compact = on
        self.header.setVisible(not on)
        if self.has_context():
            self.show_context(not on)

    def reveal_header(self, on: bool):
        """In Compact Mode the top edge brings the header back for a while."""
        if self._compact:
            self.header.setVisible(on)

    # Context panel: a workspace page (phase 3) overrides these four.
    def has_context(self) -> bool:
        return False

    def context_shown(self) -> bool:
        return False

    def context_width(self) -> int:
        return 0

    def show_context(self, on: bool):
        pass


class PlaceholderPage(ToolPage):
    """What a tool shows until its Qt page is written."""

    def __init__(self, tool=None, window=None, title: str | None = None):
        name = title or plain_label(getattr(tool, "label", "") or type(tool).__name__)
        super().__init__(name, "", tool=tool, window=window)
        self.note = muted_caption(f"{name} is being moved to the new interface.")
        self.note.setObjectName("placeholderNote")
        self.body.addWidget(self.note)
        self.body.addStretch(1)


# ── Group templates: phase 3 ──────────────────────────────────────────────────
class WorkspacePage(ToolPage):
    """TODO(phase 3): group A, document workspace (Annotate, Redact, Edit Text,
    Find & Replace, Reader).

    The page in the centre on a page-coloured canvas, a slim tool rail at the
    left, a contextual panel at the right (QSplitter, 220-480 px, collapses
    below 220, double-click the handle to toggle, animated SLIDE_MS) that
    changes with the selection or tool, and page navigation and zoom in a
    fixed strip under the canvas.  Implements has_context / context_shown /
    context_width / show_context so Compact Mode can hide the panel and the
    right edge can bring it back.  scroll=False.  Reader is exempt from the
    main-action rule."""


class CollectionPage(ToolPage):
    """TODO(phase 3): group D, collection (Merge, Image -> PDF, Batch).

    Several files in a chosen order: a list with a toolbar (Add, Up, Down,
    Remove) in the centre, the settings beside it, the main action fixed.
    accept_drop takes every dropped file of the accepted types and appends
    it; delete() removes the selected entry."""


class OrganiserPage(ToolPage):
    """TODO(phase 3): group B, page organiser (Rotate & Reorder, Split by
    Bookmarks).

    A thumbnail grid of the pages in the centre; the actions for the
    selected pages in a context bar above it; the main action fixed."""


class MasterDetailPage(ToolPage):
    """TODO(phase 3): group E, structured editor (Bookmarks / TOC, Metadata).

    A list on the left (outline entries or field names), the selected item's
    fields on the right, the main action fixed."""
