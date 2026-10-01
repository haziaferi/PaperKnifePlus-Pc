from __future__ import annotations
import re
import tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path
from PIL import Image, ImageTk
import customtkinter as ctk
import pymupdf as fitz
from ..tool_base import ToolBase, register
from ..theme import (ACCENT, ACCENT_H, CARD, CARD2, TEXT, MUTED, SUCCESS, WARN, DANGER, DANGER_H,
                     CANVAS_BG, WARN_BG, WARN_TITLE, WARN_BODY, _tk_color)
from ..pages import render

_INFO_KEYS = ("title", "author", "subject", "keywords", "creator", "producer")
# Annotation text a reader sees; the other info keys are dates, ids and icon names.
_ANNOT_TEXT_KEYS = ("content", "title", "subject")
# A line under a drawn box shorter than this (a page number, a year suffix)
# would match far too much elsewhere in the document.
_MIN_BOX_PHRASE = 4


@register
class RedactTool(ToolBase):
    section = "CONTENT"
    label   = "⬛  Redact"

    _doc:      fitz.Document | None = None
    _pg:       int   = 0
    _zoom:     float = 1.5
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

        # ── file row ──────────────────────────────────────────────────────────
        self._path_var = tk.StringVar()
        top = ctk.CTkFrame(body, fg_color="transparent")
        top.pack(fill="x", padx=24, pady=(4, 4))
        ctk.CTkEntry(top, textvariable=self._path_var, state="readonly",
                     placeholder_text="Open a PDF…", height=40
                     ).pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(top, text="Open PDF", width=128, height=40,
                      command=self._open).pack(side="left", padx=4)
        ctk.CTkButton(top, text="◀", width=40, height=40,
                      command=lambda: self._nav(-1)).pack(side="left", padx=2)
        self._pg_lbl = ctk.CTkLabel(top, text="—", width=60, text_color=TEXT)
        self._pg_lbl.pack(side="left", padx=2)
        ctk.CTkButton(top, text="▶", width=40, height=40,
                      command=lambda: self._nav(1)).pack(side="left", padx=2)

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
        self._zoom_sl = ctk.CTkSlider(trow, from_=0.5, to=3.0,
                                       number_of_steps=50, width=120)
        self._zoom_sl.set(1.5)
        self._zoom_sl.configure(command=self._on_zoom)
        self._zoom_sl.pack(side="left")

        self._pending_lbl = ctk.CTkLabel(
            trow, text="0 box(es) pending", width=130,
            text_color=MUTED, font=ctk.CTkFont(size=12))
        self._pending_lbl.pack(side="left", padx=12)
        ctk.CTkButton(trow, text="↩ Undo last", width=100, height=32,
                      fg_color=CARD, text_color=TEXT,
                      command=self._undo).pack(side="left", padx=4)

        # ── canvas ────────────────────────────────────────────────────────────
        cf = ctk.CTkFrame(body, fg_color=CARD2, corner_radius=8)
        cf.pack(fill="both", expand=True, padx=24, pady=4)
        vbar = tk.Scrollbar(cf, orient="vertical")
        vbar.pack(side="right", fill="y")
        hbar = tk.Scrollbar(cf, orient="horizontal")
        hbar.pack(side="bottom", fill="x")
        self._canvas = tk.Canvas(
            cf, bg=_tk_color(CANVAS_BG), highlightthickness=0, cursor="crosshair",
            yscrollcommand=vbar.set, xscrollcommand=hbar.set)
        self._canvas.pack(fill="both", expand=True)
        vbar.configure(command=self._canvas.yview)
        hbar.configure(command=self._canvas.xview)
        self._canvas.bind("<ButtonPress-1>",  self._press)
        self._canvas.bind("<B1-Motion>",       self._drag)
        self._canvas.bind("<ButtonRelease-1>", self._release)
        self._canvas.bind(
            "<MouseWheel>",
            lambda e: self._canvas.yview_scroll(-1 * (e.delta // 120), "units"))

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
        self._doc     = None
        self._pg      = 0
        # (page_num, fitz.Rect in unrotated page space, search phrase or None) — not yet applied
        self._pending: list = []
        # phrase burned out of page content -> match whole words only (drawn boxes)
        self._secrets: dict[str, bool] = {}

    # ── file / navigation ─────────────────────────────────────────────────────
    def _open(self):
        f = filedialog.askopenfilename(filetypes=[("PDF", "*.pdf")])
        if not f:
            return
        self._close_doc()
        self._doc     = self.app._open_pdf_safe(f)
        self._pending = []
        self._secrets = {}
        if not self._doc:
            return
        self._path_var.set(f)
        self._pg = 0
        self._render()

    def _nav(self, d):
        if not self._doc:
            return
        new = self._pg + d
        if 0 <= new < len(self._doc):
            self._pg = new
            self._render()

    def _on_zoom(self, v):
        self._zoom = float(v)
        self._render()

    # ── draw interaction ──────────────────────────────────────────────────────
    def _press(self, event):
        self._start = (self._canvas.canvasx(event.x),
                       self._canvas.canvasy(event.y))

    def _drag(self, event):
        if not self._start:
            return
        cx = self._canvas.canvasx(event.x)
        cy = self._canvas.canvasy(event.y)
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
        cx = self._canvas.canvasx(event.x)
        cy = self._canvas.canvasy(event.y)
        if self._drag_id:
            self._canvas.delete(self._drag_id)
            self._drag_id = None
        x0, y0 = self._start
        self._start = None
        if abs(cx - x0) < 4 and abs(cy - y0) < 4:
            return
        z   = self._zoom
        # The preview shows the page rotated; redaction annots live in unrotated space.
        r   = fitz.Rect(min(x0,cx)/z, min(y0,cy)/z,
                        max(x0,cx)/z, max(y0,cy)/z) * self._doc[self._pg].derotation_matrix
        self._pending.append((self._pg, r, None))
        self._update_pending_lbl()
        self._render()

    # ── search and mark ───────────────────────────────────────────────────────
    def _mark_search(self):
        if not self._doc:
            return messagebox.showwarning("Mark", "Open a PDF first.")
        needle = self._search_var.get().strip()
        if not needle:
            return messagebox.showwarning("Mark", "Enter search text.")
        count = 0
        for pg_num in range(len(self._doc)):
            # search_for ignores case; for redaction over-marking is the safe side
            # (Find & Replace needs exact case and searches the characters itself).
            for rect in self._doc[pg_num].search_for(needle):
                self._pending.append((pg_num, rect, needle))
                count += 1
        self._update_pending_lbl()
        if count:
            self._render()
            self.app._set_status(
                f"Marked {count} occurrence(s) of '{needle}' across all pages", WARN)
        else:
            messagebox.showinfo("Mark", f"'{needle}' not found in this PDF.")

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
        fill = (0, 0, 0) if self._fill_var.get() == "Black" else (1, 1, 1)
        by_page: dict[int, list[fitz.Rect]] = {}
        for pg_num, r, phrase in self._pending:
            by_page.setdefault(pg_num, []).append(r)
            if phrase:
                self._secrets[phrase] = False
            else:
                # Remember what a drawn box covered so _save can find it outside the page content.
                for ln in self._doc[pg_num].get_textbox(r).splitlines():
                    if len(ln.strip()) >= _MIN_BOX_PHRASE:
                        self._secrets.setdefault(ln.strip(), True)
        for pg_num, rects in by_page.items():
            page = self._doc[pg_num]
            # apply_redactions removes only the redact annots themselves; a note or a
            # form field under a box would keep showing (and storing) the content.
            for annot in list(page.annots()):
                if any(annot.rect.intersects(r) for r in rects):
                    page.delete_annot(annot)
            for widget in list(page.widgets()):
                if any(widget.rect.intersects(r) for r in rects):
                    page.delete_widget(widget)
            # The page thumbnail is a picture of the unredacted page.
            self._doc.xref_set_key(page.xref, "Thumb", "null")
            for r in rects:
                page.add_redact_annot(r, fill=fill)
            page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_PIXELS)
        self._pending = []
        self._update_pending_lbl()
        self.app._set_status(
            f"✓  {n} redaction(s) applied — save to write to disk", SUCCESS)
        self._render()

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
    def _render(self):
        if not self._doc:
            return
        c    = self._canvas
        page = self._doc[self._pg]
        pix  = render(page, self._zoom, shrink=True)
        img  = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        self._raw_img = ImageTk.PhotoImage(img)
        c.delete("all")
        c.create_image(0, 0, anchor="nw", image=self._raw_img)
        c.configure(scrollregion=(0, 0, pix.width, pix.height))
        self._pg_lbl.configure(
            text=f"{self._pg + 1} / {len(self._doc)}")
        z    = self._zoom
        fill = "black" if self._fill_var.get() == "Black" else "white"
        for pg_num, r, _ in self._pending:
            if pg_num != self._pg:
                continue
            r = r * page.rotation_matrix
            c.create_rectangle(
                r.x0 * z, r.y0 * z, r.x1 * z, r.y1 * z,
                fill=fill, outline=DANGER, width=2, stipple="gray25")
            c.create_text(
                (r.x0 + r.x1) / 2 * z, (r.y0 + r.y1) / 2 * z,
                text="REDACT", fill=DANGER,
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
        try:
            removed = self._scrub_secrets()
            # garbage=4 + no incremental save: the old content streams, Info dict
            # and XMP stream must not survive as unreferenced objects in the file.
            self._save_doc(out, deflate=True, garbage=4, clean=True)
            self.app._set_status(f"✓  Saved → {Path(out).name}", SUCCESS)
            extra = ("\n\nAlso removed from: " + ", ".join(removed)) if removed else ""
            messagebox.showinfo("Saved", f"Redacted PDF saved:\n{out}{extra}")
        except Exception as e:
            messagebox.showerror("Save Error", str(e))

    def _scrub_secrets(self) -> list[str]:
        """Remove every redacted phrase from the places apply_redactions does not touch.

        Returns the names of the places that were changed.
        """
        if not self._secrets:
            return []
        doc  = self._doc
        # A phrase taken from under a drawn box must not cut a longer word apart.
        pats = [re.compile(rf"(?<!\w){re.escape(s)}(?!\w)" if whole else re.escape(s),
                           re.IGNORECASE)
                for s, whole in self._secrets.items()]

        def hit(text) -> bool:
            return bool(text) and any(p.search(text) for p in pats)

        def strip(text: str) -> str:
            for p in pats:
                text = p.sub("", text)
            return text

        removed = []
        meta = doc.metadata or {}
        if any(hit(meta.get(k)) for k in _INFO_KEYS):
            doc.set_metadata({k: strip(meta.get(k) or "") for k in _INFO_KEYS})
            removed.append("document properties")
        if hit(doc.get_xml_metadata()):
            doc.del_xml_metadata()
            removed.append("XMP metadata")

        toc = doc.get_toc(simple=False)
        if any(hit(item[1]) for item in toc):
            for item in toc:
                item[1] = strip(item[1])
            doc.set_toc(toc)
            removed.append("bookmarks")

        for name in doc.embfile_names():
            info = doc.embfile_info(name)
            body = doc.embfile_get(name)
            texts = [name, info.get("filename"), info.get("ufilename"), info.get("description"),
                     body.decode("utf-8", "ignore")]
            # Any binary decodes to some UTF-16 text; only a marked UTF-16 file is text.
            if body[:2] in (b"\xff\xfe", b"\xfe\xff"):
                texts.append(body.decode("utf-16", "ignore"))
            if any(hit(t) for t in texts):
                doc.embfile_del(name)
                removed.append(f"attachment '{name}'")

        notes = fields = 0
        for page in doc:
            for annot in list(page.annots()):
                if any(hit(annot.info.get(k)) for k in _ANNOT_TEXT_KEYS):
                    page.delete_annot(annot)
                    notes += 1
            for widget in list(page.widgets()):
                if widget.field_type == fitz.PDF_WIDGET_TYPE_TEXT and hit(widget.field_value):
                    widget.field_value = strip(widget.field_value)
                    widget.update()
                    fields += 1
                elif hit(str(widget.field_value)) or hit(widget.field_label):
                    page.delete_widget(widget)
                    fields += 1
        if notes:
            removed.append(f"{notes} annotation(s)")
        if fields:
            removed.append(f"{fields} form field(s)")
        return removed
