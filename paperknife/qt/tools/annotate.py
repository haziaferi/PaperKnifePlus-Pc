"""Annotate — add, select and remove annotations on a page (document workspace, group A)."""
from __future__ import annotations


from PySide6.QtWidgets import QFrame
from qfluentwidgets import BodyLabel, LineEdit, PushButton, Slider

from ...core import annotate as core_annotate
from .. import dialogs, theme
from ..pages import WorkspaceDoc, WorkspacePage, register_page

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
        super().__init__("Annotate", "Open a PDF to start", tool=tool, window=window)
        self.kind = "highlight"
        self.color = (1.0, 1.0, 0.0)
        self.opacity = 60
        self.note_text = "Note"
        self.sel_xref = None
        self._undo_stack: list = []
        for key, (name, _desc) in TOOLS.items():
            self.add_rail(key, GLYPHS[key], name, lambda _=False, k=key: self.set_kind(k))
        self.add_rail_gap()
        self.add_rail("undo", GLYPHS["undo"], "Undo (Ctrl+Z)", self.undo, toggle=False)
        self.secondary("Open", self.open)
        self.primary("Save", self.save)
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
            self.opacity_slider = Slider()
            self.opacity_slider.setOrientation(self.zoom_slider.orientation())
            self.opacity_slider.setRange(10, 100)
            self.opacity_slider.setValue(self.opacity)
            lbl = BodyLabel(f"{self.opacity}%")
            self.opacity_slider.valueChanged.connect(
                lambda v: (setattr(self, "opacity", v), lbl.setText(f"{v}%")))
            row.addWidget(self.opacity_slider, 1)
            row.addWidget(lbl)
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

    def deactivate(self):
        self._close_doc()
        self._undo_stack, self.sel_xref = [], None
        self.set_title("Annotate", "Open a PDF to start")
        self.build_panel()
        self.show_current()

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
        try:
            ann = core_annotate.add(page, self.kind, (p0.x, p0.y), (p1.x, p1.y), self.color,
                                    self.opacity / 100.0, self.note_text)
        except Exception as ex:
            self.window_.set_status(f"Annotation error: {ex}", "danger")
        if ann is not None:
            self._undo_stack.append((self._pg, ann.xref))
        self.show_current()

    def draw_overlay(self, page):
        sel = core_annotate.by_xref(page, self.sel_xref) if self.sel_xref else None
        if sel is not None:
            self.view.add_rect(sel.rect, theme.hex_color("danger"), dash=True, pad=3)

    # ── undo / delete / save ─────────────────────────────────────────────────
    def undo(self):
        if self._doc is None:
            return
        while self._undo_stack:
            pg_num, xref = self._undo_stack.pop()
            page = self._doc[pg_num]
            annot = core_annotate.by_xref(page, xref)
            if annot is not None:
                page.delete_annot(annot)
                break
        self.show_current()

    def delete(self):
        if not self.sel_xref or self._doc is None:
            return
        page = self._doc[self._pg]
        annot = core_annotate.by_xref(page, self.sel_xref)
        if annot is not None:
            page.delete_annot(annot)
        self.sel_xref = None
        self.build_panel()
        self.show_current()
