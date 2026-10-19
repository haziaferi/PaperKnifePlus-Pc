"""Redact — a document workspace (group A).

Drawn boxes and search matches are overlays on the page view until the primary
action: after the confirmation it burns them in through core.redact (line art
cut at the box edge, the phrases scrubbed from metadata, bookmarks, attachments,
notes and fields) and saves with garbage collection, all in one job."""
from __future__ import annotations

from pathlib import Path

import pymupdf as fitz
from qfluentwidgets import BodyLabel, ComboBox, LineEdit, ListWidget, PushButton

from ...core import redact as core_redact
from .. import dialogs, theme
from ..pages import (WorkspaceDoc, WorkspacePage, ask_keep_password, muted_caption,
                     register_page, same_path)

PAGES_ONLY_QUESTION = "Save the page changes? No redaction boxes are drawn."

# Segoe Fluent Icons code points
GLYPHS = {"box": 0xE739, "search": 0xE721, "undo": 0xE7A7}
TOOLS = {
    "box": ("Draw box", "Draw rectangles over sensitive content."),
    "search": ("Find & redact text", "Mark every occurrence of a phrase on every page."),
}
SUBTITLE = "Draw rectangles over sensitive content"
WARN_TITLE = "⚠  Redaction is permanent and irreversible once applied."
WARN_BODY = ("Content under redaction boxes is completely destroyed — "
             "not merely covered. Always work on a copy.")


@register_page("RedactTool")
class RedactPage(WorkspaceDoc, WorkspacePage):
    save_name = "redacted.pdf"
    saved_what = "PDF"

    def __init__(self, tool=None, window=None):
        super().__init__("Redact", SUBTITLE, tool=tool, window=window, page_strip=True)
        self._undo_stack: list = []         # page changes (PagesStep); boxes undo as _pending
        self.kind = "box"
        self.fill = "Black"
        self.search_text = ""
        # (page number, fitz.Rect in unrotated page space, search phrase or None)
        self._pending: list = []
        # phrase burned out of page content -> match whole words only (drawn boxes)
        self._secrets: dict[str, bool] = {}
        for key, (name, _desc) in TOOLS.items():
            self.add_rail(key, GLYPHS[key], name, lambda _=False, k=key: self.set_kind(k))
        self.add_pages_tool()
        self.add_rail_gap()
        self.add_rail("undo", GLYPHS["undo"], "Undo last (Ctrl+Z)", self.undo, toggle=False)
        self.primary("Apply and save", self.save, danger=True)
        self.enable_band(lambda: ("rect", theme.hex_color("danger")), self._add_box,
                         drag_needs_doc=True)
        self.set_kind("box")
        self.show_current()

    # ── tool and panel ───────────────────────────────────────────────────────
    def set_kind(self, kind: str):
        self.kind = kind
        self.mark_rail(kind)
        self.build_panel()

    def build_panel(self):
        name, desc = TOOLS[self.kind]
        self.panel_begin(name, desc)
        row = self.panel_field("Fill")
        self.fill_box = ComboBox()
        self.fill_box.addItems(list(core_redact.FILLS))
        self.fill_box.setCurrentText(self.fill)
        self.fill_box.currentTextChanged.connect(self.set_fill)
        row.addWidget(self.fill_box)
        if self.kind == "search":
            row = self.panel_field("Find & redact text")
            self.search_edit = LineEdit()
            self.search_edit.setPlaceholderText("exact phrase…")
            self.search_edit.setText(self.search_text)
            self.search_edit.textChanged.connect(lambda t: setattr(self, "search_text", t))
            self.search_edit.returnPressed.connect(self.mark_search)
            row.addWidget(self.search_edit, 1)
            mark = PushButton("Mark all")
            mark.clicked.connect(self.mark_search)
            self.panel_body.addSpacing(4)
            self.panel_body.addWidget(mark)
        self.panel_body.addSpacing(16)
        self.pending_label = BodyLabel()
        self.panel_body.addWidget(self.pending_label)
        self.box_list = ListWidget()
        self.box_list.setMinimumHeight(140)
        self.panel_body.addWidget(self.box_list)
        rm = PushButton("Remove")
        rm.clicked.connect(self.delete)
        self.panel_body.addWidget(rm)
        self.panel_body.addSpacing(16)
        warn = BodyLabel(WARN_TITLE)
        warn.setWordWrap(True)
        theme.keep_styled(warn, lambda w: w.setStyleSheet(
            f"color: {theme.hex_color('warning')}; font-weight: 600;"))
        self.panel_body.addWidget(warn)
        body = muted_caption(WARN_BODY)
        body.setWordWrap(True)
        self.panel_body.addWidget(body)
        self._refresh_boxes()
        self.box_list.currentRowChanged.connect(lambda _r: self.show_current())

    def set_fill(self, text: str):
        if text in core_redact.FILLS:
            self.fill = text
            self.show_current()

    def _refresh_boxes(self):
        n = len(self._pending)
        self.pending_label.setText(f"{n} box{'es' if n != 1 else ''} pending")
        theme.keep_styled(self.pending_label, lambda w: w.setStyleSheet(
            f"color: {theme.hex_color('danger')};" if len(self._pending) else ""))
        self.box_list.clear()
        for pg, _r, phrase in self._pending:
            self.box_list.addItem(f"Page {pg + 1} · '{phrase}'" if phrase
                                  else f"Page {pg + 1} · box")

    # ── document ─────────────────────────────────────────────────────────────
    def open_path(self, path: str):
        if self.open_document(path, "Redact") is None:
            return
        self._pending, self._secrets, self._undo_stack = [], {}, []
        self.build_panel()
        self.show_current()

    def clear_document(self):
        self._pending, self._secrets, self._undo_stack = [], {}, []
        super().clear_document()
        self.build_panel()

    def is_dirty(self) -> bool:
        """Boxes pending, or pages redacted in memory and not saved yet."""
        return self._doc is not None and (bool(self._pending) or self._dirty)

    def recovery_extra(self) -> dict:
        return {"boxes": [[pg, list(r), phrase] for pg, r, phrase in self._pending],
                "secrets": dict(self._secrets)}

    def restore_extra(self, state: dict) -> None:
        n = len(self._doc)
        self._pending = [(pg, fitz.Rect(r), phrase) for pg, r, phrase in state.get("boxes", [])
                         if isinstance(pg, int) and 0 <= pg < n]
        self._secrets = {str(k): bool(v) for k, v in state.get("secrets", {}).items()}
        self.build_panel()

    # ── page changes (the page strip): the boxes follow their pages ────────
    def page_state(self):
        return list(self._pending)

    def restore_page_state(self, state):
        self._pending = list(state)
        self._refresh_boxes()

    def remap_pages(self, mapping, turned):
        # A box is kept in the page's unrotated space: a turn leaves it as it is.
        self._pending = [(mapping[pg], r, phrase) for pg, r, phrase in self._pending
                         if mapping.get(pg) is not None]
        self._refresh_boxes()

    def pages_after(self):
        return list(self._pending)

    def page_step_on_top(self) -> bool:
        """A box drawn since the last page change comes off before it."""
        if not super().page_step_on_top():
            return False
        after = self._undo_stack[-1].after or []
        return not (self._pending and not any(b is self._pending[-1] for b in after))

    # ── mouse ────────────────────────────────────────────────────────────────
    def _add_box(self, start, end, click: bool):
        if click:
            return
        (x0, y0), (cx, cy) = start, end
        r = fitz.Rect(self.view.scene_to_page(x0, y0),
                      self.view.scene_to_page(cx, cy)).normalize()
        self._pending.append((self._pg, r, None))
        self._refresh_boxes()
        self.show_current()

    def draw_overlay(self, page):
        fill = "#80000000" if self.fill == "Black" else "#C0FFFFFF"
        sel = self.box_list.currentRow()
        for i, (pg, r, _) in enumerate(self._pending):
            if pg == self._pg:
                self.view.add_rect(r, theme.hex_color("danger"), fill=fill, dash=i == sel)

    # ── search and mark ──────────────────────────────────────────────────────
    def mark_search(self):
        if self._doc is None:
            return dialogs.warning("Mark", "Open a PDF first.")
        needle = self.search_text.strip()
        if not needle:
            return dialogs.warning("Mark", "Enter search text.")
        win = self.window_

        def done(kind, found):
            # A cancelled search marks nothing: half the matches would look like all.
            if kind != "done" or found is None:
                return
            self._pending += found
            self._refresh_boxes()
            self.show_current()
            if found:
                win.set_status(
                    f"Marked {len(found)} occurrence(s) of '{needle}' across all pages",
                    "warning")
            else:
                dialogs.info("Mark", f"'{needle}' not found in this PDF.")

        win.run_job(
            lambda stop: core_redact.find_phrase(
                self._doc, needle, stop, win.progress_callback()),
            f"Searching for '{needle}'…", lock=True, then=done)

    # ── undo / delete ────────────────────────────────────────────────────────
    def undo(self):
        if self.undo_page_change():
            return
        if self._pending:
            self._pending.pop()
            self._refresh_boxes()
            self.show_current()

    def delete(self):
        i = self.box_list.currentRow()
        if 0 <= i < len(self._pending):
            del self._pending[i]
            self._refresh_boxes()
            self.show_current()

    # ── apply and save ───────────────────────────────────────────────────────
    def save(self, after=None):
        if self._doc is None:
            return dialogs.warning("Apply", "Open a PDF first.")
        if not self._pending and self._pages_changed:
            # Pages moved, turned or deleted, no box (owner, 2026-10-18): the
            # page changes are saved, the file written whole.
            if not dialogs.ask_yes_no("Apply and save", PAGES_ONLY_QUESTION):
                return

            def saved():
                self._pages_changed = False
                if callable(after):
                    after()
            return WorkspaceDoc.save(self, saved)
        if not self._pending:
            return dialogs.info("Apply", "No redaction boxes drawn yet.")
        n = len(self._pending)
        if not dialogs.ask_yes_no(
                "Confirm Redaction",
                f"Permanently destroy content under {n} redaction box(es)?\n\n"
                "This cannot be undone once saved."):
            return
        out = dialogs.ask_save(self.save_name, ".pdf", [("PDF", "*.pdf")])
        if not out:
            return
        kept = ask_keep_password(self._doc)
        fill = core_redact.FILLS[self.fill]
        pending = list(self._pending)
        pages = len({p[0] for p in pending})
        modes: dict[int, str] = {}      # page number -> how its line art went
        found: dict[str, bool] = {}
        saved: list = []
        win = self.window_

        def work(stop):
            core_redact.apply_boxes(self._doc, pending, fill, stop,
                                    win.progress_callback(), modes, found)
            if stop.is_set() and len(modes) < pages:
                return None             # the boxes of the pages not done stay pending
            # Every page is redacted in memory now, even if Cancel came during the
            # last one: save, or nothing would ever be able to write them.
            secrets = dict(self._secrets)
            core_redact.merge_secrets(secrets, found)
            removed = core_redact.scrub_secrets(self._doc, secrets)
            # garbage=4 + no incremental save: the old content streams, Info dict
            # and XMP stream must not survive as unreferenced objects in the file.
            self._save_doc(out, deflate=True, garbage=4, clean=True)
            saved.append(removed)
            return removed

        def then(kind, _value):
            # Pages done are redacted in memory whatever the outcome.
            core_redact.merge_secrets(self._secrets, found)
            self._pending = [p for p in self._pending if p[0] not in modes]
            if modes:
                # An undone page change would bring back what was redacted.
                self._undo_stack = []
                self.strip_refresh(sorted(modes))
            self._refresh_boxes()
            self.show_current()
            if not saved:
                self._dirty = self._dirty or bool(modes)    # redacted in memory, not saved
                return
            self._dirty = self._pages_changed = False
            removed = saved[0]
            whole = [str(p + 1) for p, m in modes.items() if m == "whole"]
            image = [str(p + 1) for p, m in modes.items() if m == "image"]
            note = ((f" · page {', '.join(whole)}: drawings under a box removed whole"
                     if whole else "")
                    + (f" · page {', '.join(image)}: turned into an image (its text is no "
                       "longer selectable)" if image else ""))
            win.set_status(f"✓  {n} redaction(s) applied · Saved → {Path(out).name}{note}",
                           "success")
            if image:
                dialogs.warning(
                    "Redact",
                    f"Page {', '.join(image)} holds drawings this tool cannot cut at a "
                    "box edge (a gradient mesh, or a soft mask), so the page was replaced "
                    "by an image of itself. Its text can no longer be selected or searched.")
            extra = ("\n\nAlso removed from: " + ", ".join(removed)) if removed else ""
            dialogs.info("Saved", f"Redacted PDF saved:\n{out}{extra}")
            if not same_path(out, self._src_path):
                self.offer_output(out)
            if callable(after):
                after()

        win.run_job(work, f"Redacting {pages} page(s)…", lock=True, then=then,
                    keep_password=(kept, [out]))
