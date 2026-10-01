from __future__ import annotations
import tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path
import fitz
import customtkinter as ctk
from ..tool_base import ToolBase, register
from ..theme import ACCENT, ACCENT_H, CARD, TEXT, MUTED, SUCCESS, WARN
from ..recent import RECENT


@register
class PdfToolsTool(ToolBase):
    section = "ENHANCE"
    label   = "🔧  PDF Tools"

    def show(self):
        app  = self.app
        body = self._card("🔧  PDF Tools",
                          "PDF/A conversion · linearise for web · repair corrupt files")
        self._path = tk.StringVar()
        self._file_row(body, self._path)

        self._op = tk.StringVar(value="pdfa")
        ops = [
            ("pdfa",       "PDF/A-1b  —  Convert to ISO archival format",
             "Embeds all fonts, sets colour profile. Required for long-term archiving\n"
             "and many government/legal submission systems."),
            ("linearise",  "Linearise  —  Optimise for fast web / browser viewing",
             "Rearranges internal structure so the first page loads before the whole\n"
             "file downloads. Also called 'Fast Web View'."),
            ("repair",     "Repair  —  Attempt to recover a corrupt or truncated PDF",
             "Re-parses the file's cross-reference table. Can rescue files that other\n"
             "tools refuse to open. May not recover all pages."),
        ]
        for val, label, desc in ops:
            card = ctk.CTkFrame(body, fg_color=CARD, corner_radius=8)
            card.pack(fill="x", padx=24, pady=6)
            top = ctk.CTkFrame(card, fg_color="transparent")
            top.pack(fill="x", padx=16, pady=(12, 4))
            ctk.CTkRadioButton(top, text=label, variable=self._op, value=val,
                               text_color=TEXT,
                               font=ctk.CTkFont(size=13, weight="bold")
                               ).pack(side="left")
            ctk.CTkLabel(card, text=desc, font=ctk.CTkFont(size=12),
                         text_color=MUTED, anchor="w", justify="left"
                         ).pack(padx=32, pady=(0, 12), fill="x")

        # PDF/A level selector (only relevant for PDF/A)
        self._pdfa_level = tk.StringVar(value="1b")
        al = ctk.CTkFrame(body, fg_color="transparent")
        al.pack(fill="x", padx=24, pady=(0, 4))
        ctk.CTkLabel(al, text="PDF/A level:", width=120, text_color=MUTED,
                     font=ctk.CTkFont(size=12), anchor="w").pack(side="left")
        for lv in ("1b", "2b", "3b"):
            ctk.CTkRadioButton(al, text=f"PDF/A-{lv}", variable=self._pdfa_level,
                               value=lv, text_color=TEXT,
                               font=ctk.CTkFont(size=12)).pack(side="left", padx=8)

        app._big_btn(body, "  Run  →", self._run).pack(fill="x", padx=24, pady=16)
        app._cur_open_fn = lambda: self._path.set(
            filedialog.askopenfilename(filetypes=[("PDF", "*.pdf")]) or self._path.get())

    def _run(self):
        src = self._path.get()
        if not src:
            return messagebox.showwarning("PDF Tools", "Select a PDF first.")
        op  = self._op.get()
        out = self.app._save_as(
            {"pdfa": "archived.pdf", "linearise": "linearised.pdf",
             "repair": "repaired.pdf"}[op])
        if not out:
            return
        try:
            doc = fitz.open(src)
            if op == "repair":
                # Re-open with repair flag
                doc.close()
                doc = fitz.open(src, filetype="pdf")
                doc.save(out, deflate=True, garbage=4, clean=True)
                doc.close()
                msg = "Repaired PDF saved"

            elif op == "linearise":
                doc.save(out, deflate=True, linear=True)
                doc.close()
                msg = "Linearised PDF saved"

            elif op == "pdfa":
                level_map = {"1b": 1, "2b": 2, "3b": 3}
                lv = level_map.get(self._pdfa_level.get(), 1)
                # PyMuPDF ≥ 1.24 supports pdfa= parameter
                try:
                    doc.save(out, deflate=True, pdfa=lv)
                except TypeError:
                    # Older PyMuPDF: save normally and warn
                    doc.save(out, deflate=True, garbage=4)
                    self.app._set_status(
                        "⚠  PDF/A requires PyMuPDF ≥ 1.24; saved as standard PDF", WARN)
                    messagebox.showwarning(
                        "PDF/A",
                        "Full PDF/A conversion requires PyMuPDF ≥ 1.24.\n"
                        "File saved as a cleaned standard PDF instead.\n\n"
                        "Upgrade:  pip install --upgrade PyMuPDF")
                    doc.close()
                    return
                doc.close()
                msg = f"PDF/A-{self._pdfa_level.get()} saved"

            RECENT.push(src)
            self.app._set_status(f"✓  {msg} → {Path(out).name}", SUCCESS)
            messagebox.showinfo("Done", f"{msg}:\n{out}")
        except Exception as e:
            messagebox.showerror("Error", str(e))
