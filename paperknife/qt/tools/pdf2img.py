"""PDF → Images — the chosen pages as PNGs, bundled in a ZIP.  The pages are on
screen (owner, 2026-10-17: the page-range tools show the document's pages);
the options sit in the column at the right."""
from __future__ import annotations

from pathlib import Path

from ...core import convert as core_convert
from ...pages import selected_pages
from ...prefs import pref_dpi
from ..pages import PagePickPage, card, group_title, labelled_slider, register_page

DPI_RANGE = (72, 300)


@register_page("Pdf2ImgTool")
class Pdf2ImgPage(PagePickPage):
    def __init__(self, tool=None, window=None):
        super().__init__("PDF → Images", "Export the chosen pages as PNGs · bundled in a ZIP",
                         tool=tool, window=window)
        s = self.settings
        s.addWidget(group_title("Options"))
        group = card(padding=0)
        s.addWidget(group)
        row = self.setting_row(group, "Resolution (DPI)",
                               "72=screen  ·  150=standard  ·  300=print quality")
        self.dpi_slider = labelled_slider(row, *DPI_RANGE, pref_dpi(*DPI_RANGE), " DPI",
                                          width=120, fixed=False)
        self.dpi_label = self.dpi_slider.value_label
        s.addWidget(group_title("Pages"))
        pages = card(padding=0)
        s.addWidget(pages)
        self.setting_row(pages, "Apply to", "or click the pages").layout().addWidget(
            self.make_range_field(width=140))
        s.addStretch(1)
        self.primary("Export as ZIP", self.run)

    @property
    def dpi(self) -> int:
        return int(self.dpi_slider.value())

    def run(self):
        src = self.chosen_file("Export")
        if not src or self._doc is None:
            return
        dpi = self.dpi
        range_str = self.range_text()
        pages: list[int] = []

        def prepare(doc):
            pages[:] = selected_pages(range_str, len(doc))

        def work(doc, out, stop, progress):
            # PNG pages in a ZIP, written atomically.
            return core_convert.pdf_to_doc(doc, "PNG", out, stop, progress, dpi=dpi,
                                           pages=pages)

        self.run_on_file(
            "Export", work, "Exporting pages to PNG…",
            lambda _ok, out: ("success", f"✓  Exported {len(pages)} pages → {Path(out).name}",
                              "Done", f"Exported {len(pages)} pages to:\n{out}"),
            src=src, save=("pages.zip", ".zip", [("ZIP", "*.zip")]), prepare=prepare,
            open_doc=self.job_copy)
