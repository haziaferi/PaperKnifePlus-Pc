"""Doc / Text → PDF — a TXT, HTML, XML, RTF, DOCX, PPTX, XLSX, PNG or JPEG file to PDF (group C)."""
from __future__ import annotations

from pathlib import Path

from qfluentwidgets import CaptionLabel, ComboBox

from ...core import convert as core_convert
from .. import dialogs, theme
from ..pages import ToolPage, card, file_card, group_title, register_page, setting_row

INFO = {
    "TXT":  "Text is typeset into A4 pages at 11pt with automatic line-wrapping.",
    "HTML": "HTML is rendered to PDF using PyMuPDF's built-in Story engine (supports basic CSS).",
    "XML":  "XML tag text is extracted and typeset into A4 pages.",
    "RTF":  "RTF content is converted to plain text and typeset into A4 pages.",
    "DOCX": "Paragraphs, headings, and tables are extracted from the Word document.",
    "PPTX": "Each slide's title and text content is typeset on its own PDF page.",
    "XLSX": "Each sheet is rendered as a plain-text table across A4 landscape pages.",
    "PNG":  "The PNG image is placed on a page sized to match the image exactly.",
    "JPEG": "The JPEG image is placed on a page sized to match the image exactly.",
}
# The input formats by extension: what the file card accepts, and how the
# format is detected from a chosen or dropped file.
EXT2FMT = {
    ".txt": "TXT", ".html": "HTML", ".htm": "HTML", ".xml": "XML",
    ".rtf": "RTF", ".docx": "DOCX", ".pptx": "PPTX", ".xlsx": "XLSX",
    ".png": "PNG", ".jpg": "JPEG",  ".jpeg": "JPEG",
}


@register_page("Doc2PdfTool")
class Doc2PdfPage(ToolPage):
    def __init__(self, tool=None, window=None):
        super().__init__(
            "Doc / Text → PDF",
            "Convert TXT · HTML · DOCX · PPTX · XLSX · XML · RTF · PNG · JPEG to PDF",
            tool=tool, window=window)
        self.file = file_card(on_change=self._file_changed, exts=tuple(EXT2FMT))
        self.body.addWidget(self.file)
        self.body.addSpacing(16)
        self.body.addWidget(group_title("Input"))
        group = card(padding=0)
        self.body.addWidget(group)
        row = setting_row(group, "Input format", INFO["TXT"])
        self.fmt_info = row.desc_label
        self.fmt = ComboBox()
        self.fmt.addItems(core_convert.FORMATS)
        self.fmt.setCurrentText("TXT")
        self.fmt.setMinimumWidth(160)
        row.layout().addWidget(self.fmt)
        self.missing = CaptionLabel("")
        theme.label_role(self.missing, "warning")
        self.missing.setWordWrap(True)
        self.missing.setContentsMargins(0, 4, 0, 0)
        self.body.addWidget(self.missing)
        self.body.addStretch(1)
        self.fmt.currentTextChanged.connect(self._fmt_changed)
        self._fmt_changed("TXT")
        self.primary("Convert to PDF", self.run)

    # ── options ──
    def _fmt_changed(self, fmt: str):
        self.fmt_info.setText(INFO.get(fmt, ""))
        lib, installed = core_convert.NEEDS.get(fmt, ("", True))
        self.missing.setText("" if installed else f"⚠  '{lib}' not installed — pip install {lib}")
        self.missing.setVisible(not installed)

    def _file_changed(self, path: str):
        detected = EXT2FMT.get(Path(path).suffix.lower()) if path else None
        if detected and detected != self.format:
            self.fmt.setCurrentText(detected)

    @property
    def format(self) -> str:
        return self.fmt.currentText()

    # ── actions ──
    def run(self):
        src = self.file.path()
        if not src:
            return dialogs.warning("Convert", "Select a file first.")
        out = dialogs.ask_save("converted.pdf")
        if not out:
            return
        fmt = self.format
        win = self.window_

        written = {}

        def work(stop):
            # The notes on fallbacks that changed the output; None if cancelled.
            written["notes"] = core_convert.doc_to_pdf(src, fmt, out, stop)
            return written["notes"]

        def then(kind, notes):
            if kind == "cancel":
                # Cancel came after the PDF was in place: it was still written.
                notes = written.get("notes")
            elif kind != "done":
                return
            if notes is None:
                return
            note = "\n\n" + "\n".join(notes) if notes else ""
            win.set_status(f"✓  {fmt} → PDF: {Path(out).name}",
                           "warning" if notes else "success")
            dialogs.info("Done", f"Converted PDF saved:\n{out}{note}")

        win.set_status(f"Converting {fmt} → PDF…")
        win.run_job(work, f"Converting {fmt} → PDF…", then=then)
