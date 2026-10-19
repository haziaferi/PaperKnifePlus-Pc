"""PDF → Other — the selected pages to TXT, HTML, XML, RTF, DOCX, PPTX, XLSX or
page images (PDF → Doc / Text, with PDF → Images folded in: owner, 2026-10-18).
The pages are on screen (owner, 2026-10-17: the page-range tools show the
document's pages); the options sit in the column at the right."""
from __future__ import annotations

from pathlib import Path

from ...core import convert as core_convert
from ...pages import selected_pages
from ..pages import PagePickPage, card, group_title, register_page
from ..tool_options import DPI_FORMATS, OTHER_INFO as INFO, OtherOptions  # noqa: F401

# format -> (extension, save-dialog filter name, default file name)
OUT = {
    "TXT":  (".txt",  "Text File",      "output.txt"),
    "HTML": (".html", "HTML File",      "output.html"),
    "XML":  (".xml",  "XML File",       "output.xml"),
    "RTF":  (".rtf",  "RTF File",       "output.rtf"),
    "DOCX": (".docx", "Word Document",  "output.docx"),
    "PPTX": (".pptx", "PowerPoint",     "output.pptx"),
    "XLSX": (".xlsx", "Excel Workbook", "output.xlsx"),
    "PNG":  (".zip",  "ZIP of PNGs",    "pages_png.zip"),
    "JPEG": (".zip",  "ZIP of JPEGs",   "pages_jpeg.zip"),
}


@register_page("Pdf2DocTool")
class Pdf2DocPage(PagePickPage):
    def __init__(self, tool=None, window=None):
        super().__init__(
            "PDF → Other",
            "Export the selected pages to TXT · HTML · DOCX · PPTX · XLSX · XML · RTF · PNG · JPEG",
            tool=tool, window=window)
        s = self.settings
        o = self.opts = OtherOptions(s, self.setting_row, parent=self)
        self.fmt, self.fmt_info, self.missing = o.fmt, o.fmt_info, o.missing
        self.image_title, self.image_card = o.image_title, o.image_card
        self.dpi_slider, self.quality_slider = o.dpi_slider, o.quality_slider
        self.quality_row, self._quality_divider = o.quality_row, o._quality_divider

        s.addWidget(group_title("Pages"))
        pages = card(padding=0)
        s.addWidget(pages)
        self.setting_row(pages, "Apply to", "or click the pages").layout().addWidget(
            self.make_range_field(width=140))
        s.addStretch(1)
        self.primary("Convert PDF", self.run)

    # ── options (the panel's) ──
    def _fmt_changed(self, fmt: str):
        self.opts.fmt_changed(fmt)

    @property
    def format(self) -> str:
        return self.opts.format

    def options(self) -> tuple[int, int]:
        """(dpi, quality) for the conversion: the slider values when
        the format shows them, else 150 and 92."""
        return self.opts.dpi_quality()

    # ── actions ──
    def run(self):
        src = self.chosen_file("Convert")
        if not src or self._doc is None:
            return
        fmt = self.format
        ext, desc, default = OUT[fmt]
        dpi, quality = self.options()
        range_str = self.range_text()
        pages: list[int] = []

        def prepare(doc):
            pages[:] = selected_pages(range_str, len(doc))

        def work(doc, out, stop, progress):
            return core_convert.pdf_to_doc(doc, fmt, out, stop, progress,
                                           dpi=dpi, quality=quality, pages=pages)

        self.run_on_file(
            "Convert", work, f"Converting PDF → {fmt}…",
            lambda _ok, out: ("success", f"✓  PDF → {fmt}: {Path(out).name}",
                              "Done", f"Saved:\n{out}"),
            src=src, save=(default, ext, [(desc, f"*{ext}"), ("All", "*.*")]), prepare=prepare,
            open_doc=self.job_copy)
