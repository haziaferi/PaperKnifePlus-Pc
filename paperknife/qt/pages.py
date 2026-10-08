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


def setting_row(group: QWidget, title: str, desc: str = "",
                label_width: int | None = None) -> QWidget:
    """Add a Windows 11 settings row to *group* (a card()) and return the
    container for its control: the name and description sit in a fixed-width
    column on the left, the control right-aligned, rows split by thin lines.

        row = setting_row(level_card, "Level", "How hard to compress")
        row.layout().addWidget(combo)

    label_width: the name column's width (LABEL_COLUMN by default); 0 lets it
    take the room the control leaves, for a narrow column such as a
    CollectionPage's settings.
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
    lw = LABEL_COLUMN if label_width is None else label_width
    if lw:
        texts.setFixedWidth(lw)
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
    h.addWidget(texts, 0 if lw else 1)
    if lw:
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


def spin_box(lo: int, hi: int, value: int, width: int = 160):
    """A Fluent SpinBox that shows its number.

    With PySide6 6.12 and PySide6-Fluent-Widgets 1.11.3 the SpinBox's inner
    line edit is laid out 1 px wide, so the value is invisible; this subclass
    gives it the space left of the buttons on every resize.  Use this, not
    qfluentwidgets.SpinBox, in every page."""
    from qfluentwidgets import SpinBox

    class _SpinBox(SpinBox):
        def resizeEvent(self, e):
            super().resizeEvent(e)
            buttons = [w for w in self.children()
                       if isinstance(w, QWidget) and w is not self.lineEdit() and w.isVisible()]
            right = min((b.x() for b in buttons if b.x() > 0), default=self.width())
            self.lineEdit().setGeometry(10, 1, max(20, right - 12), self.height() - 2)

    sb = _SpinBox()
    sb.setRange(lo, hi)
    sb.setValue(value)
    sb.setMinimumWidth(width)
    return sb


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
PANEL_W, PANEL_MIN, PANEL_MAX, SLIDE_MS = 280, 220, 480, 250


class WorkspacePage(ToolPage):
    """Group A, document workspace (Annotate, Redact, Edit Text, Find & Replace,
    Reader): a slim tool rail at the left, the page in the centre (PageView),
    a contextual panel at the right that a tool refills for its tool or
    selection (QSplitter: 220-480 px, collapses below 220, double-click the
    handle to toggle, animated SLIDE_MS), and page navigation and zoom in a
    fixed strip under the page.  Compact Mode hides the panel; the right edge
    brings it back.

    Subclasses: add_rail(key, glyph, tip, slot), panel_begin(title, desc) then
    add widgets to self.panel_body, set_doc / show_current for the document."""

    def __init__(self, title: str, subtitle: str = "", *, tool=None, window=None):
        from PySide6.QtCore import QEasingCurve, QVariantAnimation
        from PySide6.QtWidgets import QSplitter
        from qfluentwidgets import (Slider, SubtitleLabel, TransparentToggleToolButton,
                                    TransparentToolButton)
        from qfluentwidgets import FluentIcon as FIF
        from .pageview import PageView
        super().__init__(title, subtitle, tool=tool, window=window, scroll=False)
        self._QEasingCurve, self._QVariantAnimation = QEasingCurve, QVariantAnimation
        self._TransparentToolButton = TransparentToolButton
        self._ToggleButton = TransparentToggleToolButton
        self._SubtitleLabel = SubtitleLabel

        frame = SimpleCardWidget()
        h = QHBoxLayout(frame)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        rail_w = QWidget()
        self.rail = QVBoxLayout(rail_w)
        self.rail.setContentsMargins(4, 8, 4, 8)
        self.rail.setSpacing(4)
        self.rail.addStretch(1)
        h.addWidget(rail_w)
        h.addWidget(Divider(vertical=True))

        self.split = QSplitter(Qt.Horizontal)
        self.split.setHandleWidth(6)
        accent = theme.hex_color("accent")
        self.split.setStyleSheet("QSplitter::handle { background: transparent; }"
                                 f"QSplitter::handle:hover {{ background: {accent}; }}")
        self.split.setChildrenCollapsible(True)
        mid = QWidget()
        mv = QVBoxLayout(mid)
        mv.setContentsMargins(0, 0, 0, 0)
        mv.setSpacing(0)
        self.view = PageView(theme.hex_color("page_bg"))
        mv.addWidget(self.view, 1)
        mv.addWidget(Divider())
        strip = QHBoxLayout()
        strip.setContentsMargins(8, 4, 12, 4)
        self.prev_btn = TransparentToolButton(FIF.LEFT_ARROW)
        self.next_btn = TransparentToolButton(FIF.RIGHT_ARROW)
        self.page_label = BodyLabel("–")
        self.prev_btn.clicked.connect(lambda: self.go(-1))
        self.next_btn.clicked.connect(lambda: self.go(1))
        strip.addWidget(self.prev_btn)
        strip.addWidget(self.page_label)
        strip.addWidget(self.next_btn)
        strip.addStretch(1)
        strip.addWidget(muted_caption("Zoom"))
        self.zoom_slider = Slider(Qt.Horizontal)
        self.zoom_slider.setRange(50, 300)
        self.zoom_slider.setValue(int(self.view.zoom * 100))
        self.zoom_slider.setFixedWidth(140)
        self.zoom_slider.valueChanged.connect(self._zoom_changed)
        self.view.zoomed.connect(lambda z: self.zoom_slider.setValue(int(z * 100)))
        strip.addWidget(self.zoom_slider)
        self.reopen_btn = TransparentToolButton(theme.glyph_icon(0xE76B, 14))
        self.reopen_btn.setToolTip("Show panel")
        self.reopen_btn.clicked.connect(lambda: self.show_context(True))
        self.reopen_btn.hide()
        strip.addWidget(self.reopen_btn)
        mv.addLayout(strip)

        panel = QWidget()
        self._panel_v = QVBoxLayout(panel)
        self._panel_v.setContentsMargins(16, 12, 12, 16)
        self._panel_v.setSpacing(0)
        self._panel_box = None
        self.panel = panel
        self.split.addWidget(mid)
        self.split.addWidget(panel)
        self.split.setStretchFactor(0, 1)
        self.split.setSizes([700, PANEL_W])
        panel.setMinimumWidth(PANEL_MIN)   # below it the splitter collapses the panel
        panel.setMaximumWidth(PANEL_MAX)
        self.split.splitterMoved.connect(self._clamp)
        self.split.handle(1).installEventFilter(self)
        h.addWidget(self.split, 1)
        self.body.addWidget(frame, 1)
        self._panel_w = PANEL_W
        self._zoom_timer = None
        self.panel_body = None

    # ── rail ──
    def add_rail(self, key: str, glyph: int, tip: str, slot, toggle: bool = True):
        cls = self._ToggleButton if toggle else self._TransparentToolButton
        btn = cls(theme.glyph_icon(glyph, 18))
        btn.setFixedSize(40, 40)
        btn.setToolTip(tip)
        btn.pk_key, btn.pk_glyph = key, glyph
        btn.clicked.connect(slot)
        self.rail.insertWidget(self.rail.count() - 1, btn)
        return btn

    def add_rail_gap(self):
        self.rail.insertSpacing(self.rail.count() - 1, 12)

    def mark_rail(self, key: str):
        """Mark the chosen tool: its toggle button checked (Fluent draws it)."""
        for i in range(self.rail.count()):
            w = self.rail.itemAt(i).widget()
            if w is not None and hasattr(w, "pk_key") and w.isCheckable():
                w.setChecked(w.pk_key == key)

    # ── context panel ──
    def panel_begin(self, title: str, desc: str = ""):
        """Empty the panel and give it a title; widgets go into self.panel_body.
        The old contents go at once (hidden and detached), not at the next
        event-loop turn, so they are never drawn under the new ones."""
        old = self._panel_box
        if old is not None:
            old.hide()
            self._panel_v.removeWidget(old)
            old.setParent(None)
            old.deleteLater()
        while self._panel_v.count():          # the trailing stretch
            self._panel_v.takeAt(0)
        box = QWidget(self.panel)
        self._panel_box = box
        bv = QVBoxLayout(box)
        bv.setContentsMargins(0, 0, 0, 0)
        bv.setSpacing(4)
        top = QHBoxLayout()
        top.addWidget(self._SubtitleLabel(title))
        top.addStretch(1)
        hide = self._TransparentToolButton(theme.glyph_icon(0xE76C, 14))
        hide.setToolTip("Hide panel")
        hide.clicked.connect(lambda: self.show_context(False))
        top.addWidget(hide)
        bv.addLayout(top)
        if desc:
            d = muted_caption(desc)
            d.setWordWrap(True)
            bv.addWidget(d)
        self.panel_body = QVBoxLayout()
        self.panel_body.setContentsMargins(0, 8, 0, 0)
        self.panel_body.setSpacing(4)
        bv.addLayout(self.panel_body)
        self._panel_v.addWidget(box)
        self._panel_v.addStretch(1)
        box.show()
        return self.panel_body

    def panel_field(self, label: str) -> QHBoxLayout:
        """A small label above its control, as a narrow panel stacks them."""
        self.panel_body.addSpacing(12)
        self.panel_body.addWidget(muted_caption(label))
        row = QHBoxLayout()
        row.setSpacing(8)
        self.panel_body.addLayout(row)
        return row

    def _clamp(self, *_):
        w = self.split.sizes()[1]
        if 0 < w < PANEL_MIN:
            self.show_context(False)
        elif w:
            self._panel_w = min(PANEL_MAX, w)
        self.reopen_btn.setVisible(self.split.sizes()[1] == 0)

    def eventFilter(self, obj, ev):
        if ev.type() == ev.Type.MouseButtonDblClick:
            self.show_context(not self.context_shown())
            return True
        return False

    def has_context(self) -> bool:
        return True

    def context_shown(self) -> bool:
        return self.split.sizes()[1] > 0

    def context_width(self) -> int:
        return self.split.sizes()[1]

    def show_context(self, on: bool):
        target = self._panel_w if on else 0
        total = sum(self.split.sizes())
        start = self.split.sizes()[1]
        if start == target:
            return
        a = self._QVariantAnimation(self)
        a.setDuration(SLIDE_MS)
        a.setStartValue(start)
        a.setEndValue(target)
        a.setEasingCurve(self._QEasingCurve.OutCubic)
        a.valueChanged.connect(lambda w: self.split.setSizes([total - int(w), int(w)]))
        a.finished.connect(lambda: self.reopen_btn.setVisible(target == 0))
        a.start()
        self._panel_anim = a

    # ── pages ──
    def page_count(self) -> int:
        doc = getattr(self, "_doc", None)
        return len(doc) if doc is not None else 0

    def go(self, d: int):
        n = self.page_count()
        if n and 0 <= self._pg + d < n:
            self._pg += d
            self.on_page()
            self.show_current()

    def show_current(self):
        """Render the current page and the tool's overlay; update the page label."""
        doc = getattr(self, "_doc", None)
        if doc is None:
            self.view.show_page(None)
            self.page_label.setText("–")
            return
        self.view.show_page(doc[self._pg])
        self.page_label.setText(f"{self._pg + 1} / {len(doc)}")
        self.draw_overlay(doc[self._pg])

    def _zoom_changed(self, v: int):
        # Render once the slider rests: a render costs ~30 ms.
        from PySide6.QtCore import QTimer
        if self._zoom_timer is None:
            self._zoom_timer = QTimer(self, singleShot=True, interval=120)
            self._zoom_timer.timeout.connect(
                lambda: (self.view.set_zoom(self.zoom_slider.value() / 100),
                         self.show_current()))
        self._zoom_timer.start()

    # hooks for subclasses
    def on_page(self):
        pass

    def draw_overlay(self, page):
        pass


def _clear_layout(layout):
    while layout.count():
        item = layout.takeAt(0)
        if item.widget() is not None:
            item.widget().deleteLater()
        elif item.layout() is not None:
            _clear_layout(item.layout())


SETTINGS_W = 360            # collection: width of the settings column


class CollectionRow(QWidget):
    """One entry of a CollectionPage list: its number, the file's name and
    folder, an optional control of its own (row.extra, e.g. a page range)
    and a note at the right (row.set_note, e.g. a batch result)."""

    def __init__(self, page, path: str, extra: QWidget | None = None):
        super().__init__()
        self.setObjectName("collectionRow")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.page, self.path, self.extra = page, str(path), extra
        self.setMinimumHeight(52)
        h = QHBoxLayout(self)
        h.setContentsMargins(12, 6, 12, 6)
        h.setSpacing(12)
        self.num = muted_caption("")
        self.num.setFixedWidth(24)
        self.num.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        h.addWidget(self.num)
        texts = QVBoxLayout()
        texts.setSpacing(0)
        p = Path(path)
        self.name_label = BodyLabel(p.name)
        self.name_label.setToolTip(str(p))
        self.folder_label = muted_caption(str(p.parent))
        texts.addWidget(self.name_label)
        texts.addWidget(self.folder_label)
        h.addLayout(texts, 1)
        self.note = muted_caption("")
        self.note.hide()
        h.addWidget(self.note, 0, Qt.AlignVCenter)
        if extra is not None:
            h.addWidget(extra, 0, Qt.AlignVCenter)
        self.set_selected(False)

    def set_number(self, n: int):
        self.num.setText(f"{n}.")

    def set_note(self, text: str, role: str = "muted"):
        self.note.setText(text)
        self.note.setTextColor(*theme.pair(role))
        self.note.setVisible(bool(text))

    def set_selected(self, on: bool):
        self.selected = on
        if on:
            a = theme.color("accent")
            bg = f"rgba({a.red()},{a.green()},{a.blue()},40)"
            self.setStyleSheet(f"QWidget#collectionRow {{ background: {bg}; border-radius: 4px; }}")
        else:
            self.setStyleSheet("QWidget#collectionRow { background: transparent; }")

    def mousePressEvent(self, e):
        self.page.select(self.page.rows.index(self))
        super().mousePressEvent(e)


class CollectionPage(ToolPage):
    """Group D, collection (Merge, Image -> PDF, Batch): several files in a
    chosen order.  A list card fills the centre with its toolbar on top
    (Add, Up, Down, Remove, plus any add_tool() buttons) and an empty-state
    line that says what to drop; a settings column of fixed width
    (SETTINGS_W) sits at the right when settings=True, filled through
    self.settings (a QVBoxLayout: group_title + card + setting_row, as in
    group C).  The main action stays where ToolPage puts it.

    accept_drop / open() add files of *exts*; delete() removes the selected
    entry; Alt+Up / Alt+Down move it.  make_extra(path) -> QWidget | None
    gives each new row its own control (Merge's page range).

        rows / paths() / selected_index() / select(i) / add_paths(paths)
        move(d) / remove_selected() / clear_rows()
        setting_row(card, name, desc): a setting row sized for the column"""

    def __init__(self, title: str, subtitle: str = "", *, tool=None, window=None,
                 exts=(".pdf",), add_text: str = "Add PDFs", empty_text: str = "",
                 settings: bool = True, toolbar: bool = True, parent=None):
        from PySide6.QtGui import QKeySequence, QShortcut
        from qfluentwidgets import FluentIcon as FIF
        from qfluentwidgets import TransparentPushButton
        super().__init__(title, subtitle, tool=tool, window=window, scroll=False,
                         parent=parent)
        self.exts = tuple(e.lower() for e in (exts or ()))
        self.add_text = add_text
        self.rows: list[CollectionRow] = []
        self._sel: int | None = None

        cols = QHBoxLayout()
        cols.setSpacing(16)
        # list card
        self.list_card = SimpleCardWidget()
        lv = QVBoxLayout(self.list_card)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(0)
        bar = QWidget(self.list_card)
        bar.setObjectName("collectionToolbar")
        self.toolbar = QHBoxLayout(bar)
        self.toolbar.setContentsMargins(8, 6, 8, 6)
        self.toolbar.setSpacing(4)
        self.add_btn = self.up_btn = self.down_btn = self.remove_btn = None
        if toolbar:
            def tb(text, icon, slot):
                b = TransparentPushButton(icon, text, bar)
                b.clicked.connect(slot)
                self.toolbar.addWidget(b)
                return b
            self.add_btn = tb(add_text, FIF.ADD, self.open)
            self.up_btn = tb("Up", FIF.UP, lambda: self.move(-1))
            self.down_btn = tb("Down", FIF.DOWN, lambda: self.move(1))
            self.remove_btn = tb("Remove", FIF.DELETE, self.remove_selected)
        self.toolbar.addStretch(1)
        self.count_label = muted_caption("")
        self.toolbar.addWidget(self.count_label)
        lv.addWidget(bar)
        lv.addWidget(Divider())
        area = SingleDirectionScrollArea(self.list_card, Qt.Vertical)
        area.setWidgetResizable(True)
        area.enableTransparentBackground()
        area.setFrameShape(QFrame.NoFrame)
        inner = QWidget()
        inner.setObjectName("collectionList")
        inner.setStyleSheet("QWidget#collectionList { background: transparent; }")
        self.list_v = QVBoxLayout(inner)
        self.list_v.setContentsMargins(4, 4, 4, 4)
        self.list_v.setSpacing(2)
        self.empty_label = muted_caption(empty_text or self._default_empty())
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setWordWrap(True)
        self.empty_label.setContentsMargins(24, 48, 24, 48)
        self.list_v.addWidget(self.empty_label)
        self.list_v.addStretch(1)
        area.setWidget(inner)
        self.list_area = area
        lv.addWidget(area, 1)
        cols.addWidget(self.list_card, 1)
        # settings column
        self.settings_area = None
        self.settings = None
        if settings:
            sa = SingleDirectionScrollArea(self, Qt.Vertical)
            sa.setWidgetResizable(True)
            sa.enableTransparentBackground()
            sa.setFrameShape(QFrame.NoFrame)
            sa.setFixedWidth(SETTINGS_W)
            sw = QWidget()
            sw.setObjectName("collectionSettings")
            sw.setStyleSheet("QWidget#collectionSettings { background: transparent; }")
            self.settings = QVBoxLayout(sw)
            self.settings.setContentsMargins(0, 0, 0, 0)
            self.settings.setSpacing(8)
            sa.setWidget(sw)
            self.settings_area = sa
            cols.addWidget(sa)
        self.body.addLayout(cols, 1)

        for keys, d in (("Alt+Up", -1), ("Alt+Down", 1)):
            sc = QShortcut(QKeySequence(keys), self)
            sc.activated.connect(lambda d=d: self.move(d))
        self._refresh()

    def _default_empty(self) -> str:
        what = "PDFs" if self.exts == (".pdf",) else "files"
        return f"Drop {what} here, or use {self.add_text}."

    @staticmethod
    def setting_row(group: QWidget, title: str, desc: str = "") -> QWidget:
        return setting_row(group, title, desc, label_width=0)

    # ── hooks a tool may override ──
    def make_extra(self, path: str) -> QWidget | None:
        return None

    def add_tool(self, text: str, icon, slot):
        """Another toolbar button (after Remove)."""
        from qfluentwidgets import TransparentPushButton
        b = TransparentPushButton(icon, text)
        b.clicked.connect(slot)
        self.toolbar.insertWidget(self.toolbar.count() - 2, b)
        return b

    # ── entries ──
    def paths(self) -> list[str]:
        return [r.path for r in self.rows]

    def selected_index(self) -> int | None:
        return self._sel

    def accepts(self, path: str) -> bool:
        return os.path.isfile(path) and (not self.exts or Path(path).suffix.lower() in self.exts)

    def add_paths(self, paths) -> int:
        n = 0
        for p in paths:
            row = CollectionRow(self, str(p), self.make_extra(str(p)))
            self.rows.append(row)
            self.list_v.insertWidget(self.list_v.count() - 1, row)
            n += 1
        self._refresh()
        return n

    def clear_rows(self):
        for r in self.rows:
            r.hide()
            self.list_v.removeWidget(r)
            r.setParent(None)
            r.deleteLater()
        self.rows = []
        self._sel = None
        self._refresh()

    def select(self, i: int | None):
        self._sel = i if i is not None and 0 <= i < len(self.rows) else None
        for j, r in enumerate(self.rows):
            r.set_selected(j == self._sel)
        self._refresh()

    def move(self, d: int):
        i = self._sel
        if i is None:
            return
        j = i + d
        if not 0 <= j < len(self.rows):
            return
        self.rows[i], self.rows[j] = self.rows[j], self.rows[i]
        for r in self.rows:
            self.list_v.removeWidget(r)
        for k, r in enumerate(self.rows):
            self.list_v.insertWidget(1 + k, r)      # after the empty-state label
        self.select(j)

    def remove_selected(self):
        i = self._sel
        if i is None or i >= len(self.rows):
            return
        r = self.rows.pop(i)
        r.hide()
        self.list_v.removeWidget(r)
        r.setParent(None)
        r.deleteLater()
        self._sel = None
        self.select(min(i, len(self.rows) - 1) if self.rows else None)

    def _refresh(self):
        for k, r in enumerate(self.rows):
            r.set_number(k + 1)
        self.empty_label.setVisible(not self.rows)
        n = len(self.rows)
        self.count_label.setText(f"{n} file{'s' if n != 1 else ''}" if n else "")
        has = self._sel is not None
        for b, ok in ((self.up_btn, has and self._sel > 0),
                      (self.down_btn, has and self._sel < n - 1),
                      (self.remove_btn, has)):
            if b is not None:
                b.setEnabled(bool(ok))

    # ── shell hooks ──
    def open(self):
        if self.exts:
            pats = " ".join(f"*{e}" for e in self.exts)
            label = "PDF" if self.exts == (".pdf",) else "Supported files"
            filters = [(label, pats), ("All", "*.*")]
        else:
            filters = None
        self.add_paths(dialogs.ask_open_many(self.add_text, filters))

    def delete(self):
        self.remove_selected()

    def accept_drop(self, path: str) -> bool:
        if self.accepts(path):
            self.add_paths([path])
            return True
        return super().accept_drop(path)        # a file card in the settings


class OrganiserPage(ToolPage):
    """TODO(phase 3): group B, page organiser (Rotate & Reorder, Split by
    Bookmarks).

    A thumbnail grid of the pages in the centre; the actions for the
    selected pages in a context bar above it; the main action fixed."""


class MasterDetailPage(ToolPage):
    """TODO(phase 3): group E, structured editor (Bookmarks / TOC, Metadata).

    A list on the left (outline entries or field names), the selected item's
    fields on the right, the main action fixed."""
