"""Merge — a collection page (group D): PDFs in order, each with its own page range."""
from __future__ import annotations

from pathlib import Path

from qfluentwidgets import LineEdit

from ...core import organise
from ...pages import PageRangeError, parse_ranges
from .. import bridge, dialogs
from ..pages import CollectionPage, register_page

RANGE_PLACEHOLDER = "all  or  1-3, 5, 8-end"
HINT = ("Add PDFs in order · optionally set page ranges per file"
        " (e.g.  1-3, 5, 8-end)  ·  leave blank to include all pages")


@register_page("MergeTool")
class MergePage(CollectionPage):
    def __init__(self, tool=None, window=None):
        super().__init__("Merge", "Combine PDFs · set per-file page ranges",
                         tool=tool, window=window, exts=(".pdf",), add_text="Add PDFs",
                         empty_text=HINT, settings=False)
        self.primary("Merge", self.run)

    def make_extra(self, path: str):
        ed = LineEdit()
        ed.setPlaceholderText(RANGE_PLACEHOLDER)
        ed.setFixedWidth(180)
        ed.setToolTip("Pages")
        return ed

    def ranges(self) -> list[str]:
        return [r.extra.text().strip() for r in self.rows]

    def run(self):
        if not self.rows:
            return dialogs.warning("Merge", "Add at least one PDF file.")
        win = self.window_
        # Open (and unlock) every input and check its range first, so a
        # password prompt or a bad range stops the merge before it starts.
        jobs = []

        def close_all():
            for _, d, _ in jobs:
                if not d.is_closed:
                    d.close()

        for path, rng in zip(self.paths(), self.ranges(), strict=True):
            src = win.open_pdf_safe(path)
            if src is None:
                return close_all()
            try:
                groups = (parse_ranges(rng, len(src)) if rng
                          else [(0, len(src) - 1)])
            except PageRangeError as err:
                src.close()
                close_all()
                return dialogs.error("Merge", f"{Path(path).name}:\n{err}")
            jobs.append((path, src, groups))
        out = dialogs.ask_save("merged.pdf", ".pdf", [("PDF", "*.pdf")])
        if not out:
            return close_all()
        n = len(jobs)

        def work(stop):
            try:
                return organise.merge(
                    [(src, groups) for _, src, groups in jobs], out, stop,
                    lambda v: bridge.post(win.set_progress, v))
            finally:
                close_all()

        def then(kind, pg_total):
            if kind != "done":
                return
            win.set_status(f"✓  Merged {n} file(s) · {pg_total} pages → "
                           f"{Path(out).name}", "success")
            dialogs.info("Merge Complete", f"Merged PDF saved:\n{out}")

        win.set_status("Merging…")
        if win.run_job(work, f"Merging {n} PDF(s)…", then=then) is None:
            close_all()
