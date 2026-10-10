"""Image → PDF — several images, in the order chosen, into one PDF (group D)."""
from __future__ import annotations

from pathlib import Path

from ...core import convert as core_convert
from .. import dialogs
from ..pages import CollectionPage, register_page


@register_page("Img2PdfTool")
class Img2PdfPage(CollectionPage):
    def __init__(self, tool=None, window=None):
        super().__init__(
            "Image → PDF", "Convert JPG · PNG · WEBP · BMP · TIFF images into a PDF",
            tool=tool, window=window, exts=core_convert.IMAGE_EXTS,
            add_text="Add Images", settings=False, filter_label="Images",
            open_title="Select Images",
            empty_text="Add images in the order they should appear: "
                       "drop them here, or use Add Images.")
        self.primary("Convert to PDF", self.run)

    def run(self):
        paths = self.paths()
        if not paths:
            return dialogs.warning("Convert", "Add images first.")
        out = dialogs.ask_save("from_images.pdf", ".pdf", [("PDF", "*.pdf")])
        if not out:
            return
        win = self.window_

        def work(stop):
            return core_convert.images_to_pdf(
                paths, out, stop, win.progress_callback())

        def then(kind, written):
            if kind != "done":
                return
            win.set_status(f"✓  Converted {len(paths)} image(s) → {Path(out).name}", "success")
            dialogs.info("Done", f"PDF saved:\n{out}")
            self.clear_rows()               # a finished job empties the list (owner)
            self.offer_output(out)

        win.set_status(f"Converting {len(paths)} image(s)…")
        win.run_job(work, f"Converting {len(paths)} image(s)…", then=then)
