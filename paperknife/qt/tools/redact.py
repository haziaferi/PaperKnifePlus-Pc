"""Redact — a document workspace (group A).

Drawn boxes and search matches are marks on the page view, beside the window's
document.  The primary action, after the confirmation, burns them into a copy
of the document through core.redact (line art cut at the box edge, the phrases
scrubbed from metadata, bookmarks, attachments, notes and fields) and writes
that copy, with garbage collection, to a new file in one job: the document
open here and its boxes stay as they were (owner, 2026-10-23)."""
from __future__ import annotations

from pathlib import Path

import pymupdf as fitz
from PySide6.QtWidgets import QSizePolicy
from qfluentwidgets import BodyLabel, ComboBox, LineEdit, ListWidget, PushButton

from ...core import redact as core_redact
from ...core.password import carry_open_password
from ...job_queue import atomic_output
from .. import dialogs, theme
from ..pages import (WorkspaceDoc, WorkspacePage, ask_keep_password, muted_caption,
                     register_page, same_path)

# Segoe Fluent Icons code points
GLYPHS = {"box": 0xE739, "search": 0xE721, "undo": 0xE7A7}
TOOLS = {
    "box": ("Draw box", "Draw rectangles over sensitive content."),
    "search": ("Find & redact text", "Mark every occurrence of a phrase on every page."),
}
SUBTITLE = "Draw rectangles over sensitive content"
BOX_ROWS = 5            # pending boxes listed before the list scrolls
WARN_TITLE = "⚠  Redaction is permanent and irreversible once applied."
WARN_BODY = ("Content under redaction boxes is completely destroyed — "
             "not merely covered. Always work on a copy.")


@register_page("RedactTool")
class RedactPage(WorkspaceDoc, WorkspacePage):
    save_name = "redacted.pdf"
    saved_what = "PDF"

    def __init__(self, tool=None, window=None):
        super().__init__("Redact", SUBTITLE, tool=tool, window=window, page_strip=True)
        self.kind = "box"
        self.fill = "Black"
        self.search_text = ""
        # (page number, fitz.Rect in unrotated page space, search phrase or None)
        self._pending: list = []
        # each box's number on the window's counter (SharedDocument.tick): undo
        # takes back a box or the document's last step, whichever came later
        self._marked_at: list[int] = []
        # phrase burned out of page content -> match whole words only (drawn boxes)
        self._secrets: dict[str, bool] = {}
        for key, (name, _desc) in TOOLS.items():
            self.add_rail(key, GLYPHS[key], name, lambda _=False, k=key: self.set_kind(k))
        self.add_pages_tool()
        self.add_rail_gap()
        self.add_rail("undo", GLYPHS["undo"], "Undo last (Ctrl+Z)", self.undo, toggle=False)
        self.primary("Apply and save", self.apply_redactions, danger=True)
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
        # As tall as its boxes, up to BOX_ROWS, and gone while there are none: an empty
        # list grew to fill the column and pushed the permanence warning out of sight
        # (owner, 2026-10-22).
        self.box_list = ListWidget()
        self.box_list.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.panel_body.addWidget(self.box_list)
        rm = self.remove_button = PushButton("Remove")
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
        # A role, not a style sheet: clearing the sheet for "0 boxes" also dropped the
        # label's own colour, and it painted near-invisible grey (2026-10-22).
        theme.label_role(self.pending_label, "danger" if n else "text")
        self.box_list.clear()
        for pg, _r, phrase in self._pending:
            self.box_list.addItem(f"Page {pg + 1} · '{phrase}'" if phrase
                                  else f"Page {pg + 1} · box")
        rows = min(n, BOX_ROWS)
        self.box_list.setVisible(n > 0)
        if rows:
            row_h = max(self.box_list.sizeHintForRow(0), 24)
            frame = 2 * self.box_list.frameWidth() + 4
            self.box_list.setFixedHeight(rows * row_h + frame)
        self.remove_button.setEnabled(n > 0)

    # ── document ─────────────────────────────────────────────────────────────
    def open_path(self, path: str):
        if self.open_document(path, "Redact") is None:
            return
        self._drop_boxes()
        self.build_panel()
        self.show_current()

    def clear_document(self):
        self._drop_boxes()
        super().clear_document()
        self.build_panel()

    def _drop_boxes(self):
        self._pending, self._secrets, self._marked_at = [], {}, []

    def _tick(self) -> int:
        sd = self._shared()
        return sd.tick() if sd is not None else 0

    def _add_marks(self, boxes):
        self._pending += boxes
        self._marked_at += [self._tick() for _ in boxes]

    def unapplied_marks(self) -> int:
        return len(self._pending)

    def drop_marks(self):
        self._drop_boxes()
        self._refresh_boxes()
        self.show_current()

    def recovery_extra(self) -> dict:
        if not self._pending and not self._secrets:
            return {}
        return {"boxes": [[pg, list(r), phrase] for pg, r, phrase in self._pending],
                "secrets": dict(self._secrets)}

    def restore_extra(self, state: dict) -> None:
        n = len(self._doc)
        boxes = [(pg, fitz.Rect(r), phrase) for pg, r, phrase in state.get("boxes", [])
                 if isinstance(pg, int) and 0 <= pg < n]
        self._pending, self._marked_at = [], []
        self._add_marks(boxes)
        self._secrets = {str(k): bool(v) for k, v in state.get("secrets", {}).items()}
        self.build_panel()

    # ── page changes (the page strip): the boxes follow their pages ────────
    def page_state(self):
        return list(self._pending), list(self._marked_at)

    def restore_page_state(self, state):
        self._pending, self._marked_at = list(state[0]), list(state[1])
        self._refresh_boxes()

    def remap_pages(self, mapping, turned):
        # A box is kept in the page's unrotated space: a turn leaves it as it is.
        kept = [(b, at) for b, at in zip(self._pending, self._marked_at, strict=True)
                if mapping.get(b[0]) is not None]
        self._pending = [(mapping[pg], r, phrase) for (pg, r, phrase), _ in kept]
        self._marked_at = [at for _, at in kept]
        self._refresh_boxes()

    # ── mouse ────────────────────────────────────────────────────────────────
    def _add_box(self, start, end, click: bool):
        if click:
            return
        (x0, y0), (cx, cy) = start, end
        r = fitz.Rect(self.view.scene_to_page(x0, y0),
                      self.view.scene_to_page(cx, cy)).normalize()
        self._add_marks([(self._pg, r, None)])
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
            self._add_marks(found)
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
        """The last box drawn or marked, or the document's last edit,
        whichever came later."""
        sd = self._shared()
        if self._pending and (sd is None or self._marked_at[-1] > sd.last_step_seq()):
            self._pending.pop()
            self._marked_at.pop()
            self._refresh_boxes()
            self.show_current()
            return True
        return self.window_.undo()

    def delete(self):
        i = self.box_list.currentRow()
        if 0 <= i < len(self._pending):
            del self._pending[i]
            del self._marked_at[i]
            self._refresh_boxes()
            self.show_current()

    # ── apply: a new redacted copy ───────────────────────────────────────────
    def apply_redactions(self):
        if self._doc is None:
            return dialogs.warning("Apply", "Open a PDF first.")
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
        if same_path(out, self._src_path):
            return dialogs.warning("Apply", "Choose another file: this one is the PDF open here.")
        kept = ask_keep_password(self._doc)
        # The job's own copy (made here, on the main thread): the document
        # open here keeps its content and its boxes.
        copy = fitz.open("pdf", self._doc.tobytes())
        carry_open_password(self._doc, copy)
        fill = core_redact.FILLS[self.fill]
        pending = list(self._pending)
        pages = len({p[0] for p in pending})
        modes: dict[int, str] = {}      # page number -> how its line art went
        found: dict[str, bool] = {}
        saved: list = []
        win = self.window_

        def work(stop):
            try:
                core_redact.apply_boxes(copy, pending, fill, stop,
                                        win.progress_callback(), modes, found)
                if stop.is_set():
                    return None         # nothing is written: a part would look like all
                secrets = dict(self._secrets)
                core_redact.merge_secrets(secrets, found)
                removed = core_redact.scrub_secrets(copy, secrets)
                # garbage=4, written whole: the old content streams, Info dict
                # and XMP stream must not survive as unreferenced objects.
                with atomic_output(out) as tmp:
                    copy.save(tmp, deflate=True, garbage=4, clean=True)
                saved.append(removed)
                return removed
            finally:
                copy.close()

        def then(kind, _value):
            if kind != "done" or not saved:
                return
            core_redact.merge_secrets(self._secrets, found)
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
            self.offer_output(out)

        if win.run_job(work, f"Redacting {pages} page(s)…", lock=True, then=then,
                       keep_password=(kept, [out])) is None:
            copy.close()
