"""Annotate — add, select and remove annotations on a page (document workspace, group A)."""
from __future__ import annotations


from PySide6.QtWidgets import QFrame
from qfluentwidgets import BodyLabel, LineEdit, PushButton

from ...core import annotate as core_annotate
from .. import dialogs, theme
from ..pages import NUMBER_BOX_W, WorkspaceDoc, WorkspacePage, register_page, spin_box

# Segoe Fluent Icons code points
GLYPHS = {"highlight": 0xE7E6, "underline": 0xE8DC, "strikeout": 0xEDE0, "rect": 0xE739,
          "line": 0xE738, "note": 0xE8BD, "freetext": 0xE8D2, "undo": 0xE7A7}
TOOLS = {
    "highlight": ("Highlight", "Drag across text to mark it."),
    "underline": ("Underline", "Drag across text to underline it."),
    "strikeout": ("Strikeout", "Drag across text to strike it through."),
    "rect": ("Rectangle", "Drag to draw a filled box."),
    "line": ("Line", "Drag from one end to the other."),
    "note": ("Note", "Click where the note's icon should go."),
    "freetext": ("Text box", "Drag the box; the text appears in it."),
}


@register_page("AnnotateTool")
class AnnotatePage(WorkspaceDoc, WorkspacePage):
    save_name = "annotated.pdf"
    saved_what = "Annotated PDF"

    def __init__(self, tool=None, window=None):
        super().__init__("Annotate", "Open a PDF to start", tool=tool, window=window,
                         page_strip=True)
        self.kind = "highlight"
        self.color = (1.0, 1.0, 0.0)
        self.opacity = 60
        self.note_text = "Note"
        self.sel_xref = None
        for key, (name, _desc) in TOOLS.items():
            self.add_rail(key, GLYPHS[key], name, lambda _=False, k=key: self.set_kind(k))
        self.add_pages_tool()
        self.add_rail_gap()
        self.add_rail("undo", GLYPHS["undo"], "Undo (Ctrl+Z)", self.undo, toggle=False)
        self.enable_band(lambda: ("line" if self.kind == "line" else "rect",
                                  theme.hex_color("accent")),
                         self._add_at)
        self.set_kind("highlight")
        self.show_current()

    # ── tool and panel ───────────────────────────────────────────────────────
    def set_kind(self, kind: str):
        self.kind = kind
        self.mark_rail(kind)
        self.build_panel()

    def build_panel(self):
        name, desc = TOOLS[self.kind]
        self.panel_begin(name, desc)
        if self.kind != "note":
            row = self.panel_field("Colour")
            self.swatch = QFrame()
            self.swatch.setFixedSize(32, 32)
            self._paint_swatch()
            row.addWidget(self.swatch)
            pick = PushButton("Choose")
            pick.clicked.connect(self.pick_color)
            row.addWidget(pick)
            row.addStretch(1)
        if self.kind not in ("note", "freetext"):
            row = self.panel_field("Opacity")
            self.opacity_box = spin_box(10, 100, self.opacity, width=NUMBER_BOX_W)
            self.opacity_box.setFixedWidth(NUMBER_BOX_W)
            self.opacity_box.setSuffix("%")
            self.opacity_box.valueChanged.connect(lambda v: setattr(self, "opacity", v))
            row.addWidget(self.opacity_box)
            row.addStretch(1)
        if self.kind in ("note", "freetext"):
            row = self.panel_field("Text")
            self.text_edit = LineEdit()
            self.text_edit.setText(self.note_text)
            self.text_edit.textChanged.connect(lambda t: setattr(self, "note_text", t))
            row.addWidget(self.text_edit, 1)
        if self.sel_xref:
            self.panel_body.addSpacing(16)
            self.panel_body.addWidget(BodyLabel("Selected annotation"))
            rm = PushButton("Remove")
            rm.clicked.connect(self.delete)
            self.panel_body.addWidget(rm)

    def _paint_swatch(self):
        r, g, b = (int(c * 255) for c in self.color)
        self.swatch.setStyleSheet(f"background: rgb({r},{g},{b});"
                                  "border: 1px solid rgba(0,0,0,0.15); border-radius: 4px;")

    def pick_color(self):
        rgb = dialogs.ask_color(tuple(int(c * 255) for c in self.color))
        if rgb:
            self.color = tuple(c / 255 for c in rgb)
            self._paint_swatch()

    # ── document ─────────────────────────────────────────────────────────────
    def open_path(self, path: str):
        if self.open_document(path, "Annotate") is None:
            return
        self.sel_xref = None
        self.build_panel()
        self.show_current()

    def on_page(self):
        self.sel_xref = None
        self.build_panel()

    def remap_pages(self, mapping, turned):
        self.sel_xref = None

    def clear_document(self):
        self.sel_xref = None
        super().clear_document()
        self.build_panel()

    # ── mouse ────────────────────────────────────────────────────────────────
    def _add_at(self, start, end, click: bool):
        (x0, y0), (cx, cy) = start, end
        page = self._doc[self._pg]
        if click:
            # A click on an existing annotation selects it for Remove.
            pt = self.view.scene_to_page(x0, y0)
            hit = next((a for a in page.annots() if pt in a.rect), None)
            if hit is not None:
                self.sel_xref = hit.xref
                self.build_panel()
                self.show_current()
                return
            cx, cy = x0 + 60, y0 + 16
        p0 = self.view.scene_to_page(x0, y0)
        p1 = self.view.scene_to_page(cx, cy)
        ann = None
        self._push_undo(TOOLS[self.kind][0])
        try:
            ann = core_annotate.add(self._doc[self._pg], self.kind, (p0.x, p0.y), (p1.x, p1.y),
                                    self.color, self.opacity / 100.0, self.note_text)
        except Exception as ex:
            self._pop_undo()                # it may have half-added: the page as it was
            self.window_.set_status(f"Annotation error: {ex}", "danger")
            self.show_current()
            return
        if ann is None:
            self._drop_undo()               # nothing added: nothing to undo
            if self.kind in core_annotate.MARKUP_KINDS:
                self.window_.set_status("No text under the drag: drag across words to mark them.",
                                        "warning")
        else:
            # Only added: a save over the file may append it (owner's choice 2026-10-12).
            self._adds_pending = True
            self._dirty = True
            self.strip_refresh([self._pg])
        self.show_current()

    def draw_overlay(self, page):
        sel = core_annotate.by_xref(page, self.sel_xref) if self.sel_xref else None
        if sel is not None:
            self.view.add_rect(sel.rect, theme.hex_color("danger"), dash=True, pad=3)

    # ── delete (undo and save are the window's) ──────────────────────────────
    def delete(self):
        if not self.sel_xref or self._doc is None:
            return
        page = self._doc[self._pg]
        annot = core_annotate.by_xref(page, self.sel_xref)
        if annot is not None:
            self._push_undo("Remove annotation")
            page.delete_annot(annot)
            self._dirty = True              # removed: the file is written whole
            self.strip_refresh([self._pg])
        self.sel_xref = None
        self.build_panel()
        self.show_current()
