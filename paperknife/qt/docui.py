"""
paperknife.qt.docui
The current document's controls, in one of two layouts chosen by env
PK_DOCUI (owner's decision 2026-10-10):

    nav   (default) a slot in the navigation pane directly under the search
          box.  With a document: one full-width drop-down button, the file
          icon and the name (shortened in the middle, the path in the
          tooltip); its menu is Browse…, the recent files, Clear.  With none:
          "No document" and the Open split control.  With the pane collapsed
          to its icon strip: a 40x40 file icon button with the same menu.
    bar   a row directly under each single-input page's subtitle: the Open
          split control, then the document as a chip (name, x).

Both share OpenControl ("Open", the arrow listing the recent files then
"Browse…") and DropTarget, the empty-state target a single-input page shows
while it has no document: clicking it opens the file dialog.
"""
from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QPoint, QRectF, QSize, Qt
from PySide6.QtGui import QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget
from qfluentwidgets import (Action, BodyLabel, RoundMenu, SplitPushButton,
                            TransparentDropDownPushButton, TransparentToolButton)
from qfluentwidgets.components.navigation.navigation_widget import NavigationWidget

from . import theme

FILE_GLYPH = 0xE8A5         # Segoe Fluent Icons: Document
CLEAR_GLYPH = 0xE711        # Cancel (x)
SLOT_H = 40                 # Fluent navigation item height (the brief's)
TARGET_H = 200              # the empty-state target's height in a page view
TARGET_FORM_H = 120         # ... at the top of a page body (owner, 2026-10-10)
OPEN_TEXT = "Open"
BROWSE_TEXT = "Browse…"
NO_DOCUMENT = "No document"
DROP_TEXT = "Drop a PDF here or click to choose one"
CLEAR_TIP = "Clear"
CLEAR_TEXT = "Clear"


def layout() -> str:
    """"nav" (the default) or "bar", from env PK_DOCUI."""
    v = os.environ.get("PK_DOCUI", "nav").strip().lower()
    return v if v in ("nav", "bar") else "nav"


def recent_paths() -> list[str]:
    """The recent files, newest first (paperknife.recent.RECENT)."""
    from ..recent import RECENT
    return [e["path"] for e in RECENT.all()]


def open_menu(window, parent=None) -> RoundMenu:
    """The Open control's list: the recent files, then Browse…."""
    menu = RoundMenu(parent=parent)
    paths = recent_paths()
    for p in paths:
        a = Action(Path(p).name, menu)
        a.setToolTip(p)
        a.pk_path = p
        a.triggered.connect(lambda _=False, p=p: window is not None and window.open_document(p))
        menu.addAction(a)
    if paths:
        menu.addSeparator()
    b = Action(BROWSE_TEXT, menu)
    b.pk_path = None
    b.triggered.connect(lambda _=False: window is not None and window.browse_document())
    menu.addAction(b)
    return menu


class OpenControl(SplitPushButton):
    """"Open v": the main part opens the file dialog, the arrow lists the
    recent files, then Browse…."""

    def __init__(self, window, parent=None):
        super().__init__(parent)
        self.setText(OPEN_TEXT)
        self.setObjectName("openControl")
        self.window_ = window
        self.clicked.connect(lambda: window is not None and window.browse_document())
        # dropDownClicked is emitted before showFlyout: the list is read fresh.
        self.dropDownClicked.connect(self._rebuild)

    def menu(self) -> RoundMenu:
        """A fresh copy of the list (what the arrow shows)."""
        return open_menu(self.window_, self)

    def _rebuild(self):
        old = self.flyout
        self.setFlyout(self.menu())
        if old is not None:
            old.deleteLater()


class _Rounded(QWidget):
    """A widget that draws its own rounded outline."""
    radius = 4

    def _outline(self, p: QPainter, pen: QPen, fill=None):
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(pen)
        p.setBrush(fill if fill is not None else Qt.NoBrush)
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5),
                          self.radius, self.radius)


class DocChip(_Rounded):
    """bar layout: the document's name (elided in the middle, full path in the
    tooltip) and a clear (x) button."""

    def __init__(self, window, parent=None):
        from .pages import ElidedLabel, icon_button
        super().__init__(parent)
        self.setObjectName("docChip")
        self.window_ = window
        h = QHBoxLayout(self)
        h.setContentsMargins(12, 0, 0, 0)
        h.setSpacing(4)
        self.name_label = ElidedLabel("", self)
        self.name_label.setMinimumWidth(80)
        h.addWidget(self.name_label, 1)
        self.clear_btn = icon_button(theme.Glyph(CLEAR_GLYPH))   # follows the theme
        self.clear_btn.setIconSize(QSize(12, 12))
        self.clear_btn.setToolTip(CLEAR_TIP)
        self.clear_btn.clicked.connect(
            lambda: window is not None and window.clear_current_document())
        h.addWidget(self.clear_btn)
        self.setMaximumWidth(360)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

    def show_path(self, path: str):
        self.name_label.setText(Path(path).name if path else "")
        self.name_label.setToolTip(path)
        self.setToolTip(path)
        self.setVisible(bool(path))

    def paintEvent(self, _e):
        p = QPainter(self)
        self._outline(p, QPen(theme.color("control_border"), 1), theme.color("control"))


class DocBar(QWidget):
    """bar layout: the row under a page's subtitle, at its left margin."""

    def __init__(self, window, parent=None):
        super().__init__(parent)
        self.setObjectName("docBar")
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 8, 0, 0)
        h.setSpacing(8)
        self.open_control = OpenControl(window, self)
        h.addWidget(self.open_control, 0, Qt.AlignLeft | Qt.AlignVCenter)
        self.chip = DocChip(window, self)
        self.chip.setFixedHeight(32)
        h.addWidget(self.chip, 0, Qt.AlignLeft | Qt.AlignVCenter)
        h.addStretch(1)
        self.chip.show_path("")

    def show_path(self, path: str):
        self.chip.show_path(path)


class DropTarget(_Rounded):
    """The empty-state target: the width of the body, *height* tall, a dashed
    1 px border in the control-border role (palettes "input_underline"),
    rounded 4 px, "Drop a PDF here or click to choose one" centred in it.
    The whole target is the button: a click (or Enter / Space) opens the
    file dialog; under the pointer it takes the hover tint (palettes
    "tint_hover").  Drops reach the page through the window
    (MainWindow.dropEvent)."""

    def __init__(self, window, parent=None, height: int = TARGET_H):
        super().__init__(parent)
        self.setObjectName("dropTarget")
        self.window_ = window
        self.setFixedHeight(height)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAccessibleName(DROP_TEXT)
        self.hovered = False
        v = QVBoxLayout(self)
        v.setContentsMargins(16, 16, 16, 16)
        self.label = BodyLabel(DROP_TEXT, self)
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        v.addWidget(self.label, 1, Qt.AlignCenter)

    def choose(self):
        if self.window_ is not None:
            self.window_.browse_document()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.rect().contains(e.position().toPoint()):
            self.choose()
            e.accept()
            return
        super().mouseReleaseEvent(e)

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.choose()
            return
        super().keyPressEvent(e)

    def enterEvent(self, e):
        self.hovered = True
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.hovered = False
        self.update()
        super().leaveEvent(e)

    def paintEvent(self, _e):
        p = QPainter(self)
        pen = QPen(theme.color("input_underline"), 1)
        pen.setStyle(Qt.DashLine)
        self._outline(p, pen, theme.color("tint_hover") if self.hovered else None)


def slot_menu(window, parent=None) -> RoundMenu:
    """The nav slot's list (and the collapsed button's): Browse…, the recent
    files newest first (the current one left out), then Clear while there is
    a current document."""
    from .pages import same_path
    menu = RoundMenu(parent=parent)
    b = Action(BROWSE_TEXT, menu)
    b.pk_path = None
    b.triggered.connect(lambda _=False: window.browse_document())
    menu.addAction(b)
    cur = window.current_document
    paths = [p for p in recent_paths() if not same_path(p, cur)]
    if paths:
        menu.addSeparator()
    for p in paths:
        a = Action(Path(p).name, menu)
        a.setToolTip(p)
        a.pk_path = p
        a.triggered.connect(lambda _=False, p=p: window.open_document(p))
        menu.addAction(a)
    if cur:
        menu.addSeparator()
        c = Action(CLEAR_TEXT, menu)
        c.pk_path = None
        c.triggered.connect(lambda _=False: window.clear_current_document())
        menu.addAction(c)
    return menu


class DocButton(TransparentDropDownPushButton):
    """nav slot with a document: one full-width drop-down button, the file
    icon and the name shortened in the middle to the room there is (the
    full path in the tooltip); its menu is slot_menu, read fresh each time."""

    def __init__(self, window, parent=None):
        super().__init__(parent)
        self.setObjectName("docButton")
        self.window_ = window
        self.setIcon(theme.Glyph(FILE_GLYPH))
        self._name = ""

    def set_name(self, name: str):
        self._name = name
        self._fit()

    def name(self) -> str:
        return self._name

    def room(self) -> int:
        """The width the name gets: the button's contents, i.e. less the style
        sheet's paddings (the icon at the left, the arrow at the right)."""
        from PySide6.QtWidgets import QStyle, QStyleOptionButton
        opt = QStyleOptionButton()
        self.initStyleOption(opt)
        r = self.style().subElementRect(QStyle.SE_PushButtonContents, opt, self)
        return max(1, r.width() - 2)

    def _fit(self):
        self.setText(self.fontMetrics().elidedText(self._name, Qt.ElideMiddle, self.room()))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._fit()

    def _showMenu(self):
        old = self.menu()
        self.setMenu(slot_menu(self.window_, self))
        if old is not None:
            old.deleteLater()
        super()._showMenu()


class DocSlot(NavigationWidget):
    """nav layout: the navigation pane's slot under the search box.  With a
    document: DocButton across the slot.  With none: "No document" and the
    Open split control.  Collapsed: a 40x40 file icon button with
    slot_menu."""

    def __init__(self, window, parent=None):
        super().__init__(isSelectable=False, parent=parent)
        self.window_ = window
        self.empty_row = QWidget(self)
        h = QHBoxLayout(self.empty_row)
        h.setContentsMargins(12, 0, 0, 0)           # in line with the items' icons
        h.setSpacing(4)
        self.name_label = BodyLabel(NO_DOCUMENT, self.empty_row)
        h.addWidget(self.name_label, 0, Qt.AlignVCenter)
        h.addStretch(1)
        self.open_control = OpenControl(window, self.empty_row)
        h.addWidget(self.open_control, 0, Qt.AlignVCenter)
        self.doc_button = DocButton(window, self)
        # collapsed: the file icon button whose menu is the same list
        self.compact_btn = TransparentToolButton(theme.Glyph(FILE_GLYPH), self)
        self.compact_btn.setFixedSize(SLOT_H, SLOT_H)
        self.compact_btn.clicked.connect(self._show_compact_menu)
        self._menu = None
        self.setCompacted(True)
        window.current_document_changed.connect(lambda _p: self.refresh())
        self.refresh()

    def setCompacted(self, isCompacted: bool):  # noqa: N802,N803 (Qt naming)
        self.isCompacted = isCompacted
        if isCompacted:
            self.setFixedSize(SLOT_H, SLOT_H)
        else:
            self.setFixedSize(self.EXPAND_WIDTH, SLOT_H)
        self.refresh()
        self.update()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._fit()

    def _fit(self):
        self.empty_row.setGeometry(0, 0, self.width(), self.height())
        h = self.doc_button.sizeHint().height()
        self.doc_button.setGeometry(0, (self.height() - h) // 2, self.width(), h)
        self.compact_btn.move(0, 0)

    def refresh(self):
        path = self.window_.current_document or ""
        name = Path(path).name if path else ""
        wide = not self.isCompacted
        self.empty_row.setVisible(wide and not path)
        self.doc_button.setVisible(wide and bool(path))
        self.compact_btn.setVisible(not wide)
        self.doc_button.set_name(name)
        self.doc_button.setToolTip(path)
        self.compact_btn.setToolTip(name or NO_DOCUMENT)
        self.setToolTip(path)
        self._fit()

    def compact_menu(self) -> RoundMenu:
        """What the collapsed button shows (the slot's list)."""
        return slot_menu(self.window_, self)

    def _show_compact_menu(self):
        if self._menu is not None:
            self._menu.deleteLater()
        self._menu = self.compact_menu()
        self._menu.exec(self.compact_btn.mapToGlobal(QPoint(self.compact_btn.width(), 0)))

    def paintEvent(self, e):
        pass                            # its children draw it
