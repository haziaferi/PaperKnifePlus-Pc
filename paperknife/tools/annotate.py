from __future__ import annotations
import tkinter as tk
from tkinter import colorchooser
import customtkinter as ctk
from ..core import annotate as core_annotate
from ..page_canvas import PageCanvasTool
from ..tool_base import register
from ..theme import ACCENT, ACCENT_H, CARD, CARD2, TEXT, WARN, DANGER, ON_ACCENT, _tk_color


@register
class AnnotateTool(PageCanvasTool):
    section = "CONTENT"
    label   = "📝  Annotate"
    save_name  = "annotated.pdf"
    saved_what = "Annotated PDF"

    _tool:   str   = "highlight"
    _color:  tuple = (1.0, 1.0, 0.0)   # yellow
    _start:  tuple | None = None

    def show(self):
        app  = self.app
        body = self._card("📝  Annotate PDF",
                          "Highlight · Underline · Strikethrough · Rectangle · Line · Note · Freetext")
        self._viewer_file_row(body)

        # ── annotation toolbar ────────────────────────────────────────────────
        toolbar = ctk.CTkFrame(body, fg_color=CARD, corner_radius=8)
        toolbar.pack(fill="x", padx=24, pady=4)

        tools = [
            ("highlight",     "🟡 Highlight"),
            ("underline",     "U  Underline"),
            ("strikeout",     "S̶  Strikeout"),
            ("rect",          "▭  Rectangle"),
            ("line",          "╱  Line"),
            ("note",          "💬 Note"),
            ("freetext",      "T   Freetext"),
        ]
        self._tool_btns: dict[str, ctk.CTkButton] = {}
        trow = ctk.CTkFrame(toolbar, fg_color="transparent")
        trow.pack(fill="x", padx=8, pady=(8, 4))
        for tid, label in tools:
            btn = ctk.CTkButton(
                trow, text=label, width=95, height=34,
                fg_color=ACCENT if tid == self._tool else CARD,
                hover_color=ACCENT_H,
                text_color=ON_ACCENT if tid == self._tool else TEXT,
                font=ctk.CTkFont(size=12),
                command=lambda t=tid: self._set_tool(t),
            )
            btn.pack(side="left", padx=3)
            self._tool_btns[tid] = btn

        opts = ctk.CTkFrame(toolbar, fg_color="transparent")
        opts.pack(fill="x", padx=8, pady=(4, 8))
        ctk.CTkLabel(opts, text="Colour:", text_color=TEXT,
                     font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 4))
        self._color_preview = ctk.CTkFrame(
            opts, width=28, height=22, corner_radius=4, fg_color="#FFFF00")
        self._color_preview.pack(side="left", padx=(0, 6))
        ctk.CTkButton(opts, text="Pick…", width=64, height=28,
                      command=self._pick_color).pack(side="left", padx=4)
        ctk.CTkLabel(opts, text="Opacity:", text_color=TEXT,
                     font=ctk.CTkFont(size=12)).pack(side="left", padx=(12, 4))
        self._opacity = ctk.CTkSlider(opts, from_=10, to=100, number_of_steps=90,
                                       width=140)
        self._opacity.set(60)
        self._opacity.pack(side="left")
        self._op_lbl = ctk.CTkLabel(opts, text="60%", width=40, text_color=TEXT)
        self._op_lbl.pack(side="left", padx=4)
        self._opacity.configure(
            command=lambda v: self._op_lbl.configure(text=f"{int(v)}%"))
        ctk.CTkLabel(opts, text="Zoom:", text_color=TEXT,
                     font=ctk.CTkFont(size=12)).pack(side="left", padx=(12, 4))
        self._viewer_zoom(opts, width=120).pack(side="left")
        ctk.CTkButton(opts, text="↩ Undo", width=80, height=28,
                      command=self._undo).pack(side="left", padx=(12, 4))
        ctk.CTkButton(opts, text="✕ Remove sel.", width=110, height=28,
                      fg_color=DANGER, command=self._remove_selected
                      ).pack(side="left", padx=4)
        self._ft_var = tk.StringVar(value="Note")
        self._ft_lbl = ctk.CTkLabel(opts, text="Text:", text_color=TEXT,
                                     font=ctk.CTkFont(size=12))
        self._ft_entry = ctk.CTkEntry(opts, textvariable=self._ft_var,
                                       width=140, height=28)
        if self._tool in ("note", "freetext"):
            self._ft_lbl.pack(side="left", padx=(12, 4))
            self._ft_entry.pack(side="left")

        c = self._viewer_canvas(body, frame_color=CARD2, cursor="crosshair")
        c.bind("<ButtonPress-1>",   self._press)
        c.bind("<ButtonRelease-1>", self._release)
        c.bind("<B1-Motion>",       self._drag)
        self._drag_id = None

        ctk.CTkButton(body, text="  Save Annotated PDF  →", height=46,
                      command=self._save,
                      fg_color=ACCENT, hover_color=ACCENT_H,
                      font=ctk.CTkFont(size=15, weight="bold")
                      ).pack(fill="x", padx=24, pady=8)

        app._cur_open_fn = self._open
        app._cur_save_fn = self._save
        app._cur_undo_fn = self._undo
        self._viewer_reset()

    # Undo here removes the last annotation this tool added: (page, annotation xref).
    def _on_open(self):
        self._sel_annot = None        # xref of the clicked annotation on the current page

    def _on_page(self):
        self._sel_annot = None

    # ── tool / colour selection ───────────────────────────────────────────────
    def _set_tool(self, tid):
        self._tool = tid
        for t, b in self._tool_btns.items():
            b.configure(
                fg_color=ACCENT if t == tid else CARD,
                text_color=ON_ACCENT if t == tid else TEXT,
            )
        if tid in ("note", "freetext"):
            self._ft_lbl.pack(side="left", padx=(12, 4))
            self._ft_entry.pack(side="left")
        else:
            self._ft_lbl.pack_forget()
            self._ft_entry.pack_forget()

    def _pick_color(self):
        rgb, hexc = colorchooser.askcolor(title="Annotation colour",
                                          initialcolor="#FFFF00")
        if rgb:
            self._color = tuple(c / 255 for c in rgb)
            self._color_preview.configure(fg_color=hexc)

    # ── canvas interaction ────────────────────────────────────────────────────
    def _press(self, event):
        self._start = self._event_point(event)
        if self._drag_id:
            self._canvas.delete(self._drag_id)
            self._drag_id = None

    def _drag(self, event):
        if not self._start:
            return
        cx, cy = self._event_point(event)
        if self._drag_id:
            self._canvas.delete(self._drag_id)
        x0, y0 = self._start
        if self._tool == "line":
            self._drag_id = self._canvas.create_line(
                x0, y0, cx, cy, fill=_tk_color(ACCENT), width=2, dash=(4, 2))
        else:
            self._drag_id = self._canvas.create_rectangle(
                x0, y0, cx, cy, outline=_tk_color(ACCENT), width=2, dash=(4, 2))

    def _release(self, event):
        if not self._start or not self._doc:
            return
        cx, cy = self._event_point(event)
        x0, y0 = self._start
        if self._drag_id:
            self._canvas.delete(self._drag_id)
            self._drag_id = None
        self._start = None
        page = self._doc[self._pg]
        if abs(cx - x0) < 4 and abs(cy - y0) < 4:
            # A click on an existing annotation selects it for "Remove sel.".
            pt = self._screen_to_page((x0, y0))
            hit = next((a for a in page.annots() if pt in a.rect), None)
            if hit is not None:
                self._sel_annot = hit.xref
                self._render()
                return
            cx, cy = x0 + 60, y0 + 16
        px0, py0 = self._screen_to_page((x0, y0))
        px1, py1 = self._screen_to_page((cx, cy))
        ann = None
        try:
            ann = core_annotate.add(page, self._tool, (px0, py0), (px1, py1), self._color,
                                    self._opacity.get() / 100.0, self._ft_var.get())
        except Exception as ex:
            self.app._set_status(f"Annotation error: {ex}", WARN)
        if ann is not None:
            self._undo_stack.append((self._pg, ann.xref))
        self._render()

    # ── undo / remove ─────────────────────────────────────────────────────────
    @staticmethod
    def _annot_by_xref(page, xref):
        return core_annotate.by_xref(page, xref)

    def _undo(self):
        if not self._doc:
            return
        # Entries whose annotation was already removed with "Remove sel." are skipped.
        while self._undo_stack:
            pg_num, xref = self._undo_stack.pop()
            page = self._doc[pg_num]
            annot = self._annot_by_xref(page, xref)
            if annot is not None:
                page.delete_annot(annot)
                break
        self._render()

    def _remove_selected(self):
        if not self._sel_annot or not self._doc:
            return
        page = self._doc[self._pg]
        annot = self._annot_by_xref(page, self._sel_annot)
        if annot is not None:
            page.delete_annot(annot)
        self._sel_annot = None
        self._render()

    # ── render ────────────────────────────────────────────────────────────────
    def _draw_overlay(self, page):
        sel = self._annot_by_xref(page, self._sel_annot) if self._sel_annot else None
        if sel is not None:
            x0, y0, x1, y1 = self._page_to_screen(sel.rect, page)
            self._canvas.create_rectangle(x0 - 3, y0 - 3, x1 + 3, y1 + 3,
                                          outline=DANGER, width=2, dash=(4, 2))
