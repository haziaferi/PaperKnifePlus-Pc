"""Header / Footer — a single-file transform (group C): a line of text in a page margin."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from PySide6.QtWidgets import QButtonGroup
from qfluentwidgets import ComboBox, LineEdit, RadioButton

from ...core import headerfooter as core_hf
from ...pages import PageRangeError, selected_pages
from .. import dialogs
from ..pages import (ToolPage, card, file_card, group_title, muted_caption, register_page,
                     setting_row)

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
        self.pos_group = QButtonGroup(self)
        self.positions: dict[str, RadioButton] = {}
        for val, label in POSITIONS:
            holder = setting_row(group, label)
            rb = RadioButton("")
            rb.setChecked(val == "bottom-center")
            self.pos_group.addButton(rb)
            holder.layout().addWidget(rb)
            self.positions[val] = rb

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
        return next(v for v, rb in self.positions.items() if rb.isChecked())

    @property
    def font_name(self) -> str:
        return FONTS[self.font.currentIndex()][0]

    def open(self):
        self.file.choose()

    def run(self):
        src = self.file.path()
        if not src:
            return dialogs.warning("Header/Footer", "Select a PDF first.")
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

        win = self.window_
        doc = win.open_pdf_safe(src)
        if doc is None:
            return
        try:
            pages = selected_pages(range_str, len(doc))
        except PageRangeError as e:
            doc.close()
            return dialogs.error("Header/Footer", str(e))
        out = dialogs.ask_save("stamped.pdf", ".pdf", [("PDF", "*.pdf")])
        if not out:
            return doc.close()

        def work(stop):
            return core_hf.stamp_pdf(doc, out, pages, template, pos, font, size, margin,
                                     today, stop)

        def then(kind, result):
            if kind != "done" or not result:
                return
            win.set_status(f"✓  Stamped {len(pages)} page(s) → {Path(out).name}", "success")
            dialogs.info("Done", f"PDF with header/footer saved:\n{out}")

        if win.run_job(work, f"Stamping {len(pages)} page(s)…", then=then) is None:
            doc.close()
