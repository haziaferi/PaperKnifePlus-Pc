"""OCR — a single-file transform (group C): make a scanned PDF searchable with Tesseract."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QButtonGroup
from qfluentwidgets import BodyLabel, InfoBar, InfoBarPosition, LineEdit, RadioButton, Slider

from ...core import ocr as core_ocr
from ...prefs import PREFS, pref_dpi
from .. import bridge, dialogs
from ..pages import (ToolPage, card, file_card, group_title, muted_caption, register_page,
                     setting_row)

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
        dpi = pref_dpi(72, 400)
        self.dpi = Slider(Qt.Horizontal)
        self.dpi.setRange(72, 400)
        self.dpi.setValue(dpi)
        self.dpi.setMinimumWidth(200)
        self.dpi_label = BodyLabel(f"{dpi} DPI")
        self.dpi_label.setFixedWidth(64)
        self.dpi.valueChanged.connect(lambda v: self.dpi_label.setText(f"{int(v)} DPI"))
        row.layout().addWidget(self.dpi)
        row.layout().addWidget(self.dpi_label)

        self.body.addWidget(group_title("Output mode"))
        group = card(padding=0)
        self.body.addWidget(group)
        self.mode_group = QButtonGroup(self)
        self.modes: dict[str, RadioButton] = {}
        for val, name, desc in MODES:
            holder = setting_row(group, name, desc)
            rb = RadioButton("")
            rb.setChecked(val == "overlay")
            self.mode_group.addButton(rb)
            holder.layout().addWidget(rb)
            self.modes[val] = rb

        self.log = muted_caption("")
        self.log.setContentsMargins(0, 8, 0, 0)
        self.body.addWidget(self.log)

    @property
    def text_only(self) -> bool:
        return self.modes["text"].isChecked()

    def open(self):
        if self.available:
            self.file.choose()

    def run(self):
        if not self.available:
            return
        src = self.file.path()
        if not src:
            return dialogs.warning("OCR", "Select a PDF first.")
        win = self.window_
        doc = win.open_pdf_safe(src)
        if doc is None:
            return
        out = dialogs.ask_save("ocr_output.pdf", ".pdf", [("PDF", "*.pdf")])
        if not out:
            return doc.close()
        lang = self.lang.text().strip() or "eng"
        dpi = int(self.dpi.value())
        text_only = self.text_only
        log = self.log

        def work(stop):
            return core_ocr.ocr_pdf(
                doc, out, lang, dpi, text_only, stop,
                lambda v: bridge.post(win.set_progress, v),
                lambda n, t: bridge.post(log.setText, f"OCR — page {n} / {t}"))

        def then(kind, total):
            if kind != "done" or total is None:
                return
            log.setText(f"✓  Done — {total} page(s) processed")
            win.set_status(f"✓  OCR complete — {total} page(s) → {Path(out).name}", "success")
            dialogs.info("OCR Complete", f"OCR PDF saved:\n{out}\n\nPages processed: {total}")

        win.set_status(f"Starting OCR ({lang}, {dpi} DPI)…")
        if win.run_job(work, f"OCR — {dpi} DPI · lang={lang}", then=then) is None:
            doc.close()
