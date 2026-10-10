"""
paperknife.qt.docui
The current document's controls (owner's decisions 2026-10-10): a row
directly under each single-input page's subtitle, at the page's left
margin, with the Open split control ("Open", the arrow listing the recent
files then "Browse…") and the document as a chip (its name, a clear x);
and DropTarget, the empty-state target a single-input page shows while it
has no document: clicking it opens the file dialog.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget
from qfluentwidgets import Action, BodyLabel, RoundMenu, SplitPushButton

from . import theme

FILE_GLYPH = 0xE8A5         # Segoe Fluent Icons: Document
CLEAR_GLYPH = 0xE711        # Cancel (x)
TARGET_H = 200              # the empty-state target's height in a page view
TARGET_FORM_H = 120         # ... at the top of a page body (owner, 2026-10-10)
OPEN_TEXT = "Open"
BROWSE_TEXT = "Browse…"
NO_DOCUMENT = "No document"
DROP_TEXT = "Drop a PDF here or click to choose one"
CLEAR_TIP = "Clear"
CHIP_NAME_MIN = 160          # the name's least room: twice the 80 px of before (owner)


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


class _ChipName:
    """The chip's name: it asks for its whole width, takes at least
    CHIP_NAME_MIN, and is shortened in the middle only when the row
    leaves it less than the whole name (ElidedLabel)."""

    def sizeHint(self):  # noqa: N802 (Qt naming)
        h = super().sizeHint()
        h.setWidth(max(CHIP_NAME_MIN, self.fontMetrics().horizontalAdvance(self.text()) + 2))
        return h

    def minimumSizeHint(self):  # noqa: N802
        h = super().minimumSizeHint()
        h.setWidth(CHIP_NAME_MIN)
        return h


class DocChip(_Rounded):
    """The document's name (whole when the row has room, else shortened in
    the middle; the full path in the tooltip) and a clear (x) button."""

    def __init__(self, window, parent=None):
        from .pages import ElidedLabel, icon_button

        class ChipName(_ChipName, ElidedLabel):
            pass
        super().__init__(parent)
        self.setObjectName("docChip")
        self.window_ = window
        h = QHBoxLayout(self)
        h.setContentsMargins(12, 0, 0, 0)
        h.setSpacing(4)
        self.name_label = ChipName("", self)
        self.name_label.setMinimumWidth(CHIP_NAME_MIN)
        self.name_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        h.addWidget(self.name_label, 1)
        self.clear_btn = icon_button(theme.Glyph(CLEAR_GLYPH))   # follows the theme
        self.clear_btn.setIconSize(QSize(12, 12))
        self.clear_btn.setToolTip(CLEAR_TIP)
        self.clear_btn.clicked.connect(
            lambda: window is not None and window.clear_current_document())
        h.addWidget(self.clear_btn)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

    def show_path(self, path: str):
        self.name_label.setText(Path(path).name if path else "")
        self.name_label.setToolTip(path)
        self.name_label.updateGeometry()
        self.setToolTip(path)
        self.setVisible(bool(path))

    def paintEvent(self, _e):
        p = QPainter(self)
        self._outline(p, QPen(theme.color("control_border"), 1), theme.color("control"))


class DocBar(QWidget):
    """The row under a page's subtitle, at its left margin."""

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
