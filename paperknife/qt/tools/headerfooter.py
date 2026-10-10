"""Header / Footer — a single-file transform (group C): a line of text in a page margin."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QPainter, QPen
from PySide6.QtWidgets import QGridLayout, QWidget
from qfluentwidgets import ComboBox, LineEdit

from ...core import headerfooter as core_hf
from ...pages import selected_pages
from .. import dialogs, theme
from ..pages import (RadioChoice, ToolPage, card, group_title, muted_caption,
                     radio_button, register_page, setting_row)

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
class HeaderFooterPage(ToolPage):
    def __init__(self, tool=None, window=None):
        super().__init__("Header / Footer",
                         "Stamp text into the top or bottom margin of every page",
                         tool=tool, window=window)
        self.doc_input()
        self.body.addSpacing(16)

        self.body.addWidget(group_title("Content"))
        group = card(padding=0)
        self.body.addWidget(group)
        row = setting_row(group, "Position", "Where the text goes on every page")
        picker, self.pos_group = position_picker("bottom-center", parent=self)
        row.layout().addWidget(picker)
        self.positions = self.pos_group.buttons
        row = setting_row(group, "Content", TOKENS)
        self.content = _field("Page {page} of {total}", width=260)
        row.layout().addWidget(self.content)

        self.body.addWidget(group_title("Style"))
        group = card(padding=0)
        self.body.addWidget(group)
        row = setting_row(group, "Font")
        self.font = ComboBox()
        self.font.addItems([label for _f, label in FONTS])
        self.font.setCurrentText("Helvetica")
        self.font.setMinimumWidth(150)
        row.layout().addWidget(self.font)
        row = setting_row(group, "Size and margin")
        self.size = _field("10")
        self.size.setAccessibleName("Size")
        row.layout().addWidget(self.size)
        row.layout().addWidget(muted_caption("pt"))
        row.layout().addSpacing(8)
        self.margin = _field("20")
        self.margin.setAccessibleName("Margin")
        row.layout().addWidget(self.margin)
        row.layout().addWidget(muted_caption("pt"))

        self.body.addWidget(group_title("Pages"))
        group = card(padding=0)
        self.body.addWidget(group)
        row = setting_row(group, "Apply to pages", "blank = all pages")
        self.page_range = _field(width=180, placeholder="all  or  1-5, 8, 10-end")
        row.layout().addWidget(self.page_range)

        self.body.addStretch(1)
        self.primary("Apply Header / Footer", self.run)

    @property
    def pos(self) -> str:
        return self.pos_group.value()

    @property
    def font_name(self) -> str:
        return FONTS[self.font.currentIndex()][0]

    def run(self):
        src = self.chosen_file("Header/Footer")
        if not src:
            return
        template = self.content.text().strip()
        if not template:
            return dialogs.warning("Header/Footer", "Enter content text.")
        pos, font = self.pos, self.font_name
        try:
            size, margin = core_hf.parse_style(self.size.text(), self.margin.text())
        except ValueError as e:
            return dialogs.warning("Header/Footer", str(e))
        range_str = self.page_range.text().strip()
        today = date.today().strftime("%Y-%m-%d")

        pages: list[int] = []

        def prepare(doc):
            pages[:] = selected_pages(range_str, len(doc))

        def work(doc, out, stop, progress):
            return core_hf.stamp_pdf(doc, out, pages, template, pos, font, size, margin,
                                     today, stop)

        self.run_on_file(
            "Header/Footer", work, lambda: f"Stamping {len(pages)} page(s)…",
            lambda _r, out: ("success", f"✓  Stamped {len(pages)} page(s) → {Path(out).name}",
                             "Done", f"PDF with header/footer saved:\n{out}"),
            src=src, save=("stamped.pdf", ".pdf", [("PDF", "*.pdf")]), prepare=prepare)
