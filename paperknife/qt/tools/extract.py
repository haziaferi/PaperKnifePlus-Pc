"""Extract Images — every embedded image of a PDF into a folder (group C)."""
from __future__ import annotations

from qfluentwidgets import ComboBox

from ...core import convert as core_convert
from ..pages import (spin_box, ToolPage, card, file_card, group_title, muted_caption, register_page,
                     setting_row)

FORMATS = ["Keep original", "PNG", "JPEG"]
DEFAULT_MIN_PX = 50


@register_page("ExtractTool")
class ExtractPage(ToolPage):
    def __init__(self, tool=None, window=None):
        super().__init__("Extract Images",
                         "Pull every embedded image out of a PDF and save to a folder",
                         tool=tool, window=window)
        self.file = file_card()
        self.body.addWidget(self.file)
        self.body.addSpacing(16)
        self.body.addWidget(group_title("Options"))
        group = card(padding=0)
        self.body.addWidget(group)
        row = setting_row(group, "Minimum dimension", "px  (skip smaller images)")
        self.min_px = spin_box(0, 100000, DEFAULT_MIN_PX)
        row.layout().addWidget(self.min_px)
        row = setting_row(group, "Output format")
        self.fmt = ComboBox()
        self.fmt.addItems(FORMATS)
        self.fmt.setCurrentText(FORMATS[0])
        self.fmt.setMinimumWidth(160)
        row.layout().addWidget(self.fmt)
        self.log = muted_caption("")
        self.log.setWordWrap(True)
        self.body.addSpacing(8)
        self.body.addWidget(self.log)
        self.body.addStretch(1)
        self.primary("Extract Images", self.run)

    def open(self):
        self.file.choose()

    def run(self):
        src = self.chosen_file("Extract")
        if not src:
            return
        min_px = int(self.min_px.value())
        fmt = self.fmt.currentText()

        def work(doc, out_dir, stop, progress):
            return core_convert.extract_images(doc, out_dir, fmt, min_px, stop, progress)

        def report(res, out_dir):
            count, failed = res.count, res.failed
            msg = (f"Found and extracted {count} image(s)  "
                   f"({res.scanned} unique xrefs scanned)")
            fail_txt = f"\n{failed} image(s) could not be extracted." if failed else ""
            self.log.setText(msg + fail_txt.replace("\n", "  ·  "))
            return ("warning" if failed else "success",
                    f"✓  Extracted {count} image(s) → {out_dir}",
                    "Done", f"Extracted {count} image(s) to:\n{out_dir}{fail_txt}")

        self.run_on_file("Extract", work, "Extracting images…", report, src=src)
