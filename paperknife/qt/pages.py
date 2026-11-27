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

import json
import os
from pathlib import Path

import pymupdf as fitz
from PySide6.QtCore import (QEasingCurve, QEvent, QItemSelectionModel, QObject, QPoint, QSize, Qt,
                            QTimer, QVariantAnimation, Signal)
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import (QAbstractItemView, QButtonGroup, QFrame, QHBoxLayout, QLayout, QListView,
                               QListWidget, QListWidgetItem, QSizePolicy, QVBoxLayout, QWidget)
from qfluentwidgets import (BodyLabel, CaptionLabel, IconWidget, LineEdit, PrimaryPushButton, PushButton,
                            RadioButton, Slider, SwitchButton,
                            SimpleCardWidget, SingleDirectionScrollArea, StrongBodyLabel,
                            TitleLabel, TransparentPushButton,
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


def batch_prototype() -> str:
    """Which Batch prototype runs (owner, 2026-10-18; env PK_BATCH): "A"
    Batch as it is (the default), "B" a folder input on Compress, Watermark,
    OCR and PDF → Other (no Batch screen), "C" Batch with each tool's full
    settings."""
    v = os.environ.get("PK_BATCH", "A").strip().upper()
    return v if v in ("A", "B", "C") else "A"


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


def info_button(title: str, text: str, within: QWidget | None = None) -> QWidget:
    """A circled "i" that shows *text* in a small card just under it, inside the
    card or row that holds it, until a click elsewhere (owner, 2026-10-31:
    descriptions as overlay cards, not lines under the name; 2026-11-01: every
    description).  *within*: the box the card opens inside, when it is not the
    tool card or setting row around the "i" (a side panel).  set_info(text)
    changes the text, for a description that follows a choice."""
    from qfluentwidgets import Flyout, FlyoutAnimationType, FlyoutView
    from qfluentwidgets import FluentIcon as FIF
    b = TransparentToolButton(FIF.INFO)
    b.setFixedSize(INFO_SIZE, INFO_SIZE)
    b.setIconSize(QSize(16, 16))
    b.setToolTip(f"About {title}")              # the text itself is the card's
    b.setAccessibleName(f"About {title}")
    b.info_text = text

    def set_info(new: str):
        b.info_text = new
    b.set_info = set_info

    def show():
        # What holds it: the floating tool card, else its setting row.
        def holder(name):
            w = b.parentWidget()
            while w is not None and w.objectName() != name:
                w = w.parentWidget()
            return w
        box = holder("toolCard") or within or holder("settingRow") or b.window()
        width = min(INFO_W, box.width() - 2 * INFO_INSET)
        view = FlyoutView(title, b.info_text)
        view.iconWidget.hide()          # no icon: its empty column was a blank band
        # The library wraps the text by a character count taken from the screen's
        # width (one long line on a wide screen): the card takes *width* and its
        # labels wrap inside it.
        view.contentLabel.setWordWrap(True)
        view.titleLabel.setWordWrap(True)
        view.setFixedWidth(width)
        fl = Flyout(view, b.window(), isDeleteOnClose=True)
        at = QPoint(box.mapToGlobal(QPoint(INFO_INSET, 0)).x(),
                    b.mapToGlobal(QPoint(0, b.height() + 2)).y())
        b.flyout = fl
        fl.exec(at, FlyoutAnimationType.FADE_IN)
        fl.move(at - view.mapTo(fl, QPoint(0, 0)))  # the view, not its shadow, at *at*
    b.clicked.connect(show)
    return b


INFO_SIZE = CONTROL_H   # the "i" beside a name: no control is shorter (owner's rule)
INFO_W = 280            # its card at most; never wider than what holds the "i"
INFO_INSET = 8          # the card's edge inside what holds the "i"


def setting_row(group: QWidget, title: str, desc: str = "",
                label_width: int | None = None, path: bool = False,
                info: bool = True) -> QWidget:
    """Add a Windows 11 settings row to *group* (a card()) and return the
    container for its control: the name and description sit in a fixed-width
    column on the left, the control right-aligned, rows split by thin lines.

        row = setting_row(level_card, "Level", "How hard to compress")
        row.layout().addWidget(combo)

    label_width: the name column's width (LABEL_COLUMN by default); 0 lets it
    take the room the control leaves, for a narrow column such as a
    CollectionPage's settings.  path: the description is a file path, one
    line shortened in the middle (ElidedCaption) instead of wrapped.  info (the
    default): the description is not shown under the name but by a circled "i"
    beside it, in a small overlay card (control.info_button).  A path, and the
    hint of a row without a name, stay lines: they are the row's content.

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
    if not lw:
        # A settings column's row: a long name wraps rather than push the
        # control past the column's edge.
        name.setWordWrap(True)
    d = info_btn = None
    info = bool(info and desc and title and not path)
    if info:
        line = QHBoxLayout()
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(4)
        line.addWidget(name)
        info_btn = info_button(title, desc)
        line.addWidget(info_btn, 0, Qt.AlignVCenter)
        line.addStretch(1)
        tv.addLayout(line)
    else:
        tv.addWidget(name)
    if desc and not info:
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
    control.info_button = info_btn
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


CHOOSE_COLOUR = "Choose…"   # one label for the colour button everywhere ("Choose" / "Pick…")


EXAMPLES_TEXT = "Examples"


def example_chips(examples, on_pick) -> QWidget:
    """One "Examples" button whose menu fills a field with a worked example: *examples*
    are (label, value or a function giving it); choosing one calls on_pick(value).
    For fields with a notation of their own (Split's ranges, Header / Footer's
    tokens), so the notation is shown by doing, not explained (critique 2026-11-21).
    One row: a row of buttons wrapped to three in the 200 px card.  pick(label) runs
    an example as its menu item does; labels() lists them."""
    from qfluentwidgets import Action, DropDownPushButton, RoundMenu
    w = QWidget()
    w.setObjectName("exampleChips")
    h = QHBoxLayout(w)
    h.setContentsMargins(0, 4, 0, 0)
    btn = DropDownPushButton(EXAMPLES_TEXT, w)
    btn.setFixedHeight(CONTROL_H)
    menu = RoundMenu(parent=btn)
    table = dict(examples)

    def pick(label):
        v = table[label]
        on_pick(v() if callable(v) else v)
    for label, _value in examples:
        a = Action(label)
        a.triggered.connect(lambda _=False, lb=label: pick(lb))
        menu.addAction(a)
    btn.setMenu(menu)
    h.addWidget(btn)
    h.addStretch(1)
    w.button, w.menu, w.pick = btn, menu, pick
    w.labels = lambda: [lb for lb, _v in examples]
    return w
FIELD_W = 160           # an input field on a tool card: text, number, language (owner, 2026-10-31)
NUMBER_BOX_W = FIELD_W  # every number box one width: "120 pt" and its arrows


def number_box(row: QWidget, lo: int, hi: int, value: int, unit: str, *,
               width: int = NUMBER_BOX_W):
    """A number typed in (owner, 2026-10-23: Font size and Opacity as boxes, not
    sliders, so an exact value can be typed): a spin_box from *lo* to *hi* at
    *value*, *unit* after the number, added to *row* (a setting_row's control)."""
    sb = spin_box(lo, hi, value, width=width)
    sb.setFixedWidth(width)
    sb.setSuffix(unit)
    row.layout().addWidget(sb)
    return sb


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


class LanguagePicker(QWidget):
    """The OCR language(s) (owner, 2026-10-22: one button reading "Italian + English",
    opening a ticked list of the languages Tesseract has installed).  text() / setText()
    carry Tesseract's form, "ita+eng", in the order ticked: the first leads.  At least
    one stays ticked.  A language saved but not installed stays listed, so a choice
    made elsewhere is not lost."""
    changed = Signal(str)

    def __init__(self, value: str = "", width: int = 160, installed=None, parent=None):
        from qfluentwidgets import CheckableMenu, DropDownPushButton, MenuIndicatorType
        from ..core import ocr as core_ocr
        super().__init__(parent)
        self._installed = list(core_ocr.installed_languages() if installed is None else installed)
        self._chosen: list[str] = []
        self._width = width
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.button = DropDownPushButton(self)
        # As wide as it is given, up to *width*: a stacked row (the 200 px card) sizes
        # a control by its hint, and the button's own hint is its text, so it shrank to
        # "Italian" and cut "Italian + English" to "Italian ..." (the live check,
        # 2026-10-23).  The text is shortened again at each resize.
        self.button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.button.setMaximumWidth(width)
        # its value at the left, as every combo box's (critique 2026-11-21: centred)
        left = "QPushButton{text-align:left;padding-left:11px;}"
        setCustomStyleSheet(self.button, left, left)
        lay.addWidget(self.button)
        self.menu = CheckableMenu(parent=self.button, indicatorType=MenuIndicatorType.CHECK)
        self.button.setMenu(self.menu)
        self.setText(value)

    def chosen(self) -> bool:
        """A language was given or ticked, not only the starting default shown."""
        return self._chosen_explicitly

    def _order(self) -> list[str]:
        """The chosen first (in their order), then Windows' language, English, the rest
        by name."""
        from ..core import ocr as core_ocr
        win = core_ocr.windows_language()
        rest = [c for c in self._installed if c not in self._chosen]
        rest.sort(key=lambda c: (c != win, c != "eng", core_ocr.lang_name(c)))
        return self._chosen + rest

    def _rebuild(self):
        from qfluentwidgets import Action
        from ..core import ocr as core_ocr
        self.menu.clear()
        self.actions_by_code = {}
        for code in self._order():
            a = Action(core_ocr.lang_name(code), checkable=True)
            a.setChecked(code in self._chosen)
            a.toggled.connect(lambda on, c=code: self._toggle(c, on))
            self.menu.addAction(a)
            self.actions_by_code[code] = a
        self._relabel()

    def _full_label(self) -> str:
        from ..core import ocr as core_ocr
        return " + ".join(core_ocr.lang_name(c) for c in self._chosen)

    def _relabel(self):
        full = self._full_label()
        fm = self.button.fontMetrics()
        room = self.button.width() - 44                  # the arrow and the padding
        self.button.setText(fm.elidedText(full, Qt.ElideRight, max(40, room)))
        self.button.setToolTip(full)

    def sizeHint(self):
        return QSize(self._width, self.button.sizeHint().height())

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._relabel()

    def _toggle(self, code: str, on: bool):
        self._chosen_explicitly = True
        if on and code not in self._chosen:
            self._chosen.append(code)
        elif not on and code in self._chosen:
            if len(self._chosen) == 1:                   # the last one stays
                QTimer.singleShot(0, self._rebuild)
                return
            self._chosen.remove(code)
        QTimer.singleShot(0, self._rebuild)              # not while the menu emits
        self.changed.emit(self.text())

    def text(self) -> str:
        return "+".join(self._chosen)

    def setText(self, value: str):
        """Tesseract's form ("ita+eng"); "" shows the starting default (core.ocr.default_lang)."""
        from ..core import ocr as core_ocr
        codes = [c for c in (value or "").replace(" ", "").split("+") if c]
        self._chosen_explicitly = bool(codes)
        if not codes:
            codes = core_ocr.default_lang(self._installed).split("+")
        self._chosen = list(dict.fromkeys(codes)) or ["eng"]
        for c in self._chosen:
            if c not in self._installed:
                self._installed.append(c)
        self._rebuild()


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


def shared_copy(win, path: str):
    """A job's own copy of the window's document when *path* is its file
    (unsaved edits and the open password go with it), else None."""
    sd = getattr(win, "document", None)
    if sd is None or not sd.is_open() or not same_path(sd.path, path):
        return None
    from ..core.password import carry_open_password
    copy = fitz.open("pdf", sd.doc.tobytes())
    carry_open_password(sd.doc, copy)
    return copy


class SharedDocPage(DocHolder):
    """A page that works on the window's one document (window.document, a
    core.document.SharedDocument; owner's decision 2026-10-23) instead of a
    copy of its own: self._doc is that document while the page shows it
    (borrow), None otherwise.  Closing it here only lets it go: the window
    opens and closes it.  The page's edits are the document's: _dirty and
    is_dirty() read it, _push_undo puts a step on its one history (with the
    page's undo_state(), handed back to restore_step on undo), and setting
    _dirty after an edit marks it changed.

    Hooks: undo_state() / restore_step(state) for a page's own state on a
    step; document_replaced() redraws after another tool's edit or an undo
    (sync_document calls it once per change); document_moved(path) after
    Save as; recovery_extra() / restore_extra() / drop_marks() for marks a
    page keeps beside the document (Redact's boxes).

    A page without a window (none of the app's) holds its own document."""

    def _shared(self):
        w = getattr(self, "window_", None)
        return getattr(w, "document", None) if w is not None else None

    @property
    def _doc(self):
        sd = self._shared()
        if sd is None:
            return self.__dict__.get("_own_doc")
        return sd._doc if self.__dict__.get("_attached") else None

    @_doc.setter
    def _doc(self, value):
        sd = self._shared()
        if sd is None:
            self.__dict__["_own_doc"] = value
        elif value is None:
            self.__dict__["_attached"] = False
        else:                               # a new content (_replace_doc) for every tool
            sd._doc = value
            self.__dict__["_attached"] = True

    def _close_doc(self) -> None:
        if self._shared() is None:
            return DocHolder._close_doc(self)
        self.__dict__["_attached"] = False

    def borrow(self, path: str):
        """The window's document, made *path* first when it is another file
        (after the unsaved-edits question); None when it cannot be."""
        win, sd = self.window_, self._shared()
        if sd is None:
            return None
        if not win.adopt(path, ask=True):
            return None
        self.__dict__["_attached"] = True
        self.__dict__["_seen_edits"] = sd.edits
        win.note_document_page(self)
        return sd._doc

    def shows_document(self) -> bool:
        sd = self._shared()
        return sd is not None and bool(self.__dict__.get("_attached")) and sd.is_open()

    @property
    def _dirty(self) -> bool:
        sd = self._shared()
        if sd is not None and self.shows_document():
            return sd.dirty
        return self.__dict__.get("_dirty_flag", False)

    @_dirty.setter
    def _dirty(self, value: bool):
        sd = self._shared()
        if sd is None or not self.shows_document():
            self.__dict__["_dirty_flag"] = value
            return
        if value:
            sd.changed(adds=self.__dict__.pop("_adds_pending", False))
            self.__dict__["_seen_edits"] = sd.edits

    def is_dirty(self) -> bool:
        """Unsaved: the document's edits, or input typed here not applied yet."""
        return self.shows_document() and (self._dirty or self.has_pending())

    def has_pending(self) -> bool:
        """Input typed on this page and not applied to the document yet
        (Metadata's fields): Save applies it first (commit_edits)."""
        return False

    def commit_edits(self) -> bool:
        """Apply the pending input as an edit; False when it cannot be (the
        page said why)."""
        return True

    def edit_document(self, label: str, fn, *, adds: bool = False):
        """Run fn(doc) as one undoable edit of the window's document, with
        this page's undo_state() on the step; its result."""
        res = self._shared().edit(label, fn, {"page": self.page_key(), "state": self.undo_state()},
                                  adds=adds)
        self.__dict__["_seen_edits"] = self._shared().edits
        return res

    def is_parked(self) -> bool:
        return False        # the window holds the document: nothing to reopen

    def park_document(self):
        """Left: the window keeps the document open, so nothing to close."""

    def page_key(self) -> str:
        t = getattr(self, "tool", None)
        return getattr(t, "name", "") or type(self).__name__

    # ── the one history ──
    def _push_undo(self, label: str | None = None, state=None) -> None:
        """Before an edit made in place: a step on the window's history, with
        *state* (else undo_state()) for restore_step."""
        sd = self._shared()
        if sd is None:
            return DocHolder._push_undo(self)
        sd.begin(label or self.title_label.text(),
                 {"page": self.page_key(),
                  "state": self.undo_state() if state is None else state}, pg=self._pg)

    def _pop_undo(self) -> None:
        """An edit begun with _push_undo failed: the document as it was."""
        sd = self._shared()
        if sd is None:
            return DocHolder._pop_undo(self)
        sd.abandon()

    def _drop_undo(self) -> None:
        """An edit begun with _push_undo changed nothing: its step goes."""
        sd = self._shared()
        if sd is not None:
            sd.drop_step()

    def undo(self):
        """Ctrl+Z: the document's last edit, whichever tool made it (the window's)."""
        return self.window_.undo() if self.window_ is not None else False

    def undo_state(self):
        """The page's own state to keep on a history step (none by default)."""
        return None

    def restore_step(self, state) -> None:
        """Undo reached a step this page made: *state* is its undo_state() then."""

    def sync_document(self) -> None:
        """Redraw once when the document changed since this page last showed it."""
        sd = self._shared()
        if sd is None or not self.shows_document():
            return
        if self.__dict__.get("_seen_edits") != sd.edits:
            self.__dict__["_seen_edits"] = sd.edits
            self._pg = max(0, min(self._pg, len(sd.doc) - 1))
            self.document_replaced()

    def document_replaced(self) -> None:
        """The document's content changed under the page (another tool, an undo)."""

    def document_moved(self, path: str) -> None:
        """Save as: the document belongs to *path* now."""

    def drop_marks(self) -> None:
        """The unsaved edits were discarded: marks held beside them go too."""


class HeldDoc(SharedDocPage):
    """A page that works on its input's (self.file) document: the window's
    (SharedDocPage); self._src is the file it belongs to."""
    _src: str = ""

    def open_held(self, path: str, title: str | None = None):
        """Show *path* as the held document (the page's subtitle names it:
        refresh_document).  When it cannot be opened the document shown
        stays and the input goes back to its file.  The document, or None.
        *title* is not used any more."""
        doc = self.borrow(path)
        if doc is None:
            self.file.set_path(self._src if self._doc is not None else "", notify=False)
            return None
        self._src = str(path)
        return doc

    def document_moved(self, path: str) -> None:
        if self._src:
            self._src = str(path)
            if isinstance(getattr(self, "file", None), DocInput):
                self.file.set_path(path, notify=False)

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

    def document_replaced(self) -> None:
        """Another tool's edit or an undo: the page shows the document again
        (a page of thumbnails renders them anew)."""
        load = getattr(self, "load", None)
        if callable(load) and self._src:
            load(self._src)


class WorkspaceDoc(SharedDocPage):
    """The document a WorkspacePage edits: the window's (SharedDocPage)."""

    _src_path: str = ""

    def open_document(self, path: str, title: str = ""):
        """Show *path* (made the window's document first when it is another
        file), at page 1; it becomes the current document.  The document, or
        None (the one shown stays) when it cannot be opened.  *title* is not
        used any more (the subtitle names the file)."""
        doc = self.borrow(path)
        if doc is None:
            return None
        self._pg = 0
        self._src_path = str(path)
        self.refresh_document(announce=True)
        return doc

    def save(self, after=None):
        """Save (Ctrl+S, the page's Save): the window's Save, over the file."""
        return self.window_.save(after)

    def document_moved(self, path: str) -> None:
        if self._src_path:
            self._src_path = str(path)
            self.refresh_document()

    def document_replaced(self) -> None:
        self._strip_doc = None
        self.on_page()
        self.show_current()

    def restore_step(self, state) -> None:
        """A page change undone: the tool's page-bound state as it was."""
        if isinstance(state, tuple) and len(state) == 2 and state[0] == "pages":
            self.restore_page_state(state[1])

    def undo(self):
        """Ctrl+Z, the rail's Undo: the document's last edit (the window's)."""
        return self.window_.undo()

    # ── marks beside the document (crash recovery copies them with it) ──
    def recovery_extra(self) -> dict:
        """Unsaved state beyond the document (a page's own, e.g. Redact's boxes)."""
        return {}

    def restore_extra(self, state: dict) -> None:
        """Put back what recovery_extra() returned."""


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
        self.doc_bar = None                 # the document bar: the Open control + chip row
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
        """The page's own subtitle (the bar's chip names the file); one that
        only says to open a file (HINT_SUBTITLE) gives way to the file name."""
        path = self.document_path() if self.follows_document else ""
        name, base = (Path(path).name if path else ""), self._subtitle
        text = name if name and base == HINT_SUBTITLE else base
        self.subtitle_label.setText(text)
        self.subtitle_label.setVisible(bool(text))

    # ── the document (single-input pages) ──
    follows_document = False    # True: the page shows the window's current document

    def doc_input(self, on_change=None) -> DocInput:
        """Make this a single-input page: self.file holds its PDF (nothing
        drawn), the empty-state target goes into the body here (where a
        FileCard went, TARGET_FORM_H tall, the options below it stay shown)
        while there is no document; the document bar goes under the
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
        if self.doc_bar is None:
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

    @property
    def _dirty(self) -> bool:
        return self.__dict__.get("_dirty_flag", False)

    @_dirty.setter
    def _dirty(self, value: bool):
        self.__dict__["_dirty_flag"] = value

    def is_dirty(self) -> bool:
        """Edits since the last save or open (the editing screens: the
        window's document, SharedDocPage)."""
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
            fm = self.__dict__.get("_folder_mode")
            self.drop_target.setVisible(empty and not (fm is not None and fm.on))

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
        # The buttons follow the text: the library gives the spare width to the
        # title and the (empty) description, so a wide bar pushed them to its
        # far end.  The bar is half the page wide on every screen (owner).
        bar.contentLabel.hide()
        # the library's SetMinimumSize constraint resets the minimum width, so
        # a fixed width would not hold: _size_offer sets the width itself
        bar.hBoxLayout.setSizeConstraint(QLayout.SetNoConstraint)
        bar.textLayout.setStretchFactor(bar.titleLabel, 0)
        bar.textLayout.setStretchFactor(bar.contentLabel, 0)
        # in a horizontal bar the buttons sit beside the text, in the outer
        # layout: the spare width goes after them
        bar.hBoxLayout.setStretchFactor(bar.textLayout, 0)
        bar.hBoxLayout.addStretch(1)
        self.layout().insertWidget(0, bar, 0, Qt.AlignLeft)
        self._offer = (bar, str(out))
        self._size_offer()

    def _size_offer(self):
        if self._offer is not None:
            bar = self._offer[0]
            bar.setFixedWidth(max(bar.minimumSizeHint().width(), self.width() // 2))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._size_offer()

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
        """This tool and the current document are cleared (after the
        unsaved-edits question)."""
        win = self.window_
        if win is not None:
            if win.clear_current_document():
                self.dismiss_offer()
            return
        self.dismiss_offer()
        self.clear_document()

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
                    parts: bool = False, in_place: str | None = None, applied=None):
        """Run *work* on the chosen file: the file card's (or *src*, already
        checked), opened, prepare(doc), the output asked for, then
        work(doc, out, stop, progress) in a job (it closes doc) and, when the
        job is done, report(result, out) -> (role, status, box title, box text).
        warning_box: a "warning" result is shown in a warning box, not an
        information box (Compress: the saved file is no smaller).

        save: (default name, extension, filters) asks for a file; None asks
        for a folder.  label: the job's label, or a callable giving it after
        prepare.  prepare(doc): a ValueError's message is shown as an error,
        a Refusal's as a warning; either closes doc and stops, as does a
        return of False (prepare has said why, or asked and been told no).  open_doc(src)
        -> doc | None replaces window.open_pdf_safe.  ended(kind) runs however
        the job ended, before report.

        A PDF output (save with ".pdf", or *parts*: work writes PDFs into the
        chosen folder) from an input opened with a password asks once whether
        the new files keep it (ask_keep_password).  One PDF written (save with
        ".pdf") puts the after-job question up (offer_output); a folder of
        outputs asks nothing.

        in_place (owner's sort, 2026-10-23: the tools applied with OK): the
        edit's label.  The file is made the window's document first (after
        the unsaved-edits question), the work writes a temporary file, and
        that takes the document's place as one undoable edit: no save
        dialog, no after-job question, *report* is not used.  applied(result)
        -> (role, status, box text or None, take it) says how it went; take
        it False leaves the document as it was (Compress: no smaller).

        The job, or None when none was started (no file, a refusal, a
        cancelled save dialog, another job running)."""
        if src is None:
            src = self.chosen_file(title)
            if not src:
                return None
        win = self.window_
        if in_place and not win.adopt(src, ask=True):
            return None
        if open_doc is not None:
            doc = open_doc(src)
        else:
            doc = shared_copy(win, src) or win.open_pdf_safe(src)
        if doc is None:
            return None
        if prepare is not None:
            try:
                go_on = prepare(doc)
                if go_on is False:          # prepare said why (or the user said no)
                    doc.close()
                    return None
            except Refusal as e:
                doc.close()
                dialogs.warning(title, str(e))
                return None
            except ValueError as e:
                doc.close()
                dialogs.error(title, str(e))
                return None
        if in_place:
            import tempfile
            tmp_dir = tempfile.mkdtemp(prefix="pk-apply-")
            out = os.path.join(tmp_dir, "applied.pdf")
            kept = None                 # the document keeps its own password
        else:
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
            if in_place:
                try:
                    if kind == "done":
                        self._take_output(out, in_place, result, applied, title, warning_box)
                finally:
                    import shutil
                    shutil.rmtree(tmp_dir, ignore_errors=True)
                return
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
            if in_place:
                import shutil
                shutil.rmtree(tmp_dir, ignore_errors=True)
        return job

    def _take_output(self, out: str, label: str, result, applied, title: str,
                     warning_box: bool):
        """An in-place run ended: its output becomes the document's content
        (the open password goes with it) as one undoable edit."""
        win = self.window_
        role, status, box, take = (applied(result) if applied is not None else
                                   ("success", f"✓  {label} applied · Save writes it to the file",
                                    None, True))
        if take:
            sd = win.document
            with open(out, "rb") as f:
                new = fitz.open("pdf", f.read())
            from ..core.password import carry_open_password
            carry_open_password(sd.doc, new)
            key = getattr(getattr(self, "tool", None), "name", "") or type(self).__name__
            sd.replace(new, label, {"page": key})
        win.set_status(status, role)
        if box:
            (dialogs.warning if warning_box and role == "warning" else dialogs.info)(title, box)

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
        visible file card that takes it gets it.  With a folder input
        (prototype B, folder_mode), a dropped folder becomes its input."""
        fm = self.__dict__.get("_folder_mode")
        if fm is not None and fm.accept_drop(path):
            return True
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
# The editors' page strip (owner, 2026-10-18): left of the page, resizable,
# collapses below STRIP_MIN; open or closed is remembered (prefs qt_page_strip).
STRIP_W, STRIP_MIN, STRIP_MAX = 150, 120, 240
STRIP_THUMB = (84, 108)         # its largest thumbnail, in px
STRIP_ZOOM = 0.16
GLYPH_PAGES = 0xE7C3            # Segoe Fluent Icons: Page
PAGES_TITLE = "Pages"
PAGES_DESC = "Select pages in the strip · drag them to move"
KEEP_ONE = "A PDF needs at least one page: keep one or more."


def pages_phrase(nums) -> str:
    """How the delete question names 1-based page numbers: "page 4",
    "pages 2 and 3", "pages 1-3, 7"."""
    from ..pages import ranges_text as _rt
    nums = sorted(nums)
    if len(nums) == 1:
        return f"page {nums[0]}"
    if len(nums) == 2:
        return f"pages {nums[0]} and {nums[1]}"
    return "pages " + _rt([n - 1 for n in nums])


def delete_question(nums) -> str:
    return f"Delete {pages_phrase(nums)}? Undo brings them back until you save."


def _rearrange(doc, order) -> None:
    """*doc*'s pages in *order*, in place, with what belongs to the document
    kept (core.organise.rearrange: bookmarks, forms, labels, layers)."""
    from ..core import organise
    organise.rearrange(doc, list(order))


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
    colour; rail=False hides the rail and its divider (a viewer has no tools).

    page_strip=True (the editors, owner 2026-10-18): a strip of page
    thumbnails between the rail and the page, resizable and collapsible like
    the panel.  A click goes to the page; Ctrl / Shift click selects several;
    a drag moves them.  add_pages_tool() puts "Pages" in the rail: the panel
    then shows Rotate left / right and Delete for the selection.  A page
    change is a step on the window's one history (SharedDocPage), and a
    tool with state tied to page numbers keeps it in step (page_state,
    restore_page_state, remap_pages)."""

    def __init__(self, title: str, subtitle: str = "", *, tool=None, window=None,
                 view_cls=None, rail: bool = True, page_strip: bool = False):
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
        self.strip_reopen_btn = None
        if page_strip:
            # The page strip's way back, at the left as the panel's is at the right.
            self.strip_reopen_btn = icon_button(theme.glyph_icon(0xE76C, 14))
            self.strip_reopen_btn.setToolTip("Show pages")
            self.strip_reopen_btn.clicked.connect(lambda: self.show_strip(True))
            self.strip_reopen_btn.hide()
            strip.addWidget(self.strip_reopen_btn)
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
        pv = QVBoxLayout(panel)
        pv.setContentsMargins(16, 12, 12, 16)
        pv.setSpacing(0)
        # The tool's own panel (panel_begin) and, with a page strip, the Pages
        # panel: one of the two shows, so neither is rebuilt for the other.
        self._panel_tools = QWidget(panel)
        self._panel_v = QVBoxLayout(self._panel_tools)
        self._panel_v.setContentsMargins(0, 0, 0, 0)
        self._panel_v.setSpacing(0)
        pv.addWidget(self._panel_tools, 1)
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
        self.thumbs = None
        if page_strip:
            h.addWidget(self._build_strip(), 1)
        else:
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
        qss = ("QSplitter::handle { background: transparent; }"
               f"QSplitter::handle:hover {{ background: {accent}; }}")
        self.split.setStyleSheet(qss)
        if getattr(self, "outer", None) is not None:
            self.outer.setStyleSheet(qss)

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
        if self.thumbs is not None:
            self.strip_reopen_btn.setIcon(theme.glyph_icon(0xE76C, 14))
            self._strip_hide_btn.setIcon(theme.glyph_icon(0xE76B, 14))
            if self._pages_hide_btn is not None:
                self._pages_hide_btn.setIcon(theme.glyph_icon(0xE76C, 14))

    # ── rail ──
    def add_rail(self, key: str, glyph: int, tip: str, slot, toggle: bool = True):
        cls = TransparentToggleToolButton if toggle else TransparentToolButton
        btn = cls(theme.glyph_icon(glyph, 18))
        btn.setFixedSize(40, 40)
        btn.setToolTip(tip)
        btn.pk_key, btn.pk_glyph = key, glyph
        if toggle and key != "pages":
            # A tool of the page's own: its panel comes back from the Pages one.
            btn.clicked.connect(lambda _=False: self._pages_on and self.show_pages_panel(False))
        btn.clicked.connect(slot)
        self.rail.insertWidget(self.rail.count() - 1, btn)
        return btn

    def add_rail_gap(self):
        self.rail.insertSpacing(self.rail.count() - 1, 12)

    _pages_on = False       # the Pages panel shows (page_strip)
    _tool_key = ""          # the tool marked last, for when the Pages panel goes

    def mark_rail(self, key: str):
        """Mark the chosen tool: its toggle button checked (Fluent draws it).
        While the Pages panel shows, Pages stays marked."""
        if key != "pages":
            self._tool_key = key
        shown = "pages" if self._pages_on else key
        for i in range(self.rail.count()):
            w = self.rail.itemAt(i).widget()
            if w is not None and hasattr(w, "pk_key") and w.isCheckable():
                w.setChecked(w.pk_key == shown)

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
        # One section-heading style on every card (critique 2026-11-21: 20 px here,
        # 14 px semibold on the forms' cards).
        head = StrongBodyLabel(title)
        head.setObjectName("panelTitle")
        top.addWidget(head)
        self.panel_info = None
        if desc:                    # the description by an "i", as every row's
            self.panel_info = info_button(title, desc, within=box)
            top.addWidget(self.panel_info, 0, Qt.AlignVCenter)
        top.addStretch(1)
        if not self.panel_hosted:
            hide = icon_button(theme.glyph_icon(0xE76C, 14))
            hide.setToolTip("Hide panel")
            hide.clicked.connect(lambda: self.show_context(False))
            top.addWidget(hide)
            self._panel_hide_btn = hide
        bv.addLayout(top)
        self.panel_body = QVBoxLayout()
        # hosted on the card: the heading binds to what follows (critique 2026-11-21)
        self.panel_body.setContentsMargins(0, 4 if self.panel_hosted else 8, 0, 0)
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
        if self.panel_hosted:
            return
        w = self.split.sizes()[1]
        if 0 < w < PANEL_MIN:
            self.show_context(False)
        elif w:
            self._panel_w = min(PANEL_MAX, w)
        self.reopen_btn.setVisible(self.split.sizes()[1] == 0)

    def eventFilter(self, obj, ev):
        if ev.type() == ev.Type.MouseButtonDblClick:
            if obj is self.__dict__.get("_strip_handle"):
                self.show_strip(not self.strip_shown())
            else:
                self.show_context(not self.context_shown())
            return True
        return False

    def has_context(self) -> bool:
        return True

    def context_shown(self) -> bool:
        return self.panel_hosted or self.split.sizes()[1] > 0

    def context_width(self) -> int:
        return self.split.sizes()[1]

    def show_context(self, on: bool):
        if self.panel_hosted:                   # in a host's pane: always shown
            return
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

    # ── page strip (page_strip=True) ──
    _strip_doc = None       # the document the strip shows (None: load it again)
    _pages_box = None
    _pages_hide_btn = None
    panel_hosted = False    # the context panel moved into a host's pane (structure.py)

    def _build_strip(self) -> QWidget:
        """The strip and the panel's splitter in one splitter of their own."""
        from PySide6.QtWidgets import QSplitter
        from ..prefs import PREFS
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(8, 8, 2, 8)
        v.setSpacing(4)
        top = QHBoxLayout()
        top.addWidget(muted_caption(PAGES_TITLE))
        top.addStretch(1)
        self._strip_hide_btn = icon_button(theme.glyph_icon(0xE76B, 14))
        self._strip_hide_btn.setToolTip("Hide pages")
        self._strip_hide_btn.clicked.connect(lambda: self.show_strip(False))
        top.addWidget(self._strip_hide_btn)
        v.addLayout(top)
        self.thumbs = ThumbList(STRIP_THUMB, can_render=self._strip_can_render)
        self.thumbs.currentItemChanged.connect(self._strip_clicked)
        self.thumbs.itemSelectionChanged.connect(self._pages_buttons)
        self.thumbs.moved.connect(self._strip_moved)
        v.addWidget(self.thumbs, 1)
        box.setMinimumWidth(STRIP_MIN)
        box.setMaximumWidth(STRIP_MAX)
        box.hide()                              # until a document is open
        self.strip_box = box
        outer = QSplitter(Qt.Horizontal)
        outer.setHandleWidth(6)
        outer.setChildrenCollapsible(True)
        outer.addWidget(box)
        outer.addWidget(self.split)
        outer.setCollapsible(1, False)
        outer.setStretchFactor(1, 1)
        self.outer = outer
        self._style_split()
        self._strip_w = STRIP_W
        self._strip_open = bool(PREFS.qt_page_strip)
        self._strip_sync = False
        self._from_strip = False
        self._strip_reselect = None
        self._strip_anim = None
        outer.splitterMoved.connect(self._clamp_strip)
        # Kept: the filter compares with it and never asks the splitter,
        # which may already be deleted while the window closes.
        self._strip_handle = outer.handle(1)
        self._strip_handle.installEventFilter(self)
        return outer

    def strip_shown(self) -> bool:
        return self.thumbs is not None and not self.strip_box.isHidden() \
            and self.outer.sizes()[0] > 0

    def _remember_strip(self, on: bool):
        from ..prefs import PREFS
        self._strip_open = on
        if PREFS.qt_page_strip != on:
            PREFS.qt_page_strip = on
            try:
                PREFS.save()
            except OSError:
                pass                            # remembered for this session only

    def _strip_buttons(self):
        if self.thumbs is not None:
            self.strip_reopen_btn.setVisible(not self.strip_box.isHidden()
                                             and self.outer.sizes()[0] == 0)

    def show_strip(self, on: bool):
        """Slide the page strip open or closed (as show_context the panel)."""
        if self.thumbs is None:
            return
        self._remember_strip(on)
        old = self._strip_anim
        if old is not None:
            self._strip_anim = None
            old.stop()
        start, target = self.outer.sizes()[0], (self._strip_w if on else 0)
        if start == target or self.strip_box.isHidden():
            self._strip_buttons()
            return
        a = QVariantAnimation(self)
        a.setDuration(SLIDE_MS)
        a.setStartValue(start)
        a.setEndValue(target)
        a.setEasingCurve(QEasingCurve.OutCubic)

        def step(w):
            total = sum(self.outer.sizes())
            self.outer.setSizes([int(w), total - int(w)])
        a.valueChanged.connect(step)
        a.finished.connect(self._strip_buttons)
        a.finished.connect(lambda: self._strip_anim is a and setattr(self, "_strip_anim", None))
        self._strip_anim = a
        a.start(QVariantAnimation.DeleteWhenStopped)

    def _clamp_strip(self, *_):
        w = self.outer.sizes()[0]
        if 0 < w < STRIP_MIN:
            self.show_strip(False)
        elif w:
            self._strip_w = min(STRIP_MAX, w)
            self._remember_strip(True)
        else:
            self._remember_strip(False)
        self._strip_buttons()

    def _strip_can_render(self) -> bool:
        """No thumbnail is drawn while a job works on the document."""
        win = self.window_
        job = getattr(win, "_current_job", None) if win is not None else None
        if job is None:
            return True
        thread = getattr(job, "_thread", None)
        return not (job.is_running or (thread is not None and thread.is_alive()))

    def _strip_render(self, key: int):
        from PySide6.QtGui import QImage
        pix = self._doc[key].get_pixmap(matrix=fitz.Matrix(STRIP_ZOOM, STRIP_ZOOM), alpha=False)
        return QImage(pix.samples, pix.width, pix.height, pix.stride,
                      QImage.Format_RGB888).copy()

    def _sync_strip(self):
        """After show_current: the strip shows the document, its page current."""
        doc = getattr(self, "_doc", None)
        if doc is None:
            if not self.strip_box.isHidden() or self._strip_doc is not None:
                self.thumbs.clear_pages()
                self._strip_doc = None
                self.strip_box.hide()
            self._strip_buttons()
            return
        if self.strip_box.isHidden():
            self.strip_box.show()
            total = sum(self.outer.sizes())
            w = self._strip_w if self._strip_open else 0
            self.outer.setSizes([w, max(1, total - w)])
        self._strip_sync = True
        try:
            if doc is not self._strip_doc or self.thumbs.count() != len(doc):
                self.thumbs.load(len(doc), self._strip_render,
                                 self.__dict__.pop("_strip_icons", None))
                self._strip_doc = doc
            else:
                self.thumbs.refresh([self._pg])     # an edit on the page shown
            reselect, self._strip_reselect = self._strip_reselect, None
            self.thumbs.show_row(self._pg, keep_selection=self._from_strip, select=reselect)
        finally:
            self._strip_sync = False
        self._strip_buttons()
        self._pages_buttons()

    def strip_refresh(self, pages=None):
        """Draw these pages' thumbnails again (None: every page), after an
        edit that reached beyond the page shown."""
        if self.thumbs is not None and self._doc is not None:
            self.thumbs.refresh(range(len(self._doc)) if pages is None else pages)

    def _strip_clicked(self, cur, _prev=None):
        if self._strip_sync or cur is None or getattr(self, "_doc", None) is None:
            return
        k = cur.data(Qt.UserRole)
        if k == self._pg or not (0 <= k < len(self._doc)):
            return
        self._pg = k
        self._from_strip = True
        try:
            self.on_page()
            self.show_current()
        finally:
            self._from_strip = False

    # ── the Pages panel ──
    def add_pages_tool(self):
        """Pages in the rail: the panel shows the page actions."""
        return self.add_rail("pages", GLYPH_PAGES, PAGES_TITLE,
                             lambda _=False: self.show_pages_panel(True))

    def _build_pages_panel(self):
        box = QWidget(self.panel)
        bv = QVBoxLayout(box)
        bv.setContentsMargins(0, 0, 0, 0)
        bv.setSpacing(4)
        top = QHBoxLayout()
        top.addWidget(StrongBodyLabel(PAGES_TITLE))
        top.addStretch(1)
        self._pages_hide_btn = icon_button(theme.glyph_icon(0xE76C, 14))
        self._pages_hide_btn.setToolTip("Hide panel")
        self._pages_hide_btn.clicked.connect(lambda: self.show_context(False))
        top.addWidget(self._pages_hide_btn)
        self._pages_hide_btn.setVisible(not self.panel_hosted)   # a hosted panel stays
        bv.addLayout(top)
        d = muted_caption(PAGES_DESC)
        d.setWordWrap(True)
        bv.addWidget(d)
        bv.addSpacing(8)
        self.rotate_left_btn = PushButton("Rotate left")
        self.rotate_left_btn.clicked.connect(lambda: self.rotate_pages(-90))
        self.rotate_right_btn = PushButton("Rotate right")
        self.rotate_right_btn.clicked.connect(lambda: self.rotate_pages(90))
        self.delete_pages_btn = PushButton("Delete")
        self.delete_pages_btn.clicked.connect(self.delete_pages)
        for b in (self.rotate_left_btn, self.rotate_right_btn, self.delete_pages_btn):
            bv.addWidget(b)
        self.pages_hint = muted_caption("")
        self.pages_hint.setWordWrap(True)
        bv.addSpacing(4)
        bv.addWidget(self.pages_hint)
        bv.addStretch(1)
        self.panel.layout().addWidget(box, 1)
        box.hide()
        self._pages_box = box

    def show_pages_panel(self, on: bool):
        """The panel shows the page actions (on) or the tool's own panel."""
        if on and self._pages_box is None:
            self._build_pages_panel()
        self._pages_on = on
        if self._pages_box is not None:
            self._pages_box.setVisible(on)
        self._panel_tools.setVisible(not on)
        self.mark_rail(self._tool_key)
        if on and not self.context_shown():
            self.show_context(True)
        self._pages_buttons()

    def _pages_buttons(self):
        """Rotate and Delete act on the strip's selection; Delete never takes
        every page (Rotate & Reorder's rule and line)."""
        if self._pages_box is None or self.thumbs is None:
            return
        doc = getattr(self, "_doc", None)
        n = len(self.thumbs.selectedItems()) if doc is not None else 0
        every = doc is not None and n == len(doc)
        self.rotate_left_btn.setEnabled(bool(n))
        self.rotate_right_btn.setEnabled(bool(n))
        self.delete_pages_btn.setEnabled(bool(n) and not every)
        self.pages_hint.setText(KEEP_ONE if every else "")
        theme.label_role(self.pages_hint, "warning" if every else "muted")

    # ── page changes and their undo ──
    def page_state(self):
        """A tool's state tied to page numbers, kept with a page change."""
        return None

    def restore_page_state(self, state) -> None:
        """Undo of a page change: the state page_state() gave back."""

    def remap_pages(self, mapping: dict, turned: set) -> None:
        """The pages changed: *mapping* old index -> new index (None: deleted);
        *turned* the indices turned (their page space changed)."""

    def rotate_pages(self, deg: int):
        rows = self.thumbs.selected_rows() if self.thumbs is not None else []
        if not rows or getattr(self, "_doc", None) is None:
            return

        def turn(doc):
            for i in rows:
                p = doc[i]
                p.set_rotation((p.rotation + deg) % 360)
        self._page_change(turn, {i: i for i in range(len(self._doc))}, turned=set(rows))

    def delete_pages(self):
        """Delete the selected pages, after asking; Undo brings them back."""
        rows = self.thumbs.selected_rows() if self.thumbs is not None else []
        doc = getattr(self, "_doc", None)
        if not rows or doc is None or len(rows) == len(doc):
            return                              # Delete is off then; the panel says why
        if not dialogs.ask_yes_no("Delete pages", delete_question([r + 1 for r in rows])):
            return
        gone = set(rows)
        keep = [i for i in range(len(doc)) if i not in gone]
        mapping = {old: None for old in gone}
        mapping.update({old: new for new, old in enumerate(keep)})
        self._page_change(lambda d: _rearrange(d, keep), mapping, cut=True)

    def _strip_moved(self, order: list):
        """A drag in the strip: *order* the pages' old indices in their new order."""
        if getattr(self, "_doc", None) is None or order == list(range(len(order))):
            return
        if sorted(order) != list(range(len(self._doc))):
            self._strip_doc = None              # not the document's pages: show them again
            return self.show_current()
        mapping = {old: new for new, old in enumerate(order)}
        self._page_change(lambda d: _rearrange(d, order), mapping)

    def _page_change(self, apply, mapping: dict, *, turned=(), cut: bool = False):
        """apply(doc) changes the open document's pages in place; on the
        window's history goes the whole document as it was."""
        doc = self._doc
        turned = set(turned)
        icons = self.thumbs.icons()
        sel = [self.thumbs.item(r).data(Qt.UserRole) for r in self.thumbs.selected_rows()]
        # On the window's one history (SharedDocPage) with the tool's
        # page-bound state, which restore_step hands back on undo.
        self._push_undo(PAGES_TITLE, ("pages", self.page_state()))
        try:
            apply(doc)
        except Exception as e:
            # Half done: the document as it was.
            self._pop_undo()
            self._strip_doc = None
            self.show_current()
            return dialogs.error(PAGES_TITLE, f"The pages could not be changed:\n{e}")
        self.remap_pages(mapping, turned)
        # A turn or a move removes nothing: Save may append it; a delete is
        # written whole (owner's choice 2026-10-12).
        self._adds_pending = not cut
        new_pg = mapping.get(self._pg)
        if new_pg is None:
            # The page shown was deleted: the next one kept, else the last.
            later = [mapping[k] for k in sorted(mapping) if k > self._pg and mapping[k] is not None]
            new_pg = later[0] if later else len(self._doc) - 1
        self._pg = new_pg
        self._strip_icons = {mapping[k]: ic for k, ic in icons.items()
                             if mapping.get(k) is not None and k not in turned}
        self._strip_reselect = sorted(mapping[k] for k in sel if mapping.get(k) is not None)
        self._strip_doc = None
        self._dirty = True
        self.on_page()
        self.show_current()
        if self.window_ is not None:
            self.window_.set_status("Pages changed — use Save to write to disk", "success")

    def undo_page_change(self) -> bool:
        """Kept for the tools' undo: page changes are on the window's history now."""
        return False

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
        else:
            self.view.show_page(doc[self._pg])
            self.page_label.setText(f"{self._pg + 1} / {len(doc)}")
            self.draw_overlay(doc[self._pg])
        if self.thumbs is not None:
            self._sync_strip()

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
            # Hidden at once: deleteLater waits for the event loop, and until
            # then the widget would still be drawn under its replacement.
            item.widget().hide()
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
        if getattr(page, "rows_stacked", False):
            # a narrow column (structure prototype, PK_DETAILS=right): the note and
            # the control under the name
            texts.addWidget(self.note)
            if extra is not None:
                texts.addWidget(extra, 0, Qt.AlignLeft)
        else:
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


THUMB_BOX = (120, 150)      # organiser: the thumbnail box in a narrow pane, in px
THUMB_MAX = (160, 200)      # ... in a wide one (pages render about 167 px wide at 0.28)
FIT_CELL = 180              # a column's width when fitting thumbnails to the pane
THUMBS_PER_TICK = 4         # thumbnails rendered per event-loop turn
PART_ROLE = Qt.UserRole + 1     # an item's part number (1-based), 0 for none, None: no parts shown
CUT_ROLE = Qt.UserRole + 2      # True: the grid is cut after this item
GAP_PX = 10                 # how near a cell's edge a click counts as the gap


def _thumb_delegate(thumb_box=THUMB_BOX):
    """Paints an organiser item: the page centred in *thumb_box* with a hairline
    border, its label under it; selected = accent border on a tinted backing,
    hover = a faint backing.  (qfluentwidgets' ListWidget delegate paints
    list rows only, clipping icons in IconMode.)"""
    from PySide6.QtCore import QRect, QRectF, QSize
    from PySide6.QtGui import QPen
    from PySide6.QtWidgets import QStyle, QStyledItemDelegate

    class ThumbDelegate(QStyledItemDelegate):
        def sizeHint(self, option, index):
            return QSize(thumb_box[0] + 24, thumb_box[1] + 40)

        def paint(self, p, option, index):
            p.save()
            p.setRenderHint(QPainter.Antialiasing)
            r = option.rect.adjusted(2, 2, -2, -2)
            sel = bool(option.state & QStyle.State_Selected)
            # A page-range tool (owner, 2026-10-17): the chosen pages look
            # plain and a page left out is veiled, so the eye goes to what is
            # not included; nothing is tinted for being selected.
            left_out = False
            view = option.widget
            if view is not None and view.property("pkMarkLeftOut"):
                left_out, sel = not sel, False
            hover = bool(option.state & QStyle.State_MouseOver)
            accent = theme.color("accent")
            part = index.data(PART_ROLE)
            if part:
                # Split's parts (owner, 2026-10-17): each part's pages sit on a
                # faint tile, alternate parts in two tones, so a part reads as
                # one block.  The tile fills the cell so a part's tiles touch.
                tint = theme.color("accent" if part % 2 else "text")
                tint.setAlpha(40 if part % 2 else 18)
                p.fillRect(option.rect, tint)
            if sel or hover:
                bg = theme.color("selection")
                bg.setAlpha(46 if sel else 18)
                p.setPen(Qt.NoPen)
                p.setBrush(bg)
                p.drawRoundedRect(QRectF(r), 6, 6)
            icon = index.data(Qt.DecorationRole)
            box = QRect(r.x() + (r.width() - thumb_box[0]) // 2, r.y() + 8, *thumb_box)
            if icon is not None and not icon.isNull():
                pm = icon.pixmap(QSize(*thumb_box))
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
            if part == 0 or left_out:       # a page in no part, or left out, is veiled
                veil = theme.color("page_bg")
                veil.setAlpha(170)
                p.fillRect(img, veil)
            label = str(index.data(Qt.DisplayRole) or "")
            if part:
                # the part named on its pages: its tint alone read as a selection
                # (critique 2026-11-21)
                label = f"{label} · Part {part}"
            p.drawText(QRect(r.x(), box.bottom() + 6, r.width(), 20),
                       Qt.AlignHCenter | Qt.AlignTop, label)
            if index.data(CUT_ROLE):
                # The cut: a bar in the gap after the page, the height of the box.
                o = option.rect
                p.fillRect(QRect(o.right() - 1, box.y(), 3, box.height()), accent)
            p.restore()

    return ThumbDelegate()


def _thumb_icon_of(img, box):
    """A rendered page (QImage) as an icon no larger than *box*."""
    from PySide6.QtGui import QIcon, QPixmap
    pm = QPixmap.fromImage(img)
    if pm.width() > box[0] or pm.height() > box[1]:
        pm = pm.scaled(*box, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    return QIcon(pm)


class ThumbList(QListWidget):
    """The editors' page strip (WorkspacePage page_strip=True): a thumbnail
    per page, its key the page's index, labelled "p.N"; drawn a few per
    event-loop turn while can_render() allows; multi-selectable.  A drag
    emits moved(keys in their new order) once the drop is over.

        load(n, render, icons)  render(key) -> QImage; icons: key -> QIcon kept
        refresh(keys)   draw these again, first
        show_row(i, keep_selection, select)   page i current (and selected)"""

    moved = Signal(list)

    def __init__(self, box=STRIP_THUMB, can_render=lambda: True, parent=None):
        from PySide6.QtCore import QSize
        super().__init__(parent)
        self._box = box
        self._can_render = can_render
        self.setObjectName("thumbStrip")
        self.setStyleSheet("QListWidget#thumbStrip { background: transparent; border: none; }")
        self._delegate = _thumb_delegate(box)       # Qt does not own a Python delegate
        self.setItemDelegate(self._delegate)
        self.setMouseTracking(True)
        self.viewport().setAttribute(Qt.WA_Hover, True)
        self.setViewMode(QListView.IconMode)
        self.setResizeMode(QListView.Adjust)
        self.setWrapping(True)
        self.setUniformItemSizes(True)
        self.setSpacing(2)
        self.setIconSize(QSize(*box))
        self.setGridSize(QSize(box[0] + 24, box[1] + 40))
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setMovement(QListView.Snap)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._render = None
        self._queue: list = []
        self._timer = QTimer(self, interval=0)
        self._timer.timeout.connect(self._render_some)
        self._move_due = False
        self.model().rowsMoved.connect(self._rows_moved)

    def load(self, n: int, render, icons: dict | None = None):
        self._timer.stop()
        self._queue = []
        self.clear()
        self._render = render
        icons = icons or {}
        for k in range(n):
            it = QListWidgetItem(f"p.{k + 1}")
            it.setData(Qt.UserRole, k)
            it.setTextAlignment(Qt.AlignHCenter | Qt.AlignTop)
            it.setFlags(it.flags() | Qt.ItemIsDragEnabled)
            if k in icons:
                it.setIcon(icons[k])
            self.addItem(it)
        self._queue = [self.item(k) for k in range(n) if k not in icons]
        if self._queue:
            self._timer.start()

    def clear_pages(self):
        self._timer.stop()
        self._queue = []
        self.clear()

    def refresh(self, keys):
        want = [self.item(k) for k in keys if 0 <= k < self.count()]
        self._queue = want + [it for it in self._queue if all(it is not w for w in want)]
        if self._queue:
            self._timer.start()

    def _render_some(self):
        if not self._can_render():
            self._timer.setInterval(100)        # a job has the document: wait, idly
            return
        self._timer.setInterval(0)
        for _ in range(THUMBS_PER_TICK):
            if not self._queue:
                self._timer.stop()
                return
            it = self._queue.pop(0)
            if self._render is None or self.row(it) < 0:
                continue
            try:
                it.setIcon(_thumb_icon_of(self._render(it.data(Qt.UserRole)), self._box))
            except Exception:
                pass                            # a page that cannot be drawn keeps its placeholder

    def rendering(self) -> bool:
        return bool(self._queue)

    def keys(self) -> list:
        return [self.item(i).data(Qt.UserRole) for i in range(self.count())]

    def selected_rows(self) -> list[int]:
        return sorted(self.row(it) for it in self.selectedItems())

    def icons(self) -> dict:
        out = {}
        for i in range(self.count()):
            it = self.item(i)
            if not it.icon().isNull():
                out[it.data(Qt.UserRole)] = it.icon()
        return out

    def show_row(self, i: int, keep_selection: bool = False, select=None):
        it = self.item(i)
        if it is None:
            return
        if select is not None:
            self.clearSelection()
            for r in select or [i]:
                x = self.item(r)
                if x is not None:
                    x.setSelected(True)
        elif not keep_selection and not it.isSelected():
            self.clearSelection()
            it.setSelected(True)
        self.setCurrentItem(it, QItemSelectionModel.NoUpdate)
        self.scrollToItem(it)

    def _rows_moved(self, *_):
        # After the drop, not inside it: the receiver rebuilds the list.
        if not self._move_due:
            self._move_due = True
            QTimer.singleShot(0, self, self._emit_moved)

    def _emit_moved(self):
        self._move_due = False
        self.moved.emit(self.keys())


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
        # As tall with or without its buttons: the grid starts at the same
        # place on every organiser screen.
        bar.setMinimumHeight(CONTROL_H)
        self.context_bar_widget = bar
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
        self.columns = cols
        self.grid_card = plain_card()
        gv = QVBoxLayout(self.grid_card)
        gv.setContentsMargins(8, 8, 8, 8)
        self._grid_v = gv
        g = QListWidget(self.grid_card)
        g.setObjectName("thumbGrid")
        g.setStyleSheet("QListWidget#thumbGrid { background: transparent; border: none; }")
        self._box = list(THUMB_BOX)              # follows the pane (_fit_thumbs)
        self._delegate = _thumb_delegate(self._box)  # Qt does not own a Python delegate
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
        self._fit_grid = g
        g.installEventFilter(self)
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
        # kept up to THUMB_MAX: the grid draws it at the size the pane allows
        if pm.width() > THUMB_MAX[0] or pm.height() > THUMB_MAX[1]:
            pm = pm.scaled(*THUMB_MAX, Qt.KeepAspectRatio, Qt.SmoothTransformation)
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

    # ── parts and cuts (Split) ──
    def enable_gaps(self, on_gap):
        """A click within GAP_PX of the edge between two thumbnails calls
        on_gap(i), i the row the gap follows, instead of selecting; the
        pointer over a gap is the split cursor."""
        self._on_gap = on_gap
        # Kept: the filter compares with it and never asks the grid, which
        # may already be deleted while the window closes.
        self._gap_viewport = self.grid.viewport()
        self._gap_viewport.installEventFilter(self)
        self._gap_viewport.setMouseTracking(True)

    def gap_at(self, pos) -> int | None:
        """The row whose following gap *pos* (viewport) is on, or None."""
        idx = self.grid.indexAt(pos)
        if not idx.isValid():
            return None
        rect = self.grid.visualRect(idx)
        row = idx.row()
        if pos.x() >= rect.right() - GAP_PX and row < self.grid.count() - 1:
            return row
        if pos.x() <= rect.left() + GAP_PX and row > 0:
            return row - 1
        return None

    def _fit_thumbs(self):
        """Thumbnails sized to the pane: as many FIT_CELL-wide columns as fit, each
        page as large as its column allows, from THUMB_BOX up to THUMB_MAX
        (critique 2026-11-21: 108 px thumbnails left 82-93 % of the pane empty)."""
        from PySide6.QtCore import QSize
        vp = self.grid.viewport().width()
        if vp <= 0:
            return
        cols = max(1, vp // FIT_CELL)
        w = max(THUMB_BOX[0], min(THUMB_MAX[0], vp // cols - 24 - 2 * self.grid.spacing()))
        box = [w, w * THUMB_MAX[1] // THUMB_MAX[0]]
        if box == self._box:
            return
        self._box[:] = box
        self.grid.setIconSize(QSize(*box))
        self.grid.setGridSize(QSize(box[0] + 24, box[1] + 40))
        self.grid.doItemsLayout()

    def eventFilter(self, obj, e):
        if obj is self.__dict__.get("_fit_grid") and e.type() == QEvent.Resize:
            self._fit_thumbs()
        if obj is self.__dict__.get("_gap_viewport"):
            t = e.type()
            if t == QEvent.MouseMove:
                gap = self.gap_at(e.position().toPoint())
                obj.setCursor(Qt.SplitHCursor if gap is not None else Qt.ArrowCursor)
            elif t == QEvent.MouseButtonPress and e.button() == Qt.LeftButton \
                    and not e.modifiers():
                gap = self.gap_at(e.position().toPoint())
                if gap is not None:
                    self._on_gap(gap)
                    return True
        return super().eventFilter(obj, e)

    def set_marks(self, parts: dict | None, cuts=()):
        """Show each row's part (parts: row -> 1-based part, 0 for a page in no
        part; None shows no parts) and a cut after each row in *cuts*."""
        cuts = set(cuts)
        for i in range(self.grid.count()):
            it = self.grid.item(i)
            it.setData(PART_ROLE, None if parts is None else parts.get(i, 0))
            it.setData(CUT_ROLE, i in cuts)
        self.grid.viewport().update()

    def marks(self) -> list[tuple]:
        """Each row's (part, cut after) as shown."""
        return [(self.grid.item(i).data(PART_ROLE), bool(self.grid.item(i).data(CUT_ROLE)))
                for i in range(self.grid.count())]

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


# ── Tools that act on chosen pages (owner, 2026-10-17) ───────────────────────
# A tool applied in place: its status ends so (the edit is unsaved, 2026-10-23).
SAVE_NOTE = " · Save writes it to the file"
APPLY = "Apply"         # the card's action on a tool that changes the open document (step 5 E)
ALL_PAGES = "all"
NO_PAGES = "Select at least one page."
PICK_HINT = "Click pages to choose them · Ctrl / Shift for several"
PICK_ZOOM = 0.28


class PagePickPage(HeldDoc, OrganiserPage):
    """A single-file tool whose pages are on screen (owner, 2026-10-17): the
    organiser layout, the grid in the centre with every page selected when a
    document opens, the tool's settings in the column at the right.  The
    selection and the page-range field (make_range_field) stay in step: the
    field reads "all" with every page selected, the selection's ranges
    otherwise, and a range typed selects its pages.  With no page selected
    the main action is off and the bar says why (as Merge's).

    The page holds the document open (HeldDoc) for its thumbnails, so an
    encrypted file asks for its password once; job_copy is the job's own copy.

        pages()  the selected pages, 0-based, in page order"""

    def __init__(self, title: str, subtitle: str = "", *, tool=None, window=None, parent=None):
        super().__init__(title, subtitle, tool=tool, window=window, settings=True,
                         drag_reorder=False, hint=PICK_HINT, parent=parent)
        self.page_range = None
        self._syncing = False
        self.grid.setProperty("pkMarkLeftOut", True)    # see _thumb_delegate
        self.all_btn = self.add_action("All pages", None, self.select_all_pages,
                                       needs_selection=False)

    # ── the range field ──
    def make_range_field(self, placeholder: str = "all  or  1-5, 8, 10-end", width: int = 180):
        ed = LineEdit()
        ed.setPlaceholderText(placeholder)
        ed.setMinimumWidth(width)
        ed.textChanged.connect(self._range_typed)
        self.page_range = ed
        return ed

    def _range_typed(self, text: str):
        if self._syncing or self._doc is None:
            return
        from ..pages import PageRangeError, selected_pages as _sel
        try:
            want = set(_sel(text, len(self._doc)))
        except PageRangeError:
            return                          # said when the tool runs
        # The field keeps what was typed: it is not rewritten under the cursor.
        self._syncing = True
        try:
            order = self.order()
            for i in range(self.grid.count()):
                self.grid.item(i).setSelected(order[i] in want)
            self._selection_changed()
        finally:
            self._syncing = False

    def _selection_changed(self):
        super()._selection_changed()
        if not hasattr(self, "all_btn"):
            return
        fm = self.__dict__.get("_folder_mode")
        if fm is not None and fm.on:
            return                          # a folder is the input: no page to choose
        n, total = len(self.grid.selectedItems()), self.grid.count()
        if self.page_range is not None and not self._syncing and total:
            from ..pages import ranges_text as _rt
            self._syncing = True
            try:
                self.page_range.setText(ALL_PAGES if n == total else _rt(self.pages()))
            finally:
                self._syncing = False
        none = bool(total) and not n
        for b in self._buttons:
            if getattr(b, "pk_primary", False):
                b.setEnabled(not none)
        if none:
            self.hint_label.setText(NO_PAGES)
        theme.label_role(self.hint_label, "warning" if none else "muted")
        self.all_btn.setEnabled(bool(total) and n < total)

    def select_all_pages(self):
        self.grid.selectAll()

    def pages(self) -> list[int]:
        order = self.order()
        return sorted(order[i] for i in self.selected())

    # ── the document ──
    def load(self, path: str):
        if not path:
            return
        doc = self.open_held(path, self.title_label.text())
        if doc is None:
            return
        self.set_pages(list(range(len(doc))), self.render, lambda k: f"p.{k + 1}")
        self.select_all_pages()
        self.on_loaded(doc)

    def on_loaded(self, doc):
        """A document was opened (a tool's own state)."""

    def render(self, key: int):
        import pymupdf as _fitz
        from PySide6.QtGui import QImage
        pix = self._doc[key].get_pixmap(matrix=_fitz.Matrix(PICK_ZOOM, PICK_ZOOM), alpha=False)
        return QImage(pix.samples, pix.width, pix.height, pix.stride,
                      QImage.Format_RGB888).copy()

    def clear_document(self):
        self._timer.stop()
        self.clear_pages()
        self.release_held()
        self.refresh_document()

    def park_document(self):
        if self._doc is not None:
            self._timer.stop()              # no thumbnail may render from a closed file
            self._queue = []
        super().park_document()

    def job_copy(self, _src=None):
        """The job's own copy of the held document (its password goes with it)."""
        import pymupdf as _fitz
        from ..core.password import carry_open_password as _carry
        copy = _fitz.open("pdf", self._doc.tobytes())
        _carry(self._doc, copy)
        return copy

    def range_text(self) -> str:
        """The field's text for a run: "all" is every page."""
        t = self.page_range.text().strip() if self.page_range is not None else ""
        return "" if t.lower() == ALL_PAGES else t


# ── Merge's page strip (owner, 2026-10-17) ────────────────────────────────────
PAGES_MIME = "application/x-paperknife-pages"
KEY_ROLE = Qt.UserRole


def _key(item):
    k = item.data(KEY_ROLE)
    return tuple(k) if isinstance(k, list) else k


class PageStrip(QWidget):
    """Several runs of pages, each under a heading row, in one scrolling
    column: Merge's strip of every input's pages in merged order.  Pages are
    selected as in a grid (click, Ctrl / Shift, drag over; a plain click in
    one run clears the others) and dragged to a new place in any run:
    on_moved(keys, target, after) then gets the dragged keys and the key they
    were dropped before (after=False) or after.  A key is any hashable the
    page chooses; keys are passed as JSON, so tuples come back as lists and are
    turned back into tuples.

        set_runs([(heading, [key, ...]), ...], label)   label(key) -> str
        set_icon(key, icon) / keys() / selected_keys() / set_veiled(keys)"""

    def __init__(self, on_moved, on_selection=None, parent=None):
        from PySide6.QtCore import QSize
        from PySide6.QtWidgets import QAbstractItemView, QListView, QListWidget
        super().__init__(parent)
        self._on_moved, self._on_selection = on_moved, on_selection
        self._items: dict = {}
        self._lists: list = []
        self._delegate = _thumb_delegate()
        strip = self

        class RunList(QListWidget):
            def __init__(self):
                super().__init__()
                self.setObjectName("thumbGrid")
                self.setStyleSheet("QListWidget#thumbGrid { background: transparent; border: none; }")
                self.setItemDelegate(strip._delegate)
                self.setViewMode(QListView.IconMode)
                self.setResizeMode(QListView.Adjust)
                self.setWrapping(True)
                self.setUniformItemSizes(True)
                self.setMovement(QListView.Static)
                self.setIconSize(QSize(*THUMB_BOX))
                self.setGridSize(QSize(THUMB_BOX[0] + 24, THUMB_BOX[1] + 40))
                self.setSelectionMode(QAbstractItemView.ExtendedSelection)
                self.setDragEnabled(True)
                self.setAcceptDrops(True)
                self.setDropIndicatorShown(True)
                self.setDragDropMode(QAbstractItemView.DragDrop)
                self.setFrameShape(QFrame.NoFrame)
                self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
                self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
                self.setMouseTracking(True)
                self.viewport().setAttribute(Qt.WA_Hover, True)
                self.itemSelectionChanged.connect(strip._selection_changed)

            def fit(self):
                """As tall as its rows: the strip scrolls, not the run."""
                per_row = max(1, self.viewport().width() // self.gridSize().width())
                rows = max(1, -(-self.count() // per_row))
                self.setFixedHeight(rows * self.gridSize().height() + 8)

            def resizeEvent(self, e):
                super().resizeEvent(e)
                self.fit()

            def mousePressEvent(self, e):
                if not (e.modifiers() & (Qt.ControlModifier | Qt.ShiftModifier)):
                    for other in strip._lists:
                        if other is not self:
                            other.clearSelection()
                super().mousePressEvent(e)

            def startDrag(self, actions):
                from PySide6.QtCore import QMimeData
                from PySide6.QtGui import QDrag
                keys = strip.selected_keys()
                if not keys:
                    return
                mime = QMimeData()
                mime.setData(PAGES_MIME, json.dumps(keys).encode("utf-8"))
                drag = QDrag(self)
                drag.setMimeData(mime)
                first = strip._items.get(keys[0])
                if first is not None and not first.icon().isNull():
                    drag.setPixmap(first.icon().pixmap(48, 60))
                drag.exec(Qt.MoveAction)

            def dragEnterEvent(self, e):
                if e.mimeData().hasFormat(PAGES_MIME):
                    e.acceptProposedAction()
                else:
                    e.ignore()

            def dragMoveEvent(self, e):
                if e.mimeData().hasFormat(PAGES_MIME):
                    e.acceptProposedAction()
                else:
                    e.ignore()

            def dropEvent(self, e):
                if not e.mimeData().hasFormat(PAGES_MIME):
                    return e.ignore()
                keys = [tuple(k) if isinstance(k, list) else k
                        for k in json.loads(bytes(e.mimeData().data(PAGES_MIME)).decode("utf-8"))]
                pos = e.position().toPoint()
                idx = self.indexAt(pos)
                if idx.isValid():
                    target = _key(self.item(idx.row()))
                    after = pos.x() > self.visualRect(idx).center().x()
                else:
                    target, after = _key(self.item(self.count() - 1)), True
                e.setDropAction(Qt.CopyAction)      # the strip is rebuilt; Qt deletes nothing
                e.accept()
                # After the drag returns: the page rebuilds the lists.
                from PySide6.QtCore import QTimer
                QTimer.singleShot(0, lambda: strip._on_moved(keys, target, after))

        self._RunList = RunList
        area = SingleDirectionScrollArea(self, Qt.Vertical)
        area.setWidgetResizable(True)
        area.enableTransparentBackground()
        area.setFrameShape(QFrame.NoFrame)
        inner = QWidget()
        inner.setObjectName("pageStrip")
        inner.setStyleSheet("QWidget#pageStrip { background: transparent; }")
        self._v = QVBoxLayout(inner)
        self._v.setContentsMargins(8, 8, 8, 8)
        self._v.setSpacing(4)
        self._v.addStretch(1)
        area.setWidget(inner)
        self.area = area
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(area)
        self.headings: list = []

    def set_runs(self, runs, label):
        """Show *runs*, keeping the icons already made and the selection."""
        from PySide6.QtWidgets import QListWidgetItem
        icons = {k: it.icon() for k, it in self._items.items() if not it.icon().isNull()}
        selected = set(self.selected_keys())
        _clear_layout(self._v)
        self._items, self._lists, self.headings = {}, [], []
        for heading, keys in runs:
            h = StrongBodyLabel(heading)
            h.setContentsMargins(4, 8, 0, 0)
            self._v.addWidget(h)
            self.headings.append(h)
            run = self._RunList()
            for k in keys:
                it = QListWidgetItem(label(k))
                it.setData(KEY_ROLE, list(k) if isinstance(k, tuple) else k)
                it.setTextAlignment(Qt.AlignHCenter | Qt.AlignTop)
                if k in icons:
                    it.setIcon(icons[k])
                run.addItem(it)
                it.setSelected(k in selected)
                self._items[k] = it
            self._v.addWidget(run)
            self._lists.append(run)
            run.fit()
        self._v.addStretch(1)
        self._selection_changed()

    def set_icon(self, key, icon):
        it = self._items.get(key)
        if it is not None:
            it.setIcon(icon)

    def has_icon(self, key) -> bool:
        it = self._items.get(key)
        return it is not None and not it.icon().isNull()

    def keys(self) -> list:
        return [_key(run.item(i)) for run in self._lists for i in range(run.count())]

    def selected_keys(self) -> list:
        """The selected pages' keys, in strip order."""
        return [_key(run.item(i)) for run in self._lists for i in range(run.count())
                if run.item(i).isSelected()]

    def select_keys(self, keys):
        keys = set(keys)
        for k, it in self._items.items():
            it.setSelected(k in keys)

    def set_veiled(self, keys):
        """Veil the pages *keys* (left out), as Split veils pages in no part."""
        keys = set(keys)
        for k, it in self._items.items():
            it.setData(PART_ROLE, 0 if k in keys else None)
        for run in self._lists:
            run.viewport().update()

    def _selection_changed(self):
        if self._on_selection is not None:
            self._on_selection()


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
        top = QHBoxLayout()
        top.addWidget(StrongBodyLabel(title))
        self.detail_info = None
        if desc:                    # the description by an "i", as every row's
            self.detail_info = info_button(title, desc, within=box)
            top.addWidget(self.detail_info, 0, Qt.AlignVCenter)
        top.addStretch(1)
        bv.addLayout(top)
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
