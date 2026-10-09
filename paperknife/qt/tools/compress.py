"""Compress — the single-file transform pilot (group C)."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QButtonGroup
from qfluentwidgets import RadioButton

from ...core import enhance as core_enhance
from ...prefs import PREFS
from ..pages import ToolPage, card, file_card, group_title, register_page, setting_row

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
class CompressPage(ToolPage):
    def __init__(self, tool=None, window=None):
        super().__init__("Compress", "Reduce file size by cleaning streams and downsampling images",
                         tool=tool, window=window)
        self.file = file_card()
        self.body.addWidget(self.file)
        self.body.addSpacing(16)
        self.body.addWidget(group_title("Compression level"))
        group = card(padding=0)
        self.body.addWidget(group)
        self.level_group = QButtonGroup(self)
        self.radios: dict[str, RadioButton] = {}
        chosen = PREFS.compress_level or "medium"
        for val, title, desc in LEVELS:
            holder = setting_row(group, title, desc)
            rb = RadioButton("")
            rb.setChecked(val == chosen)
            self.level_group.addButton(rb)
            holder.layout().addWidget(rb)
            self.radios[val] = rb
        self.body.addStretch(1)
        self.primary("Compress", self.run)

    @property
    def level(self) -> str:
        return next(v for v, rb in self.radios.items() if rb.isChecked())

    def run(self):
        level, orig = self.level, [0]

        def prepare(doc):
            orig[0] = Path(doc.name).stat().st_size

        def work(doc, out, stop, progress):
            core_enhance.compress_pdf(doc, out, level)
            return Path(out).stat().st_size

        self.run_on_file("Compress", work, "Compressing PDF…",
                         lambda new, out: size_report(orig[0], new, out),
                         save=("compressed.pdf", ".pdf", [("PDF", "*.pdf")]), prepare=prepare,
                         cancellable=False, working="Compressing…", warning_box=True)
