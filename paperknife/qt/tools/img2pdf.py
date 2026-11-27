"""Other → PDF — images and documents, in the order chosen, into one PDF
(group D).  Image → PDF and Doc / Text → PDF merged into one list (owner,
2026-10-18): an image is a page of its own size, a document adds its pages,
each file's format read from its extension.  (The page key stays Img2PdfTool.)"""
from __future__ import annotations

from pathlib import Path

from ...core import convert as core_convert
from .. import dialogs
from ..pages import CollectionPage, register_page

TITLE = "Other → PDF"
SUBTITLE = ("Images and documents into one PDF · JPG · PNG · WEBP · BMP · TIFF · TXT · HTML · "
            "DOCX · PPTX · XLSX · XML · RTF")


@register_page("Img2PdfTool")
class Img2PdfPage(CollectionPage):
    def __init__(self, tool=None, window=None):
        super().__init__(
            TITLE, SUBTITLE,
            tool=tool, window=window, exts=core_convert.TO_PDF_EXTS,
            add_text="Add Files", settings=False, filter_label="Images and documents",
            open_title="Select Files",
            empty_text="Add images and documents in the order they should appear: "
                       "drop them here, or use Add Files.")
        self.primary("Convert to PDF", self.run)

    def run(self):
        paths = self.paths()
        if not paths:
            return dialogs.warning("Convert", "Add files first.")
        out = dialogs.ask_save("converted.pdf", ".pdf", [("PDF", "*.pdf")])
        if not out:
            return
        win = self.window_
        written = {}

        def work(stop):
            # The notes on fallbacks that changed the output; None if cancelled.
            written["notes"] = core_convert.files_to_pdf(paths, out, stop,
                                                         win.progress_callback())
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
            win.set_status(f"✓  Converted {len(paths)} file(s) → {Path(out).name}",
                           "warning" if notes else "success")
            dialogs.info("Done", f"PDF saved:\n{out}{note}")
            self.clear_rows()               # a finished job empties the list (owner)
            if kind == "done":
                self.offer_output(out)

        win.set_status(f"Converting {len(paths)} file(s)…")
        win.run_job(work, f"Converting {len(paths)} file(s)…", then=then)
