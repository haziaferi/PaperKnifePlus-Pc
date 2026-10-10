"""Split — a single-file transform (group C): page ranges into separate files."""
from __future__ import annotations

from pathlib import Path

from qfluentwidgets import LineEdit

from ...core import organise
from ...pages import parse_ranges
from ..pages import ToolPage, card, group_title, register_page, setting_row


@register_page("SplitTool")
class SplitPage(ToolPage):
    def __init__(self, tool=None, window=None):
        super().__init__("Split", "Extract pages or page ranges", tool=tool, window=window)
        self.doc_input()
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

    def run(self):
        src = self.chosen_file("Split")
        if not src:
            return
        ranges_str = self.ranges.text().strip()
        base = Path(src).stem
        groups: list = []

        def prepare(doc):
            total = len(doc)
            groups[:] = (parse_ranges(ranges_str, total) if ranges_str
                         else [(i, i) for i in range(total)])

        def work(doc, out_dir, stop, progress):
            with doc:                   # the job owns the document from here
                organise.split_ranges(doc, groups, out_dir, base, stop, progress)

        self.run_on_file(
            "Split", work, lambda: f"Splitting into {len(groups)} file(s)…",
            lambda _v, out_dir: ("success", f"✓  Split into {len(groups)} file(s) → {out_dir}",
                                 "Done", f"Created {len(groups)} file(s) in:\n{out_dir}"),
            src=src, prepare=prepare, parts=True)
