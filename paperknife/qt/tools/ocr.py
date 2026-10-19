"""OCR — make the selected pages of a scanned PDF searchable with Tesseract.  The
pages are on screen (owner, 2026-10-17: the page-range tools show the
document's pages); the options sit in the column at the right."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from qfluentwidgets import InfoBar, InfoBarPosition

from ...core import ocr as core_ocr
from ...pages import selected_pages
from .. import bridge
from ..pages import PagePickPage, card, group_title, muted_caption, register_page
from ..tool_options import OCR_MODES as MODES  # noqa: F401
from ..tool_options import OcrOptions
MISSING_TITLE = "⚠  pytesseract not installed"
MISSING_TEXT = ("Install it with:  pip install pytesseract\n"
                "Then install the Tesseract binary from:\n"
                "https://github.com/UB-Mannheim/tesseract/wiki")


@register_page("OCRTool")
class OCRPage(PagePickPage):
    def __init__(self, tool=None, window=None):
        super().__init__("OCR", "Make a scanned or image-only PDF searchable · "
                                "powered by Tesseract", tool=tool, window=window)
        self.available = core_ocr.HAS_OCR
        self.missing = None
        if self.available:
            self._build_options()
        else:
            # Without pytesseract the page only says how to get it.
            self.missing = InfoBar.warning(MISSING_TITLE, MISSING_TEXT, orient=Qt.Vertical,
                                           isClosable=False, duration=-1,
                                           position=InfoBarPosition.NONE, parent=self)
            self.settings.addWidget(self.missing)
            self.follows_document = False
            for w in (self.doc_bar, self.drop_target, self.grid_card):
                if w is not None:
                    w.hide()
        self.settings.addStretch(1)
        self.run_button = self.primary("Run OCR", self.run)
        self.run_button.setEnabled(self.available)

    def _build_options(self):
        s = self.settings
        o = self.opts = OcrOptions(s, self.setting_row, parent=self)
        self.lang, self.dpi, self.dpi_label = o.lang, o.dpi, o.dpi_label
        self.mode_group, self.modes = o.mode_group, o.modes

        s.addWidget(group_title("Pages"))
        pages = card(padding=0)
        s.addWidget(pages)
        self.setting_row(pages, "Apply to", "or click the pages").layout().addWidget(
            self.make_range_field(width=140))

        self.log = muted_caption("")
        self.log.setContentsMargins(0, 8, 0, 0)
        s.addWidget(self.log)

    def accept_drop(self, path: str) -> bool:
        # Without pytesseract the page only says how to get it: no document.
        return self.available and super().accept_drop(path)

    def load(self, path: str):
        if self.available:
            super().load(path)

    def _selection_changed(self):
        super()._selection_changed()
        if not getattr(self, "available", True) and hasattr(self, "run_button"):
            self.run_button.setEnabled(False)       # without Tesseract, never

    @property
    def text_only(self) -> bool:
        return self.mode_group.value() == "text"

    def open(self):
        if self.available:
            self.file.choose()

    def run(self):
        if not self.available:
            return
        src = self.chosen_file("OCR")
        if not src or self._doc is None:
            return
        lang = self.lang.text().strip() or "eng"
        dpi = int(self.dpi.value())
        text_only = self.text_only
        log = self.log
        range_str = self.range_text()
        pages: list[int] = []

        def prepare(doc):
            pages[:] = selected_pages(range_str, len(doc))

        def work(doc, out, stop, progress):
            self._release(out)              # over the open file: let it go first
            return core_ocr.ocr_pdf(
                doc, out, lang, dpi, text_only, stop, progress,
                lambda n, t: bridge.post(log.setText, f"OCR — page {n} / {t}"), pages=pages)

        def report(total, out):
            log.setText(f"✓  Done — {total} page(s) processed")
            return ("success", f"✓  OCR complete — {total} page(s) → {Path(out).name}",
                    "OCR Complete", f"OCR PDF saved:\n{out}\n\nPages processed: {total}")

        self.run_on_file("OCR", work, f"OCR — {dpi} DPI · lang={lang}", report, src=src,
                         save=("ocr_output.pdf", ".pdf", [("PDF", "*.pdf")]), prepare=prepare,
                         open_doc=self.job_copy)
