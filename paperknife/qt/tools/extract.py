"""Extract Images — every embedded image of a PDF into a folder (group C)."""
from __future__ import annotations

from qfluentwidgets import ComboBox, SpinBox

from ...core import convert as core_convert
from .. import bridge, dialogs
from ..pages import (ToolPage, card, file_card, group_title, muted_caption, register_page,
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
        self.min_px = SpinBox()
        self.min_px.setRange(0, 100000)
        self.min_px.setValue(DEFAULT_MIN_PX)
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
        src = self.file.path()
        if not src:
            return dialogs.warning("Extract", "Select a PDF first.")
        min_px = int(self.min_px.value())
        win = self.window_
        doc = win.open_pdf_safe(src)
        if doc is None:
            return
        out_dir = dialogs.ask_dir()
        if not out_dir:
            return doc.close()
        fmt = self.fmt.currentText()

        def work(stop):
            # Closes doc; None if cancelled.
            return core_convert.extract_images(doc, out_dir, fmt, min_px, stop,
                                               lambda v: bridge.post(win.set_progress, v))

        def then(kind, res):
            if kind != "done" or res is None:
                return
            count, failed = res.count, res.failed
            msg = (f"Found and extracted {count} image(s)  "
                   f"({res.scanned} unique xrefs scanned)")
            fail_txt = f"\n{failed} image(s) could not be extracted." if failed else ""
            self.log.setText(msg + fail_txt.replace("\n", "  ·  "))
            win.set_status(f"✓  Extracted {count} image(s) → {out_dir}",
                           "warning" if failed else "success")
            dialogs.info("Done", f"Extracted {count} image(s) to:\n{out_dir}{fail_txt}")

        if win.run_job(work, "Extracting images…", then=then) is None:
            doc.close()
