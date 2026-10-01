from __future__ import annotations
import tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path
from PIL import Image
import customtkinter as ctk
import fitz
from ..tool_base import ToolBase, register
from ..theme import ACCENT, ACCENT_H, CARD, CARD2, TEXT, MUTED, SUCCESS, WARN, CANVAS_BG
from ..recent import RECENT


@register
class FindReplaceTool(ToolBase):
    section = "CONTENT"
    label   = "🔍  Find & Replace"

    _doc:      fitz.Document | None = None
    _pg:       int = 0
    _zoom:     float = 1.5
    _hits:     list  = []   # list of (page_num, rect)
    _hit_idx:  int   = -1

    def show(self):
        app  = self.app
        body = self._card("🔍  Find & Replace",
                          "Search PDF text and replace across all pages · Ctrl+S to save")
        # ── file row ──────────────────────────────────────────────────────────
        self._path_var = tk.StringVar()
        top = ctk.CTkFrame(body, fg_color="transparent")
        top.pack(fill="x", padx=24, pady=8)
        ctk.CTkEntry(top, textvariable=self._path_var, state="readonly",
                     placeholder_text="Open a PDF…", height=44
                     ).pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(top, text="Open PDF", width=136, height=44,
                      command=self._open).pack(side="left")

        # ── search / replace ──────────────────────────────────────────────────
        sr_card = ctk.CTkFrame(body, fg_color=CARD, corner_radius=8)
        sr_card.pack(fill="x", padx=24, pady=8)
        r1 = ctk.CTkFrame(sr_card, fg_color="transparent")
        r1.pack(fill="x", padx=16, pady=(14, 4))
        ctk.CTkLabel(r1, text="Find:", width=90, text_color=TEXT,
                     anchor="w").pack(side="left")
        self._find_var = tk.StringVar()
        self._find_ent = ctk.CTkEntry(r1, textvariable=self._find_var,
                                       height=40, placeholder_text="Search text…")
        self._find_ent.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(r1, text="Find All", width=90, height=40,
                      command=self._find_all).pack(side="left")
        r2 = ctk.CTkFrame(sr_card, fg_color="transparent")
        r2.pack(fill="x", padx=16, pady=(4, 14))
        ctk.CTkLabel(r2, text="Replace:", width=90, text_color=TEXT,
                     anchor="w").pack(side="left")
        self._repl_var = tk.StringVar()
        self._repl_ent = ctk.CTkEntry(r2, textvariable=self._repl_var,
                                       height=40, placeholder_text="Replacement text…")
        self._repl_ent.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(r2, text="Replace All", width=110, height=40,
                      fg_color=ACCENT, hover_color=ACCENT_H,
                      command=self._replace_all).pack(side="left")

        # ── hit counter & nav ─────────────────────────────────────────────────
        nav = ctk.CTkFrame(body, fg_color="transparent")
        nav.pack(fill="x", padx=24, pady=4)
        ctk.CTkButton(nav, text="◀ Prev", width=90,
                      command=lambda: self._jump(-1)).pack(side="left", padx=4)
        ctk.CTkButton(nav, text="Next ▶", width=90,
                      command=lambda: self._jump(1)).pack(side="left", padx=4)
        self._hit_lbl = ctk.CTkLabel(nav, text="",
                                      text_color=MUTED, font=ctk.CTkFont(size=13))
        self._hit_lbl.pack(side="left", padx=12)

        # ── canvas ────────────────────────────────────────────────────────────
        cf = ctk.CTkFrame(body, fg_color=CARD, corner_radius=8)
        cf.pack(fill="both", expand=True, padx=24, pady=4)
        vbar = tk.Scrollbar(cf, orient="vertical")
        vbar.pack(side="right", fill="y")
        hbar = tk.Scrollbar(cf, orient="horizontal")
        hbar.pack(side="bottom", fill="x")
        self._canvas = tk.Canvas(cf, bg=CANVAS_BG, highlightthickness=0,
                                  yscrollcommand=vbar.set, xscrollcommand=hbar.set)
        self._canvas.pack(fill="both", expand=True)
        vbar.configure(command=self._canvas.yview)
        hbar.configure(command=self._canvas.xview)
        self._canvas.bind("<MouseWheel>",
                          lambda e: self._canvas.yview_scroll(
                              -1 * (e.delta // 120), "units"))

        ctk.CTkButton(body, text="  Save PDF  →", height=46,
                      command=self._save,
                      fg_color=ACCENT, hover_color=ACCENT_H,
                      font=ctk.CTkFont(size=15, weight="bold")
                      ).pack(fill="x", padx=24, pady=8)

        app._cur_open_fn = self._open
        app._cur_save_fn = self._save
        self._doc  = None
        self._hits = []
        self._pg   = 0

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
        self._hits = []
        RECENT.push(f, len(self._doc))
        self._render()

    # ── search ────────────────────────────────────────────────────────────────
    def _find_all(self):
        if not self._doc:
            return messagebox.showwarning("Find", "Open a PDF first.")
        needle = self._find_var.get().strip()
        if not needle:
            return
        self._hits = []
        for pg_num in range(len(self._doc)):
            for rect in self._doc[pg_num].search_for(needle):
                self._hits.append((pg_num, rect))
        if self._hits:
            self._hit_idx = 0
            self._pg      = self._hits[0][0]
            self._hit_lbl.configure(
                text=f"Found {len(self._hits)} hit(s)")
            self._render()
        else:
            self._hit_lbl.configure(text="Not found")
            messagebox.showinfo("Find", f"'{needle}' not found.")

    def _jump(self, d):
        if not self._hits:
            return
        self._hit_idx = (self._hit_idx + d) % len(self._hits)
        self._pg      = self._hits[self._hit_idx][0]
        self._render()
        self._hit_lbl.configure(
            text=f"Hit {self._hit_idx + 1} / {len(self._hits)}")

    # ── replace ───────────────────────────────────────────────────────────────
    def _replace_all(self):
        if not self._doc:
            return messagebox.showwarning("Replace", "Open a PDF first.")
        needle = self._find_var.get().strip()
        repl   = self._repl_var.get()
        if not needle:
            return messagebox.showwarning("Replace", "Enter search text.")
        if not messagebox.askyesno(
                "Confirm Replace",
                f"Replace ALL occurrences of:\n  '{needle}'\nwith:\n  '{repl}'\n\n"
                "This modifies the PDF in memory (save to keep changes)."):
            return
        count = 0
        for pg_num in range(len(self._doc)):
            page = self._doc[pg_num]
            rects = page.search_for(needle)
            if rects:
                for r in rects:
                    page.add_redact_annot(r)
                page.apply_redactions()
                for r in rects:
                    page.insert_text(r.tl, repl, fontsize=11)
                count += len(rects)
        self._hits = []
        self._hit_idx = -1
        self._hit_lbl.configure(text=f"Replaced {count} occurrence(s)")
        self.app._set_status(
            f"✓  Replaced {count} occurrence(s) · Save to write to disk", SUCCESS)
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
        # Draw hit highlights on current page
        z = self._zoom
        for hi, (pg_num, rect) in enumerate(self._hits):
            if pg_num != self._pg:
                continue
            x0, y0, x1, y1 = rect.x0*z, rect.y0*z, rect.x1*z, rect.y1*z
            is_cur = hi == self._hit_idx
            fill   = "#FFD700" if is_cur else "#FFFACD"
            c.create_rectangle(x0, y0, x1, y1,
                               fill=fill, outline=ACCENT if is_cur else "#CCC",
                               stipple="gray50" if not is_cur else "",
                               width=2)

    # ── save ──────────────────────────────────────────────────────────────────
    def _save(self):
        if not self._doc:
            return messagebox.showwarning("Save", "Open a PDF first.")
        out = self.app._save_as("replaced.pdf")
        if not out:
            return
        try:
            self._doc.save(out, deflate=True)
            self.app._set_status(f"✓  Saved → {Path(out).name}", SUCCESS)
            messagebox.showinfo("Saved", f"PDF saved:\n{out}")
        except Exception as e:
            messagebox.showerror("Save Error", str(e))
