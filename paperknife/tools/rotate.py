from __future__ import annotations
import tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path
from PIL import Image
import customtkinter as ctk
import pymupdf as fitz
from ..tool_base import ToolBase, register
from ..theme import ACCENT, CARD, CARD2, TEXT, MUTED, SUCCESS
from ..recent import RECENT


@register
class RotateTool(ToolBase):
    section = "ORGANISE"
    label   = "🔄  Rotate & Reorder"

    def show(self):
        app  = self.app
        body = self._card("🔄  Rotate & Reorder",
                          "Click a thumbnail · then rotate or move it")
        top = ctk.CTkFrame(body, fg_color="transparent")
        top.pack(fill="x", padx=24, pady=8)
        self._path = tk.StringVar()
        ctk.CTkEntry(top, textvariable=self._path, state="readonly",
                     placeholder_text="No file selected…", height=44
                     ).pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(top, text="Open PDF", width=136, height=44,
                      command=self._open).pack(side="left")

        tb = ctk.CTkFrame(body, fg_color="transparent")
        tb.pack(fill="x", padx=24, pady=4)
        for lbl, deg in [("↺ 90° CCW", -90), ("↻ 90° CW", 90), ("⤢ 180°", 180)]:
            ctk.CTkButton(tb, text=lbl, width=112,
                          command=lambda d=deg: self._rotate(d)).pack(side="left", padx=4)
        ctk.CTkButton(tb, text="← Move Left",  width=116,
                      fg_color=CARD, text_color=TEXT,
                      command=lambda: self._move(-1)).pack(side="left", padx=4)
        ctk.CTkButton(tb, text="Move Right →", width=124,
                      fg_color=CARD, text_color=TEXT,
                      command=lambda: self._move(1)).pack(side="left", padx=4)
        ctk.CTkLabel(tb, text="Click a thumbnail to select it",
                     text_color=MUTED, font=ctk.CTkFont(size=12)).pack(side="left", padx=12)

        self._scroll = ctk.CTkScrollableFrame(body, fg_color=CARD, corner_radius=8)
        self._scroll.pack(fill="both", expand=True, padx=24, pady=8)

        app._big_btn(body, "  Save PDF  →", self._save).pack(fill="x", padx=24, pady=12)

        if getattr(self, "_doc", None) is not None:
            self._doc.close()
        self._doc   = None
        self._order  = []
        self._extra  = {}
        self._sel    = None
        self._cells  = []
        self._thumbs = {}

        app._cur_open_fn = self._open
        app._cur_save_fn = self._save

    def _open(self):
        f = filedialog.askopenfilename(filetypes=[("PDF", "*.pdf")])
        if not f:
            return
        doc = self.app._open_pdf_safe(f)
        if not doc:
            return
        if self._doc is not None:
            self._doc.close()
        self._doc = doc
        self._path.set(f)
        self._order  = list(range(len(self._doc)))
        self._extra  = {i: 0 for i in self._order}
        self._sel    = None
        self._cells  = []
        self._thumbs = {}
        RECENT.push(f, len(self._doc))
        self._render()

    def _render(self):
        for w in self._scroll.winfo_children():
            w.destroy()
        self._cells = []
        if not self._doc:
            return
        COLS = 5
        for di, pi in enumerate(self._order):
            col = di % COLS
            row = di // COLS
            cimg  = self._thumb(pi, self._extra[pi])
            cell  = ctk.CTkFrame(self._scroll, fg_color=CARD2,
                                  border_color=ACCENT if di == self._sel else CARD,
                                  border_width=2, corner_radius=6)
            cell.grid(row=row, column=col, padx=6, pady=6, sticky="nsew")
            lbl = ctk.CTkLabel(cell, image=cimg, text="")
            lbl.pack(padx=4, pady=(4, 2))
            ctk.CTkLabel(cell, text=f"p.{pi + 1}",
                         font=ctk.CTkFont(size=10), text_color=MUTED).pack(pady=(0, 4))
            for w in (cell, lbl):
                w.bind("<Button-1>", lambda e, d=di: self._select(d))
            self._cells.append(cell)

    def _thumb(self, pi, extra):
        # Cached so a rotate or move re-rasterises only the page that changed.
        key = (pi, extra)
        if key not in self._thumbs:
            mat = fitz.Matrix(0.28, 0.28).prerotate(extra)
            pix = self._doc[pi].get_pixmap(matrix=mat, alpha=False)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            scale = min(100 / pix.width, 130 / pix.height)
            self._thumbs[key] = ctk.CTkImage(
                img, size=(round(pix.width * scale), round(pix.height * scale)))
        return self._thumbs[key]

    def _select(self, di):
        self._sel = di
        for i, c in enumerate(self._cells):
            c.configure(border_color=ACCENT if i == di else CARD)

    def _rotate(self, deg):
        if self._sel is None:
            return messagebox.showinfo("Select Page", "Click a thumbnail first.")
        pi = self._order[self._sel]
        self._extra[pi] = (self._extra[pi] + deg) % 360
        saved = self._sel
        self._render()
        self._select(saved)

    def _move(self, d):
        if self._sel is None:
            return messagebox.showinfo("Select Page", "Click a thumbnail first.")
        ni = self._sel + d
        if 0 <= ni < len(self._order):
            self._order[self._sel], self._order[ni] = (
                self._order[ni], self._order[self._sel])
            self._sel = ni
            self._render()
            self._select(self._sel)

    def _save(self):
        if not self._doc:
            return messagebox.showwarning("Save", "Open a PDF first.")
        out = self.app._save_as("reordered.pdf")
        if not out:
            return
        try:
            nd = fitz.open()
            for pi in self._order:
                nd.insert_pdf(self._doc, from_page=pi, to_page=pi)
            for ni, pi in enumerate(self._order):
                ex = self._extra[pi]
                if ex:
                    p = nd[ni]
                    p.set_rotation((p.rotation + ex) % 360)
            nd.save(out, deflate=True)
            nd.close()
            self.app._set_status(f"✓  Saved → {Path(out).name}", SUCCESS)
            messagebox.showinfo("Saved", f"PDF saved:\n{out}")
        except Exception as e:
            messagebox.showerror("Error", str(e))
