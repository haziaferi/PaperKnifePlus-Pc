from __future__ import annotations
import tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path
from datetime import date
import pymupdf as fitz
import customtkinter as ctk
from ..tool_base import ToolBase, register
from ..theme import ACCENT, ACCENT_H, CARD, TEXT, MUTED, SUCCESS
from ..job_queue import atomic_output
from ..pages import PageRangeError, selected_pages

_TOKENS = (
    "Use {page} for page number · {total} for total pages · "
    "{date} for today's date"
)
_FONTS = ["helv", "tiro", "cour"]
_FONT_LABELS = ["Helvetica", "Times Roman", "Courier"]


@register
class HeaderFooterTool(ToolBase):
    section = "ENHANCE"
    label   = "📋  Header / Footer"

    def show(self):
        app  = self.app
        body = self._card("📋  Header / Footer",
                          "Stamp text into the top or bottom margin of every page")
        self._path = tk.StringVar()
        self._file_row(body, self._path)

        card = ctk.CTkFrame(body, fg_color=CARD, corner_radius=8)
        card.pack(fill="x", padx=24, pady=8)

        # ── position grid ─────────────────────────────────────────────────────
        ctk.CTkLabel(card, text="Position",
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=TEXT, anchor="w").pack(padx=16, pady=(14, 6), fill="x")
        pos_grid = ctk.CTkFrame(card, fg_color="transparent")
        pos_grid.pack(padx=16, pady=(0, 8), anchor="w")
        self._pos = tk.StringVar(value="bottom-center")
        positions = [
            ("top-left",    "↖ Top left",    0, 0),
            ("top-center",  "↑ Top center",  0, 1),
            ("top-right",   "↗ Top right",   0, 2),
            ("bottom-left", "↙ Bot left",    1, 0),
            ("bottom-center","↓ Bot center", 1, 1),
            ("bottom-right","↘ Bot right",   1, 2),
        ]
        for val, lbl, r, c in positions:
            ctk.CTkRadioButton(pos_grid, text=lbl, variable=self._pos, value=val,
                               text_color=TEXT, font=ctk.CTkFont(size=12)
                               ).grid(row=r, column=c, padx=10, pady=3, sticky="w")

        ctk.CTkFrame(card, height=1, fg_color=MUTED).pack(fill="x", padx=16, pady=6)

        # ── content ───────────────────────────────────────────────────────────
        ctk.CTkLabel(card, text="Content",
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=TEXT, anchor="w").pack(padx=16, pady=(4, 4), fill="x")
        ctk.CTkLabel(card, text=_TOKENS,
                     font=ctk.CTkFont(size=11), text_color=MUTED, anchor="w"
                     ).pack(padx=16, pady=(0, 4), fill="x")
        self._content = tk.StringVar(value="Page {page} of {total}")
        ctk.CTkEntry(card, textvariable=self._content, height=40,
                     font=ctk.CTkFont(size=14)
                     ).pack(fill="x", padx=16, pady=(0, 8))

        ctk.CTkFrame(card, height=1, fg_color=MUTED).pack(fill="x", padx=16, pady=4)

        # ── style options ─────────────────────────────────────────────────────
        ctk.CTkLabel(card, text="Style",
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=TEXT, anchor="w").pack(padx=16, pady=(8, 4), fill="x")
        srow = ctk.CTkFrame(card, fg_color="transparent")
        srow.pack(fill="x", padx=16, pady=4)

        ctk.CTkLabel(srow, text="Font:", width=60, text_color=TEXT,
                     anchor="w").pack(side="left")
        self._font = ctk.CTkOptionMenu(srow, values=_FONT_LABELS,
                                        width=150, height=36)
        self._font.set("Helvetica")
        self._font.pack(side="left", padx=(0, 16))

        ctk.CTkLabel(srow, text="Size:", width=46, text_color=TEXT,
                     anchor="w").pack(side="left")
        self._size = ctk.CTkEntry(srow, width=56, height=36)
        self._size.insert(0, "10")
        self._size.pack(side="left", padx=(0, 16))

        ctk.CTkLabel(srow, text="Margin:", width=66, text_color=TEXT,
                     anchor="w").pack(side="left")
        self._margin = ctk.CTkEntry(srow, width=56, height=36)
        self._margin.insert(0, "20")
        self._margin.pack(side="left")
        ctk.CTkLabel(srow, text="pt", text_color=MUTED,
                     font=ctk.CTkFont(size=12)).pack(side="left", padx=4)

        # ── page range ────────────────────────────────────────────────────────
        prow = ctk.CTkFrame(card, fg_color="transparent")
        prow.pack(fill="x", padx=16, pady=(8, 4))
        ctk.CTkLabel(prow, text="Apply to pages:", width=140,
                     text_color=TEXT, anchor="w").pack(side="left")
        self._page_range = ctk.CTkEntry(prow, width=180, height=36,
                                         placeholder_text="all  or  1-5, 8, 10-end")
        self._page_range.pack(side="left")
        ctk.CTkLabel(prow, text="(blank = all pages)",
                     text_color=MUTED, font=ctk.CTkFont(size=11)
                     ).pack(side="left", padx=8)

        ctk.CTkButton(card, text="  Apply Header / Footer  →",
                      height=44, fg_color=ACCENT, hover_color=ACCENT_H,
                      font=ctk.CTkFont(size=14, weight="bold"),
                      command=self._run,
                      ).pack(fill="x", padx=16, pady=(12, 16))

        app._cur_open_fn = lambda: self._path.set(
            filedialog.askopenfilename(filetypes=[("PDF","*.pdf")]) or self._path.get())

    def _run(self):
        src = self._path.get()
        if not src:
            return messagebox.showwarning("Header/Footer", "Select a PDF first.")
        content_tmpl = self._content.get().strip()
        if not content_tmpl:
            return messagebox.showwarning("Header/Footer", "Enter content text.")
        pos    = self._pos.get()
        fi     = _FONT_LABELS.index(self._font.get())
        font   = _FONTS[fi]
        try:
            size   = float(self._size.get()   or "10")
            margin = float(self._margin.get() or "20")
        except ValueError:
            return messagebox.showwarning(
                "Header/Footer", "Enter numeric values for size and margin.")

        range_str = self._page_range.get().strip()
        today_str = date.today().strftime("%Y-%m-%d")

        doc = self.app._open_pdf_safe(src)
        if doc is None:
            return
        total = len(doc)
        try:
            pages = selected_pages(range_str, total)
        except PageRangeError as e:
            doc.close()
            return messagebox.showerror("Header/Footer", str(e))
        out = self.app._save_as("stamped.pdf")
        if not out:
            return doc.close()

        is_top   = pos.startswith("top")
        is_left  = pos.endswith("left")
        is_right = pos.endswith("right")
        try:
            with atomic_output(out) as tmp, doc:
                for pg_num in pages:
                    page = doc[pg_num]
                    w, h = page.rect.width, page.rect.height
                    text = (content_tmpl
                            .replace("{page}",  str(pg_num + 1))
                            .replace("{total}", str(total))
                            .replace("{date}",  today_str))
                    tw = fitz.get_text_length(text, fontname=font, fontsize=size)
                    if is_left:
                        x = margin
                    elif is_right:
                        x = w - margin - tw
                    else:
                        x = (w - tw) / 2

                    y = margin + size if is_top else h - margin

                    page.insert_text(
                        fitz.Point(x, y), text,
                        fontname=font, fontsize=size,
                        color=(0, 0, 0),
                    )

                doc.save(tmp, deflate=True)
            self.app._set_status(
                f"✓  Stamped {len(pages)} page(s) → {Path(out).name}", SUCCESS)
            messagebox.showinfo("Done", f"PDF with header/footer saved:\n{out}")
        except Exception as e:
            messagebox.showerror("Error", str(e))
