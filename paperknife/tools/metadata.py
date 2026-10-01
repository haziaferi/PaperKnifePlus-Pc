from __future__ import annotations
import tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path
import fitz
import customtkinter as ctk
from ..tool_base import ToolBase, register
from ..theme import ACCENT, ACCENT_H, CARD, TEXT, MUTED, SUCCESS
from ..recent import RECENT

_FIELDS = [
    ("title",    "Title"),
    ("author",   "Author"),
    ("subject",  "Subject"),
    ("keywords", "Keywords"),
    ("creator",  "Creator (application)"),
    ("producer", "Producer"),
    ("creationDate", "Creation date"),
    ("modDate",      "Modified date"),
]


@register
class MetadataTool(ToolBase):
    section = "CONTENT"
    label   = "🏷   Metadata"

    def show(self):
        app  = self.app
        body = self._card("🏷  Edit Metadata",
                          "View and edit the PDF's document properties · Ctrl+S to save")
        self._path_var = tk.StringVar()
        top = ctk.CTkFrame(body, fg_color="transparent")
        top.pack(fill="x", padx=24, pady=8)
        ctk.CTkEntry(top, textvariable=self._path_var, state="readonly",
                     placeholder_text="Open a PDF…", height=44
                     ).pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(top, text="Open PDF", width=136, height=44,
                      command=self._open).pack(side="left")

        card = ctk.CTkFrame(body, fg_color=CARD, corner_radius=8)
        card.pack(fill="x", padx=24, pady=8)

        self._vars: dict[str, tk.StringVar] = {}
        for key, label in _FIELDS:
            row = ctk.CTkFrame(card, fg_color="transparent")
            row.pack(fill="x", padx=16, pady=4)
            ctk.CTkLabel(row, text=f"{label}:", width=180,
                         text_color=TEXT, anchor="w",
                         font=ctk.CTkFont(size=13)).pack(side="left")
            var = tk.StringVar()
            ctk.CTkEntry(row, textvariable=var, height=38,
                         font=ctk.CTkFont(size=13)).pack(side="left", fill="x", expand=True)
            self._vars[key] = var

        btn_row = ctk.CTkFrame(card, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=(8, 16))
        ctk.CTkButton(btn_row, text="Clear all fields", width=130, height=36,
                      fg_color=CARD, text_color=MUTED,
                      command=self._clear).pack(side="left")
        ctk.CTkButton(btn_row, text="  Save PDF with metadata  →",
                      height=36, fg_color=ACCENT, hover_color=ACCENT_H,
                      font=ctk.CTkFont(size=13, weight="bold"),
                      command=self._save).pack(side="right")

        self._doc = None
        app._cur_open_fn = self._open
        app._cur_save_fn = self._save

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
        RECENT.push(f, len(self._doc))
        meta = self._doc.metadata or {}
        for key, _ in _FIELDS:
            self._vars[key].set(meta.get(key, "") or "")

    def _clear(self):
        for var in self._vars.values():
            var.set("")

    def _save(self):
        if not self._doc:
            return messagebox.showwarning("Save", "Open a PDF first.")
        out = self.app._save_as("with_metadata.pdf")
        if not out:
            return
        try:
            meta = {key: self._vars[key].get() for key, _ in _FIELDS}
            self._doc.set_metadata(meta)
            self._doc.save(out, deflate=True)
            self.app._set_status(f"✓  Saved → {Path(out).name}", SUCCESS)
            messagebox.showinfo("Saved", f"PDF with updated metadata saved:\n{out}")
        except Exception as e:
            messagebox.showerror("Error", str(e))
