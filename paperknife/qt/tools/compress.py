"""Compress — the single-file transform pilot (group C).  No page grid (owner,
2026-10-18): it always works on the whole file."""
from __future__ import annotations

from pathlib import Path

from ...core import enhance as core_enhance
from ..pages import ToolPage, batch_prototype, register_page, setting_row
from ..tool_options import LEVELS, CompressOptions  # noqa: F401  (LEVELS: Batch's)


def size_report(orig: int, new: int):
    """(role, status line, box text or None, take it) for a finished
    compression: a result no smaller leaves the document as it was."""
    orig_kb, new_kb = orig // 1024, new // 1024
    if new < orig:
        pct = round((1 - new / orig) * 100)
        return ("success", f"✓  {orig_kb} KB → {new_kb} KB (−{pct}%) · Save writes it to the file",
                None, True)
    return ("warning", f"⚠  No size reduction: {orig_kb} KB → {new_kb} KB",
            "Compressing would not make this PDF smaller "
            f"({orig_kb} KB → {new_kb} KB): it is left as it was.", False)


@register_page("CompressTool")
class CompressPage(ToolPage):
    def __init__(self, tool=None, window=None):
        super().__init__("Compress", "Reduce file size by cleaning streams and downsampling images",
                         tool=tool, window=window)
        self.doc_input()
        self.body.addSpacing(16)
        self.opts = CompressOptions(self.body, setting_row, parent=self)
        self.level_group, self.radios = self.opts.level_group, self.opts.radios
        self.body.addStretch(1)
        self.primary("Compress", self.run)
        if batch_prototype() == "B":
            from ..folder_mode import FolderMode
            FolderMode(self, self.opts, "compress", "Compress", self.body, self.drop_target)

    @property
    def level(self) -> str:
        return self.level_group.value()

    def run(self):
        fm = self.__dict__.get("_folder_mode")
        if fm is not None and fm.run():
            return                          # a folder is the input (prototype B)
        level, orig = self.level, [0]

        src = self.file.path()

        def prepare(doc):
            # the file's size: the job's copy of the document is in memory
            orig[0] = Path(src).stat().st_size

        def work(doc, out, stop, progress):
            core_enhance.compress_pdf(doc, out, level)
            return Path(out).stat().st_size

        self.run_on_file("Compress", work, "Compressing PDF…", None, prepare=prepare,
                         cancellable=False, warning_box=True, in_place="Compress",
                         applied=lambda new: size_report(orig[0], new))
