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

Optional hooks the shell calls when a page defines them:
    open() / save() / undo()     Ctrl+O / Ctrl+S / Ctrl+Z
    delete()                     Delete (not while a text field has focus)
    accept_drop(path) -> bool    a file dropped on the window (a single-input
                                 page makes it the current document)
    activate() / deactivate()    the page is shown / left
    open_path(path)              open this file (a Home recent-file click)

A single-input page (doc_input(), or a WorkspacePage) follows the window's
current document: document_path() / load_document(path) / clear_document(),
and an editor adds is_dirty() / discard_changes() / save(after=None) for the
unsaved-edits question (MainWindow.settle_unsaved).
"""
from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QEasingCurve, QEvent, QObject, QPoint, Qt, QVariantAnimation
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import (QButtonGroup, QFrame, QHBoxLayout, QSizePolicy, QVBoxLayout,
                               QWidget)
from qfluentwidgets import (BodyLabel, CaptionLabel, IconWidget, PrimaryPushButton, PushButton,
                            RadioButton, Slider, SwitchButton,
                            SimpleCardWidget, SingleDirectionScrollArea, StrongBodyLabel,
                            SubtitleLabel, TitleLabel, TransparentPushButton,
                            TransparentToggleToolButton,
                            TransparentToolButton, setCustomStyleSheet)

from . import dialogs
from . import theme
from ..core.doc_state import DocHolder
from ..core.password import OpenPassword, open_password_of, shared_open_password

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
CONTROL_H = 32              # Fluent's standard control height: no control is shorter
ACTION_SIZE = (160, CONTROL_H)
CARD_RADIUS = 4             # WinUI ControlCornerRadius (settings cards, expanders)

# The current document (owner's decisions 2026-10-10)
HINT_SUBTITLE = "Open a PDF to start"       # a subtitle that gives way to the file name
CONTINUE_TEXT = "Continue with it"          # after a job: the output becomes current
START_OVER_TEXT = "Start over"              # after a job: the tool and the document clear


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


class _Elided:
    """One line that shortens in the middle when it does not fit (as File
    Explorer shows a long path), then the whole text in its tooltip.  text() is
    the whole text."""

    _full = ""

    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self.setMinimumWidth(1)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setText(text)

    def setText(self, text: str):
        self._full = text
        self._fit()

    def text(self) -> str:
        return self._full

    def _fit(self):
        shown = self.fontMetrics().elidedText(self._full, Qt.ElideMiddle, max(1, self.width()))
        super().setText(shown)
        self.setToolTip(self._full if shown != self._full else "")

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._fit()


class ElidedLabel(_Elided, BodyLabel):
    pass


class ElidedCaption(_Elided, CaptionLabel):
    pass


def muted_caption(text: str = "", parent=None) -> CaptionLabel:
    lbl = CaptionLabel(text, parent)
    theme.label_role(lbl, "muted")
    return lbl


def muted_path(text: str = "", parent=None) -> ElidedCaption:
    """A muted caption holding a path: one line, shortened in the middle."""
    lbl = ElidedCaption(text, parent)
    theme.label_role(lbl, "muted")
    return lbl


def plain_card() -> SimpleCardWidget:
    """A Fluent card with Windows 11's corner radius."""
    c = SimpleCardWidget()
    c.setBorderRadius(CARD_RADIUS)
    return c


def card(padding: int = 16) -> SimpleCardWidget:
    """A plain card with a vertical layout (card.layout())."""
    c = plain_card()
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
                label_width: int | None = None, path: bool = False) -> QWidget:
    """Add a Windows 11 settings row to *group* (a card()) and return the
    container for its control: the name and description sit in a fixed-width
    column on the left, the control right-aligned, rows split by thin lines.

        row = setting_row(level_card, "Level", "How hard to compress")
        row.layout().addWidget(combo)

    label_width: the name column's width (LABEL_COLUMN by default); 0 lets it
    take the room the control leaves, for a narrow column such as a
    CollectionPage's settings.  path: the description is a file path, one
    line shortened in the middle (ElidedCaption) instead of wrapped.

    The control also carries the row's labels and the line above it:
    control.title_label, control.desc_label (None without *desc*) and
    control.divider (None for the first row).
    """
    lay = group.layout()
    rows = int(group.property("pk_rows") or 0)
    divider = None
    if rows == 0:
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
    else:
        divider = Divider()
        lay.addWidget(divider)
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
    d = None
    if desc:
        if path:
            d = muted_path(desc, texts)
        else:
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
    control.title_label, control.desc_label, control.divider = name, d, divider
    return control


class RadioChoice(QButtonGroup):
    """A one-of-N choice: self.buttons maps each value to its RadioButton."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.buttons: dict = {}

    def value(self):
        return next(v for v, rb in self.buttons.items() if rb.isChecked())

    def set(self, value):
        self.buttons[value].setChecked(True)


def radio_rows(group: QWidget, choices, default, *, row=setting_row,
               parent=None) -> RadioChoice:
    """One setting row per (value, title, desc) in *choices* in *group* (a
    card()), each with a radio button; *default* is checked.  *row* makes a
    row (a page's own setting_row)."""
    choice = RadioChoice(parent)
    for value, title, desc in choices:
        rb = radio_button()
        rb.setChecked(value == default)
        choice.addButton(rb)
        control = row(group, title, desc)
        control.layout().addWidget(rb)
        _ClickSelects(control.parentWidget(), rb, rb.click)
        choice.buttons[value] = rb
    return choice


_TARGET_QSS = (f"RadioButton {{ min-height: {CONTROL_H}px; max-height: {CONTROL_H}px; "
               f"min-width: {CONTROL_H}px; }}")


def radio_button() -> RadioButton:
    """A text-less RadioButton in a CONTROL_H square, its circle in the middle
    (the library's style sheet holds it 24 px tall, the circle at 11, 12)."""
    rb = RadioButton("")
    setCustomStyleSheet(rb, _TARGET_QSS, _TARGET_QSS)
    rb.setFixedSize(CONTROL_H, CONTROL_H)
    rb.indicatorPos = QPoint(CONTROL_H // 2, CONTROL_H // 2)
    return rb


def toggle_switch(on: bool) -> SwitchButton:
    """A Fluent toggle without its On / Off text, in a CONTROL_H tall box
    that all takes the click (the library's box is the 22 px pill)."""
    s = SwitchButton()
    s.setOnText("")
    s.setOffText("")
    s.setChecked(on)
    s.setFixedHeight(CONTROL_H)

    def flip():
        s.indicator.toggle()
        s.indicator.checkedChanged.emit(s.indicator.isChecked())   # as a click on the pill
    _ClickSelects(s, s.indicator, flip)
    return s


class _ClickSelects(QObject):
    """A left click on *row* (its parts that take no click themselves) runs
    *action*, while *button* is enabled: a settings row checks its radio
    button, as on Windows, so the target is the row and not the 20 px circle."""

    def __init__(self, row: QWidget, button, action):
        super().__init__(row)
        self._button, self._action = button, action
        row.installEventFilter(self)

    def eventFilter(self, obj, e):
        if e.type() not in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease):
            return False
        if e.button() != Qt.LeftButton or not self._button.isEnabled():
            return False
        if e.type() == QEvent.MouseButtonRelease and obj.rect().contains(e.position().toPoint()):
            self._action()
        return True


class TallSlider(Slider):
    """Fluent's Slider in a CONTROL_H tall box, its groove and handle drawn in
    the middle (the library draws them at the top of a 22 px box), so the
    whole box takes clicks."""

    def __init__(self, orientation=Qt.Horizontal, parent=None):
        super().__init__(orientation, parent)
        self.setMinimumHeight(CONTROL_H)

    def _offset(self) -> int:
        return max(0, (self.height() - self.handle.height()) // 2)

    def _adjustHandlePos(self):
        super()._adjustHandlePos()
        self.handle.move(self.handle.x(), self._offset())

    def _drawHorizonGroove(self, painter):
        painter.translate(0, self._offset())
        super()._drawHorizonGroove(painter)


def icon_button(icon) -> TransparentToolButton:
    """A borderless icon-only button, CONTROL_H square."""
    b = TransparentToolButton(icon)
    b.setFixedSize(CONTROL_H, CONTROL_H)
    return b


def labelled_slider(row: QWidget, lo: int, hi: int, value: int, unit: str, *,
                    width: int = 220, label_width: int = 64, fixed: bool = True):
    """A horizontal Slider from *lo* to *hi* at *value* and, beside it, a
    label of fixed *label_width* showing the value and *unit* (s.value_label),
    both added to *row* (a setting_row's control).  The slider is *width*
    wide, or at least that wide when not *fixed*."""
    s = TallSlider(Qt.Horizontal)
    s.setRange(lo, hi)
    if fixed:
        s.setFixedWidth(width)
    else:
        s.setMinimumWidth(width)
    lbl = BodyLabel()
    lbl.setFixedWidth(label_width)
    s.valueChanged.connect(lambda v: lbl.setText(f"{v}{unit}"))
    s.setValue(value)
    lbl.setText(f"{s.value()}{unit}")
    s.value_label = lbl
    row.layout().addWidget(s)
    row.layout().addWidget(lbl)
    return s


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
        self.setBorderRadius(CARD_RADIUS)
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
        self.meta_label = muted_path("", self)
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


def same_path(a: str | None, b: str | None) -> bool:
    """Whether two paths name the same file (case and form ignored)."""
    if not a or not b:
        return False
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


class DocInput:
    """The PDF a single-input page acts on (in place of a FileCard, which
    pages no longer show): the same API, path() / set_path() / clear() /
    accepts() / accept_drop() / choose(), with nothing drawn.  The page shows
    it through refresh_document (subtitle, bar chip, empty-state target).

    set_path(path) is a choice of file: on_change(path) runs, then the page
    tells the window, which makes *path* the current document when it is
    still the page's file (a load that failed puts the old one back)."""

    exts = (".pdf",)

    def __init__(self, page, on_change=None):
        self._page = page
        self._on_change = on_change
        self._path = ""

    def path(self) -> str:
        return self._path

    def set_path(self, path: str, notify: bool = True):
        new = str(path) if path else ""
        self._path = new
        if notify and self._on_change is not None:
            self._on_change(new)
        self._page.refresh_document(announce=notify and bool(new) and self._path == new)

    def clear(self):
        self.set_path("", notify=False)

    def accepts(self, path: str) -> bool:
        return os.path.isfile(path) and Path(path).suffix.lower() == ".pdf"

    def accept_drop(self, path: str) -> bool:
        if not self.accepts(path):
            return False
        self.set_path(path)
        return True

    def choose(self):
        win = self._page.window_
        if win is not None:
            return win.browse_document()
        p = dialogs.ask_open("Open PDF", [("PDF", "*.pdf")])
        if p:
            self.set_path(p)


def ask_keep_password(*docs) -> OpenPassword | None:
    """Before a PDF is written from *docs* (one input, or a merge's): when the
    input was opened with a password, ask whether the new file keeps it.  The
    OpenPassword to pass to window.run_job(keep_password=...) on Yes; None on
    No or when there is no open password (an unprotected input, or one with
    an owner password only).  Several inputs ask only when every protected one
    has the same open password (shared_open_password: the first one's name,
    the rights all of them allow).  Ask after the save dialog, so Cancel
    there asks nothing."""
    kept = shared_open_password([open_password_of(d) for d in docs])
    if kept is None:
        return None
    if dialogs.ask_yes_no("Password", f'"{kept.name}" is password-protected. '
                                      "Keep the password on the new file?"):
        return kept
    return None


class HeldDoc(DocHolder):
    """A page that keeps its input's (self.file) document open in
    self._doc; self._src is the file it was read from."""
    _src: str = ""

    def open_held(self, path: str, title: str | None = None):
        """Open *path* as the held document and close the one before (the
        page's subtitle names it: refresh_document).  When it cannot be opened
        the document already open stays and the input goes back to its file.
        The new document, or None.  *title* is not used any more."""
        doc = self.window_.open_pdf_safe(path)
        if doc is None:
            self.file.set_path(self._src if self._doc is not None else "", notify=False)
            return None
        self._close_doc()
        self._doc, self._src = doc, path
        self._dirty = False
        return doc

    def release_held(self, title: str | None = None, subtitle: str = ""):
        """Close the held document and empty the input (*title* and
        *subtitle* are not used any more: the subtitle never changes)."""
        self._close_doc()
        self._src = ""
        self._dirty = False
        self.file.clear()

    def saved_elsewhere(self, out: str) -> bool:
        """Whether *out* is a file other than the one the document came from."""
        return not same_path(out, self._src)

    def park_document(self):
        """The page is left: a document with no unsaved edits is closed, so
        its file is free for other tools to overwrite; the input keeps the
        path and the page reopens it when shown (MainWindow._follow)."""
        if self._doc is not None and not self.is_dirty():
            self._close_doc()

    def is_parked(self) -> bool:
        return self._doc is None and bool(self.file.path())


class WorkspaceDoc(DocHolder):
    """The document a WorkspacePage edits, held in self._doc."""

    _src_path: str = ""

    def open_document(self, path: str, title: str = ""):
        """Open *path* in place of the document shown, at page 1 with no undo
        history and no unsaved edits; it becomes the current document.  The
        new document, or None (the old one stays) when it cannot be opened.
        *title* is not used any more (the subtitle names the file)."""
        doc = self.window_.open_pdf_safe(path)
        if doc is None:
            return None
        self._close_doc()
        self._doc, self._pg, self._undo_stack = doc, 0, []
        self._src_path, self._dirty = str(path), False
        self.refresh_document(announce=True)
        return doc

    def save(self, after=None):
        """Ctrl+S: save the document to a file the user chooses (save_name
        offered); the box says "<saved_what> saved".  after(): run once it
        is saved (the unsaved-edits question's Save)."""
        if self._doc is None:
            return dialogs.warning("Save", "Open a PDF first.")
        out = dialogs.ask_save(self.save_name, ".pdf", [("PDF", "*.pdf")])
        if not out:
            return
        kept = ask_keep_password(self._doc)
        win = self.window_

        def done(kind, _value):
            # A save over the open file goes on from an in-memory copy of it.
            self.show_current()
            if kind == "done":
                self._dirty = False
                win.set_status(f"✓  Saved → {Path(out).name}", "success")
                dialogs.info("Saved", f"{self.saved_what} saved:\n{out}")
                if not same_path(out, self._src_path):
                    self.offer_output(out)
                if callable(after):
                    after()

        win.run_job(lambda stop: self._save_doc(out, deflate=True), f"Saving {Path(out).name}…",
                    lock=True, then=done, cancellable=False, keep_password=(kept, [out]))


class Refusal(Exception):
    """Raised by run_on_file's prepare(doc): its message is shown as a warning."""


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
        self._ctx_before_compact = True     # the panel as the user left it
        self._buttons: list = []
        self._subtitle = subtitle           # the page's own; the document's name follows it
        self.doc_bar = None                 # bar layout: the Open control + chip row
        self.drop_target = None             # the empty-state target (single-input pages)
        self._offer = None                  # (InfoBar, output path): the after-job question

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
        self._titles = titles
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
        """The title, and with *subtitle* the page's own subtitle (the
        document's name follows it: _show_subtitle)."""
        self.title_label.setText(title)
        if subtitle is not None:
            self._subtitle = subtitle
        self._show_subtitle()

    def _show_subtitle(self):
        """nav layout: "<subtitle> · <file name>" while the page has a
        document; bar layout: the subtitle (the chip names the file).  A
        subtitle that only says to open a file (HINT_SUBTITLE) gives way to
        the file name in either layout."""
        from . import docui
        path = self.document_path() if self.follows_document else ""
        name, base = (Path(path).name if path else ""), self._subtitle
        if name and base == HINT_SUBTITLE:
            text = name
        elif name and docui.layout() == "nav":
            text = f"{base} · {name}" if base else name
        else:
            text = base
        self.subtitle_label.setText(text)
        self.subtitle_label.setVisible(bool(text))

    # ── the document (single-input pages) ──
    follows_document = False    # True: the page shows the window's current document

    def doc_input(self, on_change=None) -> DocInput:
        """Make this a single-input page: self.file holds its PDF (nothing
        drawn), the empty-state target goes into the body here (where a
        FileCard went, TARGET_FORM_H tall, the options below it stay shown)
        while there is no document; the bar layout adds its row under the
        subtitle."""
        from . import docui
        self.file = DocInput(self, on_change)
        self.follows_document = True
        self.drop_target = docui.DropTarget(self.window_, height=docui.TARGET_FORM_H)
        self.body.addWidget(self.drop_target)
        self._build_doc_bar()
        return self.file

    def _build_doc_bar(self):
        from . import docui
        if docui.layout() == "bar" and self.doc_bar is None:
            self.doc_bar = docui.DocBar(self.window_, self.header)
            self._titles.addWidget(self.doc_bar)

    def document_path(self) -> str:
        """The file this page acts on ("" for none)."""
        f = getattr(self, "file", None)
        return f.path() if isinstance(f, DocInput) else ""

    def document_name(self) -> str:
        return Path(self.document_path()).name

    def load_document(self, path: str) -> bool:
        """Show *path* (the window's current document); whether it is shown."""
        self.file.set_path(path)
        return same_path(self.document_path(), path)

    def clear_document(self):
        """Empty the page's input (Start over, the clear action)."""
        f = getattr(self, "file", None)
        if isinstance(f, (DocInput, FileCard)):
            f.clear()
        self.refresh_document()

    _dirty = False

    def is_dirty(self) -> bool:
        """Edits since the last save or open (the editing screens)."""
        return False

    def park_document(self):
        """The page is left (after deactivate): a page holding its document
        open lets the file go and keeps the path (HeldDoc, WorkspacePage)."""

    def is_parked(self) -> bool:
        """The document is parked: to be reopened when the page is shown."""
        return False

    def discard_changes(self):
        """Drop the unsaved edits: the page lets its document go (it opens
        it afresh the next time it follows the current document)."""
        self.clear_document()
        self._dirty = False

    def refresh_document(self, announce: bool = False):
        """Show what the page acts on: the subtitle, the bar chip, and the
        empty-state target while there is none.
        announce: the user chose this file; it becomes the current document."""
        path = self.document_path() if self.follows_document else ""
        self._show_subtitle()
        if self.doc_bar is not None:
            self.doc_bar.show_path(path)
        self._show_target(not path)
        if announce and path and self.window_ is not None:
            self.window_.set_current_document(path)

    def _show_target(self, empty: bool):
        if self.drop_target is not None:
            self.drop_target.setVisible(empty)

    def showEvent(self, e):
        super().showEvent(e)
        if self.follows_document:
            self.refresh_document()

    # ── after a job: the question (owner: ask once) ──
    def offer_output(self, out: str):
        """A job wrote one PDF, *out*: an InfoBar at the top of the page,
        "<name> is ready", with Continue with it / Start over."""
        from qfluentwidgets import InfoBar, InfoBarIcon, InfoBarPosition
        self.dismiss_offer()
        bar = InfoBar(InfoBarIcon.SUCCESS, f"{Path(out).name} is ready", "",
                      Qt.Horizontal, isClosable=False, duration=-1,
                      position=InfoBarPosition.NONE, parent=self)
        bar.setObjectName("afterJobBar")
        cont = PushButton(CONTINUE_TEXT, bar)
        cont.clicked.connect(self.continue_with_output)
        over = PushButton(START_OVER_TEXT, bar)
        over.clicked.connect(self.start_over)
        bar.addWidget(cont)
        bar.addWidget(over)
        bar.continue_button, bar.start_over_button = cont, over
        self.layout().insertWidget(0, bar)
        self._offer = (bar, str(out))

    def offered_output(self) -> str | None:
        return self._offer[1] if self._offer is not None else None

    def offer_bar(self):
        return self._offer[0] if self._offer is not None else None

    def dismiss_offer(self):
        if self._offer is None:
            return
        bar, _out = self._offer
        self._offer = None
        bar.hide()
        self.layout().removeWidget(bar)
        bar.setParent(None)
        bar.deleteLater()

    def continue_with_output(self):
        """The output becomes the current document; this tool shows it."""
        out = self.offered_output()
        self.dismiss_offer()
        if out and self.window_ is not None:
            self.window_.open_document(out)

    def start_over(self):
        """This tool and the current document are cleared."""
        win = self.window_
        if win is not None and not win.settle_unsaved(self, self.start_over):
            return
        self.dismiss_offer()
        self.clear_document()
        if win is not None:
            win.set_current_document(None)

    def leave_offer(self):
        """The page is left with the question open: as Continue with it."""
        out = self.offered_output()
        self.dismiss_offer()
        if out and self.window_ is not None:
            self.window_.set_current_document(out)

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
                fg = theme.hex_color("on_danger", dark)
                return (f"PrimaryPushButton{{background-color:{bg};border:1px solid {bg};"
                        f"color:{fg};}}"
                        f"PrimaryPushButton:hover{{background-color:{hv};border-color:{hv};}}"
                        f"PrimaryPushButton:pressed{{background-color:{hv};}}")
            theme.keep_styled(btn, lambda b: setCustomStyleSheet(b, qss(False), qss(True)))
        if slot is not None:
            btn.clicked.connect(slot)
        self._place(btn, True)
        return btn

    def secondary(self, text: str, slot=None) -> PushButton:
        btn = PushButton(text, self)
        btn.setMinimumHeight(CONTROL_H)
        btn.pk_primary = False
        if slot is not None:
            btn.clicked.connect(slot)
        self._place(btn, False)
        return btn

    def add_header_widget(self, w: QWidget):
        """Something for the header's actions area that is not an action
        (a file chip, a page counter); it stays in the header either way."""
        self.header_actions.insertWidget(0, w, 0, Qt.AlignTop)

    # ── the single-file run ──
    def chosen_file(self, title: str) -> str:
        """The file card's path; "" after a warning when none is chosen."""
        src = self.file.path()
        if not src:
            dialogs.warning(title, "Select a PDF first.")
        return src

    def run_on_file(self, title: str, work, label, report, *, src: str | None = None,
                    save: tuple | None = None, prepare=None, open_doc=None, ended=None,
                    cancellable: bool = True, warning_box: bool = False,
                    parts: bool = False):
        """Run *work* on the chosen file: the file card's (or *src*, already
        checked), opened, prepare(doc), the output asked for, then
        work(doc, out, stop, progress) in a job (it closes doc) and, when the
        job is done, report(result, out) -> (role, status, box title, box text).
        warning_box: a "warning" result is shown in a warning box, not an
        information box (Compress: the saved file is no smaller).

        save: (default name, extension, filters) asks for a file; None asks
        for a folder.  label: the job's label, or a callable giving it after
        prepare.  prepare(doc): a ValueError's message is shown as an error,
        a Refusal's as a warning; either closes doc and stops.  open_doc(src)
        -> doc | None replaces window.open_pdf_safe.  ended(kind) runs however
        the job ended, before report.

        A PDF output (save with ".pdf", or *parts*: work writes PDFs into the
        chosen folder) from an input opened with a password asks once whether
        the new files keep it (ask_keep_password).  One PDF written (save with
        ".pdf") puts the after-job question up (offer_output); a folder of
        outputs asks nothing.

        The job, or None when none was started (no file, a refusal, a
        cancelled save dialog, another job running)."""
        if src is None:
            src = self.chosen_file(title)
            if not src:
                return None
        win = self.window_
        doc = open_doc(src) if open_doc is not None else win.open_pdf_safe(src)
        if doc is None:
            return None
        if prepare is not None:
            try:
                prepare(doc)
            except Refusal as e:
                doc.close()
                dialogs.warning(title, str(e))
                return None
            except ValueError as e:
                doc.close()
                dialogs.error(title, str(e))
                return None
        out = dialogs.ask_save(*save) if save is not None else dialogs.ask_dir()
        if not out:
            doc.close()
            return None
        pdf_out = parts or (save is not None and save[1].lower() == ".pdf")
        kept = ask_keep_password(doc) if pdf_out else None
        progress = win.progress_callback()

        def then(kind, result):
            if ended is not None:
                ended(kind)
            if kind != "done":
                return
            role, status, box_title, text = report(result, out)
            win.set_status(status, role)
            box = dialogs.warning if warning_box and role == "warning" else dialogs.info
            box(box_title, text)
            if save is not None and save[1].lower() == ".pdf":
                self.offer_output(out)

        job = win.run_job(lambda stop: work(doc, out, stop, progress),
                          label if isinstance(label, str) else label(),
                          then=then, cancellable=cancellable,
                          keep_password=(kept, out if parts else [out]))
        if job is None:
            doc.close()
        return job

    # ── shell hooks ──
    def open(self):
        """Ctrl+O: the file dialog for the current document (a single-input
        page), else Choose file on the first visible file card."""
        if isinstance(getattr(self, "file", None), DocInput):
            return self.file.choose()
        for fc in self.findChildren(FileCard):
            if fc.isVisibleTo(self):
                return fc.choose()

    def accept_drop(self, path: str) -> bool:
        """A dropped PDF becomes the current document (a single-input page,
        through the window: unsaved edits are asked about), else the first
        visible file card that takes it gets it."""
        f = getattr(self, "file", None)
        if isinstance(f, DocInput):
            if not f.accepts(path):
                return False
            if self.window_ is not None:
                self.window_.open_document(path)
            else:
                f.set_path(path)
            return True
        for fc in self.findChildren(FileCard):
            if fc.isVisibleTo(self) and fc.accept_drop(path):
                return True
        return False

    # ── window modes (the shell calls these) ──
    def set_compact(self, on: bool):
        """Compact Mode: the header and any context panel are hidden; leaving
        it brings the panel back only if it was shown when Compact Mode began."""
        if self.has_context() and on and not self._compact:
            self._ctx_before_compact = self.context_shown()
        self._compact = on
        self.header.setVisible(not on)
        if self.has_context():
            self.show_context(False if on else self._ctx_before_compact)

    def reveal_header(self, on: bool):
        """In Compact Mode the top edge brings the header back for a while."""
        if self._compact:
            self.header.setVisible(on)

    # Context panel: a workspace page overrides these four.
    def has_context(self) -> bool:
        return False

    def context_shown(self) -> bool:
        return False

    def context_width(self) -> int:
        return 0

    def show_context(self, on: bool):
        pass


# ── Group templates ───────────────────────────────────────────────────────────
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
    add widgets to self.panel_body, set_doc / show_current for the document.
    view_cls: the centre view's class (PageView), built with the page ground
    colour; rail=False hides the rail and its divider (a viewer has no tools)."""

    def __init__(self, title: str, subtitle: str = "", *, tool=None, window=None,
                 view_cls=None, rail: bool = True):
        from PySide6.QtWidgets import QSplitter
        from qfluentwidgets import FluentIcon as FIF
        from .pageview import PageView
        super().__init__(title, subtitle, tool=tool, window=window, scroll=False)

        frame = plain_card()
        h = QHBoxLayout(frame)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        rail_w = QWidget()
        self.rail = QVBoxLayout(rail_w)
        self.rail.setContentsMargins(4, 8, 4, 8)
        self.rail.setSpacing(4)
        self.rail.addStretch(1)
        h.addWidget(rail_w)
        rail_divider = Divider(vertical=True)
        h.addWidget(rail_divider)
        if not rail:
            rail_w.hide()
            rail_divider.hide()

        self.split = QSplitter(Qt.Horizontal)
        self.split.setHandleWidth(6)
        self._style_split()
        self.split.setChildrenCollapsible(True)
        mid = QWidget()
        mv = QVBoxLayout(mid)
        mv.setContentsMargins(0, 0, 0, 0)
        mv.setSpacing(0)
        self.view = (view_cls or PageView)(theme.hex_color("page_bg"))
        mv.addWidget(self.view, 1)
        # No document: the empty-state target in the page view's place.
        from . import docui
        self.target_box = QWidget()
        tv = QVBoxLayout(self.target_box)
        tv.setContentsMargins(16, 16, 16, 16)
        tv.addStretch(1)
        self.drop_target = docui.DropTarget(window)
        tv.addWidget(self.drop_target)
        tv.addStretch(1)
        mv.addWidget(self.target_box, 1)
        mv.addWidget(Divider())
        strip = QHBoxLayout()
        strip.setContentsMargins(8, 4, 12, 4)
        self.prev_btn = icon_button(FIF.LEFT_ARROW)
        self.next_btn = icon_button(FIF.RIGHT_ARROW)
        self.page_label = BodyLabel("–")
        self.prev_btn.clicked.connect(lambda: self.go(-1))
        self.next_btn.clicked.connect(lambda: self.go(1))
        strip.addWidget(self.prev_btn)
        strip.addWidget(self.page_label)
        strip.addWidget(self.next_btn)
        strip.addStretch(1)
        strip.addWidget(muted_caption("Zoom"))
        self.zoom_slider = TallSlider(Qt.Horizontal)
        self.zoom_slider.setRange(50, 300)
        self.zoom_slider.setValue(int(self.view.zoom * 100))
        self.zoom_slider.setFixedWidth(140)
        self.zoom_slider.valueChanged.connect(self._zoom_changed)
        self.view.zoomed.connect(self._wheel_zoomed)
        strip.addWidget(self.zoom_slider)
        self.reopen_btn = icon_button(theme.glyph_icon(0xE76B, 14))
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
        self._panel_hide_btn = None
        # The glyph pixmaps, the page ground and the splitter accent are
        # baked for one theme: redo them when Preferences or Windows switch it.
        from qfluentwidgets import qconfig
        qconfig.themeChangedFinished.connect(self._apply_theme)
        self._build_doc_bar()
        self._show_target(True)

    follows_document = True

    def _show_target(self, empty: bool):
        self.target_box.setVisible(empty)
        self.view.setVisible(not empty)

    def document_path(self) -> str:
        """The file shown (also while it is parked: closed while the page is away)."""
        return self._src_path

    def load_document(self, path: str) -> bool:
        """Open *path*; a parked document comes back at the page it was on."""
        pg = self._pg if self.is_parked() and same_path(path, self._src_path) else 0
        self.open_path(path)
        doc = getattr(self, "_doc", None)
        if doc is not None and 0 < pg < len(doc):
            self._pg = pg
            self.on_page()
            self.show_current()
        return doc is not None and same_path(self.document_path(), path)

    def clear_document(self):
        """Close the document (the page's own state goes with it: subclasses)."""
        self._close_doc()
        self._src_path, self._dirty = "", False
        self.show_current()
        self.refresh_document()

    def park_document(self):
        """The page is left: a document with no unsaved edits is closed (its
        file free for other tools); the page keeps the path and its page
        number and reopens it when shown again (MainWindow._follow)."""
        if getattr(self, "_doc", None) is not None and not self.is_dirty():
            self._close_doc()
            self._undo_stack = []
            self.show_current()

    def is_parked(self) -> bool:
        return getattr(self, "_doc", None) is None and bool(self._src_path)

    def is_dirty(self) -> bool:
        return getattr(self, "_doc", None) is not None and self._dirty

    def _style_split(self):
        accent = theme.hex_color("accent")
        self.split.setStyleSheet("QSplitter::handle { background: transparent; }"
                                 f"QSplitter::handle:hover {{ background: {accent}; }}")

    def _apply_theme(self):
        from PySide6.QtGui import QBrush
        self.view.setBackgroundBrush(QBrush(theme.color("page_bg")))
        self._style_split()
        for i in range(self.rail.count()):
            w = self.rail.itemAt(i).widget()
            if w is not None and hasattr(w, "pk_glyph"):
                w.setIcon(theme.glyph_icon(w.pk_glyph, 18))
        self.reopen_btn.setIcon(theme.glyph_icon(0xE76B, 14))
        if self._panel_hide_btn is not None:
            self._panel_hide_btn.setIcon(theme.glyph_icon(0xE76C, 14))

    # ── rail ──
    def add_rail(self, key: str, glyph: int, tip: str, slot, toggle: bool = True):
        cls = TransparentToggleToolButton if toggle else TransparentToolButton
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
        top.addWidget(SubtitleLabel(title))
        top.addStretch(1)
        hide = icon_button(theme.glyph_icon(0xE76C, 14))
        hide.setToolTip("Hide panel")
        hide.clicked.connect(lambda: self.show_context(False))
        top.addWidget(hide)
        self._panel_hide_btn = hide
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
        return _field_row(self.panel_body, label)

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
        # One slide at a time: a second call within SLIDE_MS takes over from
        # where the running one is instead of fighting it over setSizes.
        old = getattr(self, "_panel_anim", None)
        if old is not None:
            self._panel_anim = None
            old.stop()
        start = self.split.sizes()[1]
        if start == target:
            if old is not None:
                self.reopen_btn.setVisible(target == 0)
            return
        a = QVariantAnimation(self)
        a.setDuration(SLIDE_MS)
        a.setStartValue(start)
        a.setEndValue(target)
        a.setEasingCurve(QEasingCurve.OutCubic)

        def step(w):
            total = sum(self.split.sizes())       # now, not when the slide began
            self.split.setSizes([total - int(w), int(w)])
        a.valueChanged.connect(step)
        a.finished.connect(lambda: self.reopen_btn.setVisible(target == 0))
        # Deleted when it stops, so a page that slides often keeps none.
        a.finished.connect(lambda: self._panel_anim is a and setattr(self, "_panel_anim", None))
        self._panel_anim = a
        a.start(QVariantAnimation.DeleteWhenStopped)

    # ── document ──
    _src_path = ""

    def open(self):
        if self.window_ is not None:
            return self.window_.browse_document()
        path = dialogs.ask_open("Open PDF", [("PDF", "*.pdf")])
        if path:
            self.open_path(path)

    def accept_drop(self, path: str) -> bool:
        """A dropped PDF becomes the current document, shown here (through
        the window: unsaved edits are asked about first)."""
        if not str(path).lower().endswith(".pdf"):
            return False
        if self.window_ is not None:
            self.window_.open_document(path)
        else:
            self.open_path(path)
        return True

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

    def _wheel_zoomed(self, z: float):
        # Ctrl+wheel set the view's zoom without rendering: move the slider
        # quietly and draw the page with its overlay once.
        self.zoom_slider.blockSignals(True)
        self.zoom_slider.setValue(int(round(z * 100)))
        self.zoom_slider.blockSignals(False)
        if self._zoom_timer is not None:
            self._zoom_timer.stop()
        self.show_current()

    def _zoom_changed(self, v: int):
        # Apply once the slider rests: a render costs ~30 ms.
        from PySide6.QtCore import QTimer
        if self._zoom_timer is None:
            self._zoom_timer = QTimer(self, singleShot=True, interval=120)
            self._zoom_timer.timeout.connect(
                lambda: self.apply_zoom(self.zoom_slider.value() / 100))
        self._zoom_timer.start()

    def apply_zoom(self, z: float):
        """The zoom slider rested at *z*: one render, page and overlay."""
        self.view.set_zoom(z, render=False)
        self.show_current()

    # ── rubber band ──
    def enable_band(self, style, on_release, *, drag_needs_doc: bool = False):
        """Draw a rubber band while the page is dragged: style() -> (shape,
        colour) for view.add_scene_shape, read at each move.  When the mouse
        is released over an open document the band goes and
        on_release(start, end, click) runs with the scene points; click: the
        mouse moved less than 4 px.  drag_needs_doc: no band without a document."""
        self._band_style, self._band_done = style, on_release
        self._band_needs_doc = drag_needs_doc
        self._start = None
        self._band = None
        self.view.pressed.connect(self._press)
        self.view.dragged.connect(self._drag)
        self.view.released.connect(self._mouse_up)

    def _press(self, xy):
        self._start = xy
        if self._band is not None:
            self.view.remove(self._band)
            self._band = None

    def _drag(self, xy):
        if self._start is None or (self._band_needs_doc and self._doc is None):
            return
        if self._band is not None:
            self.view.remove(self._band)
        (x0, y0), (shape, colour) = self._start, self._band_style()
        self._band = self.view.add_scene_shape(shape, x0, y0, xy[0], xy[1], colour)

    def _mouse_up(self, xy):
        if self._start is None or self._doc is None:
            return
        start, self._start = self._start, None
        if self._band is not None:
            self.view.remove(self._band)
            self._band = None
        click = abs(xy[0] - start[0]) < 4 and abs(xy[1] - start[1]) < 4
        self._band_done(start, xy, click)

    # hooks for subclasses
    def on_page(self):
        pass

    def draw_overlay(self, page):
        pass


class FieldRow(QHBoxLayout):
    """A field's row under its small label: a control of fixed width sits at
    the left edge instead of centred in the row."""

    def addWidget(self, w, stretch=0, alignment=None):
        if alignment is None:
            fixed = w.maximumWidth() < 16777215
            alignment = (Qt.AlignLeft | Qt.AlignVCenter) if fixed else Qt.AlignmentFlag(0)
        super().addWidget(w, stretch, alignment)


def _clear_layout(layout):
    while layout.count():
        item = layout.takeAt(0)
        if item.widget() is not None:
            item.widget().deleteLater()
        elif item.layout() is not None:
            _clear_layout(item.layout())


SETTINGS_W = 360            # collection: width of the settings column


def _settings_column(owner: QWidget, name: str):
    """The settings column at a template's right: (scroll area, its QVBoxLayout)."""
    sa = SingleDirectionScrollArea(owner, Qt.Vertical)
    sa.setWidgetResizable(True)
    sa.enableTransparentBackground()
    sa.setFrameShape(QFrame.NoFrame)
    sa.setFixedWidth(SETTINGS_W)
    sw = QWidget()
    sw.setObjectName(name)
    sw.setStyleSheet(f"QWidget#{name} {{ background: transparent; }}")
    lay = QVBoxLayout(sw)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(8)
    sa.setWidget(sw)
    return sa, lay


def column_setting_row(group: QWidget, title: str, desc: str = "", path: bool = False) -> QWidget:
    """A setting row sized for a settings column (the name takes the room)."""
    return setting_row(group, title, desc, label_width=0, path=path)


def _field_row(lay: QVBoxLayout, label: str) -> QHBoxLayout:
    """A small label above its control, as a narrow column stacks them."""
    lay.addSpacing(12)
    lay.addWidget(muted_caption(label))
    row = FieldRow()
    row.setSpacing(8)
    lay.addLayout(row)
    return row


def _tool_button(text: str, icon, slot, needs_selection: bool = False,
                 parent=None) -> TransparentPushButton:
    """A toolbar / context-bar button; pk_needs_selection marks one that is
    enabled only while something is selected."""
    b = (TransparentPushButton(icon, text, parent) if icon is not None
         else TransparentPushButton(text, parent))
    b.setMinimumHeight(CONTROL_H)
    b.clicked.connect(slot)
    b.pk_needs_selection = needs_selection
    return b


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
        self.folder_label = muted_path(str(p.parent))
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
        theme.label_role(self.note, role)
        self.note.setVisible(bool(text))

    def set_selected(self, on: bool):
        self.selected = on
        theme.keep_styled(self, CollectionRow._style_selected)

    def _style_selected(self):
        if self.selected:
            c = theme.color("selection")
            bg = f"rgba({c.red()},{c.green()},{c.blue()},{c.alpha()})"
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
                 settings: bool = True, toolbar: bool = True, filter_label: str | None = None,
                 open_title: str | None = None, parent=None):
        from PySide6.QtGui import QKeySequence, QShortcut
        from qfluentwidgets import FluentIcon as FIF
        super().__init__(title, subtitle, tool=tool, window=window, scroll=False,
                         parent=parent)
        self.exts = tuple(e.lower() for e in (exts or ()))
        self.add_text = add_text
        self.filter_label = filter_label or ("PDF" if self.exts == (".pdf",) else "Supported files")
        self.open_title = open_title or add_text
        self.rows: list[CollectionRow] = []
        self._sel: int | None = None

        cols = QHBoxLayout()
        cols.setSpacing(16)
        # list card
        self.list_card = plain_card()
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
                b = _tool_button(text, icon, slot, parent=bar)
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
            self.settings_area, self.settings = _settings_column(self, "collectionSettings")
            cols.addWidget(self.settings_area)
        self.body.addLayout(cols, 1)

        for keys, d in (("Alt+Up", -1), ("Alt+Down", 1)):
            sc = QShortcut(QKeySequence(keys), self)
            sc.activated.connect(lambda d=d: self.move(d))
        self._refresh()

    def _default_empty(self) -> str:
        what = "PDFs" if self.exts == (".pdf",) else "files"
        return f"Drop {what} here, or use {self.add_text}."

    setting_row = staticmethod(column_setting_row)

    # ── hooks a tool may override ──
    def make_extra(self, path: str) -> QWidget | None:
        return None

    def add_tool(self, text: str, icon, slot):
        """Another toolbar button (after Remove)."""
        b = _tool_button(text, icon, slot)
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
            filters = [(self.filter_label, pats), ("All", "*.*")]
        else:
            filters = None
        self.add_paths(dialogs.ask_open_many(self.open_title, filters))

    def delete(self):
        self.remove_selected()

    def clear_document(self):
        """Start over / a finished job: the list empties (owner)."""
        self.clear_rows()

    def accept_drop(self, path: str) -> bool:
        if self.accepts(path):
            self.add_paths([path])
            return True
        return super().accept_drop(path)        # a file card in the settings


THUMB_BOX = (120, 150)      # organiser: the largest thumbnail, in px
THUMBS_PER_TICK = 4         # thumbnails rendered per event-loop turn


def _thumb_delegate():
    """Paints an organiser item: the page centred in THUMB_BOX with a hairline
    border, its label under it; selected = accent border on a tinted backing,
    hover = a faint backing.  (qfluentwidgets' ListWidget delegate paints
    list rows only, clipping icons in IconMode.)"""
    from PySide6.QtCore import QRect, QRectF, QSize
    from PySide6.QtGui import QPen
    from PySide6.QtWidgets import QStyle, QStyledItemDelegate

    class ThumbDelegate(QStyledItemDelegate):
        def sizeHint(self, option, index):
            return QSize(THUMB_BOX[0] + 24, THUMB_BOX[1] + 40)

        def paint(self, p, option, index):
            p.save()
            p.setRenderHint(QPainter.Antialiasing)
            r = option.rect.adjusted(2, 2, -2, -2)
            sel = bool(option.state & QStyle.State_Selected)
            hover = bool(option.state & QStyle.State_MouseOver)
            accent = theme.color("accent")
            if sel or hover:
                bg = theme.color("selection")
                bg.setAlpha(46 if sel else 18)
                p.setPen(Qt.NoPen)
                p.setBrush(bg)
                p.drawRoundedRect(QRectF(r), 6, 6)
            icon = index.data(Qt.DecorationRole)
            box = QRect(r.x() + (r.width() - THUMB_BOX[0]) // 2, r.y() + 8, *THUMB_BOX)
            if icon is not None and not icon.isNull():
                pm = icon.pixmap(QSize(*THUMB_BOX))
                dpr = pm.devicePixelRatio() or 1
                w, h = int(pm.width() / dpr), int(pm.height() / dpr)
                img = QRect(box.x() + (box.width() - w) // 2,
                            box.y() + (box.height() - h) // 2, w, h)
                p.drawPixmap(img, pm)
            else:
                img = QRect(box.x() + 20, box.y() + 10, box.width() - 40, box.height() - 20)
                p.fillRect(img, theme.color("drop_zone"))
            if sel:
                p.setPen(QPen(accent, 2))
            else:
                p.setPen(QPen(theme.color("thumb_border"), 1))
            p.setBrush(Qt.NoBrush)
            p.drawRect(QRectF(img).adjusted(-0.5, -0.5, 0.5, 0.5))
            p.setPen(theme.color("text" if sel else "muted"))
            f = p.font()
            f.setPixelSize(12)
            p.setFont(f)
            p.drawText(QRect(r.x(), box.bottom() + 6, r.width(), 20),
                       Qt.AlignHCenter | Qt.AlignTop, str(index.data(Qt.DisplayRole) or ""))
            p.restore()

    return ThumbDelegate()


class OrganiserPage(ToolPage):
    """Group B, page organiser (Rotate & Reorder, Split by Bookmarks): the
    empty-state target while there is no document, then a context bar with
    the actions for the selected pages (add_action; they are enabled only while something is selected,
    and a hint takes their place's meaning when nothing is), then the pages
    as a thumbnail grid in a card.  Thumbnails can be dragged to a new place
    (drag_reorder=True) and are rendered a few per event-loop turn, so a long
    document never blocks the window.  settings=True adds a settings column
    at the right (self.settings, as CollectionPage).  A page whose centre is
    not a thumbnail grid (an outline) calls set_centre(widget).

    The input's (doc_input) on_change calls self.load(path); a subclass overrides
    load() to open the document and call set_pages(keys, render, label).

        set_pages(keys, render, label)  render(key) -> QImage; label(key) -> str
        order() -> keys in their current order
        selected() -> indices, in order; select(i); current() -> index | None
        move(d)   move the selected page(s) by d places
        refresh(i)  render item i again (after a rotation)"""

    def __init__(self, title: str, subtitle: str = "", *, tool=None, window=None,
                 settings: bool = False, drag_reorder: bool = True,
                 hint: str = "Click a thumbnail to select it", parent=None):
        from PySide6.QtCore import QSize, QTimer
        from PySide6.QtWidgets import QAbstractItemView, QListView, QListWidget
        super().__init__(title, subtitle, tool=tool, window=window, scroll=False,
                         parent=parent)
        self.doc_input(self.load)
        self.body.addSpacing(8)

        bar = QWidget()
        bar.setObjectName("contextBar")
        self.context_bar = QHBoxLayout(bar)
        self.context_bar.setContentsMargins(0, 0, 0, 0)
        self.context_bar.setSpacing(4)
        self.hint_label = muted_caption(hint)
        self.context_bar.addStretch(1)
        self.context_bar.addWidget(self.hint_label)
        self._hint = hint
        self._actions: list = []
        self.body.addWidget(bar)

        cols = QHBoxLayout()
        cols.setSpacing(16)
        self.grid_card = plain_card()
        gv = QVBoxLayout(self.grid_card)
        gv.setContentsMargins(8, 8, 8, 8)
        self._grid_v = gv
        g = QListWidget(self.grid_card)
        g.setObjectName("thumbGrid")
        g.setStyleSheet("QListWidget#thumbGrid { background: transparent; border: none; }")
        self._delegate = _thumb_delegate()       # Qt does not own a Python delegate
        g.setItemDelegate(self._delegate)
        g.setMouseTracking(True)
        g.viewport().setAttribute(Qt.WA_Hover, True)
        g.setViewMode(QListView.IconMode)
        g.setResizeMode(QListView.Adjust)
        g.setWrapping(True)
        g.setUniformItemSizes(True)
        g.setSpacing(8)
        g.setIconSize(QSize(*THUMB_BOX))
        g.setGridSize(QSize(THUMB_BOX[0] + 24, THUMB_BOX[1] + 40))
        g.setSelectionMode(QAbstractItemView.ExtendedSelection)
        g.setMovement(QListView.Snap if drag_reorder else QListView.Static)
        g.setDragDropMode(QAbstractItemView.InternalMove if drag_reorder
                          else QAbstractItemView.NoDragDrop)
        g.setDefaultDropAction(Qt.MoveAction)
        g.setFrameShape(QFrame.NoFrame)
        g.itemSelectionChanged.connect(self._selection_changed)
        self.grid = g
        gv.addWidget(g)
        self.empty_label = muted_caption("Open a PDF to see its pages")
        self.empty_label.setAlignment(Qt.AlignCenter)
        gv.addWidget(self.empty_label)
        cols.addWidget(self.grid_card, 1)

        self.settings_area = None
        self.settings = None
        if settings:
            self.settings_area, self.settings = _settings_column(self, "organiserSettings")
            cols.addWidget(self.settings_area)
        self.body.addLayout(cols, 1)

        self._centre: QWidget | None = None
        self._render = None
        self._label = None
        self._queue: list = []
        self._timer = QTimer(self, interval=0)
        self._timer.timeout.connect(self._render_some)
        self._show_grid_state()
        self._selection_changed()

    setting_row = staticmethod(column_setting_row)

    # ── what a subclass fills ──
    def load(self, path: str):
        """The file card changed; open *path* and call set_pages()."""

    def add_action(self, text: str, icon, slot, needs_selection: bool = True):
        b = _tool_button(text, icon, slot, needs_selection)
        self.context_bar.insertWidget(len(self._actions), b)
        self._actions.append(b)
        self._selection_changed()
        return b

    def set_centre(self, w: QWidget):
        """Put *w* in the card instead of the thumbnail grid."""
        self.grid.hide()
        self.empty_label.hide()
        self._grid_v.addWidget(w)
        self._centre = w

    # ── pages ──
    def set_pages(self, keys, render, label=None):
        from PySide6.QtWidgets import QListWidgetItem
        self._timer.stop()
        self.grid.clear()
        self._render, self._label = render, (label or (lambda k: str(k)))
        for k in keys:
            it = QListWidgetItem(self._label(k))
            it.setData(Qt.UserRole, k)
            it.setTextAlignment(Qt.AlignHCenter | Qt.AlignTop)
            it.setFlags(it.flags() | Qt.ItemIsDragEnabled)
            self.grid.addItem(it)
        # The items themselves, not their rows: a move or a drag reorders the
        # rows while the queue drains.
        self._queue = [self.grid.item(i) for i in range(self.grid.count())]
        if self._queue:
            self._timer.start()
        self._show_grid_state()
        self._selection_changed()

    def clear_pages(self):
        self._timer.stop()
        self._queue = []
        self.grid.clear()
        self._show_grid_state()
        self._selection_changed()

    def _show_grid_state(self):
        if self._centre is not None:
            return
        empty = self.grid.count() == 0
        self.grid.setVisible(not empty)
        self.empty_label.setVisible(empty)

    def _thumb_icon(self, key):
        from PySide6.QtGui import QIcon, QPixmap
        img = self._render(key)
        pm = QPixmap.fromImage(img)
        if pm.width() > THUMB_BOX[0] or pm.height() > THUMB_BOX[1]:
            pm = pm.scaled(*THUMB_BOX, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        return QIcon(pm)

    def _render_some(self):
        for _ in range(THUMBS_PER_TICK):
            if not self._queue:
                self._timer.stop()
                return
            it = self._queue.pop(0)
            if self._render is not None and self.grid.row(it) >= 0:
                it.setIcon(self._thumb_icon(it.data(Qt.UserRole)))

    def rendering(self) -> bool:
        return bool(self._queue)

    def refresh(self, i: int):
        it = self.grid.item(i)
        if it is not None and self._render is not None:
            it.setIcon(self._thumb_icon(it.data(Qt.UserRole)))
            it.setText(self._label(it.data(Qt.UserRole)))

    def order(self) -> list:
        return [self.grid.item(i).data(Qt.UserRole) for i in range(self.grid.count())]

    def selected(self) -> list[int]:
        return sorted(self.grid.row(it) for it in self.grid.selectedItems())

    def current(self) -> int | None:
        s = self.selected()
        return s[0] if s else None

    def select(self, i: int | None):
        self.grid.clearSelection()
        if i is not None and 0 <= i < self.grid.count():
            self.grid.item(i).setSelected(True)
            self.grid.setCurrentRow(i)
            self.grid.scrollToItem(self.grid.item(i))

    def move(self, d: int):
        """Move the selected pages by *d* places as a block, keeping them selected."""
        sel = self.selected()
        n = self.grid.count()
        if not sel or not (0 <= sel[0] + d and sel[-1] + d < n):
            return
        items = [self.grid.takeItem(i) for i in reversed(sel)][::-1]
        for k, it in zip([i + d for i in sel], items, strict=True):
            self.grid.insertItem(k, it)
        self.grid.clearSelection()
        for it in items:
            it.setSelected(True)

    def _selection_changed(self):
        has = bool(self.grid.selectedItems())
        for b in self._actions:
            if b.pk_needs_selection:
                b.setEnabled(has)
        n = len(self.grid.selectedItems())
        self.hint_label.setText(self._hint if not n else
                                f"{n} page{'s' if n != 1 else ''} selected")


class MasterDetailPage(ToolPage):
    """Group E, structured editor (Bookmarks / TOC): the empty-state target
    while there is no document, then the list of entries in a card with its toolbar (add_tool; buttons made
    with needs_selection=True are enabled only while an entry is selected)
    and, at the right, a detail column of fixed width (SETTINGS_W) with the
    selected entry's fields: detail_begin(title) empties it, detail_field(label)
    gives a row for a control under a small label (as a context panel stacks
    them).  A tool with fields but no list (Metadata) uses the group C form
    instead.

    The input's (doc_input) on_change calls self.load(path).

        set_items(texts, keep=None)  keep = the index to select afterwards
        current() -> index | None; select(i); on_select(i) (override)
        count()"""

    def __init__(self, title: str, subtitle: str = "", *, tool=None, window=None,
                 empty_text: str = "Open a PDF to see its entries", parent=None):
        from qfluentwidgets import ListWidget
        super().__init__(title, subtitle, tool=tool, window=window, scroll=False,
                         parent=parent)
        self.doc_input(self.load)
        self.body.addSpacing(8)
        cols = QHBoxLayout()
        cols.setSpacing(16)

        self.list_card = plain_card()
        lv = QVBoxLayout(self.list_card)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(0)
        bar = QWidget(self.list_card)
        self.toolbar = QHBoxLayout(bar)
        self.toolbar.setContentsMargins(8, 6, 8, 6)
        self.toolbar.setSpacing(4)
        self.toolbar.addStretch(1)
        self.count_label = muted_caption("")
        self.toolbar.addWidget(self.count_label)
        self._tools: list = []
        lv.addWidget(bar)
        lv.addWidget(Divider())
        self.list = ListWidget(self.list_card)
        self.list.setFrameShape(QFrame.NoFrame)
        self.list.currentRowChanged.connect(self._row_changed)
        self.list.itemSelectionChanged.connect(self._selection_changed)
        self._shown: int | None = None          # what on_select last heard
        lv.addWidget(self.list, 1)
        self.empty_label = muted_caption(empty_text)
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setContentsMargins(24, 48, 24, 48)
        lv.addWidget(self.empty_label)
        lv.addStretch(0)
        cols.addWidget(self.list_card, 1)

        detail = QWidget()
        detail.setFixedWidth(SETTINGS_W)
        self._detail_v = QVBoxLayout(detail)
        self._detail_v.setContentsMargins(0, 0, 0, 0)
        self._detail_v.setSpacing(0)
        self._detail_box = None
        self.detail = None
        self.detail_panel = detail
        cols.addWidget(detail)
        self.body.addLayout(cols, 1)
        self._refresh()

    # ── what a subclass fills ──
    def load(self, path: str):
        """The file card changed; open *path* and call set_items()."""

    def on_select(self, i: int | None):
        """The selection changed (None = nothing selected)."""

    def add_tool(self, text: str, icon, slot, needs_selection: bool = False):
        b = _tool_button(text, icon, slot, needs_selection)
        self.toolbar.insertWidget(len(self._tools), b)
        self._tools.append(b)
        self._refresh()
        return b

    def detail_begin(self, title: str, desc: str = "") -> QVBoxLayout:
        """Empty the detail column (at once, as WorkspacePage.panel_begin)."""
        old = self._detail_box
        if old is not None:
            old.hide()
            self._detail_v.removeWidget(old)
            old.setParent(None)
            old.deleteLater()
        while self._detail_v.count():
            self._detail_v.takeAt(0)
        box = card(padding=16)
        self._detail_box = box
        bv = box.layout()
        bv.setSpacing(4)
        bv.addWidget(SubtitleLabel(title))
        if desc:
            d = muted_caption(desc)
            d.setWordWrap(True)
            bv.addWidget(d)
        self.detail = QVBoxLayout()
        self.detail.setContentsMargins(0, 4, 0, 0)
        self.detail.setSpacing(4)
        bv.addLayout(self.detail)
        self._detail_v.addWidget(box)
        self._detail_v.addStretch(1)
        return self.detail

    def detail_field(self, label: str) -> QHBoxLayout:
        return _field_row(self.detail, label)

    # ── entries ──
    def count(self) -> int:
        return self.list.count()

    def set_items(self, texts, keep: int | None = None):
        self.list.blockSignals(True)
        self.list.clear()
        self.list.addItems([str(t) for t in texts])
        self.list.blockSignals(False)
        self._refresh()
        self.select(keep)

    def current(self) -> int | None:
        r = self.list.currentRow()
        return r if 0 <= r < self.list.count() and self.list.currentItem().isSelected() else None

    def select(self, i: int | None):
        if i is not None and 0 <= i < self.list.count():
            self.list.setCurrentRow(i)
            self.list.item(i).setSelected(True)
        else:
            self.list.clearSelection()
            self.list.setCurrentRow(-1)
            self._row_changed(-1)

    def _row_changed(self, r: int):
        self._refresh()
        self._shown = r if 0 <= r < self.list.count() else None
        self.on_select(self._shown)

    def _selection_changed(self):
        # Ctrl+click on the selected entry deselects it (and a second one
        # selects it again) without moving currentRow.
        self._refresh()
        cur = self.current()
        if cur != self._shown:
            self._shown = cur
            self.on_select(cur)

    def _refresh(self):
        n = self.list.count()
        self.list.setVisible(bool(n))
        self.empty_label.setVisible(not n)
        self.count_label.setText(f"{n} entr{'ies' if n != 1 else 'y'}" if n else "")
        has = self.current() is not None
        for b in self._tools:
            if b.pk_needs_selection:
                b.setEnabled(has)
