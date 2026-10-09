"""PDF → Images — every page as a PNG, bundled in a ZIP (group C)."""
from __future__ import annotations

from pathlib import Path

from ...core import convert as core_convert
from ...prefs import pref_dpi
from ..pages import (ToolPage, card, file_card, group_title, labelled_slider, register_page,
                     setting_row)

DPI_RANGE = (72, 300)


@register_page("Pdf2ImgTool")
class Pdf2ImgPage(ToolPage):
    def __init__(self, tool=None, window=None):
        super().__init__("PDF → Images", "Export every page as a PNG · bundled in a ZIP",
                         tool=tool, window=window)
        self.file = file_card()
        self.body.addWidget(self.file)
        self.body.addSpacing(16)
        self.body.addWidget(group_title("Options"))
        group = card(padding=0)
        self.body.addWidget(group)
        row = setting_row(group, "Resolution (DPI)",
                          "72=screen  ·  150=standard  ·  300=print quality")
        self.dpi_slider = labelled_slider(row, *DPI_RANGE, pref_dpi(*DPI_RANGE), " DPI")
        self.dpi_label = self.dpi_slider.value_label
        self.body.addStretch(1)
        self.primary("Export as ZIP", self.run)

    @property
    def dpi(self) -> int:
        return int(self.dpi_slider.value())

    def run(self):
        src = self.chosen_file("Export")
        if not src:
            return
        dpi = self.dpi
        total = [0]

        def prepare(doc):
            total[0] = len(doc)

        def work(doc, out, stop, progress):
            # PNG pages in a ZIP, written atomically.
            return core_convert.pdf_to_doc(doc, "PNG", out, stop, progress, dpi=dpi)

        self.run_on_file(
            "Export", work, "Exporting pages to PNG…",
            lambda _ok, out: ("success", f"✓  Exported {total[0]} pages → {Path(out).name}",
                              "Done", f"Exported {total[0]} pages to:\n{out}"),
            src=src, save=("pages.zip", ".zip", [("ZIP", "*.zip")]), prepare=prepare,
            working="Exporting pages…")
