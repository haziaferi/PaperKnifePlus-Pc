"""Extract Images — the embedded images of the chosen pages into a folder.  The
pages are on screen (owner, 2026-10-17: the page-range tools show the
document's pages); the options sit in the column at the right."""
from __future__ import annotations

from qfluentwidgets import ComboBox

from ...core import convert as core_convert
from ...pages import selected_pages
from ..pages import (PagePickPage, card, group_title, muted_caption, register_page,
                     spin_box)

FORMATS = ["Keep original", "PNG", "JPEG"]
DEFAULT_MIN_PX = 50


@register_page("ExtractTool")
class ExtractPage(PagePickPage):
    def __init__(self, tool=None, window=None):
        super().__init__("Extract Images",
                         "Pull the embedded images of the chosen pages out to a folder",
                         tool=tool, window=window)
        s = self.settings
        s.addWidget(group_title("Options"))
        group = card(padding=0)
        s.addWidget(group)
        row = self.setting_row(group, "Minimum dimension", "px  (skip smaller images)")
        self.min_px = spin_box(0, 100000, DEFAULT_MIN_PX)
        row.layout().addWidget(self.min_px)
        row = self.setting_row(group, "Output format")
        self.fmt = ComboBox()
        self.fmt.addItems(FORMATS)
        self.fmt.setCurrentText(FORMATS[0])
        self.fmt.setMinimumWidth(140)
        row.layout().addWidget(self.fmt)
        s.addWidget(group_title("Pages"))
        pages = card(padding=0)
        s.addWidget(pages)
        self.setting_row(pages, "Apply to", "or click the pages").layout().addWidget(
            self.make_range_field(width=140))
        self.log = muted_caption("")
        self.log.setWordWrap(True)
        s.addSpacing(8)
        s.addWidget(self.log)
        s.addStretch(1)
        self.primary("Extract Images", self.run)

    def run(self):
        src = self.chosen_file("Extract")
        if not src or self._doc is None:
            return
        min_px = int(self.min_px.value())
        fmt = self.fmt.currentText()
        range_str = self.range_text()
        pages: list[int] = []

        def prepare(doc):
            pages[:] = selected_pages(range_str, len(doc))

        def work(doc, out_dir, stop, progress):
            return core_convert.extract_images(doc, out_dir, fmt, min_px, stop, progress,
                                               pages=pages)

        def report(res, out_dir):
            count, failed = res.count, res.failed
            msg = (f"Found and extracted {count} image(s)  "
                   f"({res.scanned} unique xrefs scanned)")
            fail_txt = f"\n{failed} image(s) could not be extracted." if failed else ""
            self.log.setText(msg + fail_txt.replace("\n", "  ·  "))
            return ("warning" if failed else "success",
                    f"✓  Extracted {count} image(s) → {out_dir}",
                    "Done", f"Extracted {count} image(s) to:\n{out_dir}{fail_txt}")

        self.run_on_file("Extract", work, "Extracting images…", report, src=src,
                         prepare=prepare, open_doc=self.job_copy)
