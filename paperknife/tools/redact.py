from __future__ import annotations
import tkinter as tk
from tkinter import messagebox
from pathlib import Path
import customtkinter as ctk
from ..page_canvas import PageCanvasTool
from ..tool_base import register
from ..theme import (ACCENT, ACCENT_H, CARD, CARD2, TEXT, MUTED, SUCCESS, WARN, DANGER, DANGER_H,
                     WARN_BG, WARN_TITLE, WARN_BODY)
from ..core import redact as core_redact
from ..core.redact import (  # noqa: F401  (old names, used by tests)
    redact_page, _page_to_image, _INFO_KEYS, _ANNOT_TEXT_KEYS, _MIN_BOX_PHRASE)

@register
class RedactTool(PageCanvasTool):
    section = "CONTENT"
    label   = "⬛  Redact"

    _start:    tuple | None = None
    _drag_id:  int | None   = None

    def show(self):
        app  = self.app
        body = self._card(
            "⬛  Redact PDF",
            "Draw rectangles over sensitive content · Apply burns them in permanently")

        # ── warning banner ────────────────────────────────────────────────────
        warn = ctk.CTkFrame(body, fg_color=WARN_BG, corner_radius=8)
        warn.pack(fill="x", padx=24, pady=(12, 4))
        ctk.CTkLabel(
            warn,
            text="⚠  Redaction is permanent and irreversible once applied.",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=WARN_TITLE,
        ).pack(padx=16, pady=(10, 2), anchor="w")
        ctk.CTkLabel(
            warn,
            text="Content under redaction boxes is completely destroyed — "
                 "not merely covered. Always work on a copy.",
            font=ctk.CTkFont(size=12), text_color=WARN_BODY, justify="left",
        ).pack(padx=16, pady=(0, 10), anchor="w")

        self._viewer_file_row(body, pady=(4, 4))

        # ── toolbar ───────────────────────────────────────────────────────────
        tb = ctk.CTkFrame(body, fg_color=CARD, corner_radius=8)
        tb.pack(fill="x", padx=24, pady=4)
        trow = ctk.CTkFrame(tb, fg_color="transparent")
        trow.pack(fill="x", padx=12, pady=10)

        # Fill colour (default black, can choose white for "whiteout")
        ctk.CTkLabel(trow, text="Fill:", text_color=TEXT,
                     font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 4))
        self._fill_var = tk.StringVar(value="Black")
        ctk.CTkOptionMenu(
            trow, variable=self._fill_var,
            values=["Black", "White"],
            width=100, height=32,
        ).pack(side="left", padx=(0, 12))

        # Search-and-redact
        ctk.CTkLabel(trow, text="Find & redact text:",
                     text_color=TEXT, font=ctk.CTkFont(size=12)
                     ).pack(side="left", padx=(8, 4))
        self._search_var = tk.StringVar()
        ctk.CTkEntry(trow, textvariable=self._search_var,
                     width=200, height=32,
                     placeholder_text="exact phrase…"
                     ).pack(side="left", padx=(0, 6))
        ctk.CTkButton(trow, text="Mark all", width=88, height=32,
                      command=self._mark_search
                      ).pack(side="left", padx=(0, 12))

        ctk.CTkLabel(trow, text="Zoom:", text_color=TEXT,
                     font=ctk.CTkFont(size=12)).pack(side="left", padx=(4, 4))
        self._viewer_zoom(trow, width=120).pack(side="left")

        self._pending_lbl = ctk.CTkLabel(
            trow, text="0 box(es) pending", width=130,
            text_color=MUTED, font=ctk.CTkFont(size=12))
        self._pending_lbl.pack(side="left", padx=12)
        ctk.CTkButton(trow, text="↩ Undo last", width=100, height=32,
                      fg_color=CARD, text_color=TEXT,
                      command=self._undo).pack(side="left", padx=4)

        c = self._viewer_canvas(body, frame_color=CARD2, cursor="crosshair")
        c.bind("<ButtonPress-1>",  self._press)
        c.bind("<B1-Motion>",       self._drag)
        c.bind("<ButtonRelease-1>", self._release)

        # ── apply / save row ──────────────────────────────────────────────────
        bot = ctk.CTkFrame(body, fg_color="transparent")
        bot.pack(fill="x", padx=24, pady=(4, 12))
        ctk.CTkButton(
            bot, text="⬛  Apply Redactions", height=46, width=220,
            fg_color=DANGER, hover_color=DANGER_H,
            font=ctk.CTkFont(size=15, weight="bold"),
            command=self._apply,
        ).pack(side="left", padx=(0, 12))
        ctk.CTkLabel(
            bot,
            text="Apply burns the marks into the PDF in memory.\n"
                 "Then save to write to disk.",
            font=ctk.CTkFont(size=11), text_color=MUTED, justify="left",
        ).pack(side="left")
        ctk.CTkButton(
            bot, text="  Save PDF  →", height=46,
            fg_color=ACCENT, hover_color=ACCENT_H,
            font=ctk.CTkFont(size=15, weight="bold"),
            command=self._save,
        ).pack(side="right")

        app._cur_open_fn = self._open
        app._cur_save_fn = self._save
        app._cur_undo_fn = self._undo
        self._viewer_reset()

    def _on_open(self):
        # (page_num, fitz.Rect in unrotated page space, search phrase or None) — not yet applied
        self._pending: list = []
        # phrase burned out of page content -> match whole words only (drawn boxes)
        self._secrets: dict[str, bool] = {}
        if getattr(self, "_pending_lbl", None) is not None and self._pending_lbl.winfo_exists():
            self._update_pending_lbl()

    # ── draw interaction ──────────────────────────────────────────────────────
    def _press(self, event):
        self._start = self._event_point(event)

    def _drag(self, event):
        if not self._start:
            return
        cx, cy = self._event_point(event)
        if self._drag_id:
            self._canvas.delete(self._drag_id)
        x0, y0 = self._start
        fill = "black" if self._fill_var.get() == "Black" else "white"
        self._drag_id = self._canvas.create_rectangle(
            x0, y0, cx, cy,
            fill=fill, outline=DANGER, width=2, stipple="gray50")

    def _release(self, event):
        if not self._start or not self._doc:
            return
        cx, cy = self._event_point(event)
        if self._drag_id:
            self._canvas.delete(self._drag_id)
            self._drag_id = None
        x0, y0 = self._start
        self._start = None
        if abs(cx - x0) < 4 and abs(cy - y0) < 4:
            return
        self._pending.append((self._pg, self._screen_rect_to_page(x0, y0, cx, cy), None))
        self._update_pending_lbl()
        self._render()

    # ── search and mark ───────────────────────────────────────────────────────
    def _mark_search(self):
        if not self._doc:
            return messagebox.showwarning("Mark", "Open a PDF first.")
        needle = self._search_var.get().strip()
        if not needle:
            return messagebox.showwarning("Mark", "Enter search text.")
        app = self.app

        def work(stop):
            return core_redact.find_phrase(
                self._doc, needle, stop,
                lambda v: app.after(0, lambda: app._prog_update(v)))

        def done(found):
            # A cancelled search marks nothing: half the matches would look like all.
            if found is None:
                return
            self._pending += found
            self._update_pending_lbl()
            if found:
                self.app._set_status(
                    f"Marked {len(found)} occurrence(s) of '{needle}' across all pages", WARN)
            else:
                messagebox.showinfo("Mark", f"'{needle}' not found in this PDF.")

        self._run_on_doc(work, f"Searching for '{needle}'…", done)

    # ── apply ─────────────────────────────────────────────────────────────────
    def _apply(self):
        if not self._pending:
            return messagebox.showinfo("Apply", "No redaction boxes drawn yet.")
        n = len(self._pending)
        if not messagebox.askyesno(
            "Confirm Redaction",
            f"Permanently destroy content under {n} redaction box(es)?\n\n"
            "This cannot be undone once saved.",
            icon="warning",
        ):
            return
        fill = core_redact.FILLS[self._fill_var.get()]
        pending = list(self._pending)
        pages = len({p[0] for p in pending})
        modes: dict[int, str] = {}      # page number -> how its line art went
        secrets: dict[str, bool] = {}
        app = self.app

        def work(stop):
            core_redact.apply_boxes(
                self._doc, pending, fill, stop,
                lambda v: app.after(0, lambda: app._prog_update(v)), modes, secrets)

        def settle(_kind):
            # Pages done are redacted in memory whatever the outcome.
            core_redact.merge_secrets(self._secrets, secrets)
            self._pending = [p for p in self._pending if p[0] not in modes]
            self._update_pending_lbl()

        def done(_):
            whole = [str(p + 1) for p, m in modes.items() if m == "whole"]
            image = [str(p + 1) for p, m in modes.items() if m == "image"]
            note = ((f" · page {', '.join(whole)}: drawings under a box removed whole"
                     if whole else "")
                    + (f" · page {', '.join(image)}: turned into an image (its text is no "
                       "longer selectable)" if image else ""))
            self.app._set_status(
                f"✓  {n} redaction(s) applied — save to write to disk{note}", SUCCESS)
            if image:
                messagebox.showwarning(
                    "Redact",
                    f"Page {', '.join(image)} holds drawings this tool cannot cut at a "
                    "box edge (a gradient mesh, or a soft mask), so the page was replaced "
                    "by an image of itself. Its text can no longer be selected or searched.")

        self._run_on_doc(work, f"Redacting {pages} page(s)…", done, settle)

    # ── undo last pending box ─────────────────────────────────────────────────
    def _undo(self):
        if self._pending:
            self._pending.pop()
            self._update_pending_lbl()
            self._render()

    def _update_pending_lbl(self):
        n = len(self._pending)
        self._pending_lbl.configure(
            text=f"{n} box{'es' if n != 1 else ''} pending",
            text_color=DANGER if n else MUTED)

    # ── render ────────────────────────────────────────────────────────────────
    def _draw_overlay(self, page):
        c    = self._canvas
        fill = "black" if self._fill_var.get() == "Black" else "white"
        for pg_num, r, _ in self._pending:
            if pg_num != self._pg:
                continue
            x0, y0, x1, y1 = self._page_to_screen(r, page)
            c.create_rectangle(x0, y0, x1, y1,
                               fill=fill, outline=DANGER, width=2, stipple="gray25")
            c.create_text((x0 + x1) / 2, (y0 + y1) / 2, text="REDACT", fill=DANGER,
                          font=("Segoe UI", 9, "bold"))

    # ── save ──────────────────────────────────────────────────────────────────
    def _save(self):
        if not self._doc:
            return messagebox.showwarning("Save", "Open a PDF first.")
        if self._pending:
            if not messagebox.askyesno(
                "Pending boxes",
                f"You have {len(self._pending)} unapplied box(es).\n"
                "They will NOT be burned in unless you click 'Apply Redactions' first.\n\n"
                "Save anyway (without applying)?",
            ):
                return
        out = self.app._save_as("redacted.pdf")
        if not out:
            return

        def work(stop):
            removed = core_redact.scrub_secrets(self._doc, self._secrets)
            # garbage=4 + no incremental save: the old content streams, Info dict
            # and XMP stream must not survive as unreferenced objects in the file.
            self._save_doc(out, deflate=True, garbage=4, clean=True)
            return removed

        def done(removed):
            self.app._set_status(f"✓  Saved → {Path(out).name}", SUCCESS)
            extra = ("\n\nAlso removed from: " + ", ".join(removed)) if removed else ""
            messagebox.showinfo("Saved", f"Redacted PDF saved:\n{out}{extra}")

        self._run_on_doc(work, f"Saving {Path(out).name}…", done)
