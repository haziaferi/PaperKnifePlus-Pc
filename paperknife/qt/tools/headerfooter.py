"""Header / Footer — a single-file transform (group C): a line of text in a page margin."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from qfluentwidgets import ComboBox, LineEdit

from ...core import headerfooter as core_hf
from ...pages import selected_pages
from .. import dialogs
from ..pages import (ToolPage, card, file_card, group_title, muted_caption, radio_rows,
                     register_page, setting_row)

TOKENS = ("Use {page} for page number · {total} for total pages · "
          "{date} for today's date")
FONTS = [("helv", "Helvetica"), ("tiro", "Times Roman"), ("cour", "Courier")]
POSITIONS = [                       # the CTk grid, row by row
    ("top-left", "↖ Top left"), ("top-center", "↑ Top center"), ("top-right", "↗ Top right"),
    ("bottom-left", "↙ Bot left"), ("bottom-center", "↓ Bot center"),
    ("bottom-right", "↘ Bot right"),
]


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
        self.file = file_card()
        self.body.addWidget(self.file)
        self.body.addSpacing(16)

        self.body.addWidget(group_title("Position"))
        group = card(padding=0)
        self.body.addWidget(group)
        self.pos_group = radio_rows(group, [(v, label, "") for v, label in POSITIONS],
                                    "bottom-center", parent=self)
        self.positions = self.pos_group.buttons

        self.body.addWidget(group_title("Content"))
        group = card(padding=0)
        self.body.addWidget(group)
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
        row = setting_row(group, "Size")
        self.size = _field("10")
        row.layout().addWidget(self.size)
        row = setting_row(group, "Margin")
        self.margin = _field("20")
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
