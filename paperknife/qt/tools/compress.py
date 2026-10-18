"""Compress — the whole file, with its pages on screen to see what is worked
with (owner, 2026-10-17: the grid shows the pages; Compress always works on the
whole file, so it has no selection); the level sits in the column at the right."""
from __future__ import annotations

from pathlib import Path

from ...core import enhance as core_enhance
from ...prefs import PREFS
from ..pages import PagePickPage, card, group_title, radio_rows, register_page

LEVELS = [
    ("light", "Light", "Clean and deflate only. Safe for every file."),
    ("medium", "Medium", "Also resample images to 150 DPI, JPEG quality 80%."),
    ("aggressive", "Aggressive", "Also scale images to 96 DPI. Visible quality loss."),
]


def size_report(orig: int, new: int, out: str):
    """(role, status line, dialog title, dialog text) for a finished compression."""
    orig_kb, new_kb = orig // 1024, new // 1024
    if new < orig:
        pct = round((1 - new / orig) * 100)
        return ("success", f"✓  {orig_kb} KB → {new_kb} KB (−{pct}%) → {Path(out).name}",
                "Compressed", f"Compressed PDF saved:\n{out}\n\n"
                              f"Original: {orig_kb} KB  →  New: {new_kb} KB  ({pct}% smaller)")
    return ("warning", f"⚠  No size reduction: {orig_kb} KB → {new_kb} KB",
            "Compress", f"The output is not smaller than the original:\n{out}\n\n"
                        f"Original: {orig_kb} KB  →  New: {new_kb} KB")


@register_page("CompressTool")
class CompressPage(PagePickPage):
    pick_pages = False
    view_hint = "Compress works on the whole file"

    def __init__(self, tool=None, window=None):
        super().__init__("Compress", "Reduce file size by cleaning streams and downsampling images",
                         tool=tool, window=window)
        s = self.settings
        s.addWidget(group_title("Compression level"))
        group = card(padding=0)
        s.addWidget(group)
        self.level_group = radio_rows(group, LEVELS, PREFS.compress_level or "medium",
                                      row=self.setting_row, parent=self)
        self.radios = self.level_group.buttons
        s.addStretch(1)
        self.primary("Compress", self.run)

    @property
    def level(self) -> str:
        return self.level_group.value()

    def run(self):
        src = self.chosen_file("Compress")
        if not src or self._doc is None:
            return
        level, orig = self.level, [Path(src).stat().st_size]

        def work(doc, out, stop, progress):
            self._release(out)              # over the open file: let it go first
            core_enhance.compress_pdf(doc, out, level)
            return Path(out).stat().st_size

        self.run_on_file("Compress", work, "Compressing PDF…",
                         lambda new, out: size_report(orig[0], new, out), src=src,
                         save=("compressed.pdf", ".pdf", [("PDF", "*.pdf")]),
                         cancellable=False, warning_box=True, open_doc=self.job_copy)
