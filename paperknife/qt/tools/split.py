"""Split — a page organiser (group B): cut one PDF into files.

Owner, 2026-10-17: Split by Bookmarks is one of Split's "Cut at" choices; the
pages are on screen as thumbnails, with the parts as coloured groups: a click
in the gap between two pages cuts there, "Selected pages to one part" makes a
part of scattered pages, and the range field and the bookmark choices set the
same parts.  The parts to be written are listed in the settings column.

The page holds the chosen PDF open (HeldDoc) for its thumbnails and bookmarks,
so an encrypted file asks for its password once; the job works on a copy."""
from __future__ import annotations

from pathlib import Path

import pymupdf as fitz
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QHBoxLayout, QWidget
from qfluentwidgets import BodyLabel, LineEdit

from ...core import organise
from ...core.password import carry_open_password
from ...pages import PageRangeError, parse_parts, parts_text
from .. import theme
from ..pages import (HeldDoc, OrganiserPage, Refusal, _clear_layout, card, group_title,
                     muted_caption, radio_rows, register_page)

RANGES, TOP, ALL = "ranges", "top", "all"
CUT_AT = [(RANGES, "Page ranges", ""), (TOP, "Bookmarks, top level", ""),
          (ALL, "Bookmarks, all levels", "")]
RANGES_HINT = ("e.g.  1-3, 5, 7-9 · join pages with + for one part (2+5+7) · "
               "blank: every page on its own")
HINT = "Click the gap between two pages to cut there"
NO_BOOKMARKS = "⚠  This PDF has no bookmarks."
SHOWN = 60                  # parts listed
THUMB_ZOOM = 0.28


def _pages_text(pages) -> str:
    text = parts_text([list(pages)]).replace("+", ", ")
    return f"page {text}" if len(pages) == 1 else f"pages {text}"


@register_page("SplitTool")
class SplitPage(HeldDoc, OrganiserPage):
    def __init__(self, tool=None, window=None):
        super().__init__("Split", "Extract pages or page ranges", tool=tool, window=window,
                         settings=True, drag_reorder=False, hint=HINT)
        self._toc: list = []
        self._parts: list[list[int]] = []
        self._problem = ""
        self._skipped = 0
        self._chapters: list = []
        self.enable_gaps(self._toggle_cut)
        self.add_action("Selected pages to one part", None, self._selection_to_part)

        self.settings.addWidget(group_title("Cut at"))
        group = card(padding=0)
        self.settings.addWidget(group)

        def row(g, title, desc):
            control = self.setting_row(g, title, desc)
            if title == CUT_AT[0][1]:
                # The range field sits right under its choice, shown only with it.
                self._range_row = self.setting_row(g, "", RANGES_HINT)
                self.ranges = LineEdit()
                self.ranges.setPlaceholderText("e.g.  1-3, 5, 7-9")
                self.ranges.setClearButtonEnabled(True)
                self.ranges.setMinimumWidth(160)
                self._range_row.layout().addWidget(self.ranges)
            return control
        self.cut_at = radio_rows(group, CUT_AT, RANGES, row=row, parent=self)
        self.radios = self.cut_at.buttons
        self.cut_at.buttonToggled.connect(lambda _b, on: on and self._recompute())
        self.ranges.textChanged.connect(lambda *_: self._recompute())

        self.parts_title = group_title("Parts")
        self.settings.addWidget(self.parts_title)
        self.parts_card = card(padding=12)
        self.parts_lay = self.parts_card.layout()
        self.parts_lay.setSpacing(4)
        self.settings.addWidget(self.parts_card)
        self.settings.addStretch(1)
        self.primary("Split", self.run)
        self._recompute()

    # ── document ─────────────────────────────────────────────────────────────
    def load(self, path: str):
        if not path:
            return
        doc = self.open_held(path, "Split")
        if doc is None:
            return
        self._toc = doc.get_toc()
        self.set_pages(list(range(len(doc))), self.render, lambda k: f"p.{k + 1}")
        self._recompute()

    def render(self, key: int) -> QImage:
        pix = self._doc[key].get_pixmap(matrix=fitz.Matrix(THUMB_ZOOM, THUMB_ZOOM), alpha=False)
        return QImage(pix.samples, pix.width, pix.height, pix.stride,
                      QImage.Format_RGB888).copy()

    def clear_document(self):
        self._timer.stop()
        self.clear_pages()
        self.release_held()
        self._toc = []
        self._recompute()
        self.refresh_document()

    def park_document(self):
        if self._doc is not None:
            self._timer.stop()              # no thumbnail may render from a closed file
            self._queue = []
        super().park_document()

    @property
    def mode(self) -> str:
        return self.cut_at.value()

    def parts(self) -> list[list[int]]:
        return [list(p) for p in self._parts]

    # ── the parts ────────────────────────────────────────────────────────────
    def _recompute(self):
        """The parts from the Cut at choice; then the grid, the field and the list."""
        doc = self._doc
        for value in (TOP, ALL):
            self.radios[value].setEnabled(doc is not None and bool(self._toc))
        if self.mode != RANGES and not (doc is not None and self._toc):
            self.radios[RANGES].setChecked(True)
            return                          # the toggle recomputes
        self._parts, self._problem, self._skipped = [], "", 0
        if doc is not None:
            total = len(doc)
            if self.mode == RANGES:
                try:
                    self._parts = parse_parts(self.ranges.text(), total)
                except PageRangeError as e:
                    self._problem = f"⚠  {e}"
            else:
                entries, self._skipped = organise.bookmark_chapters(
                    self._toc, total, self.mode == ALL)
                self._chapters = entries
                self._parts = [list(range(start, entries[i + 1][1]))
                               for i, (_t, start) in enumerate(entries[:-1])
                               if start < entries[i + 1][1]]
                if not self._parts:
                    self._problem = "⚠  No matching bookmarks point to a page."
        self._show()

    def _set_parts(self, parts):
        """Parts made on the grid: they become the Page ranges text."""
        self.cut_at.blockSignals(True)
        self.radios[RANGES].setChecked(True)
        self.cut_at.blockSignals(False)
        self.ranges.blockSignals(True)
        self.ranges.setText(parts_text(parts))
        self.ranges.blockSignals(False)
        self._recompute()

    def _toggle_cut(self, i: int):
        """A click in the gap after page i: cut its part there, or join it
        with the next part when that part starts on the next page."""
        if self._doc is None or self._problem:
            return
        parts = self.parts()
        here = next((k for k, p in enumerate(parts) if i in p), None)
        nxt = next((k for k, p in enumerate(parts) if i + 1 in p), None)
        if here is not None and here == nxt:
            p = parts[here]
            if p == list(range(p[0], p[-1] + 1)):          # a run: cut it at i
                cut = p.index(i) + 1
                parts[here:here + 1] = [p[:cut], p[cut:]]
            else:                                           # scattered: take i+1 on
                parts[here:here + 1] = [[q for q in p if q <= i], [q for q in p if q > i]]
        elif here is not None and nxt == here + 1 and parts[here][-1] == i \
                and parts[nxt][0] == i + 1:
            parts[here:nxt + 1] = [parts[here] + parts[nxt]]   # the cut goes
        else:
            return
        self._set_parts(parts)

    def _selection_to_part(self):
        from ...pages import take_part
        rows = self.selected()
        if not rows or self._doc is None or self._problem:
            return
        order = self.order()
        self._set_parts(take_part(self.parts(), [order[r] for r in rows]))

    def _show(self):
        has_doc = self._doc is not None
        ranges = self.mode == RANGES
        self._range_row.parentWidget().setVisible(ranges)
        if self._range_row.divider is not None:
            self._range_row.divider.setVisible(ranges)
        # The grid: each page's part, and a cut between pages of two parts in a row.
        part_of = {p: k + 1 for k, part in enumerate(self._parts) for p in part}
        cuts = {part[-1] for k, part in enumerate(self._parts[:-1])
                if self._parts[k + 1] and self._parts[k + 1][0] == part[-1] + 1}
        self.set_marks(None if self._problem or not has_doc else part_of, cuts)
        # The list.
        self.parts_title.setVisible(has_doc)
        self.parts_card.setVisible(has_doc)
        _clear_layout(self.parts_lay)
        if not has_doc:
            return
        self.parts_title.setText(f"Parts ({len(self._parts)})" if self._parts else "Parts")
        if self._problem:
            msg = BodyLabel(self._problem)
            theme.label_role(msg, "warning")
            msg.setWordWrap(True)
            self.parts_lay.addWidget(msg)
            return
        names = (self._part_names() if not ranges else
                 [f"Part {k + 1:02d}" for k in range(len(self._parts))])
        for name, pages in list(zip(names, self._parts, strict=True))[:SHOWN]:
            line = QWidget()
            h = QHBoxLayout(line)
            h.setContentsMargins(0, 0, 0, 0)
            h.addWidget(BodyLabel(name), 1)
            h.addWidget(muted_caption(_pages_text(pages)))
            self.parts_lay.addWidget(line)
        if len(self._parts) > SHOWN:
            self.parts_lay.addWidget(muted_caption(f"… and {len(self._parts) - SHOWN} more"))
        if self._skipped:
            self.parts_lay.addWidget(muted_caption(
                f"{self._skipped} bookmark(s) with no page target will be skipped."))

    def _part_names(self) -> list[str]:
        entries = self._chapters
        return [f"{i + 1:02d} {title}" for i, (title, start) in enumerate(entries[:-1])
                if start < entries[i + 1][1]]

    def part_lines(self) -> list[str]:
        """What the parts list shows, one string per line."""
        out = []
        for i in range(self.parts_lay.count()):
            w = self.parts_lay.itemAt(i).widget()
            if w is None:
                continue
            if hasattr(w, "text"):
                out.append(w.text())
            else:
                lay = w.layout()
                out.append(" · ".join(lay.itemAt(j).widget().text() for j in range(lay.count())))
        return out

    # ── split ────────────────────────────────────────────────────────────────
    def _copy(self, _src):
        """The job's own copy of the held document (its password goes with it)."""
        copy = fitz.open("pdf", self._doc.tobytes())
        carry_open_password(self._doc, copy)
        return copy

    def run(self):
        src = self.chosen_file("Split")
        if not src or self._doc is None:
            return
        mode, base = self.mode, Path(src).stem
        parts = self.parts()
        entries = list(getattr(self, "_chapters", [])) if mode != RANGES else []
        skipped = self._skipped

        def prepare(doc):
            if self._problem:
                if mode != RANGES:
                    raise Refusal(self._problem.removeprefix("⚠  "))
                raise PageRangeError(self._problem.removeprefix("⚠  "))

        def work(doc, out_dir, stop, progress):
            with doc:                   # the job owns its copy from here
                if mode == RANGES:
                    return organise.split_parts(doc, parts, out_dir, base, stop, progress)
                return organise.split_chapters(doc, entries, out_dir, stop, progress,
                                               release=self._release)

        def report(count, out_dir):
            if mode == RANGES:
                return ("success", f"✓  Split into {len(parts)} file(s) → {out_dir}",
                        "Done", f"Created {len(parts)} file(s) in:\n{out_dir}")
            note = (f"\n\n{skipped} bookmark(s) with no page target were skipped."
                    if skipped else "")
            return ("success", f"✓  Split into {count} chapter(s) → {out_dir}",
                    "Done", f"Split into {count} file(s):\n{out_dir}{note}")

        self.run_on_file("Split", work, f"Splitting into {len(parts)} file(s)…", report,
                         src=src, prepare=prepare, open_doc=self._copy, parts=True)
