from __future__ import annotations
import re, os
import tkinter as tk
from tkinter import filedialog, messagebox
import pymupdf as fitz
import customtkinter as ctk
from ..tool_base import ToolBase, register
from ..theme import CARD2, TEXT, MUTED, SUCCESS, WARN
from ..job_queue import atomic_output


@register
class BookmarksTool(ToolBase):
    section = "ORGANISE"
    label   = "🔖  Split by Bookmarks"

    def show(self):
        app  = self.app
        body = self._card("🔖  Split by Bookmarks",
                          "Split a PDF at its chapter / section bookmarks")
        self._path = tk.StringVar()
        top = ctk.CTkFrame(body, fg_color="transparent")
        top.pack(fill="x", padx=24, pady=8)
        ctk.CTkEntry(top, textvariable=self._path, state="readonly",
                     placeholder_text="No file selected…", height=44
                     ).pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(top, text="Open PDF", width=136, height=44,
                      command=self._open).pack(side="left")

        self._tree_frame = ctk.CTkScrollableFrame(body, fg_color=CARD2,
                                                   corner_radius=8, height=200)
        self._tree_frame.pack(fill="x", padx=24, pady=8)
        self._tree_lbl = ctk.CTkLabel(self._tree_frame,
                                       text="Open a PDF to see its bookmarks",
                                       text_color=MUTED, font=ctk.CTkFont(size=13))
        self._tree_lbl.pack(pady=20)

        self._level_var = tk.StringVar(value="Top-level only (level 1)")
        ctk.CTkLabel(body, text="Split at:", text_color=TEXT, anchor="w",
                     font=ctk.CTkFont(size=13)).pack(padx=24, pady=(4, 2), fill="x")
        for val in ["Top-level only (level 1)", "All bookmark levels"]:
            ctk.CTkRadioButton(body, text=val, variable=self._level_var,
                               value=val, text_color=TEXT).pack(padx=36, pady=2, anchor="w")

        app._big_btn(body, "  Split by Bookmarks  →",
                     self._run).pack(fill="x", padx=24, pady=16)
        self._doc = None
        self._toc = []

    def _open(self):
        f = filedialog.askopenfilename(filetypes=[("PDF", "*.pdf")])
        if not f:
            return
        # Kept open so a password entered here also covers the split.
        doc = self.app._open_pdf_safe(f)
        if not doc:
            return
        self._close_doc()
        self._doc = doc
        self._path.set(f)
        toc = doc.get_toc()
        self._toc = toc
        for w in self._tree_frame.winfo_children():
            w.destroy()
        if not toc:
            ctk.CTkLabel(self._tree_frame,
                         text="⚠  This PDF has no bookmarks.",
                         text_color=WARN, font=ctk.CTkFont(size=13)).pack(pady=20)
            return
        for level, title, page, *_ in toc[:60]:
            indent = "  " * (level - 1) + ("▸ " if level == 1 else "  ")
            color  = TEXT if level == 1 else MUTED
            weight = "bold" if level == 1 else "normal"
            ctk.CTkLabel(self._tree_frame,
                         text=f"{indent}{title}  (p.{page})",
                         font=ctk.CTkFont(size=12, weight=weight),
                         text_color=color, anchor="w").pack(fill="x", padx=8, pady=1)
        if len(toc) > 60:
            ctk.CTkLabel(self._tree_frame,
                         text=f"… and {len(toc) - 60} more bookmarks",
                         text_color=MUTED, font=ctk.CTkFont(size=11)).pack(pady=4)

    def _run(self):
        src = self._path.get()
        if not src or self._doc is None:
            return messagebox.showwarning("Bookmarks", "Select a PDF first.")
        if not self._toc:
            return messagebox.showwarning("Bookmarks", "PDF has no bookmarks.")
        all_levels = "All" in self._level_var.get()
        total = len(self._doc)
        chosen = [(title, page) for level, title, page, *_ in self._toc
                  if all_levels or level == 1]
        # get_toc reports -1 for a bookmark with no page target; levels can
        # also point backwards, so chapters are cut in page order.
        entries = sorted(((t, p - 1) for t, p in chosen if 1 <= p <= total),
                         key=lambda e: e[1])
        skipped = len(chosen) - len(entries)
        if not entries:
            return messagebox.showwarning("Bookmarks",
                                          "No matching bookmarks point to a page.")
        out_dir = self.app._ask_dir()
        if not out_dir:
            return
        entries.append(("_END_", total))
        app, parts = self.app, len(entries) - 1

        def work(stop):
            count = 0
            for i, (title, start) in enumerate(entries[:-1]):
                if stop.is_set():
                    break
                end  = entries[i + 1][1] - 1
                if start > end:
                    continue
                safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', title)[:50].strip()
                target = os.path.join(out_dir, f"{i + 1:02d}_{safe}.pdf")
                self._release(target)
                with atomic_output(target) as tmp, fitz.open() as nd:
                    nd.insert_pdf(self._doc, from_page=start, to_page=end)
                    nd.save(tmp, deflate=True)
                count += 1
                app.after(0, lambda v=(i + 1) / parts: app._prog_update(v))
            return count

        def done(count):
            self.app._set_status(
                f"✓  Split into {count} chapter(s) → {out_dir}", SUCCESS)
            note = (f"\n\n{skipped} bookmark(s) with no page target were skipped."
                    if skipped else "")
            messagebox.showinfo("Done",
                                f"Split into {count} file(s):\n{out_dir}{note}")

        self._run_on_doc(work, "Splitting by bookmarks…", done)
