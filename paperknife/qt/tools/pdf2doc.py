"""PDF → Doc / Text — a PDF to TXT, HTML, XML, RTF, DOCX, PPTX, XLSX or page images (group C)."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from qfluentwidgets import BodyLabel, CaptionLabel, ComboBox, Slider

from ...core import convert as core_convert
from ...prefs import pref_dpi
from .. import theme
from ..pages import Divider, ToolPage, card, file_card, group_title, register_page, setting_row

INFO = {
    "TXT":  "Extracts all selectable text from the PDF into a plain .txt file.",
    "HTML": "Exports each page with HTML text structure — opens in any browser.",
    "XML":  "Exports the PDF's text and layout structure as an XML document.",
    "RTF":  "Converts PDF text to Rich Text Format, readable in Word/LibreOffice.",
    "DOCX": "Extracts text paragraph-by-paragraph into a Word document.  Requires: python-docx",
    "PPTX": "Renders each page as a slide image inside a PowerPoint file.  Requires: python-pptx",
    "XLSX": "Extracts text per page; each page goes to its own Excel sheet.  Requires: openpyxl",
    "PNG":  "Renders every page as a PNG image, bundled together in a ZIP.",
    "JPEG": "Renders every page as a JPEG image, bundled together in a ZIP.",
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


def _slider(lo: int, hi: int, value: int, unit: str, row) -> Slider:
    s = Slider(Qt.Horizontal)
    s.setRange(lo, hi)
    s.setFixedWidth(220)
    lbl = BodyLabel()
    lbl.setFixedWidth(64)
    s.valueChanged.connect(lambda v: lbl.setText(f"{v}{unit}"))
    s.setValue(value)
    lbl.setText(f"{s.value()}{unit}")
    s.value_label = lbl
    row.layout().addWidget(s)
    row.layout().addWidget(lbl)
    return s


@register_page("Pdf2DocTool")
class Pdf2DocPage(ToolPage):
    def __init__(self, tool=None, window=None):
        super().__init__(
            "PDF → Doc / Text",
            "Export a PDF to TXT · HTML · DOCX · PPTX · XLSX · XML · RTF · PNG · JPEG",
            tool=tool, window=window)
        self.file = file_card()
        self.body.addWidget(self.file)
        self.body.addSpacing(16)
        self.body.addWidget(group_title("Output"))
        group = card(padding=0)
        self.body.addWidget(group)
        row = setting_row(group, "Output format", INFO["TXT"])
        self.fmt_info = row.parent().findChildren(CaptionLabel)[0]
        self.fmt = ComboBox()
        self.fmt.addItems(core_convert.FORMATS)
        self.fmt.setCurrentText("TXT")
        self.fmt.setMinimumWidth(160)
        row.layout().addWidget(self.fmt)
        self.missing = CaptionLabel("")
        self.missing.setTextColor(*theme.pair("warning"))
        self.missing.setWordWrap(True)
        self.missing.setContentsMargins(0, 4, 0, 0)
        self.body.addWidget(self.missing)

        self.image_title = group_title("Image options")
        self.body.addWidget(self.image_title)
        self.image_card = card(padding=0)
        self.body.addWidget(self.image_card)
        row = setting_row(self.image_card, "Resolution")
        self.dpi_slider = _slider(*DPI_RANGE, pref_dpi(*DPI_RANGE), " DPI", row)
        row = setting_row(self.image_card, "JPEG quality")
        self.quality_slider = _slider(*QUALITY_RANGE, QUALITY_DEFAULT, "%", row)
        lay = self.image_card.layout()
        self.quality_row = row.parent()
        self._quality_divider = next(
            lay.itemAt(i).widget() for i in range(lay.count())
            if isinstance(lay.itemAt(i).widget(), Divider))
        self.body.addStretch(1)
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
        """(dpi, quality) as the CTk tool passes them: the slider values when
        the format shows them, else 150 and 92."""
        fmt = self.format
        dpi = int(self.dpi_slider.value()) if fmt in DPI_FORMATS else 150
        quality = int(self.quality_slider.value()) if fmt == "JPEG" else QUALITY_DEFAULT
        return dpi, quality

    # ── actions ──
    def run(self):
        src = self.chosen_file("Convert")
        if not src:
            return
        fmt = self.format
        ext, desc, default = OUT[fmt]
        dpi, quality = self.options()

        def work(doc, out, stop, progress):
            return core_convert.pdf_to_doc(doc, fmt, out, stop, progress,
                                           dpi=dpi, quality=quality)

        self.run_on_file(
            "Convert", work, f"Converting PDF → {fmt}…",
            lambda _ok, out: ("success", f"✓  PDF → {fmt}: {Path(out).name}",
                              "Done", f"Saved:\n{out}"),
            src=src, save=(default, ext, [(desc, f"*{ext}"), ("All", "*.*")]),
            working=f"Converting PDF → {fmt}…")
