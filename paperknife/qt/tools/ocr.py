"""OCR — a single-file transform (group C): make a scanned PDF searchable with Tesseract."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from qfluentwidgets import InfoBar, InfoBarPosition, LineEdit

from ...core import ocr as core_ocr
from ...prefs import PREFS, pref_dpi
from .. import bridge
from ..pages import (ToolPage, card, file_card, group_title, labelled_slider, muted_caption,
                     radio_rows, register_page, setting_row)

MODES = [("overlay", "Overlay", "invisible text layer"),
         ("text", "Text-only PDF", "")]
MISSING_TITLE = "⚠  pytesseract not installed"
MISSING_TEXT = ("Install it with:  pip install pytesseract\n"
                "Then install the Tesseract binary from:\n"
                "https://github.com/UB-Mannheim/tesseract/wiki")


@register_page("OCRTool")
class OCRPage(ToolPage):
    def __init__(self, tool=None, window=None):
        super().__init__("OCR", "Make a scanned or image-only PDF searchable · "
                                "powered by Tesseract", tool=tool, window=window)
        self.available = core_ocr.HAS_OCR
        self.missing = None
        if self.available:
            self._build_options()
        else:
            # As in the CTk tool: without pytesseract the page only says how to get it.
            self.missing = InfoBar.warning(MISSING_TITLE, MISSING_TEXT, orient=Qt.Vertical,
                                           isClosable=False, duration=-1,
                                           position=InfoBarPosition.NONE, parent=self)
            self.body.addWidget(self.missing)
        self.body.addStretch(1)
        self.run_button = self.primary("Run OCR", self.run)
        self.run_button.setEnabled(self.available)

    def _build_options(self):
        self.file = file_card()
        self.body.addWidget(self.file)
        self.body.addSpacing(16)
        self.body.addWidget(group_title("Recognition"))
        group = card(padding=0)
        self.body.addWidget(group)

        row = setting_row(group, "Language code", "e.g.  eng  ·  ita  ·  deu  ·  fra  ·  eng+ita")
        self.lang = LineEdit()
        self.lang.setPlaceholderText("eng")
        self.lang.setText(PREFS.ocr_lang or "eng")
        self.lang.setFixedWidth(120)
        row.layout().addWidget(self.lang)

        row = setting_row(group, "Render DPI")
        self.dpi = labelled_slider(row, 72, 400, pref_dpi(72, 400), " DPI", width=200,
                                   fixed=False)
        self.dpi_label = self.dpi.value_label

        self.body.addWidget(group_title("Output mode"))
        group = card(padding=0)
        self.body.addWidget(group)
        self.mode_group = radio_rows(group, MODES, "overlay", parent=self)
        self.modes = self.mode_group.buttons

        self.log = muted_caption("")
        self.log.setContentsMargins(0, 8, 0, 0)
        self.body.addWidget(self.log)

    @property
    def text_only(self) -> bool:
        return self.mode_group.value() == "text"

    def open(self):
        if self.available:
            self.file.choose()

    def run(self):
        if not self.available:
            return
        lang = self.lang.text().strip() or "eng"
        dpi = int(self.dpi.value())
        text_only = self.text_only
        log = self.log

        def work(doc, out, stop, progress):
            return core_ocr.ocr_pdf(
                doc, out, lang, dpi, text_only, stop, progress,
                lambda n, t: bridge.post(log.setText, f"OCR — page {n} / {t}"))

        def report(total, out):
            log.setText(f"✓  Done — {total} page(s) processed")
            return ("success", f"✓  OCR complete — {total} page(s) → {Path(out).name}",
                    "OCR Complete", f"OCR PDF saved:\n{out}\n\nPages processed: {total}")

        self.run_on_file("OCR", work, f"OCR — {dpi} DPI · lang={lang}", report,
                         save=("ocr_output.pdf", ".pdf", [("PDF", "*.pdf")]))
