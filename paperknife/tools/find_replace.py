from __future__ import annotations
import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk
from ..page_canvas import PageCanvasTool
from ..tool_base import register
from ..theme import ACCENT, ACCENT_H, CARD, TEXT, MUTED, SUCCESS, HIT, HIT_CUR, HIT_EDGE, _tk_color
from ..core import text as core_text
from ..core.text import (  # noqa: F401  (old names)
    find_matches as _find_matches, unicode_font as _unicode_font)


@register
class FindReplaceTool(PageCanvasTool):
    section = "CONTENT"
    label   = "🔍  Find & Replace"
    save_name  = "replaced.pdf"
    saved_what = "PDF"

    _hit_idx:  int   = -1

    def show(self):
        app  = self.app
        body = self._card("🔍  Find & Replace",
                          "Search PDF text and replace across all pages · Ctrl+S to save")
        # Pages are reached through the hits, so there are no page buttons.
        self._viewer_file_row(body, pady=8, height=44, button_width=136, page_buttons=False)

        # ── search / replace ──────────────────────────────────────────────────
        sr_card = ctk.CTkFrame(body, fg_color=CARD, corner_radius=8)
        sr_card.pack(fill="x", padx=24, pady=8)
        r1 = ctk.CTkFrame(sr_card, fg_color="transparent")
        r1.pack(fill="x", padx=16, pady=(14, 4))
        ctk.CTkLabel(r1, text="Find:", width=90, text_color=TEXT,
                     anchor="w").pack(side="left")
        self._find_var = tk.StringVar()
        self._find_ent = ctk.CTkEntry(r1, textvariable=self._find_var,
                                       height=40, placeholder_text="Search text…")
        self._find_ent.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(r1, text="Find All", width=90, height=40,
                      command=self._find_all).pack(side="left")
        r2 = ctk.CTkFrame(sr_card, fg_color="transparent")
        r2.pack(fill="x", padx=16, pady=(4, 14))
        ctk.CTkLabel(r2, text="Replace:", width=90, text_color=TEXT,
                     anchor="w").pack(side="left")
        self._repl_var = tk.StringVar()
        self._repl_ent = ctk.CTkEntry(r2, textvariable=self._repl_var,
                                       height=40, placeholder_text="Replacement text…")
        self._repl_ent.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(r2, text="Replace All", width=110, height=40,
                      fg_color=ACCENT, hover_color=ACCENT_H,
                      command=self._replace_all).pack(side="left")

        # ── hit counter & nav ─────────────────────────────────────────────────
        nav = ctk.CTkFrame(body, fg_color="transparent")
        nav.pack(fill="x", padx=24, pady=4)
        ctk.CTkButton(nav, text="◀ Prev", width=90,
                      command=lambda: self._jump(-1)).pack(side="left", padx=4)
        ctk.CTkButton(nav, text="Next ▶", width=90,
                      command=lambda: self._jump(1)).pack(side="left", padx=4)
        self._hit_lbl = ctk.CTkLabel(nav, text="",
                                      text_color=MUTED, font=ctk.CTkFont(size=13))
        self._hit_lbl.pack(side="left", padx=12)

        self._viewer_canvas(body, frame_color=CARD)

        ctk.CTkButton(body, text="  Save PDF  →", height=46,
                      command=self._save,
                      fg_color=ACCENT, hover_color=ACCENT_H,
                      font=ctk.CTkFont(size=15, weight="bold")
                      ).pack(fill="x", padx=24, pady=8)

        app._cur_open_fn = self._open
        app._cur_save_fn = self._save
        app._cur_undo_fn = self._undo
        # Undo restores the whole document as it was before each Replace All.
        self._viewer_reset()

    def _on_open(self):
        self._hits: list = []   # (page_num, [rect per line of the match])
        self._hit_idx = -1

    # ── search ────────────────────────────────────────────────────────────────
    def _find_all(self):
        if not self._doc:
            return messagebox.showwarning("Find", "Open a PDF first.")
        needle = self._find_var.get().strip()
        if not needle:
            return
        app = self.app

        def work(stop):
            found = core_text.find_all(
                self._doc, needle, stop,
                lambda v: app.after(0, lambda: app._prog_update(v)))
            if found is None:
                return None
            return [(pg_num, m["rects"]) for pg_num, ms in found for m in ms]

        def done(hits):
            if hits is None:            # cancelled: keep what was shown before
                return
            self._hits = hits
            if hits:
                self._hit_idx = 0
                self._pg      = hits[0][0]
                self._hit_lbl.configure(text=f"Found {len(hits)} hit(s)")
            else:
                self._hit_idx = -1
                self._hit_lbl.configure(text="Not found")
                messagebox.showinfo("Find", f"'{needle}' not found.")

        self._run_on_doc(work, f"Searching for '{needle}'…", done)

    def _jump(self, d):
        if not self._hits:
            return
        self._hit_idx = (self._hit_idx + d) % len(self._hits)
        self._pg      = self._hits[self._hit_idx][0]
        self._render()
        self._hit_lbl.configure(
            text=f"Hit {self._hit_idx + 1} / {len(self._hits)}")

    # ── replace ───────────────────────────────────────────────────────────────
    def _replace_all(self):
        if not self._doc:
            return messagebox.showwarning("Replace", "Open a PDF first.")
        needle = self._find_var.get().strip()
        repl   = self._repl_var.get()
        if not needle:
            return messagebox.showwarning("Replace", "Enter search text.")
        if not messagebox.askyesno(
                "Confirm Replace",
                f"Replace ALL occurrences of:\n  '{needle}'\nwith:\n  '{repl}'\n\n"
                "This modifies the PDF in memory (save to keep changes)."):
            return
        # insert_text(fontname="helv") encodes Latin-1 only and turns anything else
        # into "·"; an embedded built-in font keeps the characters.
        font = _unicode_font(repl)
        if font is None:
            return messagebox.showerror(
                "Replace", "The replacement contains characters no built-in font can draw.")
        app = self.app
        state = {"count": 0, "snapshot": False}

        def work(stop):
            found = core_text.find_all(
                self._doc, needle, stop,
                lambda v: app.after(0, lambda: app._prog_update(v * 0.5)))
            if not found or stop.is_set():
                return
            self._push_undo()
            state["snapshot"] = True
            try:
                core_text.replace_matches(self._doc, found, repl, font, stop)
            except Exception as e:
                raise RuntimeError(f"Nothing was replaced:\n{e}") from e
            state["count"] = sum(len(ms) for _, ms in found)

        def settle(kind):
            # All or nothing: pages already done would keep their text removed.
            if kind != "done" and state["snapshot"]:
                self._pop_undo()

        def done(_):
            count = state["count"]
            self._hits = []
            self._hit_idx = -1
            self._hit_lbl.configure(text=f"Replaced {count} occurrence(s)")
            self.app._set_status(
                f"✓  Replaced {count} occurrence(s) · Save to write to disk", SUCCESS)

        self._run_on_doc(work, f"Replacing '{needle}'…", done, settle)

    # ── render ────────────────────────────────────────────────────────────────
    def _draw_overlay(self, page):
        for hi, (pg_num, rects) in enumerate(self._hits):
            if pg_num != self._pg:
                continue
            is_cur = hi == self._hit_idx
            fill   = HIT_CUR if is_cur else HIT
            for rect in rects:
                x0, y0, x1, y1 = self._page_to_screen(rect, page)
                self._canvas.create_rectangle(
                    x0, y0, x1, y1,
                    fill=fill, outline=_tk_color(ACCENT) if is_cur else HIT_EDGE,
                    stipple="gray50" if not is_cur else "", width=2)

    # ── undo ──────────────────────────────────────────────────────────────────
    def _undo(self):
        if not self._undo_stack or not self._doc:
            return
        self._pop_undo()
        self._hits = []
        self._hit_idx = -1
        self._hit_lbl.configure(text="Replace undone")
        self._render()
