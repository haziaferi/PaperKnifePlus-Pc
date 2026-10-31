"""Header / Footer — a line of text in a page margin of the selected pages.  The
pages are on screen (owner, 2026-10-17: the page-range tools show the
document's pages); the options sit in the column at the right."""
from __future__ import annotations

from datetime import date

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QPainter, QPen
from PySide6.QtWidgets import QGridLayout, QWidget
from qfluentwidgets import ComboBox, LineEdit

from ...core import headerfooter as core_hf
from ...pages import selected_pages
from .. import dialogs, theme
from ..pages import (APPLY, SAVE_NOTE, PagePickPage, RadioChoice, card, group_title, muted_caption,
                     radio_button, register_page)

TOKENS = ("Use {page} for page number · {total} for total pages · "
          "{date} for today's date")
FONTS = [("helv", "Helvetica"), ("tiro", "Times Roman"), ("cour", "Courier")]
POSITIONS = [                       # row by row: the page's top edge, then its bottom
    ("top-left", "Top left"), ("top-center", "Top centre"), ("top-right", "Top right"),
    ("bottom-left", "Bottom left"), ("bottom-center", "Bottom centre"),
    ("bottom-right", "Bottom right"),
]
PAGE_W, PAGE_H = 112, 136           # the page outline: three 32 px radios 4 px apart, portrait


class PageOutline(QWidget):
    """A page drawn as a rounded outline in the control border colour."""

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(theme.color("input_underline"), 1))
        p.setBrush(theme.color("control"))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 4, 4)


def position_picker(default: str, parent=None) -> tuple[QWidget, RadioChoice]:
    """A page outline with a radio button at each of the six places the text
    can go: three along the top edge, three along the bottom."""
    page = PageOutline()
    page.setFixedSize(PAGE_W, PAGE_H)
    grid = QGridLayout(page)
    grid.setContentsMargins(4, 4, 4, 4)
    grid.setSpacing(4)
    grid.setRowStretch(1, 1)
    choice = RadioChoice(parent)
    for i, (value, label) in enumerate(POSITIONS):
        rb = radio_button()
        rb.setToolTip(label)
        rb.setAccessibleName(label)
        rb.setChecked(value == default)
        choice.addButton(rb)
        choice.buttons[value] = rb
        col = i % 3
        align = (Qt.AlignLeft, Qt.AlignHCenter, Qt.AlignRight)[col]
        grid.addWidget(rb, 0 if i < 3 else 2, col, align)
    return page, choice


def _field(text: str = "", width: int = 72, placeholder: str = "") -> LineEdit:
    e = LineEdit()
    e.setText(text)
    if placeholder:
        e.setPlaceholderText(placeholder)
    e.setFixedWidth(width)
    return e


@register_page("HeaderFooterTool")
class HeaderFooterPage(PagePickPage):
    def __init__(self, tool=None, window=None):
        super().__init__("Header / Footer",
                         "Stamp text into the top or bottom margin of the selected pages",
                         tool=tool, window=window)
        s = self.settings
        s.addWidget(group_title("Content"))
        group = card(padding=0)
        s.addWidget(group)
        row = self.setting_row(group, "Position", "Where the text goes on each page")
        picker, self.pos_group = position_picker("bottom-center", parent=self)
        row.layout().addWidget(picker)
        self.positions = self.pos_group.buttons
        row = self.setting_row(group, "Content", TOKENS)
        self.content = _field("Page {page} of {total}", width=170)
        row.layout().addWidget(self.content)

        s.addWidget(group_title("Style"))
        group = card(padding=0)
        s.addWidget(group)
        row = self.setting_row(group, "Font")
        self.font = ComboBox()
        self.font.addItems([label for _f, label in FONTS])
        self.font.setCurrentText("Helvetica")
        self.font.setMinimumWidth(140)
        row.layout().addWidget(self.font)
        # One field per row (owner, 2026-10-31: one width for a card's fields; two
        # side by side were squeezed to 96 px).
        row = self.setting_row(group, "Font size")
        self.size = _field("10", width=56)
        self.size.setAccessibleName("Size")
        row.layout().addWidget(self.size)
        row.layout().addWidget(muted_caption("pt"))
        row = self.setting_row(group, "Margin")
        self.margin = _field("20", width=56)
        self.margin.setAccessibleName("Margin")
        row.layout().addWidget(self.margin)
        row.layout().addWidget(muted_caption("pt"))

        s.addWidget(group_title("Pages"))
        group = card(padding=0)
        s.addWidget(group)
        self.setting_row(group, "Apply to", "or click the pages").layout().addWidget(
            self.make_range_field(width=140))
        s.addStretch(1)
        self.primary(APPLY, self.run)

    @property
    def pos(self) -> str:
        return self.pos_group.value()

    @property
    def font_name(self) -> str:
        return FONTS[self.font.currentIndex()][0]

    def run(self):
        src = self.chosen_file("Header/Footer")
        if not src or self._doc is None:
            return
        template = self.content.text().strip()
        if not template:
            return dialogs.warning("Header/Footer", "Enter content text.")
        pos, font = self.pos, self.font_name
        try:
            size, margin = core_hf.parse_style(self.size.text(), self.margin.text())
        except ValueError as e:
            return dialogs.warning("Header/Footer", str(e))
        range_str = self.range_text()
        today = date.today().strftime("%Y-%m-%d")

        pages: list[int] = []

        def prepare(doc):
            pages[:] = selected_pages(range_str, len(doc))

        def work(doc, out, stop, progress):
            self._release(out)              # over the open file: let it go first
            return core_hf.stamp_pdf(doc, out, pages, template, pos, font, size, margin,
                                     today, stop)

        self.run_on_file(
            "Header/Footer", work, lambda: f"Stamping {len(pages)} page(s)…", None, src=src,
            prepare=prepare, open_doc=self.job_copy, in_place="Header / Footer",
            applied=lambda _r: ("success", f"✓  Stamped {len(pages)} page(s)" + SAVE_NOTE,
                                None, True))
