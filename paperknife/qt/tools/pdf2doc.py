"""PDF → Other — the selected pages to TXT, HTML, XML, RTF, DOCX, PPTX, XLSX or
page images (PDF → Doc / Text, with PDF → Images folded in: owner, 2026-10-18).
The pages are on screen (owner, 2026-10-17: the page-range tools show the
document's pages); the options sit in the column at the right."""
from __future__ import annotations

from pathlib import Path

from qfluentwidgets import CaptionLabel, ComboBox

from ...core import convert as core_convert
from ...pages import selected_pages
from ...prefs import pref_dpi
from .. import theme
from ..pages import PagePickPage, card, group_title, labelled_slider, register_page

INFO = {
    "TXT":  "Extracts all selectable text from the PDF into a plain .txt file.",
    "HTML": "Exports each page with HTML text structure — opens in any browser.",
    "XML":  "Exports the PDF's text and layout structure as an XML document.",
    "RTF":  "Converts PDF text to Rich Text Format, readable in Word/LibreOffice.",
    "DOCX": "Extracts text paragraph-by-paragraph into a Word document.  Requires: python-docx",
    "PPTX": "Renders each page as a slide image inside a PowerPoint file.  Requires: python-pptx",
    "XLSX": "Extracts text per page; each page goes to its own Excel sheet.  Requires: openpyxl",
    "PNG":  "Renders each page as a PNG image, bundled together in a ZIP.",
    "JPEG": "Renders each page as a JPEG image, bundled together in a ZIP.",
}
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
DPI_FORMATS = ("PNG", "JPEG", "PPTX")
DPI_RANGE = (72, 300)
QUALITY_RANGE, QUALITY_DEFAULT = (50, 100), 92


@register_page("Pdf2DocTool")
class Pdf2DocPage(PagePickPage):
    def __init__(self, tool=None, window=None):
        super().__init__(
            "PDF → Other",
            "Export the selected pages to TXT · HTML · DOCX · PPTX · XLSX · XML · RTF · PNG · JPEG",
            tool=tool, window=window)
        s = self.settings
        s.addWidget(group_title("Output"))
        group = card(padding=0)
        s.addWidget(group)
        row = self.setting_row(group, "Output format", INFO["TXT"])
        self.fmt_info = row.desc_label
        self.fmt = ComboBox()
        self.fmt.addItems(core_convert.FORMATS)
        self.fmt.setCurrentText("TXT")
        self.fmt.setMinimumWidth(120)
        row.layout().addWidget(self.fmt)
        self.missing = CaptionLabel("")
        theme.label_role(self.missing, "warning")
        self.missing.setWordWrap(True)
        self.missing.setContentsMargins(0, 4, 0, 0)
        s.addWidget(self.missing)

        self.image_title = group_title("Image options")
        s.addWidget(self.image_title)
        self.image_card = card(padding=0)
        s.addWidget(self.image_card)
        row = self.setting_row(self.image_card, "Resolution")
        self.dpi_slider = labelled_slider(row, *DPI_RANGE, pref_dpi(*DPI_RANGE), " DPI",
                                          width=120, fixed=False)
        row = self.setting_row(self.image_card, "JPEG quality")
        self.quality_slider = labelled_slider(row, *QUALITY_RANGE, QUALITY_DEFAULT, "%",
                                              width=120, fixed=False)
        self.quality_row = row.parent()
        self._quality_divider = row.divider

        s.addWidget(group_title("Pages"))
        pages = card(padding=0)
        s.addWidget(pages)
        self.setting_row(pages, "Apply to", "or click the pages").layout().addWidget(
            self.make_range_field(width=140))
        s.addStretch(1)
        self.fmt.currentTextChanged.connect(self._fmt_changed)
        self._fmt_changed("TXT")
        self.primary("Convert PDF", self.run)

    # ── options ──
    def _fmt_changed(self, fmt: str):
        self.fmt_info.setText(INFO.get(fmt, ""))
        lib, installed = core_convert.NEEDS.get(fmt, ("", True))
        self.missing.setText("" if installed else
                             f"⚠  '{lib}' is not installed.\nInstall it:  pip install {lib}")
        self.missing.setVisible(not installed)
        images = fmt in DPI_FORMATS
        self.image_title.setVisible(images)
        self.image_card.setVisible(images)
        self.quality_row.setVisible(fmt == "JPEG")
        self._quality_divider.setVisible(fmt == "JPEG")

    @property
    def format(self) -> str:
        return self.fmt.currentText()

    def options(self) -> tuple[int, int]:
        """(dpi, quality) for the conversion: the slider values when
        the format shows them, else 150 and 92."""
        fmt = self.format
        dpi = int(self.dpi_slider.value()) if fmt in DPI_FORMATS else 150
        quality = int(self.quality_slider.value()) if fmt == "JPEG" else QUALITY_DEFAULT
        return dpi, quality

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
