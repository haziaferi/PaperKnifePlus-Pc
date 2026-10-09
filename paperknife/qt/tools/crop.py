"""Crop / Trim — a single-file transform (group C): cut margins off the crop box."""
from __future__ import annotations

from pathlib import Path

from qfluentwidgets import LineEdit, SwitchButton

from ...core import crop as core
from ...pages import selected_pages
from .. import dialogs
from ..pages import (Refusal, ToolPage, card, file_card, group_title, muted_caption,
                     register_page, setting_row)

# (key, row name) in the order the CTk tool lays out its cross of fields
EDGES = [("top", "Top"), ("left", "Left"), ("right", "Right"), ("bottom", "Bottom")]


def crop_report(cropped: int, wanted: int, out: str):
    """(role, status line) for a finished crop of *wanted* pages."""
    skipped = wanted - cropped
    note = (f" · {skipped} skipped (margins larger than the page)"
            if skipped else "")
    return ("warning" if skipped else "success",
            f"✓  Cropped {cropped} page(s){note} → {Path(out).name}")


@register_page("CropTool")
class CropPage(ToolPage):
    def __init__(self, tool=None, window=None):
        super().__init__("Crop / Trim",
                         "Adjust page crop box by specifying margins in points (1 pt = 0.353 mm)",
                         tool=tool, window=window)
        self.file = file_card()
        self.body.addWidget(self.file)
        self.body.addSpacing(16)

        self.body.addWidget(group_title("Margins to remove (in points)"))
        hint = muted_caption("Enter how much to cut from each edge.  "
                             "A4 = 595 × 842 pt  ·  Letter = 612 × 792 pt  ·  "
                             "72 pt = 1 inch = 25.4 mm")
        hint.setWordWrap(True)
        hint.setContentsMargins(0, 0, 0, 8)
        self.body.addWidget(hint)
        margins = card(padding=0)
        self.body.addWidget(margins)
        self.margins: dict[str, LineEdit] = {}
        for key, name in EDGES:
            e = LineEdit()
            e.setText("0")
            e.setFixedWidth(120)
            setting_row(margins, name).layout().addWidget(e)
            self.margins[key] = e

        self.body.addWidget(group_title("Pages"))
        pages = card(padding=0)
        self.body.addWidget(pages)
        self.page_range = LineEdit()
        self.page_range.setPlaceholderText("all  or  1-5, 8, 10-end")
        self.page_range.setMinimumWidth(220)
        setting_row(pages, "Apply to", "blank = all").layout().addWidget(self.page_range)
        self.reset = SwitchButton()
        self.reset.setOnText("")
        self.reset.setOffText("")
        self.reset.setChecked(False)
        setting_row(pages, "Reset to full media box first",
                    "undo previous crops").layout().addWidget(self.reset)
        self.body.addStretch(1)
        self.primary("Crop", self.run)

    def run(self):
        src = self.chosen_file("Crop")
        if not src:
            return
        try:
            margins = core.parse_margins(*(self.margins[k].text()
                                           for k in ("top", "right", "bottom", "left")))
        except ValueError as e:
            return dialogs.warning("Crop", str(e))
        range_str = self.page_range.text().strip()
        reset = self.reset.isChecked()
        pages: list[int] = []

        def prepare(doc):
            pages[:] = selected_pages(range_str, len(doc))
            if not core.croppable(doc, pages, margins, reset):
                raise Refusal("No page was cropped: the margins are larger "
                              "than every selected page.")

        def report(cropped, out):
            role, status = crop_report(cropped, len(pages), out)
            return role, status, "Done", f"Cropped PDF saved:\n{out}"

        self.run_on_file(
            "Crop", lambda doc, out, stop, _p: core.crop_pdf(doc, out, pages, margins, reset, stop),
            lambda: f"Cropping {len(pages)} page(s)…", report, src=src,
            save=("cropped.pdf", ".pdf", [("PDF", "*.pdf")]), prepare=prepare)
