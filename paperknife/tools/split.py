from __future__ import annotations
import tkinter as tk
from tkinter import filedialog, messagebox
import os
from pathlib import Path
import fitz
from ..tool_base import ToolBase, register
from ..theme import CARD, TEXT, MUTED, SUCCESS
from ..recent import RECENT


@register
class SplitTool(ToolBase):
    section = "ORGANISE"
    label   = "✂   Split"

    def show(self):
        import customtkinter as ctk
        app  = self.app
        body = self._card("✂  Split PDF",
                          "Extract pages or page ranges · Ctrl+O to pick file · Ctrl+S to split")
        self._path = tk.StringVar()
        self._file_row(body, self._path)

        card = ctk.CTkFrame(body, fg_color=CARD, corner_radius=8)
        card.pack(fill="x", padx=24, pady=8)
        ctk.CTkLabel(card, text="Page ranges  (e.g.  1-3, 5, 7-9)",
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=TEXT, anchor="w").pack(padx=16, pady=(14, 4), fill="x")
        ctk.CTkLabel(card, text="Separate with commas · leave blank to extract every page individually",
                     font=ctk.CTkFont(size=12), text_color=MUTED, anchor="w"
                     ).pack(padx=16, pady=(0, 8), fill="x")
        self._ranges = ctk.CTkEntry(card, height=44,
                                    placeholder_text="e.g.  1-3, 5, 7-9",
                                    font=ctk.CTkFont(size=14))
        self._ranges.pack(fill="x", padx=16, pady=(0, 16))

        app._big_btn(body, "  Split PDF  →", self._run).pack(fill="x", padx=24, pady=16)
        app._cur_open_fn = lambda: self._path.set(
            filedialog.askopenfilename(filetypes=[("PDF", "*.pdf")]) or self._path.get())
        app._cur_save_fn = self._run

    def _run(self):
        src = self._path.get()
        if not src:
            return messagebox.showwarning("Split", "Select a PDF first.")
        ranges_str = self._ranges.get().strip()
        out_dir = filedialog.askdirectory(title="Choose output folder")
        if not out_dir:
            return
        try:
            doc   = fitz.open(src)
            total = len(doc)
            groups: list[tuple[int, int]] = []
            if ranges_str:
                for part in ranges_str.split(","):
                    part = part.strip()
                    if "-" in part:
                        a, b = [int(x) for x in part.split("-")]
                        groups.append((max(a - 1, 0), min(b - 1, total - 1)))
                    else:
                        p = int(part) - 1
                        groups.append((p, p))
            else:
                groups = [(i, i) for i in range(total)]

            base = Path(src).stem
            for i, (fr, to) in enumerate(groups):
                nd = fitz.open()
                nd.insert_pdf(doc, from_page=fr, to_page=to)
                nd.save(os.path.join(out_dir,
                                     f"{base}_part{i + 1:02d}_p{fr + 1}-{to + 1}.pdf"),
                        deflate=True)
                nd.close()
            doc.close()
            RECENT.push(src, total)
            self.app._set_status(f"✓  Split into {len(groups)} file(s) → {out_dir}", SUCCESS)
            messagebox.showinfo("Done",
                                f"Created {len(groups)} file(s) in:\n{out_dir}")
        except Exception as e:
            messagebox.showerror("Split Error", str(e))
