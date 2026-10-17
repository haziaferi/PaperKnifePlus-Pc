"""Merge — PDFs in order, each with its own page range, and every input's pages
on screen (owner, 2026-10-17): one strip in merged order, each run of a file's
pages under a heading row; pages are left out and put back with the bar's
buttons (a left-out page stays in place, veiled) and dragged to any place, so
the merged file follows the strip.  The files, their range fields and Add /
Up / Down / Remove sit in the column at the right.

A file is read when it is added: an in-memory copy (with its open password,
asked once) gives the thumbnails and the merge, so no input stays locked on
disk and the list can be kept while other tools are used."""
from __future__ import annotations

from pathlib import Path

import pymupdf as fitz
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon, QImage, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import LineEdit

from ...core import organise
from ...core.password import carry_open_password
from ...pages import PageRangeError, parse_ranges, ranges_text, selected_pages
from .. import dialogs
from ..pages import (SETTINGS_W, THUMB_BOX, THUMBS_PER_TICK, CollectionPage, Divider, ElidedLabel,
                     PageStrip, _tool_button, ask_keep_password, icon_button, muted_caption,
                     plain_card, register_page)

RANGE_PLACEHOLDER = "all  or  1-3, 5, 8-end"
HINT = ("Add PDFs in order · optionally set page ranges per file"
        " (e.g.  1-3, 5, 8-end)  ·  leave blank to include all pages")
STRIP_HINT = "Select pages to leave out or put back · drag them to a new place"
THUMB_ZOOM = 0.28


@register_page("MergeTool")
class MergePage(CollectionPage):
    def __init__(self, tool=None, window=None):
        super().__init__("Merge", "Combine PDFs · set per-file page ranges",
                         tool=tool, window=window, exts=(".pdf",), add_text="Add PDFs",
                         empty_text=HINT, settings=False)
        self._docs: dict[int, fitz.Document] = {}
        self._names: dict[int, str] = {}
        self._next_fid = 0
        self._order: list[tuple[int, int]] = []        # (file, page) in merged order
        self._out: set[tuple[int, int]] = set()        # pages left out
        self._queue: list = []
        self._timer = QTimer(self, interval=0, timeout=self._render_some)
        self._build_strip()
        self.primary("Merge", self.run)

    # ── layout: the strip in the centre, the file list at the right ────────
    def _build_strip(self):
        cols = next(self.body.itemAt(i).layout() for i in range(self.body.count())
                    if self.body.itemAt(i).layout() is not None
                    and self.body.itemAt(i).layout().indexOf(self.list_card) >= 0)
        cols.removeWidget(self.list_card)
        card = plain_card()
        v = QVBoxLayout(card)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        bar = QWidget(card)
        bar.setObjectName("contextBar")
        h = QHBoxLayout(bar)
        h.setContentsMargins(8, 6, 8, 6)
        h.setSpacing(4)
        self.leave_btn = _tool_button("Leave out", None, self.leave_out, True, parent=bar)
        self.back_btn = _tool_button("Put back", None, self.put_back, True, parent=bar)
        h.addWidget(self.leave_btn)
        h.addWidget(self.back_btn)
        h.addStretch(1)
        self.strip_label = muted_caption(STRIP_HINT)
        h.addWidget(self.strip_label)
        self.strip_bar = bar
        v.addWidget(bar)
        self.strip_rule = Divider()
        v.addWidget(self.strip_rule)
        self.strip = PageStrip(self._moved, self._strip_selection, card)
        v.addWidget(self.strip, 1)
        self.strip_empty = muted_caption(HINT)
        self.strip_empty.setWordWrap(True)
        self.strip_empty.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        self.strip_empty.setContentsMargins(24, 48, 24, 48)
        v.addWidget(self.strip_empty, 1)
        self.strip_card = card
        cols.insertWidget(0, card, 1)
        self.list_card.setFixedWidth(SETTINGS_W)
        cols.addWidget(self.list_card)
        # The column is narrow: Up, Down and Remove keep their icon, their
        # name moves to the tooltip, so Add PDFs keeps its text.
        from qfluentwidgets import FluentIcon as FIF
        for name, icon, slot in (("up_btn", FIF.UP, lambda: self.move(-1)),
                                 ("down_btn", FIF.DOWN, lambda: self.move(1)),
                                 ("remove_btn", FIF.DELETE, self.remove_selected)):
            old = getattr(self, name)
            b = icon_button(icon)
            b.setToolTip(old.text())
            b.clicked.connect(slot)
            self.toolbar.replaceWidget(old, b)
            old.hide()
            old.deleteLater()
            setattr(self, name, b)
        self._refresh()
        self._show()

    # ── files ────────────────────────────────────────────────────────────────
    def make_extra(self, path: str):
        ed = LineEdit()
        ed.setPlaceholderText(RANGE_PLACEHOLDER)
        ed.setFixedWidth(120)
        ed.setToolTip("Pages")
        return ed

    def ranges(self) -> list[str]:
        return [r.extra.text().strip() for r in self.rows]

    def add_paths(self, paths) -> int:
        n = 0
        win = self.window_
        for p in paths:
            src = win.open_pdf_safe(str(p)) if win is not None else fitz.open(str(p))
            if src is None:
                continue
            mem = fitz.open("pdf", src.tobytes())
            carry_open_password(src, mem)
            src.close()
            super().add_paths([p])
            fid, self._next_fid = self._next_fid, self._next_fid + 1
            row = self.rows[-1]
            row.pk_fid = fid
            # The column is narrow: the name shortens in the middle.
            name = ElidedLabel(Path(p).name)
            name.setToolTip(str(p))
            texts = row.layout().itemAt(1).layout()
            texts.replaceWidget(row.name_label, name)
            row.name_label.hide()
            row.name_label.deleteLater()
            row.name_label = name
            self._docs[fid], self._names[fid] = mem, Path(p).name
            self._order += [(fid, i) for i in range(len(mem))]
            row.extra.textChanged.connect(lambda _t, fid=fid: self._range_edited(fid))
            n += 1
        self._rebuild()
        return n

    def remove_selected(self):
        i = self.selected_index()
        fid = self.rows[i].pk_fid if i is not None and i < len(self.rows) else None
        super().remove_selected()
        if fid is not None:
            self._forget(fid)
            self._rebuild()

    def _forget(self, fid):
        self._order = [k for k in self._order if k[0] != fid]
        self._out = {k for k in self._out if k[0] != fid}
        doc = self._docs.pop(fid, None)
        self._names.pop(fid, None)
        if doc is not None:
            doc.close()

    def clear_rows(self):
        for fid in list(self._docs):
            self._forget(fid)
        super().clear_rows()
        if hasattr(self, "strip"):
            self._rebuild()

    def move(self, d: int):
        """Up / Down: the file moves, and the strip follows the list: each file's
        pages together again, in the order they have in the strip."""
        super().move(d)
        rank = {getattr(r, "pk_fid", -1): k for k, r in enumerate(self.rows)}
        self._order.sort(key=lambda k: rank.get(k[0], 0))     # stable: a file keeps its order
        self._rebuild()

    # ── page ranges and leaving out ─────────────────────────────────────────
    def _row(self, fid):
        return next((r for r in self.rows if getattr(r, "pk_fid", None) == fid), None)

    def _range_edited(self, fid):
        row, doc = self._row(fid), self._docs.get(fid)
        if row is None or doc is None:
            return
        try:
            keep = set(selected_pages(row.extra.text(), len(doc)))
        except PageRangeError:
            return                          # said when Merge runs
        self._out = {k for k in self._out if k[0] != fid} | {
            (fid, p) for p in range(len(doc)) if p not in keep}
        self._show_veils()

    def _sync_field(self, fid):
        row, doc = self._row(fid), self._docs.get(fid)
        if row is None or doc is None:
            return
        kept = [p for p in range(len(doc)) if (fid, p) not in self._out]
        row.extra.blockSignals(True)
        row.extra.setText("" if len(kept) == len(doc) else ranges_text(kept))
        row.extra.blockSignals(False)

    def leave_out(self):
        keys = self.strip.selected_keys()
        self._out |= set(keys)
        for fid in {k[0] for k in keys}:
            self._sync_field(fid)
        self._show_veils()

    def put_back(self):
        keys = set(self.strip.selected_keys())
        self._out -= keys
        for fid in {k[0] for k in keys}:
            self._sync_field(fid)
        self._show_veils()

    def left_out(self) -> list:
        return [k for k in self._order if k in self._out]

    # ── the strip ────────────────────────────────────────────────────────────
    def runs(self) -> list[tuple[int, list[int]]]:
        """The strip's runs: (file, its pages in strip order), a new run each
        time the file changes."""
        out = []
        for fid, p in self._order:
            if out and out[-1][0] == fid:
                out[-1][1].append(p)
            else:
                out.append((fid, [p]))
        return out

    def _heading(self, fid, pages) -> str:
        n = len(self._docs[fid])
        if pages == list(range(n)) and sum(1 for f, _ in self.runs() if f == fid) == 1:
            return f"{self._names[fid]} · {n} page{'s' if n != 1 else ''}"
        text = ranges_text(pages) if pages == sorted(pages) else ", ".join(str(p + 1) for p in pages)
        return f"{self._names[fid]} · page{'s' if len(pages) != 1 else ''} {text}"

    def headings(self) -> list[str]:
        return [h.text() for h in self.strip.headings]

    def _rebuild(self):
        self.strip.set_runs([(self._heading(fid, pages), [(fid, p) for p in pages])
                             for fid, pages in self.runs()],
                            lambda k: f"p.{k[1] + 1}")
        self._show_veils()
        self._queue = [k for k in self._order if not self.strip.has_icon(k)]
        if self._queue:
            self._timer.start()
        self._show()

    def _show_veils(self):
        self.strip.set_veiled(self._out)
        self._strip_selection()

    def _show(self):
        has = bool(self._order)
        for w in (self.strip, self.strip_bar, self.strip_rule):
            w.setVisible(has)
        self.strip_empty.setVisible(not has)

    def _strip_selection(self):
        n = len(self.strip.selected_keys())
        self.leave_btn.setEnabled(bool(n))
        self.back_btn.setEnabled(bool(n))
        going = sum(1 for k in self._order if k not in self._out)
        self.strip_label.setText(
            f"{n} page{'s' if n != 1 else ''} selected" if n else
            (f"{going} page{'s' if going != 1 else ''} to merge" if self._order else STRIP_HINT))

    def _moved(self, keys, target, after):
        keys = [k for k in keys if k in set(self._order)]
        if not keys or target in keys:
            return
        moving = set(keys)
        rest = [k for k in self._order if k not in moving]
        at = rest.index(target) + (1 if after else 0)
        self._order = rest[:at] + keys + rest[at:]
        self._rebuild()
        self.strip.select_keys(keys)

    def _render_some(self):
        for _ in range(THUMBS_PER_TICK):
            if not self._queue:
                self._timer.stop()
                return
            key = self._queue.pop(0)
            doc = self._docs.get(key[0])
            if doc is None or doc.is_closed:
                continue
            pix = doc[key[1]].get_pixmap(matrix=fitz.Matrix(THUMB_ZOOM, THUMB_ZOOM), alpha=False)
            img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888).copy()
            pm = QPixmap.fromImage(img)
            if pm.width() > THUMB_BOX[0] or pm.height() > THUMB_BOX[1]:
                pm = pm.scaled(*THUMB_BOX, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.strip.set_icon(key, QIcon(pm))

    def rendering(self) -> bool:
        return bool(self._queue)

    # ── merge ────────────────────────────────────────────────────────────────
    def run(self):
        if not self.rows:
            return dialogs.warning("Merge", "Add at least one PDF file.")
        win = self.window_
        # Every range checked first, so a bad one stops the merge before it starts.
        for row in self.rows:
            text = row.extra.text().strip()
            if text:
                try:
                    parse_ranges(text, len(self._docs[row.pk_fid]))
                except PageRangeError as err:
                    return dialogs.error("Merge", f"{Path(row.path).name}:\n{err}")
        runs = []
        for fid, pages in self.runs():
            pages = [p for p in pages if (fid, p) not in self._out]
            if pages:
                if runs and runs[-1][0] is self._docs[fid]:
                    runs[-1][1].extend(pages)
                else:
                    runs.append((self._docs[fid], pages, self._names[fid]))
        if not runs:
            return dialogs.warning("Merge", "Every page is left out: put back at least one.")
        out = dialogs.ask_save("merged.pdf", ".pdf", [("PDF", "*.pdf")])
        if not out:
            return
        docs = list(dict.fromkeys(doc for doc, _, _ in runs))
        kept = ask_keep_password(*docs)
        n = len(docs)

        def work(stop):
            return organise.merge_runs(runs, out, stop, win.progress_callback())

        def then(kind, pg_total):
            if kind != "done":
                return
            win.set_status(f"✓  Merged {n} file(s) · {pg_total} pages → "
                           f"{Path(out).name}", "success")
            dialogs.info("Merge Complete", f"Merged PDF saved:\n{out}")
            self.clear_rows()               # a finished job empties the list (owner)
            self.offer_output(out)

        win.set_status("Merging…")
        win.run_job(work, f"Merging {n} PDF(s)…", then=then, keep_password=(kept, [out]))
