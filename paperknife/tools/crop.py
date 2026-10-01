from __future__ import annotations
import tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path
import fitz
import customtkinter as ctk
from ..tool_base import ToolBase, register
from ..theme import ACCENT, ACCENT_H, CARD, TEXT, MUTED, SUCCESS
from ..recent import RECENT


@register
class CropTool(ToolBase):
    section = "ENHANCE"
    label   = "✂   Crop / Trim"

    def show(self):
        app  = self.app
        body = self._card("✂  Crop / Trim Pages",
                          "Adjust page crop box by specifying margins in points (1 pt = 0.353 mm)")
        self._path = tk.StringVar()
        self._file_row(body, self._path)

        card = ctk.CTkFrame(body, fg_color=CARD, corner_radius=8)
        card.pack(fill="x", padx=24, pady=8)

        ctk.CTkLabel(card, text="Margins to remove (in points)",
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=TEXT, anchor="w").pack(padx=16, pady=(14, 8), fill="x")
        ctk.CTkLabel(card,
                     text="Enter how much to cut from each edge.  "
                          "A4 = 595 × 842 pt  ·  Letter = 612 × 792 pt  ·  "
                          "72 pt = 1 inch = 25.4 mm",
                     font=ctk.CTkFont(size=11), text_color=MUTED,
                     anchor="w", wraplength=700
                     ).pack(padx=16, pady=(0, 10), fill="x")

        # 4 margin fields in a cross layout
        self._margins: dict[str, tk.StringVar] = {}
        grid = ctk.CTkFrame(card, fg_color="transparent")
        grid.pack(padx=16, pady=(0, 8))

        def mfield(label, key, r, c):
            f = ctk.CTkFrame(grid, fg_color="transparent")
            f.grid(row=r, column=c, padx=8, pady=4)
            ctk.CTkLabel(f, text=label, text_color=MUTED,
                         font=ctk.CTkFont(size=12)).pack()
            var = tk.StringVar(value="0")
            ctk.CTkEntry(f, textvariable=var, width=90, height=38,
                         font=ctk.CTkFont(size=14)).pack()
            self._margins[key] = var

        mfield("Top",    "top",    0, 1)
        mfield("Left",   "left",   1, 0)
        mfield("Right",  "right",  1, 2)
        mfield("Bottom", "bottom", 2, 1)

        ctk.CTkFrame(grid, width=90, height=38, fg_color=ACCENT,
                     corner_radius=6).grid(row=1, column=1, padx=8, pady=4)

        # Mode: apply to all or range
        r1 = ctk.CTkFrame(card, fg_color="transparent")
        r1.pack(fill="x", padx=16, pady=(4, 4))
        ctk.CTkLabel(r1, text="Apply to:", width=100, text_color=TEXT,
                     anchor="w").pack(side="left")
        self._page_range = ctk.CTkEntry(r1, width=220, height=36,
                                         placeholder_text="all  or  1-5, 8, 10-end")
        self._page_range.pack(side="left")
        ctk.CTkLabel(r1, text="(blank = all)", text_color=MUTED,
                     font=ctk.CTkFont(size=11)).pack(side="left", padx=8)

        # Reset crop option
        self._reset_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(card, text="Reset to original crop box first (undo previous crops)",
                        variable=self._reset_var, text_color=TEXT
                        ).pack(padx=16, pady=(4, 14), anchor="w")

        ctk.CTkButton(card, text="  Apply Crop  →", command=self._run,
                      height=44, fg_color=ACCENT, hover_color=ACCENT_H,
                      font=ctk.CTkFont(size=14, weight="bold")
                      ).pack(fill="x", padx=16, pady=(0, 16))

        app._cur_open_fn = lambda: self._path.set(
            filedialog.askopenfilename(filetypes=[("PDF", "*.pdf")]) or self._path.get())

    def _run(self):
        src = self._path.get()
        if not src:
            return messagebox.showwarning("Crop", "Select a PDF first.")
        try:
            mt = float(self._margins["top"].get()    or "0")
            mr = float(self._margins["right"].get()  or "0")
            mb = float(self._margins["bottom"].get() or "0")
            ml = float(self._margins["left"].get()   or "0")
        except ValueError:
            return messagebox.showwarning("Crop", "Enter numeric values for all margins.")
        if mt == mr == mb == ml == 0:
            return messagebox.showwarning("Crop", "All margins are 0 — nothing to crop.")
        out = self.app._save_as("cropped.pdf")
        if not out:
            return
        range_str = self._page_range.get().strip()
        reset     = self._reset_var.get()
        try:
            doc   = fitz.open(src)
            total = len(doc)
            # Parse page range
            if not range_str:
                pages = list(range(total))
            else:
                pages = []
                for part in range_str.split(","):
                    part = part.strip().lower().replace("end", str(total))
                    if "-" in part:
                        a, b = part.split("-")
                        pages += list(range(int(a)-1, int(b)))
                    else:
                        pages.append(int(part)-1)
                pages = [p for p in pages if 0 <= p < total]

            for pg_num in pages:
                page = doc[pg_num]
                if reset:
                    # Restore media box as the crop box baseline
                    page.set_cropbox(page.mediabox)
                cb = page.cropbox
                new = fitz.Rect(
                    cb.x0 + ml, cb.y0 + mt,
                    cb.x1 - mr, cb.y1 - mb,
                )
                if new.is_empty or new.is_infinite:
                    continue
                page.set_cropbox(new)

            doc.save(out, deflate=True)
            doc.close()
            RECENT.push(src, total)
            self.app._set_status(
                f"✓  Cropped {len(pages)} page(s) → {Path(out).name}", SUCCESS)
            messagebox.showinfo("Done", f"Cropped PDF saved:\n{out}")
        except Exception as e:
            messagebox.showerror("Error", str(e))
