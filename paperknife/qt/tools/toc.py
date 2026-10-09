"""Bookmarks / TOC — a structured editor (group E): the bookmark list, and the
selected entry's Level, Title and Page with an explicit "Update selected"."""
from __future__ import annotations

from pathlib import Path

import pymupdf as fitz
from qfluentwidgets import ComboBox, FluentIcon, LineEdit, PushButton

from ...core import organise
from ...core.doc_state import DocHolder
from .. import dialogs
from ..pages import MasterDetailPage, register_page

LEVELS = ["1", "2", "3", "4"]


def entry_text(entry) -> str:
    """One list line, as the CTk list shows it: indent by level, title, page."""
    level, title, page, *_ = entry
    return f"{'  ' * (level - 1)}▸ {title}  (p.{page})"


@register_page("TocTool")
class TocPage(DocHolder, MasterDetailPage):
    save_name = "with_bookmarks.pdf"

    def __init__(self, tool=None, window=None):
        super().__init__("Bookmarks / TOC",
                         "View · add · edit · delete · reorder PDF bookmarks",
                         tool=tool, window=window,
                         empty_text="Open a PDF to see its bookmarks")
        self._toc: list = []            # [level, title, page] per bookmark
        self._path = ""                 # the file self._doc was opened from
        self.add_tool("Add below", FluentIcon.ADD, self._add)
        self.add_tool("Up", FluentIcon.UP, lambda: self._move(-1), needs_selection=True)
        self.add_tool("Down", FluentIcon.DOWN, lambda: self._move(1), needs_selection=True)
        self.add_tool("Delete", FluentIcon.DELETE, self._delete, needs_selection=True)
        self._build_detail()
        self.primary("Save PDF", self.save)

    # ── detail column ────────────────────────────────────────────────────────
    def _build_detail(self):
        self.detail_begin("Bookmark", "Select a bookmark to edit it, or fill these in "
                                      "and add a new one below the selection.")
        self.level = ComboBox()
        self.level.addItems(LEVELS)
        self.level.setCurrentIndex(0)
        self.level.setFixedWidth(90)
        self.detail_field("Level").addWidget(self.level)
        self.title_edit = LineEdit()
        self.title_edit.setPlaceholderText("New bookmark")
        self.title_edit.setClearButtonEnabled(True)
        self.detail_field("Title").addWidget(self.title_edit)
        self.page_edit = LineEdit()
        self.page_edit.setFixedWidth(90)
        self.detail_field("Page").addWidget(self.page_edit)
        self.detail.addSpacing(16)
        self.update_btn = PushButton(FluentIcon.EDIT, "Update selected")
        self.update_btn.clicked.connect(self._update_sel)
        self.update_btn.setEnabled(False)
        self.detail.addWidget(self.update_btn)

    def on_select(self, i):
        self.update_btn.setEnabled(i is not None)
        if i is None or i >= len(self._toc):
            return
        level, title, page, *_ = self._toc[i]
        if str(level) in LEVELS:
            self.level.setCurrentText(str(level))
        self.title_edit.setText(title)
        self.page_edit.setText(str(page))

    def _refresh_list(self, keep=None):
        self.set_items([entry_text(e) for e in self._toc], keep=keep)

    # ── document ─────────────────────────────────────────────────────────────
    def open_path(self, path: str):
        self.file.set_path(path)

    def load(self, path: str):
        if not path:
            return self._clear()
        doc = self.window_.open_pdf_safe(path) if self.window_ is not None else None
        if doc is None:
            # Keep what was open; the card goes back to it.
            self.file.set_path(self._path if self._doc is not None else "", notify=False)
            return
        self._close_doc()
        self._doc, self._path = doc, path
        self._toc = [list(e) for e in doc.get_toc()]
        self.set_title("Bookmarks / TOC", Path(path).name)
        self._refresh_list()

    def _clear(self):
        self._close_doc()
        self._toc, self._path = [], ""
        self.set_title("Bookmarks / TOC",
                       "View · add · edit · delete · reorder PDF bookmarks")
        self._refresh_list()

    def deactivate(self):
        self._clear()
        self.file.clear()

    # ── edit operations ──────────────────────────────────────────────────────
    def _move(self, d: int):
        i = self.current()
        if i is None:
            return
        j = i + d
        if 0 <= j < len(self._toc):
            self._toc[i], self._toc[j] = self._toc[j], self._toc[i]
            self._refresh_list(keep=j)

    def _read_fields(self, title: str):
        if self._doc is None:
            dialogs.warning(title, "Open a PDF first.")
            return None
        try:
            lvl = int(self.level.currentText())
            pg = int(self.page_edit.text())
        except ValueError:
            dialogs.warning(title, "Enter valid level and page number.")
            return None
        if not 1 <= pg <= len(self._doc):
            dialogs.warning(title, f"Page must be between 1 and {len(self._doc)}.")
            return None
        return lvl, pg

    def _add(self):
        fields = self._read_fields("Add")
        if not fields:
            return
        lvl, pg = fields
        title = self.title_edit.text().strip() or "New bookmark"
        i = self.current()
        ins = (i + 1) if i is not None else len(self._toc)
        self._toc.insert(ins, [lvl, title, pg])
        self._refresh_list(keep=ins)

    def _update_sel(self):
        i = self.current()
        if i is None:
            return
        fields = self._read_fields("Update")
        if not fields:
            return
        lvl, pg = fields
        self._toc[i] = [lvl, self.title_edit.text().strip(), pg]
        self._refresh_list(keep=i)

    def _delete(self):
        i = self.current()
        if i is None:
            return
        organise.delete_entry(self._toc, i)
        self._refresh_list()

    def delete(self):
        self._delete()

    # ── save ─────────────────────────────────────────────────────────────────
    def save(self):
        if self._doc is None:
            return dialogs.warning("Save", "Open a PDF first.")
        problem = organise.toc_level_error(self._toc)
        if problem:
            return dialogs.warning("Save", problem)
        out = dialogs.ask_save(self.save_name, ".pdf", [("PDF", "*.pdf")])
        if not out:
            return
        toc = [list(item) for item in self._toc]
        win = self.window_

        def work(stop):
            self._doc.set_toc(toc)
            # Saving over the source keeps its password; a copy elsewhere is
            # written unprotected.
            keep = {"encryption": fitz.PDF_ENCRYPT_KEEP} if self._holds(out) else {}
            self._save_doc(out, deflate=True, **keep)

        def then(kind, _value):
            if kind != "done":
                return
            win.set_status(f"✓  Saved {len(toc)} bookmark(s) → {Path(out).name}", "success")
            dialogs.info("Saved", f"PDF with updated bookmarks:\n{out}")

        win.run_job(work, f"Saving {Path(out).name}…", lock=True, then=then, cancellable=False)
