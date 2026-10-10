"""
paperknife.qt.docui
The current document's controls, in one of two layouts chosen by env
PK_DOCUI (owner's decision 2026-10-10):

    nav   (default) a slot in the navigation pane directly under the search
          box: the current document's file icon and name, a clear (x) and the
          Open split control; "No document" + Open when there is none.  With
          the pane collapsed to its icon strip it is a 40x40 file icon button
          whose menu is the same list.
    bar   a row directly under each single-input page's subtitle: the Open
          split control, then the document as a chip (name, x).

Both share OpenControl ("Open", the arrow listing the recent files then
"Browse…") and DropTarget, the empty-state target a single-input page shows
while it has no document.
"""
from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QPoint, QRectF, Qt
from PySide6.QtGui import QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget
from qfluentwidgets import (Action, BodyLabel, IconWidget, RoundMenu, SplitPushButton,
                            TransparentToolButton)
from qfluentwidgets.components.navigation.navigation_widget import NavigationWidget

from . import theme

FILE_GLYPH = 0xE8A5         # Segoe Fluent Icons: Document
CLEAR_GLYPH = 0xE711        # Cancel (x)
SLOT_H = 40                 # Fluent navigation item height (the brief's)
TARGET_H = 200              # the empty-state target's height
OPEN_TEXT = "Open"
BROWSE_TEXT = "Browse…"
NO_DOCUMENT = "No document"
DROP_TEXT = "Drop a PDF here"
CLEAR_TIP = "Clear"


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
        self.clear_btn = icon_button(theme.glyph_icon(CLEAR_GLYPH, 12))
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
    """The empty-state target: the width of the body, TARGET_H tall, a dashed
    1 px border in the control-border role (palettes "input_underline"),
    rounded 4 px, "Drop a PDF here" and the Open control centred in it.
    Drops reach the page through the window (MainWindow.dropEvent)."""

    def __init__(self, window, parent=None):
        super().__init__(parent)
        self.setObjectName("dropTarget")
        self.setFixedHeight(TARGET_H)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        v = QVBoxLayout(self)
        v.setContentsMargins(16, 16, 16, 16)
        v.setSpacing(12)
        v.addStretch(1)
        self.label = BodyLabel(DROP_TEXT, self)
        self.label.setAlignment(Qt.AlignCenter)
        v.addWidget(self.label, 0, Qt.AlignHCenter)
        self.open_control = OpenControl(window, self)
        v.addWidget(self.open_control, 0, Qt.AlignHCenter)
        v.addStretch(1)

    def paintEvent(self, _e):
        p = QPainter(self)
        pen = QPen(theme.color("input_underline"), 1)
        pen.setStyle(Qt.DashLine)
        self._outline(p, pen)


class DocSlot(NavigationWidget):
    """nav layout: the navigation pane's slot under the search box."""

    def __init__(self, window, parent=None):
        from .pages import ElidedLabel, icon_button
        super().__init__(isSelectable=False, parent=parent)
        self.window_ = window
        self.row = QWidget(self)
        h = QHBoxLayout(self.row)
        h.setContentsMargins(12, 0, 0, 0)           # the icon in line with the items' icons
        h.setSpacing(4)
        self.icon = IconWidget(theme.Glyph(FILE_GLYPH), self.row)
        self.icon.setFixedSize(16, 16)
        h.addWidget(self.icon, 0, Qt.AlignVCenter)
        self.name_label = ElidedLabel(NO_DOCUMENT, self.row)
        h.addWidget(self.name_label, 1, Qt.AlignVCenter)
        self.clear_btn = icon_button(theme.glyph_icon(CLEAR_GLYPH, 12))
        self.clear_btn.setParent(self.row)
        self.clear_btn.setToolTip(CLEAR_TIP)
        self.clear_btn.clicked.connect(lambda: window.clear_current_document())
        h.addWidget(self.clear_btn, 0, Qt.AlignVCenter)
        self.open_control = OpenControl(window, self.row)
        h.addWidget(self.open_control, 0, Qt.AlignVCenter)
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
        self.row.setVisible(not isCompacted)
        self.compact_btn.setVisible(isCompacted)
        self._fit()
        self.update()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._fit()

    def _fit(self):
        self.row.setGeometry(0, 0, self.width(), self.height())
        self.compact_btn.move(0, 0)

    def refresh(self):
        path = self.window_.current_document or ""
        name = Path(path).name if path else ""
        self.icon.setVisible(bool(path))
        self.clear_btn.setVisible(bool(path))
        self.name_label.setText(name or NO_DOCUMENT)
        self.name_label.setToolTip(path)
        self.compact_btn.setToolTip(name or NO_DOCUMENT)
        self.setToolTip(path)

    def compact_menu(self) -> RoundMenu:
        """What the collapsed button shows (the Open control's list)."""
        return open_menu(self.window_, self)

    def _show_compact_menu(self):
        if self._menu is not None:
            self._menu.deleteLater()
        self._menu = self.compact_menu()
        self._menu.exec(self.compact_btn.mapToGlobal(QPoint(self.compact_btn.width(), 0)))

    def paintEvent(self, e):
        pass                            # its children draw it
