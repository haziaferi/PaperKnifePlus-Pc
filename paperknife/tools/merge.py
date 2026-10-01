from __future__ import annotations
import tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path
import fitz
import customtkinter as ctk
from ..tool_base import ToolBase, register
from ..theme import ACCENT, ACCENT_H, CARD, CARD2, TEXT, MUTED, DANGER, DANGER_H, SUCCESS
from ..recent import RECENT


def _parse_range(range_str: str, total: int) -> list[int]:
    """Parse '1-3, 5, 8-end' into a 0-based page list. Returns all pages if blank."""
    if not range_str.strip():
        return list(range(total))
    pages: list[int] = []
    for part in range_str.split(","):
        part = part.strip().lower().replace("end", str(total))
        if "-" in part:
            a, b = part.split("-", 1)
            pages += list(range(int(a) - 1, int(b)))
        else:
            pages.append(int(part) - 1)
    return [p for p in pages if 0 <= p < total]


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
        name_btn = ctk.CTkButton(
            row, text=name, anchor="w", fg_color="transparent",
            text_color=TEXT, hover_color=CARD2, height=32,
            command=lambda i=idx: self._select(i))
        name_btn.pack(side="left", fill="x", expand=True)

        # Page range field
        ctk.CTkLabel(row, text="Pages:", text_color=MUTED,
                     font=ctk.CTkFont(size=11)).pack(side="left", padx=(8, 2))
        range_ent = ctk.CTkEntry(row, textvariable=rv, width=160, height=30,
                                  placeholder_text="all  or  1-3, 5, 8-end",
                                  font=ctk.CTkFont(size=11))
        range_ent.pack(side="left", padx=(0, 4))

        self._entries.append({"path": path, "range_var": rv,
                               "row": row, "idx_lbl": idx_lbl})

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
        out = self.app._save_as("merged.pdf")
        if not out:
            return
        app = self.app
        # Snapshot entries (path + range string) before threading
        jobs = [(e["path"], e["range_var"].get()) for e in self._entries]

        def work(stop):
            merged = fitz.open()
            pg_total = 0
            for i, (path, rng) in enumerate(jobs):
                if stop.is_set():
                    return
                src   = fitz.open(path)
                total = len(src)
                pages = _parse_range(rng, total)
                pg_total += len(pages)
                for pg in pages:
                    merged.insert_pdf(src, from_page=pg, to_page=pg)
                src.close()
                RECENT.push(path, total)
                app.after(0, lambda v=(i+1)/len(jobs): app._prog_update(v))
            merged.save(out, deflate=True)
            merged.close()
            app.after(0, lambda: [
                app._set_status(
                    f"✓  Merged {len(jobs)} file(s) · {pg_total} pages → "
                    f"{Path(out).name}", SUCCESS),
                messagebox.showinfo("Merge Complete", f"Merged PDF saved:\n{out}"),
            ])

        app._set_status("Merging…")
        app.run_job(work, f"Merging {len(jobs)} PDF(s)…")
