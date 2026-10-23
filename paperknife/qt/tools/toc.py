"""Bookmarks / TOC — a structured editor (group E): the bookmark list, and the
selected entry's Level, Title and Page with an explicit "Update selected"."""
from __future__ import annotations

from collections import Counter
from qfluentwidgets import ComboBox, FluentIcon, LineEdit, PushButton

from ...core import organise
from .. import dialogs
from ..pages import HeldDoc, MasterDetailPage, register_page

LEVELS = ["1", "2", "3", "4"]


def entry_text(entry) -> str:
    """One list line: indent by level, title, page."""
    level, title, page, *_ = entry
    return f"{'  ' * (level - 1)}▸ {title}  (p.{page})"


@register_page("TocTool")
class TocPage(HeldDoc, MasterDetailPage):
    save_name = "with_bookmarks.pdf"

    def __init__(self, tool=None, window=None):
        super().__init__("Bookmarks / TOC",
                         "View · add · edit · delete · reorder PDF bookmarks",
                         tool=tool, window=window,
                         empty_text="Open a PDF to see its bookmarks")
        self._toc: list = []            # [level, title, page] per bookmark
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
    def load(self, path: str):
        if not path:
            return self._clear()
        doc = self.open_held(path, "Bookmarks / TOC")
        if doc is None:
            return
        self._show_document_toc()

    def _clear(self):
        self.release_held()
        self._toc = []
        self._saved_toc = []
        self._refresh_list()
        self.refresh_document()

    def clear_document(self):
        self._clear()

    _saved_toc: list = []

    def _show_document_toc(self):
        self._toc = [list(e) for e in self._doc.get_toc()]
        self._saved_toc = [list(e) for e in self._toc]
        self._refresh_list()

    def has_pending(self) -> bool:
        """Bookmarks added, changed, moved or deleted here and not applied yet."""
        return self._doc is not None and self._toc != self._saved_toc

    def commit_edits(self) -> bool:
        """The bookmark list into the document, as one undoable edit."""
        if not self.has_pending():
            return True
        problem = organise.toc_level_error(self._toc)
        if problem:
            dialogs.warning("Save", problem)
            return False
        toc = [list(item) for item in self._toc]
        # Bookmarks only added (every title there was is still there): appended
        # to the file on Save (owner's choice 2026-10-12); one renamed or
        # deleted is written whole, so its old title goes.
        adds = not (Counter(e[1] for e in self._saved_toc) - Counter(e[1] for e in toc))
        self.edit_document("Bookmarks", lambda d: d.set_toc(toc), adds=adds)
        self._saved_toc = [list(e) for e in toc]
        return True

    def document_replaced(self):
        if self._doc is not None and not self.has_pending():
            self._show_document_toc()

    def recovery_extra(self) -> dict:
        """A list edited and not applied: crash recovery copies it too."""
        return {"toc": [list(e[:3]) for e in self._toc]} if self.has_pending() else {}

    def restore_extra(self, state: dict) -> None:
        toc = state.get("toc")
        if toc is not None:
            self._toc = [[int(level), str(title), int(page)] for level, title, page in toc]
            self._refresh_list()

    def drop_marks(self):
        if self._doc is not None:
            self._show_document_toc()

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

    # ── save (the window's: the list is applied first) ───────────────────────
    def save(self, after=None):
        if self._doc is None:
            return dialogs.warning("Save", "Open a PDF first.")
        return self.window_.save(after)
