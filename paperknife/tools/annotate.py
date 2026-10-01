from __future__ import annotations
import tkinter as tk
from tkinter import filedialog, messagebox, colorchooser
from pathlib import Path
from PIL import Image
import customtkinter as ctk
import fitz
from ..tool_base import ToolBase, register
from ..theme import ACCENT, ACCENT_H, CARD, CARD2, TEXT, MUTED, SUCCESS, WARN, CANVAS_BG, DANGER
from ..recent import RECENT


@register
class AnnotateTool(ToolBase):
    section = "CONTENT"
    label   = "📝  Annotate"

    # ── instance state ────────────────────────────────────────────────────────
    _doc:    fitz.Document | None = None
    _pg:     int   = 0
    _zoom:   float = 1.5
    _tool:   str   = "highlight"
    _color:  tuple = (1.0, 1.0, 0.0)   # yellow
    _start:  tuple | None = None
    _canvas: tk.Canvas | None = None

    def show(self):
        app  = self.app
        body = self._card("📝  Annotate PDF",
                          "Highlight · Underline · Strikethrough · Rectangle · Line · Note · Freetext")

        # ── file row ──────────────────────────────────────────────────────────
        self._path_var = tk.StringVar()
        top = ctk.CTkFrame(body, fg_color="transparent")
        top.pack(fill="x", padx=24, pady=(8, 4))
        ctk.CTkEntry(top, textvariable=self._path_var, state="readonly",
                     placeholder_text="Open a PDF…", height=40
                     ).pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(top, text="Open PDF", width=128, height=40,
                      command=self._open).pack(side="left", padx=4)
        ctk.CTkButton(top, text="◀", width=40, height=40,
                      command=lambda: self._nav(-1)).pack(side="left", padx=2)
        self._pg_lbl = ctk.CTkLabel(top, text="—", width=60, text_color=TEXT)
        self._pg_lbl.pack(side="left", padx=2)
        ctk.CTkButton(top, text="▶", width=40, height=40,
                      command=lambda: self._nav(1)).pack(side="left", padx=2)

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
                text_color="#FFF" if tid == self._tool else TEXT,
                font=ctk.CTkFont(size=12),
                command=lambda t=tid: self._set_tool(t),
            )
            btn.pack(side="left", padx=3)
            self._tool_btns[tid] = btn

        opts = ctk.CTkFrame(toolbar, fg_color="transparent")
        opts.pack(fill="x", padx=8, pady=(4, 8))
        # Color picker
        ctk.CTkLabel(opts, text="Colour:", text_color=TEXT,
                     font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 4))
        self._color_preview = ctk.CTkFrame(
            opts, width=28, height=22, corner_radius=4, fg_color="#FFFF00")
        self._color_preview.pack(side="left", padx=(0, 6))
        ctk.CTkButton(opts, text="Pick…", width=64, height=28,
                      command=self._pick_color).pack(side="left", padx=4)
        # Opacity
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
        # Zoom
        ctk.CTkLabel(opts, text="Zoom:", text_color=TEXT,
                     font=ctk.CTkFont(size=12)).pack(side="left", padx=(12, 4))
        self._zoom_sl = ctk.CTkSlider(opts, from_=0.5, to=3.0, number_of_steps=50,
                                       width=120)
        self._zoom_sl.set(1.5)
        self._zoom_sl.configure(command=self._on_zoom)
        self._zoom_sl.pack(side="left")
        # Undo / Remove selected
        ctk.CTkButton(opts, text="↩ Undo", width=80, height=28,
                      command=self._undo).pack(side="left", padx=(12, 4))
        ctk.CTkButton(opts, text="✕ Remove sel.", width=110, height=28,
                      fg_color=DANGER, command=self._remove_selected
                      ).pack(side="left", padx=4)
        # Freetext content
        self._ft_var = tk.StringVar(value="Note")
        self._ft_lbl = ctk.CTkLabel(opts, text="Text:", text_color=TEXT,
                                     font=ctk.CTkFont(size=12))
        self._ft_entry = ctk.CTkEntry(opts, textvariable=self._ft_var,
                                       width=140, height=28)
        if self._tool in ("note", "freetext"):
            self._ft_lbl.pack(side="left", padx=(12, 4))
            self._ft_entry.pack(side="left")

        # ── canvas ────────────────────────────────────────────────────────────
        cf = ctk.CTkFrame(body, fg_color=CARD2, corner_radius=8)
        cf.pack(fill="both", expand=True, padx=24, pady=4)
        vbar = tk.Scrollbar(cf, orient="vertical")
        vbar.pack(side="right", fill="y")
        hbar = tk.Scrollbar(cf, orient="horizontal")
        hbar.pack(side="bottom", fill="x")
        self._canvas = tk.Canvas(cf, bg=CANVAS_BG, highlightthickness=0, cursor="crosshair",
                                  yscrollcommand=vbar.set, xscrollcommand=hbar.set)
        self._canvas.pack(fill="both", expand=True)
        vbar.configure(command=self._canvas.yview)
        hbar.configure(command=self._canvas.xview)
        self._canvas.bind("<ButtonPress-1>",   self._press)
        self._canvas.bind("<ButtonRelease-1>",  self._release)
        self._canvas.bind("<B1-Motion>",        self._drag)
        self._canvas.bind("<MouseWheel>",
                          lambda e: self._canvas.yview_scroll(-1*(e.delta//120), "units"))
        self._drag_id = None

        ctk.CTkButton(body, text="  Save Annotated PDF  →", height=46,
                      command=self._save,
                      fg_color=ACCENT, hover_color=ACCENT_H,
                      font=ctk.CTkFont(size=15, weight="bold")
                      ).pack(fill="x", padx=24, pady=8)

        app._cur_open_fn = self._open
        app._cur_save_fn = self._save
        app._cur_undo_fn = self._undo
        self._undo_stack: list = []
        self._sel_annot = None
        self._doc = None
        self._pg  = 0

    # ── file ──────────────────────────────────────────────────────────────────
    def _open(self):
        f = filedialog.askopenfilename(filetypes=[("PDF", "*.pdf")])
        if not f:
            return
        if self._doc:
            self._doc.close()
        self._doc = self.app._open_pdf_safe(f)
        if not self._doc:
            return
        self._path_var.set(f)
        self._pg = 0
        RECENT.push(f, len(self._doc))
        self._render()

    def _nav(self, d):
        if not self._doc:
            return
        new = self._pg + d
        if 0 <= new < len(self._doc):
            self._pg = new
            self._render()

    def _on_zoom(self, v):
        self._zoom = float(v)
        self._render()

    # ── tool / colour selection ───────────────────────────────────────────────
    def _set_tool(self, tid):
        self._tool = tid
        for t, b in self._tool_btns.items():
            b.configure(
                fg_color=ACCENT if t == tid else CARD,
                text_color="#FFF" if t == tid else TEXT,
            )
        # Show/hide freetext entry
        if tid in ("note", "freetext"):
            self._ft_lbl.pack(side="left", padx=(12, 4))
            self._ft_entry.pack(side="left")
        else:
            try:
                self._ft_lbl.pack_forget()
                self._ft_entry.pack_forget()
            except Exception:
                pass

    def _pick_color(self):
        rgb, hexc = colorchooser.askcolor(title="Annotation colour",
                                          initialcolor="#FFFF00")
        if rgb:
            self._color = tuple(c / 255 for c in rgb)
            self._color_preview.configure(fg_color=hexc)

    # ── canvas interaction ────────────────────────────────────────────────────
    def _canvas_to_pdf(self, cx, cy):
        return cx / self._zoom, cy / self._zoom

    def _press(self, event):
        cx = self._canvas.canvasx(event.x)
        cy = self._canvas.canvasy(event.y)
        self._start = (cx, cy)
        if self._drag_id:
            self._canvas.delete(self._drag_id)
            self._drag_id = None

    def _drag(self, event):
        if not self._start:
            return
        cx = self._canvas.canvasx(event.x)
        cy = self._canvas.canvasy(event.y)
        if self._drag_id:
            self._canvas.delete(self._drag_id)
        x0, y0 = self._start
        if self._tool == "line":
            self._drag_id = self._canvas.create_line(
                x0, y0, cx, cy, fill=ACCENT, width=2, dash=(4, 2))
        else:
            self._drag_id = self._canvas.create_rectangle(
                x0, y0, cx, cy, outline=ACCENT, width=2, dash=(4, 2))

    def _release(self, event):
        if not self._start or not self._doc:
            return
        cx = self._canvas.canvasx(event.x)
        cy = self._canvas.canvasy(event.y)
        x0, y0 = self._start
        if self._drag_id:
            self._canvas.delete(self._drag_id)
            self._drag_id = None
        if abs(cx - x0) < 4 and abs(cy - y0) < 4:
            cx, cy = x0 + 60, y0 + 16
        self._start = None
        px0, py0 = self._canvas_to_pdf(min(x0, cx), min(y0, cy))
        px1, py1 = self._canvas_to_pdf(max(x0, cx), max(y0, cy))
        rect     = fitz.Rect(px0, py0, px1, py1)
        opacity  = self._opacity.get() / 100.0
        color    = self._color
        page     = self._doc[self._pg]
        tool     = self._tool
        self._undo_stack.append((self._pg,))

        try:
            if tool == "highlight":
                ann = page.add_highlight_annot(rect)
                ann.set_colors(stroke=color)
                ann.set_opacity(opacity)
                ann.update()
            elif tool == "underline":
                ann = page.add_underline_annot(rect)
                ann.set_colors(stroke=color)
                ann.set_opacity(opacity)
                ann.update()
            elif tool == "strikeout":
                ann = page.add_strikeout_annot(rect)
                ann.set_colors(stroke=color)
                ann.set_opacity(opacity)
                ann.update()
            elif tool == "rect":
                ann = page.add_rect_annot(rect)
                ann.set_colors(stroke=color, fill=(*color, opacity))
                ann.set_opacity(opacity)
                ann.update()
            elif tool == "line":
                ann = page.add_line_annot(fitz.Point(px0, py0), fitz.Point(px1, py1))
                ann.set_colors(stroke=color)
                ann.set_opacity(opacity)
                ann.update()
            elif tool == "note":
                ann = page.add_text_annot(fitz.Point(px0, py0),
                                          self._ft_var.get() or "Note")
                ann.set_colors(stroke=color)
                ann.update()
            elif tool == "freetext":
                ann = page.add_freetext_annot(
                    rect,
                    self._ft_var.get() or "Text",
                    fontsize=11, fill_color=(1, 1, 1),
                    text_color=color)
                ann.update()
        except Exception as ex:
            self.app._set_status(f"Annotation error: {ex}", WARN)
        self._render()

    # ── undo / remove ─────────────────────────────────────────────────────────
    def _undo(self):
        if not self._undo_stack or not self._doc:
            return
        pg_num, = self._undo_stack.pop()
        page = self._doc[pg_num]
        annots = list(page.annots())
        if annots:
            page.delete_annot(annots[-1])
        self._render()

    def _remove_selected(self):
        if not self._sel_annot or not self._doc:
            return
        try:
            self._doc[self._pg].delete_annot(self._sel_annot)
        except Exception:
            pass
        self._sel_annot = None
        self._render()

    # ── render ────────────────────────────────────────────────────────────────
    def _render(self):
        if not self._doc:
            return
        c = self._canvas
        c.delete("all")
        page = self._doc[self._pg]
        mat  = fitz.Matrix(self._zoom, self._zoom)
        pix  = page.get_pixmap(matrix=mat, alpha=False)
        img  = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        from PIL import ImageTk as _ITK
        self._raw_img = _ITK.PhotoImage(img)
        c.create_image(0, 0, anchor="nw", image=self._raw_img)
        c.configure(scrollregion=(0, 0, pix.width, pix.height))
        self._pg_lbl.configure(text=f"{self._pg + 1} / {len(self._doc)}")

    # ── save ──────────────────────────────────────────────────────────────────
    def _save(self):
        if not self._doc:
            return messagebox.showwarning("Save", "Open a PDF first.")
        out = self.app._save_as("annotated.pdf")
        if not out:
            return
        try:
            self._doc.save(out, deflate=True)
            self.app._set_status(f"✓  Saved → {Path(out).name}", SUCCESS)
            messagebox.showinfo("Saved", f"Annotated PDF saved:\n{out}")
        except Exception as e:
            messagebox.showerror("Save Error", str(e))
