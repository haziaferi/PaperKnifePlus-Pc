from __future__ import annotations
import tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path
import fitz
import customtkinter as ctk
from ..tool_base import ToolBase, register
from ..theme import ACCENT, CARD2, TEXT, MUTED, DANGER, DANGER_H, SUCCESS
from ..recent import RECENT
from ..pages import PageRangeError, parse_ranges


@register
class MergeTool(ToolBase):
    section = "ORGANISE"
    label   = "📎  Merge"

    def show(self):
        app  = self.app
        body = self._card("📎  Merge PDFs",
                          "Combine PDFs · set per-file page ranges · drag to reorder")

        ctk.CTkLabel(body,
                     text="Add PDFs in order · optionally set page ranges per file"
                          " (e.g.  1-3, 5, 8-end)  ·  leave blank to include all pages",
                     font=ctk.CTkFont(size=12), text_color=MUTED, anchor="w",
                     wraplength=800,
                     ).pack(padx=24, pady=(12, 4), fill="x")

        # ── file list with per-entry range fields ─────────────────────────────
        list_frame = ctk.CTkScrollableFrame(body, fg_color=CARD2,
                                             corner_radius=8, height=240)
        list_frame.pack(fill="x", padx=24, pady=4)
        self._list_frame = list_frame
        self._entries: list[dict] = []   # [{path, range_var, row_frame}, …]

        if app._dnd_ok:
            try:
                from tkinterdnd2 import DND_FILES
                list_frame.drop_target_register(DND_FILES)
                list_frame.dnd_bind("<<Drop>>", self._on_drop)
            except Exception:
                pass

        # ── list controls ─────────────────────────────────────────────────────
        ctrl = ctk.CTkFrame(body, fg_color="transparent")
        ctrl.pack(fill="x", padx=24, pady=6)
        ctk.CTkButton(ctrl, text="＋ Add PDFs", width=130,
                      command=self._add).pack(side="left", padx=4)
        ctk.CTkButton(ctrl, text="↑ Up", width=72,
                      command=lambda: self._move(-1)).pack(side="left", padx=4)
        ctk.CTkButton(ctrl, text="↓ Down", width=80,
                      command=lambda: self._move(1)).pack(side="left", padx=4)
        ctk.CTkButton(ctrl, text="✕ Remove selected", width=148,
                      fg_color=DANGER, hover_color=DANGER_H,
                      command=self._remove).pack(side="left", padx=4)
        self._sel_idx: int | None = None

        app._big_btn(body, "  Merge PDFs  →", self._run).pack(fill="x", padx=24, pady=16)
        app._cur_open_fn = self._add
        app._cur_del_fn  = self._remove

    # ── list management ───────────────────────────────────────────────────────
    def _add_entry(self, path: str):
        idx = len(self._entries)
        rv  = tk.StringVar()
        row = ctk.CTkFrame(self._list_frame, fg_color="transparent")
        row.pack(fill="x", pady=2)

        # Index label
        idx_lbl = ctk.CTkLabel(row, text=f"{idx+1}.", width=28,
                               text_color=MUTED, font=ctk.CTkFont(size=12))
        idx_lbl.pack(side="left")

        # Filename
        name = Path(path).name
        if len(name) > 46:
            name = name[:43] + "…"
        entry = {"path": path, "range_var": rv, "row": row, "idx_lbl": idx_lbl}
        # Rows move and disappear, so the click looks up the entry's index now.
        name_btn = ctk.CTkButton(
            row, text=name, anchor="w", fg_color="transparent",
            text_color=TEXT, hover_color=CARD2, height=32,
            command=lambda: self._select(self._entries.index(entry)))
        name_btn.pack(side="left", fill="x", expand=True)

        app = self.app

        def _enter(e, p=path):
            if app._last_hover_path != p:
                app._last_hover_path = p
                app.after(400, lambda x=e.x_root, y=e.y_root:
                          app._show_tooltip(x, y, p)
                          if app._last_hover_path == p else None)

        name_btn.bind("<Enter>", _enter)
        name_btn.bind("<Leave>", app._hide_tooltip)

        # Page range field
        ctk.CTkLabel(row, text="Pages:", text_color=MUTED,
                     font=ctk.CTkFont(size=11)).pack(side="left", padx=(8, 2))
        range_ent = ctk.CTkEntry(row, textvariable=rv, width=160, height=30,
                                  placeholder_text="all  or  1-3, 5, 8-end",
                                  font=ctk.CTkFont(size=11))
        range_ent.pack(side="left", padx=(0, 4))

        self._entries.append(entry)

    def _renumber(self):
        for i, e in enumerate(self._entries):
            e["idx_lbl"].configure(text=f"{i+1}.")

    def _select(self, idx: int):
        self._sel_idx = idx
        for i, e in enumerate(self._entries):
            e["row"].configure(fg_color=ACCENT if i == idx else "transparent")

    def _move(self, d: int):
        i = self._sel_idx
        if i is None:
            return
        j = i + d
        if 0 <= j < len(self._entries):
            self._entries[i], self._entries[j] = self._entries[j], self._entries[i]
            # Re-pack in new order
            for e in self._entries:
                e["row"].pack_forget()
            for e in self._entries:
                e["row"].pack(fill="x", pady=2)
            self._sel_idx = j
            self._select(j)
            self._renumber()

    def _remove(self):
        i = self._sel_idx
        if i is None or i >= len(self._entries):
            return
        self._entries[i]["row"].destroy()
        self._entries.pop(i)
        self._sel_idx = None
        self._renumber()

    def _on_drop(self, event):
        for p in self.app._parse_drop(event.data):
            if Path(p).suffix.lower() == ".pdf":
                self._add_entry(p)

    def _add(self):
        for f in filedialog.askopenfilenames(
                filetypes=[("PDF", "*.pdf"), ("All", "*.*")]):
            self._add_entry(f)

    # ── merge ─────────────────────────────────────────────────────────────────
    def _run(self):
        if not self._entries:
            return messagebox.showwarning("Merge", "Add at least one PDF file.")
        app = self.app
        # Open (and unlock) every input and check its range on the Tk thread,
        # so a password prompt or a bad range stops the merge before it starts.
        jobs: list[tuple[str, fitz.Document, list[tuple[int, int]]]] = []

        def close_all():
            for _, d, _ in jobs:
                d.close()

        for e in self._entries:
            path, rng = e["path"], e["range_var"].get().strip()
            src = app._open_pdf_safe(path)
            if not src:
                return close_all()
            try:
                groups = (parse_ranges(rng, len(src)) if rng
                          else [(0, len(src) - 1)])
            except PageRangeError as err:
                src.close()
                close_all()
                return messagebox.showerror("Merge", f"{Path(path).name}:\n{err}")
            jobs.append((path, src, groups))
        out = app._save_as("merged.pdf")
        if not out:
            return close_all()
        n = len(jobs)

        def work(stop):
            merged = fitz.open()
            pg_total = 0
            try:
                for i, (path, src, groups) in enumerate(jobs):
                    if stop.is_set():
                        return
                    for fr, to in groups:
                        merged.insert_pdf(src, from_page=fr, to_page=to)
                        pg_total += to - fr + 1
                    RECENT.push(path, len(src))
                    app.after(0, lambda v=(i+1)/n: app._prog_update(v))
                merged.save(out, deflate=True)
            finally:
                merged.close()
                close_all()
            app.after(0, lambda: [
                app._set_status(
                    f"✓  Merged {len(jobs)} file(s) · {pg_total} pages → "
                    f"{Path(out).name}", SUCCESS),
                messagebox.showinfo("Merge Complete", f"Merged PDF saved:\n{out}"),
            ])

        app._set_status("Merging…")
        app.run_job(work, f"Merging {len(jobs)} PDF(s)…")
