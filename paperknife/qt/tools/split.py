"""Split — a single-file transform (group C): page ranges into separate files."""
from __future__ import annotations

from pathlib import Path

from qfluentwidgets import LineEdit

from ...core import organise
from ...pages import PageRangeError, parse_ranges
from .. import dialogs
from ..pages import ToolPage, card, file_card, group_title, register_page, setting_row


@register_page("SplitTool")
class SplitPage(ToolPage):
    def __init__(self, tool=None, window=None):
        super().__init__("Split", "Extract pages or page ranges", tool=tool, window=window)
        self.file = file_card()
        self.body.addWidget(self.file)
        self.body.addSpacing(16)
        self.body.addWidget(group_title("Pages"))
        group = card(padding=0)
        self.body.addWidget(group)
        holder = setting_row(group, "Page ranges",
                             "e.g.  1-3, 5, 7-9. Separate with commas · leave blank to "
                             "extract every page individually")
        self.ranges = LineEdit()
        self.ranges.setPlaceholderText("e.g.  1-3, 5, 7-9")
        self.ranges.setClearButtonEnabled(True)
        self.ranges.setMinimumWidth(260)
        holder.layout().addWidget(self.ranges)
        self.body.addStretch(1)
        self.primary("Split", self.run)

    def open(self):
        self.file.choose()

    def run(self):
        src = self.file.path()
        if not src:
            return dialogs.warning("Split", "Select a PDF first.")
        ranges_str = self.ranges.text().strip()
        win = self.window_
        doc = win.open_pdf_safe(src)
        if doc is None:
            return
        total = len(doc)
        try:
            groups = (parse_ranges(ranges_str, total) if ranges_str
                      else [(i, i) for i in range(total)])
        except PageRangeError as e:
            doc.close()
            return dialogs.error("Split", str(e))
        out_dir = dialogs.ask_dir()
        if not out_dir:
            return doc.close()
        base = Path(src).stem

        def work(stop):
            with doc:                   # the job owns the document from here
                organise.split_ranges(doc, groups, out_dir, base, stop,
                                      win.progress_callback())

        def then(kind, _value):
            if kind != "done":
                return
            win.set_status(f"✓  Split into {len(groups)} file(s) → {out_dir}", "success")
            dialogs.info("Done", f"Created {len(groups)} file(s) in:\n{out_dir}")

        if win.run_job(work, f"Splitting into {len(groups)} file(s)…", then=then) is None:
            doc.close()
