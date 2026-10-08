from __future__ import annotations
import tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path
import customtkinter as ctk
import pymupdf as fitz
from ..core import organise
from ..tool_base import ToolBase, register
from ..theme import CARD, TEXT, DANGER, DANGER_H, SUCCESS


@register
class TocTool(ToolBase):
    section = "ORGANISE"
    label   = "📑  Bookmarks / TOC"

    def show(self):
        app  = self.app
        body = self._card("📑  Bookmark / TOC Editor",
                          "View · add · edit · delete · reorder PDF bookmarks")
        self._path_var = tk.StringVar()
        top = ctk.CTkFrame(body, fg_color="transparent")
        top.pack(fill="x", padx=24, pady=8)
        ctk.CTkEntry(top, textvariable=self._path_var, state="readonly",
                     placeholder_text="Open a PDF…", height=44
                     ).pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(top, text="Open PDF", width=136, height=44,
                      command=self._open).pack(side="left")

        # ── TOC list ──────────────────────────────────────────────────────────
        lf, self._lb = app._listbox(body, height=14)
        lf.pack(fill="both", expand=True, padx=24, pady=4)
        self._lb.bind("<<ListboxSelect>>", self._on_select)

        # ── edit fields ───────────────────────────────────────────────────────
        ef = ctk.CTkFrame(body, fg_color=CARD, corner_radius=8)
        ef.pack(fill="x", padx=24, pady=4)
        r1 = ctk.CTkFrame(ef, fg_color="transparent")
        r1.pack(fill="x", padx=16, pady=(12, 4))

        ctk.CTkLabel(r1, text="Level:", width=60, text_color=TEXT,
                     anchor="w").pack(side="left")
        self._level = ctk.CTkOptionMenu(r1, values=["1", "2", "3", "4"],
                                         width=70, height=36)
        self._level.set("1")
        self._level.pack(side="left", padx=(0, 16))

        ctk.CTkLabel(r1, text="Title:", width=50, text_color=TEXT,
                     anchor="w").pack(side="left")
        self._title_var = tk.StringVar()
        ctk.CTkEntry(r1, textvariable=self._title_var, height=36
                     ).pack(side="left", fill="x", expand=True, padx=(0, 16))

        ctk.CTkLabel(r1, text="Page:", width=52, text_color=TEXT,
                     anchor="w").pack(side="left")
        self._page_var = tk.StringVar()
        ctk.CTkEntry(r1, textvariable=self._page_var, width=70, height=36
                     ).pack(side="left")

        r2 = ctk.CTkFrame(ef, fg_color="transparent")
        r2.pack(fill="x", padx=16, pady=(4, 12))
        ctk.CTkButton(r2, text="↑ Up",   width=72, command=lambda: self._move(-1)
                      ).pack(side="left", padx=4)
        ctk.CTkButton(r2, text="↓ Down", width=80, command=lambda: self._move(1)
                      ).pack(side="left", padx=4)
        ctk.CTkButton(r2, text="＋ Add below", width=120, command=self._add
                      ).pack(side="left", padx=4)
        ctk.CTkButton(r2, text="✎ Update selected", width=150, command=self._update_sel
                      ).pack(side="left", padx=4)
        ctk.CTkButton(r2, text="✕ Delete", width=90,
                      fg_color=DANGER, hover_color=DANGER_H,
                      command=self._delete).pack(side="left", padx=4)

        app._big_btn(body, "  Save PDF  →", self._save).pack(fill="x", padx=24, pady=12)
        app._cur_open_fn = self._open
        app._cur_save_fn = self._save
        self._doc = None
        self._toc: list = []   # list of [level, title, page]

    # ── file ──────────────────────────────────────────────────────────────────
    def _open(self):
        f = filedialog.askopenfilename(filetypes=[("PDF", "*.pdf")])
        if not f:
            return
        self._close_doc()
        self._doc = self.app._open_pdf_safe(f)
        if not self._doc:
            return
        self._path_var.set(f)
        self._toc = [list(e) for e in self._doc.get_toc()]
        self._refresh()

    def _refresh(self):
        self._lb.delete(0, "end")
        for level, title, page, *_ in self._toc:
            indent = "  " * (level - 1)
            self._lb.insert("end", f"{indent}▸ {title}  (p.{page})")

    def _on_select(self, _=None):
        sel = self._lb.curselection()
        if not sel:
            return
        i = sel[0]
        if i < len(self._toc):
            e = self._toc[i]
            self._level.set(str(e[0]))
            self._title_var.set(e[1])
            self._page_var.set(str(e[2]))

    # ── edit operations ───────────────────────────────────────────────────────
    def _current_idx(self):
        sel = self._lb.curselection()
        return sel[0] if sel else None

    def _move(self, d):
        i = self._current_idx()
        if i is None:
            return
        j = i + d
        if 0 <= j < len(self._toc):
            self._toc[i], self._toc[j] = self._toc[j], self._toc[i]
            self._refresh()
            self._lb.selection_set(j)

    def _read_fields(self, title: str):
        if self._doc is None:
            messagebox.showwarning(title, "Open a PDF first.")
            return None
        try:
            lvl = int(self._level.get())
            pg  = int(self._page_var.get())
        except ValueError:
            messagebox.showwarning(title, "Enter valid level and page number.")
            return None
        if not 1 <= pg <= len(self._doc):
            messagebox.showwarning(
                title, f"Page must be between 1 and {len(self._doc)}.")
            return None
        return lvl, pg

    def _add(self):
        fields = self._read_fields("Add")
        if not fields:
            return
        lvl, pg = fields
        title = self._title_var.get().strip() or "New bookmark"
        i     = self._current_idx()
        ins   = (i + 1) if i is not None else len(self._toc)
        self._toc.insert(ins, [lvl, title, pg])
        self._refresh()
        self._lb.selection_set(ins)

    def _update_sel(self):
        i = self._current_idx()
        if i is None:
            return
        fields = self._read_fields("Update")
        if not fields:
            return
        lvl, pg = fields
        self._toc[i] = [lvl, self._title_var.get().strip(), pg]
        self._refresh()
        self._lb.selection_set(i)

    def _delete(self):
        i = self._current_idx()
        if i is None:
            return
        organise.delete_entry(self._toc, i)
        self._refresh()

    # ── save ──────────────────────────────────────────────────────────────────
    def _save(self):
        if not self._doc:
            return messagebox.showwarning("Save", "Open a PDF first.")
        problem = organise.toc_level_error(self._toc)
        if problem:
            return messagebox.showwarning("Save", problem)
        out = self.app._save_as("with_bookmarks.pdf")
        if not out:
            return
        toc = [list(item) for item in self._toc]

        def work(stop):
            self._doc.set_toc(toc)
            # Saving over the source keeps its password, as the incremental
            # save this replaced did; a copy elsewhere is written unprotected.
            keep = {"encryption": fitz.PDF_ENCRYPT_KEEP} if self._holds(out) else {}
            self._save_doc(out, deflate=True, **keep)

        def done(_):
            self.app._set_status(
                f"✓  Saved {len(toc)} bookmark(s) → {Path(out).name}", SUCCESS)
            messagebox.showinfo("Saved", f"PDF with updated bookmarks:\n{out}")

        self._run_on_doc(work, f"Saving {Path(out).name}…", done)
