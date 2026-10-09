"""Edit Text — a document workspace (group A): click a text block, edit it in the panel."""
from __future__ import annotations

from pathlib import Path

import pymupdf as fitz
from qfluentwidgets import PlainTextEdit, PushButton

from ...core import text as core_text
from ...core.doc_state import DocHolder
from .. import dialogs, theme
from ..pages import WorkspacePage, register_page

# Segoe Fluent Icons code points
GLYPHS = {"select": 0xE8E9, "undo": 0xE7A7}
HINT = "Click any text block to select it · edit the span · Ctrl+S to save"


@register_page("EditTextTool")
class EditTextPage(DocHolder, WorkspacePage):
    save_name = "edited.pdf"
    saved_what = "Edited PDF"

    def __init__(self, tool=None, window=None):
        super().__init__("Edit Text", "Open a PDF to start", tool=tool, window=window)
        self._undo_stack: list = []
        self._blocks: list[dict] = []      # {"bi", "block"} of the page shown
        self._sel_bi: int | None = None
        self._start = None
        self.edit_box = None
        self.apply_btn = None
        self.add_rail("select", GLYPHS["select"], "Select text", lambda _=False: self.build_panel())
        self.add_rail_gap()
        self.add_rail("undo", GLYPHS["undo"], "Undo (Ctrl+Z)", self.undo, toggle=False)
        self.mark_rail("select")
        self.secondary("Open", self.open)
        self.primary("Save", self.save)
        self.view.pressed.connect(self._mouse_down)
        self.view.released.connect(self._mouse_up)
        self.build_panel()
        self.show_current()

    # ── panel ────────────────────────────────────────────────────────────────
    def _block(self, bi):
        return next((it["block"] for it in self._blocks if it["bi"] == bi), None)

    def build_panel(self):
        """No selection: the hint.  A selected block: its text in an editor and Apply Edit."""
        self.mark_rail("select")
        block = self._block(self._sel_bi) if self._sel_bi is not None else None
        if block is None:
            self.panel_begin("Edit Text", HINT)
            self.edit_box = self.apply_btn = None
            return
        self.panel_begin("Selected block", "Edit the text, then Apply Edit; Ctrl+S saves.")
        row = self.panel_field("Text")
        # Multi-line: a block keeps its line breaks while it is edited.
        self.edit_box = PlainTextEdit()
        self.edit_box.setPlainText(core_text.block_text(block))
        self.edit_box.setMinimumHeight(140)
        row.addWidget(self.edit_box, 1)
        self.panel_body.addSpacing(12)
        self.apply_btn = PushButton("Apply Edit")
        self.apply_btn.clicked.connect(self.apply_edit)
        self.panel_body.addWidget(self.apply_btn)
        self.edit_box.setFocus()

    # ── document ─────────────────────────────────────────────────────────────
    def open(self):
        path = dialogs.ask_open("Open PDF", [("PDF", "*.pdf")])
        if path:
            self.open_path(path)

    def open_path(self, path: str):
        doc = self.window_.open_pdf_safe(path)
        if doc is None:
            return
        self._close_doc()
        # A selection belongs to one page of one document: drop it when either
        # changes, or Apply Edit would write it into another file's block.
        self._doc, self._pg, self._undo_stack = doc, 0, []
        self._blocks, self._sel_bi = [], None
        self.set_title("Edit Text", Path(path).name)
        self.build_panel()
        self.show_current()

    def accept_drop(self, path: str) -> bool:
        if not str(path).lower().endswith(".pdf"):
            return False
        self.open_path(path)
        return True

    def on_page(self):
        self._sel_bi = None
        self.build_panel()

    def deactivate(self):
        self._close_doc()
        self._blocks, self._sel_bi, self._undo_stack = [], None, []
        self.set_title("Edit Text", "Open a PDF to start")
        self.build_panel()
        self.show_current()

    # ── overlay and mouse ────────────────────────────────────────────────────
    def draw_overlay(self, page):
        self._blocks = [{"bi": bi, "block": b} for bi, b in core_text.text_blocks(page)]
        block = self._block(self._sel_bi) if self._sel_bi is not None else None
        if block is not None:
            self.view.add_rect(block["bbox"], theme.hex_color("accent"), width=2, pad=1)

    def _mouse_down(self, xy):
        self._start = xy

    def _mouse_up(self, xy):
        start, self._start = self._start, None
        if start is None or self._doc is None:
            return
        if abs(xy[0] - start[0]) > 4 or abs(xy[1] - start[1]) > 4:
            return                         # a drag, not a click
        self.select_at(self.view.scene_to_page(*xy))

    def select_at(self, pt: fitz.Point) -> bool:
        """Select the text block under the page-space point *pt*."""
        for item in self._blocks:
            if fitz.Rect(item["block"]["bbox"]).contains(pt):
                self.select_block(item["bi"])
                return True
        return False

    def select_block(self, bi: int):
        if self._block(bi) is None:
            return
        self._sel_bi = bi
        self.build_panel()
        self.show_current()

    # ── edit / undo / save ───────────────────────────────────────────────────
    def apply_edit(self):
        if self._sel_bi is None or self._doc is None or self.edit_box is None:
            return
        block = self._block(self._sel_bi)
        if not block:
            return
        new_tx = self.edit_box.toPlainText()
        win = self.window_

        self._push_undo()
        try:
            own_font = core_text.write_block(self._doc[self._pg], block, new_tx)
        except Exception as e:
            # The original text may already be redacted away; put it back.
            self._pop_undo()
            self.show_current()
            return dialogs.error("Edit Text", f"The edit could not be applied:\n{e}")

        self._sel_bi = None
        self.build_panel()
        if own_font:
            win.set_status("Edit applied — use Save to write to disk", "success")
        else:
            win.set_status(
                f"Edit applied in Helvetica: the block's font "
                f"'{core_text.block_style(block)[0]}' is not built in — use Save to write to disk",
                "warning")
        self.show_current()

    def undo(self):
        if not self._undo_stack or self._doc is None:
            return
        self._pop_undo()
        self._sel_bi = None
        self.build_panel()
        self.show_current()
        self.window_.set_status("Undo applied", "success")

    def save(self):
        if self._doc is None:
            return dialogs.warning("Save", "Open a PDF first.")
        out = dialogs.ask_save(self.save_name, ".pdf", [("PDF", "*.pdf")])
        if not out:
            return
        win = self.window_

        def done(kind, _value):
            # A save over the open file goes on from an in-memory copy of it.
            self.show_current()
            if kind == "done":
                win.set_status(f"✓  Saved → {Path(out).name}", "success")
                dialogs.info("Saved", f"{self.saved_what} saved:\n{out}")

        win.run_job(lambda stop: self._save_doc(out, deflate=True), f"Saving {Path(out).name}…",
                    lock=True, then=done, cancellable=False)
