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
from ...core.doc_state import DocHolder
from .. import bridge, dialogs, theme
from ..pages import WorkspacePage, muted_caption, register_page

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
class RedactPage(DocHolder, WorkspacePage):
    save_name = "redacted.pdf"

    def __init__(self, tool=None, window=None):
        super().__init__("Redact", SUBTITLE, tool=tool, window=window)
        self.kind = "box"
        self.fill = "Black"
        self.search_text = ""
        # (page number, fitz.Rect in unrotated page space, search phrase or None)
        self._pending: list = []
        # phrase burned out of page content -> match whole words only (drawn boxes)
        self._secrets: dict[str, bool] = {}
        self._start = None
        self._band = None
        for key, (name, _desc) in TOOLS.items():
            self.add_rail(key, GLYPHS[key], name, lambda _=False, k=key: self.set_kind(k))
        self.add_rail_gap()
        self.add_rail("undo", GLYPHS["undo"], "Undo last (Ctrl+Z)", self.undo, toggle=False)
        self.secondary("Open", self.open)
        self.primary("Apply and save", self.save, danger=True)
        self.view.pressed.connect(self._press)
        self.view.dragged.connect(self._drag)
        self.view.released.connect(self._release)
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
        warn.setStyleSheet(f"color: {theme.hex_color('warning')}; font-weight: 600;")
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
        self.pending_label.setStyleSheet(
            f"color: {theme.hex_color('danger')};" if n else "")
        self.box_list.clear()
        for pg, _r, phrase in self._pending:
            self.box_list.addItem(f"Page {pg + 1} · '{phrase}'" if phrase
                                  else f"Page {pg + 1} · box")

    # ── document ─────────────────────────────────────────────────────────────
    def open(self):
        path = dialogs.ask_open("Open PDF", [("PDF", "*.pdf")])
        if path:
            self.open_path(path)

    def open_path(self, path: str):
        doc = self.window_.open_pdf_safe(path) if self.window_ is not None else None
        if doc is None:
            return
        self._close_doc()
        self._doc, self._pg = doc, 0
        self._pending, self._secrets = [], {}
        self.set_title("Redact", Path(path).name)
        self.build_panel()
        self.show_current()

    def accept_drop(self, path: str) -> bool:
        if not str(path).lower().endswith(".pdf"):
            return False
        self.open_path(path)
        return True

    def deactivate(self):
        self._close_doc()
        self._pending, self._secrets = [], {}
        self.set_title("Redact", SUBTITLE)
        self.build_panel()
        self.show_current()

    # ── mouse ────────────────────────────────────────────────────────────────
    def _press(self, xy):
        self._start = xy
        if self._band is not None:
            self.view.remove(self._band)
            self._band = None

    def _drag(self, xy):
        if self._start is None or self._doc is None:
            return
        if self._band is not None:
            self.view.remove(self._band)
        x0, y0 = self._start
        self._band = self.view.add_scene_shape("rect", x0, y0, xy[0], xy[1],
                                               theme.hex_color("danger"))

    def _release(self, xy):
        if self._start is None or self._doc is None:
            return
        (x0, y0), (cx, cy) = self._start, xy
        self._start = None
        if self._band is not None:
            self.view.remove(self._band)
            self._band = None
        if abs(cx - x0) < 4 and abs(cy - y0) < 4:
            return
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
                self._doc, needle, stop, lambda v: bridge.post(win.set_progress, v)),
            f"Searching for '{needle}'…", lock=True, then=done)

    # ── undo / delete ────────────────────────────────────────────────────────
    def undo(self):
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
    def save(self):
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
        fill = core_redact.FILLS[self.fill]
        pending = list(self._pending)
        pages = len({p[0] for p in pending})
        modes: dict[int, str] = {}      # page number -> how its line art went
        found: dict[str, bool] = {}
        saved: list = []
        win = self.window_

        def work(stop):
            core_redact.apply_boxes(self._doc, pending, fill, stop,
                                    lambda v: bridge.post(win.set_progress, v), modes, found)
            if stop.is_set():
                return None             # the boxes of the pages not done stay pending
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
            self._refresh_boxes()
            self.show_current()
            if not saved:
                return
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

        win.run_job(work, f"Redacting {pages} page(s)…", lock=True, then=then)
