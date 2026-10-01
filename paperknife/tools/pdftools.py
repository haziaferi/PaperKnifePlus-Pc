from __future__ import annotations
import tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path
import customtkinter as ctk
from ..tool_base import ToolBase, register
from ..job_queue import atomic_output
from ..theme import CARD, TEXT, MUTED, SUCCESS
from ..recent import RECENT


@register
class PdfToolsTool(ToolBase):
    section = "ENHANCE"
    label   = "🔧  PDF Tools"

    def show(self):
        app  = self.app
        body = self._card("🔧  PDF Tools", "Repair corrupt files")
        self._path = tk.StringVar()
        self._file_row(body, self._path)

        # PDF/A and Linearise were removed: PyMuPDF 1.28 has no save(pdfa=)
        # and save(linear=True) raises "Linearisation is no longer supported".
        self._op = tk.StringVar(value="repair")
        ops = [
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

        app._big_btn(body, "  Run  →", self._run).pack(fill="x", padx=24, pady=16)
        app._cur_open_fn = lambda: self._path.set(
            filedialog.askopenfilename(filetypes=[("PDF", "*.pdf")]) or self._path.get())

    def _run(self):
        src = self._path.get()
        if not src:
            return messagebox.showwarning("PDF Tools", "Select a PDF first.")
        # MuPDF rebuilds a broken xref while opening; the garbage/clean save
        # then writes a fresh, consistent file from what it recovered.
        doc = self._open_safe(src)
        if doc is None:
            return
        out = self.app._save_as("repaired.pdf")
        if not out:
            return doc.close()
        try:
            with atomic_output(out) as tmp, doc:
                repaired = doc.is_repaired
                doc.save(tmp, deflate=True, garbage=4, clean=True)
            msg = ("Repaired PDF saved" if repaired
                   else "No damage found; cleaned copy saved")
            RECENT.push(src)
            self.app._set_status(f"✓  {msg} → {Path(out).name}", SUCCESS)
            messagebox.showinfo("Done", f"{msg}:\n{out}")
        except Exception as e:
            messagebox.showerror("Error", str(e))
