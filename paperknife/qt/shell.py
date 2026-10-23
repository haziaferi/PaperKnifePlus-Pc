"""
paperknife.qt.shell
MainWindow: the FluentWindow shell.

- Navigation from tool_registry.TOOL_REGISTRY grouped by tool.section (first-seen order,
  registry order inside a group), Home first, Preferences at the bottom,
  a search box (Ctrl+K / Ctrl+F) filtering by label.  A group folds under
  its title (click, Enter or Space; the state kept in PREFS qt_nav_folded);
  a search shows matches in folded groups too, opening a tool by search or
  open_tool unfolds its group, and the icon-only pane shows every icon.
- Pages are built on first use by page_for(tool): the class registered in
  pages.QT_PAGES under tool.name.
- Status bar with colour roles, a progress strip with Cancel, run_job with
  lock=True holding the page and navigation.
- Window modes: Ctrl+Alt+S collapses / expands the navigation; Ctrl+Alt+C
  Compact Mode (navigation, page header and context panel hidden; the
  left / top / right edge brings each back, Zen's timings); the title bar
  hides and comes back at the top edge (env PK_TITLEBAR=always keeps it).
"""
from __future__ import annotations

import gc
import json
import os
import time
from pathlib import Path

import pymupdf as fitz
from PySide6.QtCore import (QByteArray, QEasingCurve, QEvent, QPoint, QPropertyAnimation, QRect,
                            QRectF, Qt, QTimer, Signal)
from PySide6.QtGui import QCursor, QIcon, QKeySequence, QPainter, QShortcut
from PySide6.QtWidgets import (QAbstractSpinBox, QApplication, QComboBox, QHBoxLayout,
                               QLineEdit, QPlainTextEdit, QTextEdit, QVBoxLayout, QWidget)
from qfluentwidgets import (CaptionLabel, FluentWindow, NavigationItemPosition, ProgressBar,
                            PushButton, SearchLineEdit)
from qfluentwidgets.components.navigation.navigation_panel import NavigationDisplayMode
from qfluentwidgets.components.navigation.navigation_widget import (NavigationItemHeader,
                                                                    NavigationWidget)

from . import bridge, dialogs, pages, theme
from ..core import password as core_password
from ..core import recovery
from ..core.document import SharedDocument
from ..job_queue import CancellableJob, live_parts
from ..prefs import PREFS
from ..recent import RECENT
from .pages import SLIDE_MS      # sidebar / panel slide

# ── Timings (Zen defaults, refs/zen.md) ───────────────────────────────────────
TOP_SLIDE_MS = 150      # title bar slide
KEEP_MS = 150           # sidebar stays after the pointer leaves
TOP_HIDE_MS = 1000      # title bar hides after the pointer leaves
EDGE = 8                # px from the window edge that counts as "the edge"
OUTSIDE_X, OUTSIDE_Y = 200, 100   # pointer this far outside still counts
POLL_MS = 40            # edge watcher interval (runs only when needed)
CLOSE_WAIT_S = 15       # how long close waits for a cancelled job
RECOVERY_MS = 10_000    # how often changed unsaved edits are copied for crash recovery
RECOVERY_KEY = "document"   # the one entry: the shared document and the tools' marks
UNAPPLIED_QUESTION = ("{n} redaction {boxes} drawn and not applied will be lost. "
                      "Close anyway?")
BUSY_MSG = "Another job is still running. Wait for it to finish or cancel it first."

GEOMETRY_KEY = "qt_window_geometry"
STALE_PARTS_KEY = "qt_stale_parts"
FOLDED_KEY = "qt_nav_folded"     # the folded navigation groups, by section
NAV_EXPAND_WIDTH = 212
NAV_MIN_EXPAND_WINDOW = 900
BOTTOM_SECTIONS = ("SETTINGS",)

# Segoe Fluent Icons code points by tool class name (from the frame prototype)
NAV_GLYPH: dict[str, int] = {
    "home": 0xE80F, "ReaderTool": 0xE736, "MergeTool": 0xE8F1, "SplitTool": 0xE8C6,
    "RotateTool": 0xE7AD, "TocTool": 0xE8FD,
    "BatchTool": 0xE81E, "CompressTool": 0xE7B8, "WatermarkTool": 0xE790,
    "NormaliseTool": 0xE740, "OCRTool": 0xE8D2, "PasswordTool": 0xE72E,
    "HeaderFooterTool": 0xE7C3, "CropTool": 0xE7A8, "PdfToolsTool": 0xE90F,
    "Img2PdfTool": 0xE8B9, "ExtractTool": 0xE7C5,
    "Pdf2DocTool": 0xE8A5, "EditTextTool": 0xE70F,
    "FindReplaceTool": 0xE721, "AnnotateTool": 0xE7E6, "RedactTool": 0xE7AB,
    "MetadataTool": 0xE946, "SettingsTool": 0xE713,
}
DEFAULT_GLYPH = 0xE8A5
SEARCH_GLYPH = 0xE721
CHEVRON_OPEN, CHEVRON_FOLDED = 0xE70D, 0xE76C   # ChevronDown / ChevronRight

_TEXT_INPUTS = (QLineEdit, QTextEdit, QPlainTextEdit, QAbstractSpinBox)

# A coloured status line always starts with its role's symbol, so its state
# is not told by colour alone (WCAG 1.4.1); muted lines carry none.
STATUS_SYMBOLS = {"success": "✓", "warning": "⚠", "danger": "✗"}


def status_with_symbol(msg: str, role: str) -> str:
    """*msg* led by *role*'s symbol: added when it has none, replacing
    another role's symbol (a "✓" on a warning)."""
    symbol = STATUS_SYMBOLS.get(role)
    if symbol is None:
        return msg
    text = msg.lstrip()
    if text[:1] in STATUS_SYMBOLS.values():
        text = text[1:].lstrip()
    return f"{symbol}  {text}"


# ── Navigation search box ─────────────────────────────────────────────────────
class NavSearch(NavigationWidget):
    """A search field in the navigation; a search icon when it is collapsed."""

    def __init__(self, parent=None):
        super().__init__(isSelectable=False, parent=parent)
        self.edit = SearchLineEdit(self)
        self.edit.setPlaceholderText("Search tools")
        self.edit.setClearButtonEnabled(True)
        self.edit.hide()
        self._glyph = theme.Glyph(SEARCH_GLYPH)
        self.setToolTip("Search tools (Ctrl+K)")

    def setCompacted(self, isCompacted: bool):  # noqa: N802,N803 (Qt naming)
        super().setCompacted(isCompacted)
        self.edit.setVisible(not isCompacted)
        self._fit()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._fit()

    def _fit(self):
        self.edit.setGeometry(4, 1, max(0, self.width() - 8), 34)

    def paintEvent(self, e):
        if not self.isCompacted:
            return
        p = QPainter(self)
        if self.isEnter:
            p.setPen(Qt.NoPen)
            c = theme.color("text")
            c.setAlpha(15)
            p.setBrush(c)
            p.drawRoundedRect(self.rect().adjusted(4, 0, -4, 0), 5, 5)
        self._glyph.render(p, self.rect().adjusted(12, 10, -12, -10))


# ── Navigation group title ────────────────────────────────────────────────────
class GroupHeader(NavigationItemHeader):
    """A navigation group's title that folds its items: a click, or Enter /
    Space while it has the focus, emits toggled(section); a small chevron
    at its right says which way it is (down: open, right: folded).  Fluent
    hides it (height 0) in the icon-only pane."""

    toggled = Signal(str)

    def __init__(self, section: str, text: str, parent=None):
        super().__init__(text, parent)
        self.section = section
        self.folded = False
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAccessibleName(text)

    def chevron(self) -> int:
        """The glyph at the title's right: ChevronRight folded, else ChevronDown."""
        return CHEVRON_FOLDED if self.folded else CHEVRON_OPEN

    def set_folded(self, on: bool):
        if on != self.folded:
            self.folded = on
            self.update()

    def mousePressEvent(self, e):
        e.accept()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.rect().contains(e.position().toPoint()):
            self.toggled.emit(self.section)
        e.accept()

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.toggled.emit(self.section)
            return
        super().keyPressEvent(e)

    def enterEvent(self, e):
        self.isEnter = True
        self.update()

    def leaveEvent(self, e):
        self.isEnter = False
        self.update()

    def focusInEvent(self, e):
        super().focusInEvent(e)
        self.update()

    def focusOutEvent(self, e):
        super().focusOutEvent(e)
        self.update()

    def paintEvent(self, e):
        if self.height() == 0 or not self.isVisible() or self.isCompacted:
            return super().paintEvent(e)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        box = QRectF(self.rect()).adjusted(4.5, 0.5, -4.5, -0.5)
        if self.isEnter:
            c = theme.color("text")
            c.setAlpha(15)
            p.setPen(Qt.NoPen)
            p.setBrush(c)
            p.drawRoundedRect(box, 5, 5)
        if self.hasFocus():
            p.setPen(theme.color("accent"))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(box, 5, 5)
        p.end()
        super().paintEvent(e)
        p = QPainter(self)
        glyph = theme.Glyph(self.chevron())
        h = self.height()
        glyph.render(p, QRect(self.width() - 26, (h - 10) // 2, 10, 10), fill=self.textColor())
        p.end()


# ══════════════════════════════════════════════════════════════════════════════
class MainWindow(FluentWindow):

    # The current document changed: its path, or None (owner's decision
    # 2026-10-10: one document the single-input screens follow).
    current_document_changed = Signal(object)

    def __init__(self, tools=None):
        super().__init__()
        theme.window_follows_palette(self)
        bridge.install()
        from .._version import __version__
        self._app_title = f"PaperKnife+ PC  v{__version__}"
        self.setWindowTitle(self._app_title)
        # The one open document every tool works on (owner's decision 2026-10-23).
        self.document = SharedDocument()
        self.document.listen(self._on_document_event)
        icon = Path(__file__).resolve().parents[2] / "assets" / "icon.ico"
        if icon.is_file():
            self.setWindowIcon(QIcon(str(icon)))
        self.setMinimumSize(1060, 720)
        self.resize(1380, 900)
        self.setAcceptDrops(True)

        quick_tools = tools
        if tools is None:
            from ..tool_registry import TOOL_REGISTRY
            from .pages import batch_prototype
            # Prototype B: the four tools take a folder; no Batch screen.
            tools = quick_tools = [t for t in TOOL_REGISTRY
                                   if not (t.name == "BatchTool" and batch_prototype() == "B")]
            from . import structure
            if structure.active():
                # Workspaces hold the tools (structure prototypes, owner 2026-10-18).
                tools = structure.nav_tools(TOOL_REGISTRY)
        self.tools = list(tools)
        # Home's quick actions name tools, not the places a structure lists.
        self._quick_tools = list(quick_tools)

        # State
        self._current_job: CancellableJob | None = None
        self._status_seq = 0            # bumped by every set_status
        self._locked = False
        self._alive = True
        self._closing = False           # waiting for a cancelled job to end
        self._close_ok = False          # the next closeEvent is accepted
        self.compact = False
        self._autohide_title = os.environ.get("PK_TITLEBAR", "").strip().lower() != "always"
        # Hidden from the start: shown, it would float over the page header.
        self._top_shown = not self._autohide_title
        self._bar_in_use = False        # the pointer stayed on the bar since the top edge
        self._side_shown = False        # Compact Mode: navigation floated in
        self._ctx_revealed = False      # Compact Mode: context panel brought in
        self._first_show = True
        self._current_key: str | None = None
        self._pointer = QCursor.pos     # tests replace this; never move the real mouse
        self._anims: dict[str, QPropertyAnimation] = {}
        self.status_role = "muted"
        self.current_document: str | None = None
        self._keep = None               # the password a save in progress keeps (run_job)
        self._doc_pages: dict = {}      # page key -> the tool pages that showed the document

        self._build_body()
        self._build_nav()
        self._build_shortcuts()
        self._build_timers()
        self.titleBar.installEventFilter(self)
        from . import structure
        structure.install_left(self)        # a structure prototype's navigation shape

        self._stale_parts = _remove_stale_parts(PREFS.get(STALE_PARTS_KEY, []))

        self._normal_rect = QRect(self.geometry())   # the last un-maximized place
        geo = PREFS.get(GEOMETRY_KEY, "")
        if geo:
            self._restore_place(geo)

        self._ready = True              # Qt events before this point skip our handlers
        self.show_page("home")
        self._place_title_bar()

    # ══════════════════════════════════════════════════════════════════════════
    # LAYOUT
    # ══════════════════════════════════════════════════════════════════════════
    def _build_body(self):
        # FluentWindow puts stackedWidget straight into widgetLayout; wrap it
        # with the progress strip and the status bar under it.
        self.widgetLayout.removeWidget(self.stackedWidget)
        self.body = QWidget(self)
        self.body.setObjectName("shellBody")
        bv = QVBoxLayout(self.body)
        bv.setContentsMargins(0, 0, 0, 0)
        bv.setSpacing(0)
        bv.addWidget(self.stackedWidget, 1)

        # Progress strip: label, bar, Cancel (hidden until a job runs)
        self.progress_strip = QWidget(self.body)
        self.progress_strip.setObjectName("progressStrip")
        ph = QHBoxLayout(self.progress_strip)
        ph.setContentsMargins(16, 6, 12, 6)
        ph.setSpacing(12)
        self.job_label = CaptionLabel("", self.progress_strip)
        theme.label_role(self.job_label, "muted")
        self.progress = ProgressBar(self.progress_strip, useAni=False)
        self.progress.setRange(0, 1000)
        self.progress.setValue(0)
        self.cancel_button = PushButton("Cancel", self.progress_strip)
        self.cancel_button.clicked.connect(self._cancel_job)
        ph.addWidget(self.job_label)
        ph.addWidget(self.progress, 1)
        ph.addWidget(self.cancel_button)
        self.progress_strip.hide()
        bv.addWidget(self.progress_strip)

        # Status bar
        self.status_bar = QWidget(self.body)
        self.status_bar.setObjectName("statusBar")
        sh = QHBoxLayout(self.status_bar)
        sh.setContentsMargins(16, 4, 16, 6)
        self.status_label = CaptionLabel("Ready", self.status_bar)
        theme.label_role(self.status_label, "muted")
        theme.text_symbols(self.status_label)
        sh.addWidget(self.status_label, 1)
        bv.addWidget(self.status_bar)

        self.widgetLayout.addWidget(self.body)

        # The veil over a locked page (lock=True): eats clicks, shows "busy"
        self.lock_overlay = _Overlay(self.body)
        self.lock_overlay.hide()
        self.stackedWidget.installEventFilter(self)

    def _build_nav(self):
        nav = self.navigationInterface
        nav.setReturnButtonVisible(False)
        nav.setExpandWidth(NAV_EXPAND_WIDTH)
        nav.setMinimumExpandWidth(NAV_MIN_EXPAND_WINDOW)

        self.search = NavSearch()
        nav.addWidget("search", self.search, onClick=lambda *_: self.focus_search(),
                      position=NavigationItemPosition.TOP)
        self.search.edit.textChanged.connect(self._filter_nav)
        self.search.edit.returnPressed.connect(self._open_first_match)

        self._items: dict[str, NavigationWidget] = {}
        self._labels: dict[str, str] = {}
        self._tool_by_key: dict[str, object] = {}
        self._hosts: dict[str, QWidget] = {}
        self._pages: dict[str, QWidget] = {}
        self._sections: list[tuple[str, object, list[str]]] = []   # (name, header, keys)
        self.stackedWidget.currentChanged.connect(self._on_current_changed)

        self._add_item("home", "Home", theme.Glyph(NAV_GLYPH["home"]),
                       NavigationItemPosition.SCROLL)

        order: list[str] = []
        groups: dict[str, list] = {}
        for t in self.tools:
            if t.section not in groups:
                order.append(t.section)
                groups[t.section] = []
            groups[t.section].append(t)

        stored = PREFS.get(FOLDED_KEY, [])
        self._folded = {s for s in stored if isinstance(s, str)} if isinstance(stored, list) \
            else set()
        panel = nav.panel
        for section in order:
            bottom = section in BOTTOM_SECTIONS
            pos = NavigationItemPosition.BOTTOM if bottom else NavigationItemPosition.SCROLL
            header = None
            # a group of one tool (Read: Read / Preview) sits under Home with no
            # title to fold (owner)
            if not bottom and len(groups[section]) > 1:   # as panel.insertItemHeader
                header = GroupHeader(section, section.capitalize(), panel)
                panel._insertWidgetToLayout(-1, header, pos)
                header.setCompacted(panel.displayMode not in (NavigationDisplayMode.EXPAND,
                                                              NavigationDisplayMode.MENU))
                header.toggled.connect(self.toggle_group)
            keys = []
            for t in groups[section]:
                key = t.name
                self._tool_by_key[key] = t
                self._add_item(key, pages.plain_label(t.label),
                               theme.Glyph(NAV_GLYPH.get(key, DEFAULT_GLYPH)), pos)
                keys.append(key)
            self._sections.append((section, header, keys))
        panel.displayModeChanged.connect(lambda _m: self._apply_nav())
        self._apply_nav()

    def _add_item(self, key, text, icon, position):
        host = QWidget()
        host.setObjectName(key)
        host.setProperty("isStackedTransparent", False)
        hv = QVBoxLayout(host)
        hv.setContentsMargins(0, 0, 0, 0)
        self.stackedWidget.addWidget(host)
        self._hosts[key] = host
        item = self.navigationInterface.addItem(
            routeKey=key, icon=icon, text=text,
            onClick=lambda *_, k=key: self.show_page(k),
            position=position, tooltip=text)
        self._items[key] = item
        self._labels[key] = text

    def _build_shortcuts(self):
        def sc(seq, fn):
            s = QShortcut(QKeySequence(seq), self)
            s.activated.connect(fn)
            return s

        self._shortcuts = [
            sc("Ctrl+O", lambda: self.page_hook("open")),
            sc("Ctrl+S", lambda: None if self._locked else self.save()),
            sc("Ctrl+Shift+S", lambda: None if self._locked else self.save_as()),
            sc("Ctrl+P", lambda: None if self._locked else self.print_document()),
            # A tool with marks of its own (Redact's boxes) takes them back first.
            sc("Ctrl+Z", lambda: self.page_hook("undo") or self.undo()),
            sc(QKeySequence(Qt.Key_Delete), self._on_delete_key),
            sc("Ctrl+K", self.focus_search),
            sc("Ctrl+F", self.focus_search),
            sc(QKeySequence(Qt.Key_Escape), self.clear_search),
            sc("Ctrl+Alt+S", self.toggle_nav),
            sc("Ctrl+Alt+C", self.toggle_compact),
        ]

    def _build_timers(self):
        self._hide_top_timer = QTimer(self, singleShot=True, interval=TOP_HIDE_MS,
                                      timeout=self._hide_top)
        self._keep_side_timer = QTimer(self, singleShot=True, interval=KEEP_MS,
                                       timeout=lambda: self._reveal_side(False))
        self._keep_ctx_timer = QTimer(self, singleShot=True, interval=KEEP_MS,
                                      timeout=self._hide_revealed_context)
        self._edge = QTimer(self, interval=POLL_MS, timeout=self._poll_edges)
        self._close_timer = QTimer(self, interval=100, timeout=self._close_when_idle)
        try:
            self._recovery = recovery.Session()
        except OSError:
            self._recovery = None           # no recovery folder: edits are not copied
        self._recovery_tokens: dict[str, object] = {}
        self._recovery_timer = QTimer(self, interval=RECOVERY_MS, timeout=self.snapshot_edits)
        self._recovery_timer.start()

    # ══════════════════════════════════════════════════════════════════════════
    # CRASH RECOVERY (owner's choice 2026-10-12: a dialog at start)
    # ══════════════════════════════════════════════════════════════════════════
    def _page_marks(self) -> dict:
        """Each tool's unsaved marks held beside the document (Redact's
        boxes), by page key: what crash recovery copies with it."""
        marks = {}
        for key, page in list(self._doc_pages.items()):
            fn = getattr(page, "recovery_extra", None)
            if not callable(fn) or not getattr(page, "shows_document", lambda: False)():
                continue
            try:
                extra = fn()
            except Exception:
                extra = None
            if extra:
                marks[key] = extra
        return marks

    def snapshot_edits(self):
        """Copy the document's unsaved edits (and the tools' marks), when they
        changed since the last copy, into this app's recovery folder; drop
        the copy once there are none.  Not while a job holds the document."""
        rec = self._recovery
        if rec is None or self.job_running():
            return
        sd = self.document
        marks = self._page_marks() if sd.is_open() else {}
        if not (sd.is_open() and (sd.dirty or marks)):
            if self._recovery_tokens.pop(RECOVERY_KEY, None) is not None:
                rec.remove(RECOVERY_KEY)
            return
        token = (sd.edits, json.dumps(marks, sort_keys=True))
        if self._recovery_tokens.get(RECOVERY_KEY) == token:
            return
        try:
            kept = core_password.open_password_of(sd.doc)
            if kept is None:
                data = sd.doc.tobytes()
            else:       # a protected file is not left readable in the recovery folder
                data = sd.doc.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256,
                                      user_pw=kept.user_pw, owner_pw=kept.user_pw)
            page = self.current_page()
            follows = getattr(page, "follows_document", False)
            tool = page.title_label.text() if follows and hasattr(page, "title_label") else ""
            rec.write(RECOVERY_KEY, {"path": sd.path, "name": sd.name, "tool": tool,
                                     "state": {"marks": marks,
                                               "page": self._current_key if follows else ""}},
                      data)
        except (OSError, RuntimeError, ValueError):
            return                          # tried again at the next tick
        self._recovery_tokens[RECOVERY_KEY] = token

    def offer_recovery(self) -> None:
        """At start: the edits an app that did not close left behind, with
        Recover / Discard.  Recover opens the document as unsaved, with each
        tool's marks back in it."""
        try:
            left = recovery.orphaned()
        except OSError:
            return
        left = [e for e in left if e.key == RECOVERY_KEY]
        if not left:
            return
        lines = [f"{e.meta.get('name') or 'Untitled'} — {e.meta.get('tool') or 'unsaved changes'}, "
                 f"{time.strftime('%H:%M', time.localtime(e.meta.get('saved_at', 0)))}"
                 for e in left]
        answer = dialogs.ask_recover(lines)
        if answer is None:              # closed: asked again at the next start
            return
        if not answer:
            recovery.discard(left)
            return
        e = left[-1]
        ok = False
        try:
            ok = self._restore_document(e.meta.get("path", ""), e.meta.get("state") or {}, e.pdf)
        except Exception:
            ok = False
        recovery.discard(left)          # what came back is copied again from this app
        self.snapshot_edits()
        if not ok:
            dialogs.warning("Recover unsaved changes",
                            "These could not be recovered (the file is missing or "
                            "could not be opened):\n" + lines[-1])

    def _restore_document(self, path: str, state: dict, pdf: bytes | None) -> bool:
        if pdf is None or not path:
            return False
        doc = self.open_pdf_data(pdf, Path(path).name)
        if doc is None:
            return False
        self.document.open(path, doc)
        self.document.changed()             # unsaved, as it was
        self.set_current_document(path)
        shown = None
        marks = state.get("marks") or {}
        for key, extra in marks.items():
            if key not in self._hosts or key == "home":
                continue
            page = self._ensure_page(key)
            if getattr(page, "follows_document", False):
                page.load_document(path)
            fn = getattr(page, "restore_extra", None)
            if callable(fn):
                fn(extra)
            shown = shown or key
        where = state.get("page") or ""
        shown = shown or (where if where in self._hosts and where != "home" else None)
        if shown:
            self.show_page(shown)
        else:
            self._follow(self.current_page())
        return True

    # ══════════════════════════════════════════════════════════════════════════
    # PAGES AND NAVIGATION
    # ══════════════════════════════════════════════════════════════════════════
    def page_for(self, tool) -> QWidget:
        """The Qt page for *tool*: its registered class."""
        cls = pages.QT_PAGES.get(tool.name)
        if cls is None:                     # a structure prototype's workspace host
            from . import structure
            cls = structure.HOSTS[tool.name]
        return cls(tool, self)

    def _ensure_page(self, key: str) -> QWidget:
        page = self._pages.get(key)
        if page is None:
            if key == "home":
                from .home import HomePage
                page = HomePage(self)
                page.build_quick_actions(self._quick_tools)
            else:
                page = self.page_for(self._tool_by_key[key])
            self._hosts[key].layout().addWidget(page)
            self._pages[key] = page
        return page

    def current_page(self) -> QWidget | None:
        return self._pages.get(self._current_key) if self._current_key else None

    def show_page(self, key: str, follow: bool = True) -> bool:
        """Switch to the page *key* ("home" or a tool class name); False when
        refused (a job holds the view) or unknown.  The document's unsaved
        edits go along to the next tool (one document per window, owner
        2026-10-23); a page left with the after-job question open counts it
        as Continue with it.  follow: a single-input page shown takes the
        current document."""
        if key not in self._hosts and not self._locked:
            # A structure prototype: the tool lives in a workspace host.
            from . import structure
            host = structure.host_for(key)
            if host in self._hosts:
                if not self.show_page(host, follow):
                    return False
                self.current_page().pick(key)
                return True
        if self._locked or key not in self._hosts:
            if self._current_key:          # keep the selection on the shown page
                self.navigationInterface.setCurrentItem(self._current_key)
            return False
        old = self.current_page()
        if key != self._current_key and old is not None:
            if hasattr(old, "leave_offer"):
                old.leave_offer()
            if self.compact:
                old.set_compact(False)
            if hasattr(old, "deactivate"):
                old.deactivate()
            if hasattr(old, "park_document"):
                old.park_document()
        page = self._ensure_page(key)
        from . import structure
        if structure.separate(key):
            # PDF X's split: the Editor and Files open in windows of their own.
            structure.show_separate(self, key, page)
            self._current_key = key
            if follow:
                self._follow(page)
            return True
        changed = key != self._current_key
        self._current_key = key
        self._ctx_revealed = False
        self.stackedWidget.setCurrentWidget(self._hosts[key], popOut=False)
        self.navigationInterface.setCurrentItem(key)
        structure.follow_left(self, key, page)
        if changed:
            if self.compact:
                page.set_compact(True)
            if hasattr(page, "activate"):
                page.activate()
            if follow:
                from . import structure
                if structure.struct() == "pdf24":
                    # The control: no document is kept from screen to screen.
                    self.current_document = None
                self._follow(page)
        return True

    def open_tool(self, class_name: str, path: str | None = None) -> bool:
        """Open a tool (by class name); with *path*, hand it the file (it
        becomes the current document on a single-input page)."""
        if not self.show_page(class_name, follow=not path):
            return False
        self._unfold_for(class_name)
        if path:
            page = self.current_page()
            if getattr(page, "follows_document", False):
                self.open_document(path)
                return True
            fn = getattr(page, "open_path", None) or getattr(page, "accept_drop", None)
            if callable(fn):
                fn(path)
        return True

    # ══════════════════════════════════════════════════════════════════════════
    # THE CURRENT DOCUMENT
    # ══════════════════════════════════════════════════════════════════════════
    def set_current_document(self, path: str | None):
        """Make *path* (or None) the current document, and say so.  An
        after-job question about another file goes."""
        path = str(path) if path else None
        page = self.current_page()
        out = page.offered_output() if page is not None and hasattr(page, "offered_output") \
            else None
        if out and not pages.same_path(out, path):
            page.dismiss_offer()
        if path == self.current_document:
            return
        self.current_document = path
        dialogs.note_document(path)
        self.current_document_changed.emit(path)

    def open_document(self, path: str) -> bool:
        """Open *path* as the document (the Open control, a recent file, a
        drop), after the unsaved-edits question when another one has edits;
        the page shown follows it.  Whether it did."""
        if not path or self._locked:
            return False
        path = str(path)
        sd = self.document
        if not (sd.is_open() and pages.same_path(sd.path, path)):
            if not path.lower().endswith(".pdf"):
                self.set_status(f"This tool does not open {Path(path).name}", "warning")
                return False
            if not self.adopt(path, ask=True):
                return False
        self.set_current_document(sd.path)
        self._follow(self.current_page())
        return True

    def adopt(self, path: str, ask: bool = False) -> bool:
        """Make *path* the open document, unless it already is.  It is opened
        first: a file that cannot be (a cancelled password, a broken file)
        asks nothing and changes nothing.  ask: then the unsaved-edits
        question about the document before (its Save opens *path* once the
        save is done).  Whether *path* is the document now."""
        sd = self.document
        if sd.is_open() and pages.same_path(sd.path, path):
            return True
        doc = self.open_pdf_safe(path)
        if doc is None:
            return False
        if ask and not self.settle_unsaved(None, lambda: self.open_document(path)):
            doc.close()
            return False
        sd.open(path, doc)
        self.set_current_document(path)
        return True

    def browse_document(self) -> bool:
        """The Open control's main part: the file dialog, then open_document."""
        if self._locked:
            return False
        path = dialogs.ask_open("Open PDF", [("PDF", "*.pdf")])
        return self.open_document(path) if path else False

    def clear_current_document(self) -> bool:
        """The clear (x) action: after the unsaved-edits question, the
        document is closed and every tool lets it go."""
        if self._locked:
            return False
        if not self.settle_unsaved(None, self.clear_current_document):
            return False
        page = self.current_page()
        if getattr(page, "follows_document", False) and page.document_path():
            page.clear_document()
        self.document.close()
        self.set_current_document(None)
        return True

    def _follow(self, page):
        """A single-input page shown takes the current document (a document
        it parked on leaving is taken again), and shows the edits other
        tools made to it meanwhile."""
        if not getattr(page, "follows_document", False):
            return
        cur = self.current_document
        held = page.document_path()
        if cur:
            if not pages.same_path(cur, held) or page.is_parked():
                page.load_document(cur)
            else:
                sync = getattr(page, "sync_document", None)
                if callable(sync):
                    sync()
        elif held:
            page.clear_document()
        page.refresh_document()

    def settle_unsaved(self, page=None, retry=None) -> bool:
        """Before the document is closed or replaced (another file opened,
        the clear action, the window closed): when it has unsaved edits,
        "Save changes to <name>?"  True: go on now (none, or Discard).
        False: stop (Cancel, or Save, which runs retry() once the save is
        done).  *page* is not used any more: the edits are the document's."""
        sd = self.document
        if not self.has_unsaved():
            return True
        choice = dialogs.ask_unsaved(sd.name)
        if choice == "discard":
            sd.forget_edits()
            for p in list(self._doc_pages.values()):
                drop = getattr(p, "drop_marks", None)
                if callable(drop):
                    drop()
            self._update_title()
            self.snapshot_edits()           # the copy of the edits goes too
            return True
        if choice == "save":
            self.save(after=retry)
        return False

    # ── the document's events, Save, Save as, Print, Undo ──
    def _pending_pages(self) -> list:
        return [p for p in list(self._doc_pages.values())
                if p.shows_document() and p.has_pending()]

    def unapplied_marks(self) -> int:
        """Marks a tool holds beside the document and has not applied (Redact's boxes)."""
        return sum(p.unapplied_marks() for p in list(self._doc_pages.values())
                   if p.shows_document() and callable(getattr(p, "unapplied_marks", None)))

    def has_unsaved(self) -> bool:
        """The document's unsaved edits, or input typed in a tool and not applied."""
        return self.document.dirty or bool(self._pending_pages())

    def commit_pending(self) -> bool:
        """Apply each tool's typed input to the document (before a save);
        False when one cannot be (it said why)."""
        return all(p.commit_edits() is not False for p in self._pending_pages())

    def _on_document_event(self, event: str):
        """SharedDocument's listener; a save on a worker tells from there."""
        from PySide6.QtCore import QThread
        if QThread.currentThread() is not QApplication.instance().thread():
            bridge.post(self._if_alive, lambda: self._on_document_event(event))
            return
        self._update_title()
        if event == "changed" and not self.__dict__.get("_sync_queued"):
            # After the edit's own page has caught up (it notes the change
            # right after making it): the page shown redraws only if it did not.
            self._sync_queued = True
            QTimer.singleShot(0, self._sync_shown)

    def _sync_shown(self):
        self._sync_queued = False
        sync = getattr(self.current_page(), "sync_document", None)
        if callable(sync) and not self._locked:
            sync()

    def _update_title(self):
        """The file's name, with * while it holds unsaved edits (owner
        2026-10-23: the file name, not the PDF's own Title)."""
        sd = self.document
        if sd.is_open() or sd.path:
            self.setWindowTitle(f"{sd.name}{'*' if sd.dirty else ''} — {self._app_title}")
        else:
            self.setWindowTitle(self._app_title)

    def _hold_rendering(self, page):
        """While a job reads the document no thumbnail may render from it:
        the page's renderer stops; the function returned restarts it."""
        timer = getattr(page, "_timer", None)
        if timer is None or not timer.isActive():
            return lambda: None
        timer.stop()
        return lambda: timer.start() if getattr(page, "_queue", None) else None

    def _write(self, work, name: str, then):
        page = self.current_page()
        resume = self._hold_rendering(page)

        def done(kind, value):
            resume()
            then(kind, value)
        job = self.run_job(work, f"Saving {name}…", lock=True, then=done, cancellable=False,
                           keep_password=self._keep, own_save=True)
        if job is None:
            resume()
        return job

    def save(self, after=None):
        """Save (Ctrl+S): the document over its own file (owner 2026-10-23);
        a file opened with a password keeps it.  after(): once it is saved."""
        sd = self.document
        if not sd.is_open():
            return dialogs.warning("Save", "Open a PDF first.")
        if not self.commit_pending():
            return None
        out = sd.path
        opened_with = core_password.open_password_of(sd.doc)
        self._keep = (opened_with, [out])
        # A file with an owner password only (no open password) keeps its
        # encryption (MuPDF re-applies it; core.doc_state.snapshot keeps it
        # through the undo steps).
        opts = {"garbage": 1, "deflate": True}
        if opened_with is None and (sd.doc.metadata or {}).get("encryption"):
            opts["encryption"] = fitz.PDF_ENCRYPT_KEEP

        def then(kind, _value):
            if kind == "done":
                self.set_status(f"✓  Saved → {Path(out).name}", "success")
                if callable(after):
                    after()
        return self._write(lambda stop: sd.save(**opts), Path(out).name, then)

    def save_as(self, after=None):
        """Save as (Ctrl+Shift+S): the document to a new file it then belongs
        to; a file opened with a password asks whether the new one keeps it."""
        sd = self.document
        if not sd.is_open():
            return dialogs.warning("Save as", "Open a PDF first.")
        if not self.commit_pending():
            return None
        out = dialogs.ask_save(sd.name or "document.pdf", ".pdf", [("PDF", "*.pdf")])
        if not out:
            return None
        self._keep = (pages.ask_keep_password(sd.doc), [out])

        def then(kind, _value):
            if kind != "done":
                return
            self.set_current_document(sd.path)
            told = set()
            for p in list(self._doc_pages.values()) + list(self._pages.values()):
                moved = getattr(p, "document_moved", None)
                if id(p) in told or not callable(moved):
                    continue
                told.add(id(p))
                if getattr(p, "shows_document", None) is None or p.shows_document():
                    moved(sd.path)
            cur = self.current_page()
            if cur is not None and hasattr(cur, "refresh_document"):
                cur.refresh_document()
            try:
                RECENT.push(sd.path, len(sd.doc))
            except (OSError, ValueError):
                pass
            self.set_status(f"✓  Saved → {Path(out).name}", "success")
            if callable(after):
                after()
        return self._write(lambda stop: sd.save_as(out, garbage=1, deflate=True),
                           Path(out).name, then)

    def print_document(self) -> bool:
        """Print (Ctrl+P): Windows' print dialog, with a page range; the
        document as it is now, unsaved edits included."""
        sd = self.document
        if not sd.is_open():
            dialogs.warning("Print", "Open a PDF first.")
            return False
        from . import printing
        return printing.print_document(self, sd.doc, sd.name)

    def undo(self) -> bool:
        """Undo the document's last edit, whichever tool made it: that tool
        gets its own state back, every tool showing the document redraws."""
        if self._locked:
            return False
        sd = self.document
        step = sd.undo()
        if step is None:
            self.set_status("Nothing to undo", "muted")
            return False
        owner = step.extra.get("page") if isinstance(step.extra, dict) else None
        shown = self.current_page()
        for key, p in list(self._doc_pages.items()):
            if not p.shows_document():
                continue
            if key == owner:
                p.restore_step(step.extra.get("state"))
            if p is shown or p.isVisible():
                p.sync_document()
        self.set_status(f"Undone: {step.label}", "success")
        return True

    def note_document_page(self, page) -> None:
        """*page* shows the document (SharedDocPage.borrow): undo, Save as
        and the unsaved marks reach it, inside a workspace host too."""
        self._doc_pages[page.page_key()] = page

    def _on_current_changed(self, index: int):
        w = self.stackedWidget.widget(index)
        if w is not None:
            self.navigationInterface.setCurrentItem(w.objectName())
            self._updateStackedBackground()

    # ── search ──
    def _filter_nav(self, text: str = ""):
        self._apply_nav()

    def _apply_nav(self):
        """Which items show: a search shows its matches (folded groups too,
        with their title) and hides the titles with none; without one, a
        folded group shows its title only.  The icon-only pane, which has
        no titles, shows every icon."""
        q = self.search.edit.text().strip().lower()
        icons = self.navigationInterface.panel.displayMode == NavigationDisplayMode.COMPACT
        from . import structure
        # In a structure prototype the tools live in workspaces: a search for a
        # tool shows the workspace that holds it (the reference apps' Ctrl+K).
        hosting = {structure.host_for(t) for t in structure.matching_tools(q)} if q else set()
        for section, header, keys in self._sections:
            folded = header is not None and section in self._folded
            shown = 0
            for k in keys:
                vis = (q in self._labels[k].lower() or k in hosting) if q \
                    else (icons or not folded)
                self._items[k].setVisible(vis)
                shown += vis
            if header is not None:
                header.set_folded(folded)
                header.setVisible(bool(shown) if q else True)

    # ── folding groups ──
    def is_folded(self, section: str) -> bool:
        return section in self._folded

    def toggle_group(self, section: str):
        """Fold or unfold a navigation group (kept in PREFS)."""
        if section in self._folded:
            self._folded.discard(section)
        else:
            self._folded.add(section)
        self._save_folded()
        self._apply_nav()

    def _unfold_for(self, key: str):
        """Opening a tool by search or open_tool shows it: its group unfolds."""
        for section, _header, keys in self._sections:
            if key in keys and section in self._folded:
                self._folded.discard(section)
                self._save_folded()
                self._apply_nav()

    def _save_folded(self):
        setattr(PREFS, FOLDED_KEY, sorted(self._folded))
        try:
            PREFS.save()
        except OSError:
            pass

    def visible_tools(self) -> list[str]:
        """Tool keys the navigation shows now, in order (for tests)."""
        return [k for _s, _h, keys in self._sections for k in keys
                if not self._items[k].isHidden()]

    def nav_order(self) -> list[tuple[str, list[str]]]:
        """[(section header text or "" for the bottom group, [tool keys])]."""
        return [(h.text() if h is not None else "", list(keys))
                for _s, h, keys in self._sections]

    def _open_first_match(self):
        q = self.search.edit.text().strip()
        if not q:
            return
        from . import structure
        tools = structure.matching_tools(q.lower())
        if tools:                           # a tool in a workspace: open it there
            self.show_page(tools[0])
            return
        vis = self.visible_tools()
        if vis:
            self._unfold_for(vis[0])
            self.show_page(vis[0])

    def focus_search(self):
        if self._locked:
            return
        if self.compact:
            self._reveal_side(True)
        elif self.navigationInterface.panel.isCollapsed():
            self.navigationInterface.expand(useAni=False)
        self.search.edit.setFocus(Qt.ShortcutFocusReason)
        self.search.edit.selectAll()

    def clear_search(self):
        self.search.edit.clear()

    # ── shortcuts ──
    def page_hook(self, name: str) -> bool:
        """Call the current page's hook *name* (open / save / undo / delete)
        if it has one; ignored while a job holds the view."""
        if self._locked:
            return False
        fn = getattr(self.current_page(), name, None)
        if not callable(fn):
            return False
        fn()
        return True

    def _on_delete_key(self):
        fw = QApplication.focusWidget()
        if isinstance(fw, _TEXT_INPUTS) or (isinstance(fw, QComboBox) and fw.isEditable()):
            return False
        return self.page_hook("delete")

    # ══════════════════════════════════════════════════════════════════════════
    # STATUS BAR AND PROGRESS
    # ══════════════════════════════════════════════════════════════════════════
    def set_status(self, msg: str, role: str = "muted"):
        """role: muted / success / warning / danger (theme.STATUS_ROLES)."""
        if role not in theme.STATUS_ROLES:
            role = "muted"
        msg = status_with_symbol(msg, role)
        self._status_seq += 1
        self.status_role = role
        theme.label_role(self.status_label, role)
        self.status_label.setText(msg)

    def status_text(self) -> str:
        return self.status_label.text()

    def set_progress(self, value: float):
        """0.0 - 1.0; call on the main thread (bridge.post from a worker)."""
        self.progress.setValue(int(1000 * max(0.0, min(1.0, float(value)))))

    def progress_callback(self, scale: float = 1.0):
        """A worker's progress(fraction): posts set_progress(fraction * scale)
        to the main thread."""
        return lambda v: bridge.post(self.set_progress, v * scale)

    def _prog_show(self, label: str, cancellable: bool = True):
        self.progress.setValue(0)
        self.job_label.setText(label)
        self.cancel_button.setVisible(cancellable)
        self.progress_strip.show()

    def _prog_hide(self):
        self.progress_strip.hide()
        self.progress.setValue(0)
        self.job_label.setText("")

    # ══════════════════════════════════════════════════════════════════════════
    # JOBS
    # ══════════════════════════════════════════════════════════════════════════
    def run_job(self, worker_fn, label: str = "Working…", *, lock: bool = False,
                then=None, cancellable: bool = True,
                keep_password=None, own_save: bool = False) -> CancellableJob | None:
        """Run worker_fn(stop) in a background thread with progress and Cancel;
        stop is a threading.Event the worker checks with is_set().

        A str the worker returns becomes the status; a worker that posted its
        own status keeps it ("Done" / "Cancelled" only when it posted none).
        lock=True: the worker uses a document the page shows, so until it
        ends the page and the navigation are held (only Cancel works) and
        shortcuts are ignored.  then(kind, value), kind "done" / "error" /
        "cancel", runs on the main thread after the job has ended.
        cancellable=False: the worker never checks stop (a save, a single
        PyMuPDF call), so Cancel is not offered; it could not stop the write,
        only make the job report "Cancelled" after the file was written.
        keep_password=(kept, outputs): kept, from pages.ask_keep_password, is
        None (no password to keep) or the input's OpenPassword; outputs is a
        list of files, or a folder whose PDFs are the job's outputs (a split).
        Each of them the job writes gets kept's password before it reaches its
        name (core.password.protecting).

        A job that writes the open document's file (one of keep_password's
        outputs, own_save=False: a tool's output, not Save) first moves the
        document onto an in-memory copy, so the file is free to replace.

        One job at a time: while one runs this warns and returns None."""
        if self._current_job and self._current_job.is_running:
            dialogs.warning("Busy", BUSY_MSG)
            return None
        if keep_password is not None and not own_save and isinstance(keep_password[1], list):
            sd = self.document
            for out in keep_password[1]:
                if sd.is_open() and pages.same_path(str(out), sd.path):
                    sd._release(sd.path)
        if keep_password is not None and keep_password[0] is not None:
            worker_fn = _keeping_password(worker_fn, *keep_password)

        # Collect here, on the main thread, so the
        # collector never runs a widget's teardown on the worker.
        gc.collect()
        self._prog_show(label, cancellable)
        seq_at_start = self._status_seq
        if lock:
            self._lock_view()

        def finish(kind, value):
            if self._current_job is job:
                self._prog_hide()
            if lock:
                self._unlock_view()
            if then is not None:
                then(kind, value)
            if not self.job_running():
                self.snapshot_edits()       # a save drops the copy, an edit job makes one

        def on_done(result):
            if isinstance(result, str) and result:
                self.set_status(result, "success")
            elif self._status_seq == seq_at_start:
                self.set_status("Done", "success")
            finish("done", result)

        def on_error(exc):
            finish("error", exc)
            self.set_status(f"Error: {exc}", "danger")
            dialogs.error("Error", str(exc))

        def on_cancel():
            if self._status_seq == seq_at_start:
                self.set_status("Cancelled", "warning")
            finish("cancel", None)

        job = CancellableJob(
            fn=worker_fn,
            post=lambda cb: bridge.post(self._if_alive, cb),
            on_done=on_done,
            on_error=on_error,
            on_cancel=on_cancel,
        )
        self._current_job = job
        return job.start()

    def job_running(self) -> bool:
        return bool(self._current_job and self._current_job.is_running)

    def _if_alive(self, cb):
        if self._alive:
            cb()

    def _cancel_job(self):
        if (self._current_job and self._current_job.is_running
                and not self.cancel_button.isHidden()):
            self._current_job.cancel()

    def is_locked(self) -> bool:
        return self._locked

    def _lock_view(self):
        self._locked = True
        self.navigationInterface.setEnabled(False)
        self.stackedWidget.setEnabled(False)
        self.lock_overlay.setGeometry(self.stackedWidget.geometry())
        self.lock_overlay.show()
        self.lock_overlay.raise_()
        self.cancel_button.setFocus()

    def _unlock_view(self):
        self._locked = False
        self.lock_overlay.hide()
        self.navigationInterface.setEnabled(True)
        self.stackedWidget.setEnabled(True)

    # ══════════════════════════════════════════════════════════════════════════
    # FILES
    # ══════════════════════════════════════════════════════════════════════════
    def open_pdf_safe(self, path: str):
        """fitz.open(path), asking for the password of an encrypted file;
        None (after telling the user) when it cannot be opened.  Pushes the
        file to the recent list."""
        try:
            doc = fitz.open(path)
        except Exception as e:
            dialogs.error("Error", f"Could not open PDF:\n{e}")
            return None
        if not self._unlock(doc, Path(path).name):
            return None
        RECENT.push(path, len(doc))
        return doc

    def open_pdf_data(self, data: bytes, name: str):
        """open_pdf_safe for a PDF in memory (a recovered copy named *name*):
        not pushed to the recent list."""
        try:
            doc = fitz.open("pdf", data)
        except Exception as e:
            dialogs.error("Error", f"Could not open PDF:\n{e}")
            return None
        return doc if self._unlock(doc, name) else None

    @staticmethod
    def _unlock(doc, name: str) -> bool:
        """Ask for an encrypted *doc*'s password; False (closed) when it is
        not given or wrong."""
        if not doc.is_encrypted:
            return True
        pw = dialogs.ask_password(
            "Password required", "This PDF is password-protected. Enter the password:")
        if not pw:
            doc.close()
            return False
        if not doc.authenticate(pw):
            dialogs.error("Error", "Incorrect password.")
            doc.close()
            return False
        # Kept on the document until it is closed, for a PDF written from
        # it that keeps the password (pages.ask_keep_password).
        core_password.keep_open_password(doc, name, pw)
        return True

    # ── drag and drop ──
    @staticmethod
    def _local_paths(mime) -> list[str]:
        if not mime.hasUrls():
            return []
        return [u.toLocalFile() for u in mime.urls() if u.isLocalFile()]

    def dragEnterEvent(self, e):
        page = self.current_page()
        if (not self._locked and self._local_paths(e.mimeData())
                and callable(getattr(page, "accept_drop", None))):
            e.acceptProposedAction()
        else:
            e.ignore()

    def dragMoveEvent(self, e):
        self.dragEnterEvent(e)

    def dropEvent(self, e):
        n = self.forward_drop(self._local_paths(e.mimeData()))
        if n:
            e.acceptProposedAction()
        else:
            e.ignore()

    def forward_drop(self, paths) -> int:
        """Offer each path to the current page's accept_drop; how many it took."""
        if self._locked or not paths:
            return 0
        fn = getattr(self.current_page(), "accept_drop", None)
        if not callable(fn):
            return 0
        n = sum(1 for p in paths if fn(p))
        if not n:
            name = Path(paths[0]).name
            self.set_status(f"This tool does not open {name}", "warning")
        return n

    # ══════════════════════════════════════════════════════════════════════════
    # WINDOW MODES
    # ══════════════════════════════════════════════════════════════════════════
    def toggle_nav(self):
        """Ctrl+Alt+S: collapse or expand the navigation (in Compact Mode:
        bring it in or send it away).  Ignored while a job holds the view."""
        if self._locked:
            return
        if self.compact:
            self._reveal_side(not self._side_shown)
            return
        panel = self.navigationInterface.panel
        if panel.displayMode in (NavigationDisplayMode.EXPAND, NavigationDisplayMode.MENU):
            panel.collapse()
        else:
            self.navigationInterface.expand()

    def toggle_compact(self):
        if self._locked:                # the held page is not re-laid out mid-job
            return
        self.set_compact(not self.compact)

    def set_compact(self, on: bool):
        """Compact Mode: navigation, page header and context panel hidden."""
        if on == self.compact:
            return
        self.compact = on
        nav = self.navigationInterface
        self._stop_anim("side")
        self._keep_side_timer.stop()
        self._keep_ctx_timer.stop()
        self._side_shown = False
        self._ctx_revealed = False
        if on:
            self.hBoxLayout.removeWidget(nav)
            nav.hide()
        elif not getattr(self, "_nav_gone", False):   # (a prototype without the column)
            self.hBoxLayout.insertWidget(0, nav)
            nav.show()
        page = self.current_page()
        if page is not None:
            page.set_compact(on)
        self._place_title_bar()
        self._update_edge_watch()

    # ── left edge: the navigation floats in over the page ──
    def _reveal_side(self, on: bool):
        if not self.compact or on == self._side_shown:
            return
        nav = self.navigationInterface
        self._side_shown = on
        w = max(48, nav.width())
        h = self.height()
        if on:
            self._keep_side_timer.stop()
            nav.setGeometry(-w, 0, w, h)
            nav.show()
            nav.raise_()
            self.titleBar.raise_()
            self._slide("side", nav, QPoint(0, 0), SLIDE_MS)
        else:
            if self.search.edit.hasFocus():
                self.search.edit.clearFocus()
            self._slide("side", nav, QPoint(-w, 0), SLIDE_MS,
                        done=lambda: nav.hide() if not self._side_shown else None)

    # ── right edge: the page's context panel ──
    def _hide_revealed_context(self):
        page = self.current_page()
        if self._ctx_revealed and page is not None and page.has_context():
            page.show_context(False)
        self._ctx_revealed = False

    # ── top edge: the title bar ──
    def _place_title_bar(self):
        tb = self.titleBar
        if self._anims.get("top") and self._anims["top"].state() == QPropertyAnimation.Running:
            return
        x = 0 if (self.compact or getattr(self, "_nav_gone", False)) else 46
        y = 0 if (self._top_shown or not self._autohide_title) else -tb.height()
        tb.setGeometry(x, y, max(0, self.width() - x), tb.height())
        tb.raise_()
        self._set_top_margin()

    def _set_top_margin(self):
        # The bar keeps its own strip when it never hides; a hiding bar floats
        # over the page, except in Compact Mode, where the top edge brings the
        # page header back with it and the header must sit below the bar.
        reserve = (not self._autohide_title) or (self.compact and self._top_shown)
        self.widgetLayout.setContentsMargins(0, self.titleBar.height() if reserve else 0, 0, 0)

    def _show_top(self):
        if self._top_shown:
            return
        self._top_shown = True
        tb = self.titleBar
        tb.raise_()
        self._slide("top", tb, QPoint(tb.x(), 0), TOP_SLIDE_MS)
        page = self.current_page()
        if self.compact and page is not None:
            page.reveal_header(True)
        self._set_top_margin()

    def _hide_top(self):
        if not self._autohide_title or not self._top_shown:
            return
        self._top_shown = False
        tb = self.titleBar
        self._slide("top", tb, QPoint(tb.x(), -tb.height()), TOP_SLIDE_MS)
        page = self.current_page()
        if self.compact and page is not None:
            page.reveal_header(False)
        self._set_top_margin()

    def title_bar_shown(self) -> bool:
        return self._top_shown or not self._autohide_title

    def _over_title_buttons(self, x: int, y: int) -> bool:
        """Window point (x, y) over the title bar's own buttons (minimize to close)."""
        tb = self.titleBar
        first = getattr(tb, "minBtn", None)
        if first is None:
            return False
        left = tb.mapTo(self, first.pos()).x()
        return left <= x <= self.width() and 0 <= y <= tb.height()

    def _control_under(self, p: QPoint) -> bool:
        """A clickable control of the page lies under window point *p* (the bar ignored)."""
        from PySide6.QtWidgets import QAbstractButton, QAbstractItemView, QAbstractSlider
        kinds = (QAbstractButton, QLineEdit, QComboBox, QAbstractSpinBox, QAbstractSlider,
                 QAbstractItemView)
        for child in self.findChildren(QWidget, options=Qt.FindDirectChildrenOnly):
            if child is self.titleBar or not child.isVisible() or not child.geometry().contains(p):
                continue
            hit = child.childAt(child.mapFrom(self, p))
            while hit is not None and hit is not child:
                if isinstance(hit, kinds) and hit.isEnabled():
                    return True
                hit = hit.parentWidget()
        return False

    # ── the watcher ──
    def _update_edge_watch(self):
        want = ((self.compact or self._autohide_title) and self._alive
                and self.isVisible() and not self.isMinimized())
        if want and not self._edge.isActive():
            self._edge.start()
        elif not want and self._edge.isActive():
            self._edge.stop()

    def edge_watch_active(self) -> bool:
        return self._edge.isActive()

    def _poll_edges(self, pos: QPoint | None = None):
        """One look at the pointer (global *pos*, default the real one)."""
        g = pos if pos is not None else self._pointer()
        p = self.mapFromGlobal(g)
        x, y, w, h = p.x(), p.y(), self.width(), self.height()
        near_y = -OUTSIDE_Y <= y <= h + OUTSIDE_Y

        if self._autohide_title:
            tb_h = self.titleBar.height()
            page = self.current_page()
            if self.compact and page is not None and page.header.isVisible():
                tb_h = max(tb_h, page.mapTo(self, page.header.geometry().bottomLeft()).y())
            on_bar = 0 <= x <= w and 0 <= y <= tb_h
            if 0 <= x <= w and -OUTSIDE_Y <= y <= EDGE:
                self._show_top()
                self._hide_top_timer.stop()
                self._bar_in_use = True                  # brought by the top edge
            elif self._top_shown:
                if not on_bar:
                    self._bar_in_use = False             # the pointer went back to the page
                if self._over_title_buttons(x, y) or (self.compact and on_bar):
                    self._hide_top_timer.stop()          # over its buttons (or the header): keep it
                elif on_bar and self._bar_in_use:
                    # Still on the bar since the top edge brought it: on the way to its
                    # buttons, over whatever lies under it (the search field, 2026-10-22).
                    self._hide_top_timer.stop()
                elif on_bar and self._control_under(p):
                    # Back from the page onto one of its controls while the bar lingers
                    # (the main action at the top right, 2026-10-21): make way at once.
                    self._hide_top_timer.stop()
                    self._hide_top()
                elif not self._hide_top_timer.isActive():
                    self._hide_top_timer.start()

        if not self.compact:
            return

        nav = self.navigationInterface
        if self._side_shown:
            if x > nav.width() + 10 and not self.search.edit.hasFocus():
                if not self._keep_side_timer.isActive():
                    self._keep_side_timer.start()
            else:
                self._keep_side_timer.stop()
        elif -OUTSIDE_X <= x <= EDGE and 0 <= y <= h:
            self._reveal_side(True)

        page = self.current_page()
        if page is not None and page.has_context():
            if self._ctx_revealed:
                if x < w - page.context_width() - 10:
                    if not self._keep_ctx_timer.isActive():
                        self._keep_ctx_timer.start()
                else:
                    self._keep_ctx_timer.stop()
            elif w - EDGE <= x <= w + OUTSIDE_X and near_y and 0 <= y <= h \
                    and not page.context_shown():
                page.show_context(True)
                self._ctx_revealed = True

    # ── animation helper ──
    def _stop_anim(self, name: str):
        a = self._anims.pop(name, None)
        if a is not None:
            a.stop()

    def _slide(self, name: str, widget: QWidget, to: QPoint, ms: int, done=None):
        self._stop_anim(name)
        a = QPropertyAnimation(widget, b"pos", self)
        a.setDuration(ms)
        a.setEndValue(to)
        a.setEasingCurve(QEasingCurve.OutCubic)
        if done is not None:
            a.finished.connect(done)
        self._anims[name] = a
        a.start()
        return a

    # ══════════════════════════════════════════════════════════════════════════
    # QT EVENTS
    # ══════════════════════════════════════════════════════════════════════════
    def eventFilter(self, obj, e):
        if not self.__dict__.get("_ready"):   # still inside FluentWindow.__init__
            return super().eventFilter(obj, e)
        if obj is self.titleBar and e.type() == QEvent.Paint and self._autohide_title:
            # The bar floats over the page when it comes back: give it a ground.
            p = QPainter(obj)
            p.fillRect(obj.rect(), theme.color("surface"))
            p.end()
        elif obj is self.stackedWidget and e.type() in (QEvent.Resize, QEvent.Move):
            if self.lock_overlay.isVisible():
                self.lock_overlay.setGeometry(self.stackedWidget.geometry())
        return super().eventFilter(obj, e)

    def resizeEvent(self, e):
        super().resizeEvent(e)          # FluentWindow moves the title bar to (46, 0)
        if not self.__dict__.get("_ready"):
            return
        self._note_normal_rect()
        self._place_title_bar()
        if self.compact and self._side_shown:
            nav = self.navigationInterface
            nav.resize(nav.width(), self.height())

    def moveEvent(self, e):
        super().moveEvent(e)
        self._note_normal_rect()

    def _note_normal_rect(self):
        # Only a plain window's rect: a maximized frameless window reports a
        # normal geometry inset by its resize border, which saved and
        # restored moved and shrank the window 8 px a side every session.
        if self.windowState() == Qt.WindowNoState and self.__dict__.get("_ready"):
            self._normal_rect = QRect(self.geometry())

    # ── the window's place across sessions ──
    def _restore_place(self, geo: str):
        """Put the window where the last session left it: a JSON rect plus a
        maximized flag (an older base64 saveGeometry() still restores)."""
        try:
            d = json.loads(geo)
        except ValueError:
            d = None
        if not isinstance(d, dict):
            try:
                self.restoreGeometry(QByteArray.fromBase64(geo.encode("ascii")))
            except (UnicodeError, ValueError):
                pass
            return
        try:
            r = QRect(int(d["x"]), int(d["y"]), int(d["w"]), int(d["h"]))
        except (KeyError, TypeError, ValueError):
            return
        if r.width() <= 0 or r.height() <= 0:
            return
        if not _on_a_screen(r):              # its monitor is gone: bring it back
            avail = QApplication.primaryScreen().availableGeometry()
            r.moveTopLeft(avail.topLeft())
        self.setGeometry(r)
        self._normal_rect = QRect(self.geometry())
        if d.get("maximized") is True:
            self.setWindowState(self.windowState() | Qt.WindowMaximized)

    def place_pref(self) -> str:
        """What _finish_close stores: the un-maximized rect and the state."""
        if self.windowState() == Qt.WindowNoState:
            self._normal_rect = QRect(self.geometry())
        r = self._normal_rect
        return json.dumps({"x": r.x(), "y": r.y(), "w": r.width(), "h": r.height(),
                           "maximized": self.isMaximized()})

    def showEvent(self, e):
        super().showEvent(e)
        if not self.__dict__.get("_ready"):
            return
        if self._first_show:
            self._first_show = False
            nav = self.navigationInterface
            # (a structure prototype's icon strip, PK_LEFT=rail, stays one)
            if (self.width() >= NAV_MIN_EXPAND_WINDOW and not self.compact
                    and not getattr(self, "_rail", False)):
                nav.expand(useAni=False)
                self._apply_nav()       # expand(useAni=False) says nothing of its new mode
            # Once the window is up, so the question sits over it.
            QTimer.singleShot(0, lambda: self._alive and self.offer_recovery())
        self._update_edge_watch()

    def hideEvent(self, e):
        super().hideEvent(e)
        if self.__dict__.get("_ready"):
            self._update_edge_watch()

    def changeEvent(self, e):
        super().changeEvent(e)
        if e.type() == QEvent.WindowStateChange and self.__dict__.get("_ready"):
            self._update_edge_watch()

    # ══════════════════════════════════════════════════════════════════════════
    # CLOSE
    # ══════════════════════════════════════════════════════════════════════════
    def closeEvent(self, e):
        if self._close_ok:
            super().closeEvent(e)
            return
        if self._closing:               # already waiting for the job to end
            e.ignore()
            return
        job = self._current_job
        if not (job and job.is_running):        # (a running job asks its own question)
            if not self.settle_unsaved(None, self.close):
                e.ignore()
                return
            n = self.unapplied_marks()
            # Redact's boxes are marks, not edits: Save does not keep them (owner, 2026-10-23).
            if n and not dialogs.ask_yes_no("Close", UNAPPLIED_QUESTION.format(
                    n=n, boxes="box" if n == 1 else "boxes")):
                e.ignore()
                return
        if job and job.is_running:
            if not dialogs.ask_yes_no("Job running",
                                      "A job is still running. Cancel it and quit?"):
                e.ignore()
                return
            job.cancel()
            self.set_status("Cancelling before exit…", "warning")
            self._closing = True
            self._close_deadline = time.monotonic() + CLOSE_WAIT_S
            self._close_timer.start()
            e.ignore()
            return
        self._finish_close()
        super().closeEvent(e)

    def _close_when_idle(self):
        # Poll instead of join(): the worker's posts need the event loop, and
        # a save in progress must be allowed to finish.
        job = self._current_job
        if job is not None and job.is_running and time.monotonic() < self._close_deadline:
            return
        self._close_timer.stop()
        self._finish_close()
        self.close()

    def _finish_close(self):
        self._close_ok = True
        self._edge.stop()
        self._hide_top_timer.stop()
        self._recovery_timer.stop()
        if self._recovery is not None:      # a normal exit: nothing to recover
            self._recovery.close()
            self._recovery = None
        page = self.current_page()
        if hasattr(page, "deactivate"):
            try:
                page.deactivate()
            except Exception:
                pass
        setattr(PREFS, GEOMETRY_KEY, self.place_pref())
        # A job still writing past CLOSE_WAIT_S dies with the process before
        # atomic_output can delete its temp file: the next start removes it.
        stale = set(self.__dict__.get("_stale_parts", [])) | set(live_parts())
        setattr(PREFS, STALE_PARTS_KEY, sorted(p for p in stale if os.path.exists(p)))
        try:
            PREFS.save()
        except OSError:
            pass
        self._alive = False


def _norm(path: str) -> str:
    return os.path.normcase(os.path.abspath(path))


def _keeping_password(work, kept, outputs):
    """work(stop) with every output it writes (*outputs*: a list of files, or a
    folder whose PDFs are the outputs) encrypted with *kept*'s open password
    and permissions before the file reaches its name.  A file it does not
    write (Cancel before the save) is not touched.  The password is let go
    once the job ends: the window keeps its last job."""
    if isinstance(outputs, str):
        folder, names = _norm(outputs), set()
    else:
        folder, names = None, {_norm(p) for p in outputs}

    def wanted(target: str) -> bool:
        t = _norm(target)
        return t in names or (folder is not None and os.path.dirname(t) == folder
                              and t.endswith(".pdf"))
    held = [kept]

    def run(stop):
        pw = held.pop()
        with core_password.protecting(pw.user_pw, pw.perm, wanted):
            del pw
            return work(stop)
    return run


def _on_a_screen(rect: QRect) -> bool:
    """Whether some of *rect* lies on a connected screen's work area."""
    return any(s.availableGeometry().intersects(rect) for s in QApplication.screens())


def _remove_stale_parts(paths) -> list[str]:
    """Delete the temp files a killed job left (only atomic_output's own
    hidden ".<stem>-XXXX<ext>.part" names); the ones that cannot go yet."""
    left = []
    for p in paths if isinstance(paths, list) else []:
        if not isinstance(p, str):
            continue
        name = os.path.basename(p)
        if not (name.startswith(".") and name.endswith(".part")):
            continue
        try:
            os.unlink(p)
        except FileNotFoundError:
            pass
        except OSError:
            left.append(p)
    return left


class _Overlay(QWidget):
    """Covers the page while a job holds it; swallows the pointer."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setCursor(Qt.BusyCursor)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.fillRect(self.rect(), theme.color("overlay"))

    def mousePressEvent(self, e):
        e.accept()

    def mouseReleaseEvent(self, e):
        e.accept()

    def mouseDoubleClickEvent(self, e):
        e.accept()

    def wheelEvent(self, e):
        e.accept()
