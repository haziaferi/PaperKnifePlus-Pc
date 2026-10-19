"""Edit Text — a document workspace (group A): click a paragraph (or a line,
or the page's column), edit it in the panel; the edit reflows like a word
processor (core.reflow, owner 2026-10-11)."""
from __future__ import annotations


import pymupdf as fitz
from qfluentwidgets import ComboBox, PlainTextEdit, PushButton

from ...core import reflow
from .. import dialogs, theme
from ..pages import WorkspaceDoc, WorkspacePage, register_page

# Segoe Fluent Icons code points
GLYPHS = {"select": 0xE8E9, "undo": 0xE7A7}
HINT = "Click any text to select it · edit it · Ctrl+S to save"
UNIT_NAMES = {"Line": reflow.LINE, "Paragraph": reflow.PARAGRAPH, "Page": reflow.PAGE}


@register_page("EditTextTool")
class EditTextPage(WorkspaceDoc, WorkspacePage):
    save_name = "edited.pdf"
    saved_what = "Edited PDF"

    def __init__(self, tool=None, window=None):
        super().__init__("Edit Text", "Open a PDF to start", tool=tool, window=window,
                         page_strip=True)
        self._undo_stack: list = []
        self._blocks: list[dict] = []      # {"bi", "block": {"bbox"}, "lines"} of the page shown
        self._sel_bi: int | None = None
        self._start = None
        self._unit_name = "Paragraph"
        self.edit_box = None
        self.apply_btn = None
        self.add_rail("select", GLYPHS["select"], "Select text", lambda _=False: self.build_panel())
        self.add_pages_tool()
        self.add_rail_gap()
        self.add_rail("undo", GLYPHS["undo"], "Undo (Ctrl+Z)", self.undo, toggle=False)
        self.mark_rail("select")
        self.primary("Save", self.save)
        self.view.pressed.connect(self._mouse_down)
        self.view.released.connect(self._mouse_up)
        self.build_panel()
        self.show_current()

    # ── panel ────────────────────────────────────────────────────────────────
    def _block(self, bi):
        return next((it for it in self._blocks if it["bi"] == bi), None)

    def unit(self) -> str:
        return UNIT_NAMES[self._unit_name]

    def _unit_field(self):
        row = self.panel_field("Select and reflow")
        self.unit_box = ComboBox()
        self.unit_box.addItems(list(UNIT_NAMES))
        self.unit_box.setCurrentText(self._unit_name)
        self.unit_box.setToolTip("What a click selects and an edit re-wraps: a line, a paragraph, "
                                 "or the page's column")
        self.unit_box.currentTextChanged.connect(self._set_unit)
        row.addWidget(self.unit_box, 1)

    def _set_unit(self, name):
        self._unit_name = name
        self._sel_bi = None
        self.build_panel()
        self.show_current()

    def build_panel(self):
        """No selection: the hint.  A selection: its text in an editor and Apply Edit."""
        self.mark_rail("select")
        item = self._block(self._sel_bi) if self._sel_bi is not None else None
        if item is None:
            self.panel_begin("Edit Text", HINT)
            self._unit_field()
            self.edit_box = self.apply_btn = None
            return
        self.panel_begin(f"Selected {self._unit_name.lower()}",
                         "Edit the text, then Apply Edit; a new line in the text is a line break. "
                         "Ctrl+S saves.")
        self._unit_field()
        row = self.panel_field("Text")
        self.edit_box = PlainTextEdit()
        self.edit_box.setPlainText(item["text"])
        self.edit_box.setMinimumHeight(140)
        row.addWidget(self.edit_box, 1)
        self.panel_body.addSpacing(12)
        self.apply_btn = PushButton("Apply Edit")
        self.apply_btn.clicked.connect(self.apply_edit)
        self.panel_body.addWidget(self.apply_btn)
        self.edit_box.setFocus()

    # ── document ─────────────────────────────────────────────────────────────
    def open_path(self, path: str):
        if self.open_document(path, "Edit Text") is None:
            return
        # A selection belongs to one page of one document: drop it when either
        # changes, or Apply Edit would write it into another file's text.
        self._blocks, self._sel_bi = [], None
        self.build_panel()
        self.show_current()

    def on_page(self):
        self._sel_bi = None
        self.build_panel()

    def remap_pages(self, mapping, turned):
        self._sel_bi = None                 # a selection belongs to one page as it was

    def clear_document(self):
        self._blocks, self._sel_bi, self._undo_stack = [], None, []
        super().clear_document()
        self.build_panel()

    # ── overlay and mouse ────────────────────────────────────────────────────
    def draw_overlay(self, page):
        lines, _o = reflow.page_lines(page)
        eng = reflow.Engine(self._doc, self.unit())
        self._blocks = []
        for i, u in enumerate(reflow.units(lines, self.unit())):
            box = fitz.Rect(u[0].bbox)
            for ln in u[1:]:
                box |= ln.bbox
            self._blocks.append({"bi": i, "block": {"bbox": tuple(box)}, "lines": u,
                                 "text": eng.text_of(u)})
        item = self._block(self._sel_bi) if self._sel_bi is not None else None
        if item is not None:
            self.view.add_rect(item["block"]["bbox"], theme.hex_color("accent"), width=2, pad=1)

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
        """Select the text under the page-space point *pt*."""
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
        item = self._block(self._sel_bi)
        if not item:
            return
        new_tx = self.edit_box.toPlainText()
        win = self.window_

        self._push_undo()
        try:
            res = reflow.rewrite_unit(self._doc, self._pg, item["lines"], new_tx, self.unit())
        except Exception as e:
            # The original text may already be erased; put it back.
            self._pop_undo()
            self.show_current()
            return dialogs.error("Edit Text", f"The edit could not be applied:\n{e}")
        if not res.done:
            self._pop_undo()
            self.show_current()
            reason = res.skips[0].reason
            return dialogs.warning("Edit Text", f"The edit was not applied: {reason}.")

        self._dirty = True
        self._sel_bi = None
        self.build_panel()
        self.strip_refresh(range(self._pg, len(self._doc)))     # a reflow may carry on
        if res.fallback_fonts:
            fonts = ", ".join(sorted(res.fallback_fonts))
            win.set_status(f"Edit applied — some letters are not in the font '{fonts}' and were "
                           "drawn in a built-in one; use Save to write to disk", "warning")
        else:
            win.set_status("Edit applied — use Save to write to disk", "success")
        self.show_current()

    def undo(self):
        if self.undo_page_change():
            return
        if not self._undo_stack or self._doc is None:
            return
        self._pop_undo()
        self._dirty = True
        self._sel_bi = None
        self.build_panel()
        self.show_current()
        self.window_.set_status("Undo applied", "success")
