from __future__ import annotations
import re
import tkinter as tk
from tkinter import messagebox
from pathlib import Path
import customtkinter as ctk
import pymupdf as fitz
from ..page_canvas import PageCanvasTool
from ..tool_base import register
from ..theme import (ACCENT, ACCENT_H, CARD, CARD2, TEXT, MUTED, SUCCESS, WARN, DANGER, DANGER_H,
                     WARN_BG, WARN_TITLE, WARN_BODY)
from ..lineart import cut_line_art, residual

_INFO_KEYS = ("title", "author", "subject", "keywords", "creator", "producer")
# Annotation text a reader sees; the other info keys are dates, ids and icon names.
_ANNOT_TEXT_KEYS = ("content", "title", "subject")
# A line under a drawn box shorter than this (a page number, a year suffix)
# would match far too much elsewhere in the document.
_MIN_BOX_PHRASE = 4


def redact_page(doc: fitz.Document, pno: int, rects, fill) -> str:
    """Destroy everything under rects (unrotated page space) on page pno.

    fill is an RGB tuple, or None to leave the boxes unpainted.  Returns how line
    art was handled: "cut" at the box edge; "whole" (drawings a box touches removed
    entirely, when MuPDF still saw line art in a box after cutting); or "image"
    (the page replaced by a picture of itself, when neither could empty the boxes).
    """
    page = doc[pno]
    # apply_redactions removes only the redact annots themselves; a note or a
    # form field under a box would keep showing (and storing) the content.
    for annot in list(page.annots()):
        if any(annot.rect.intersects(r) for r in rects):
            page.delete_annot(annot)
    for widget in list(page.widgets()):
        if any(widget.rect.intersects(r) for r in rects):
            page.delete_widget(widget)
    # The page thumbnail is a picture of the unredacted page.
    doc.xref_set_key(page.xref, "Thumb", "null")
    # MuPDF keeps or drops whole paths; cut them at the box edge first, in place.
    # Should MuPDF still see line art in a box (a stream read differently),
    # go back to the original content and let MuPDF drop every path it touches.
    contents = doc.xref_get_key(page.xref, "Contents")
    mode, graphics, unsafe = "cut", fitz.PDF_REDACT_LINE_ART_NONE, []
    try:
        unsafe = cut_line_art(page, rects).unsafe
        left = residual(page, rects)
    except Exception:                   # a stream this module cannot read at all
        left = True
    if left:
        doc.xref_set_key(page.xref, "Contents", contents[1])
        mode, graphics = "whole", fitz.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED
    for r in rects:
        page.add_redact_annot(r, fill=fill if fill is not None else False)
    page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_PIXELS, graphics=graphics)
    # MuPDF's own removal misses soft-mask groups, and nothing removes the data of
    # a mesh shading: last resort, the page becomes a picture of itself.
    if unsafe or (mode == "whole" and residual(doc[pno], rects)):
        _page_to_image(doc, pno)
        mode = "image"
    return mode


def _page_to_image(doc: fitz.Document, pno: int, dpi: int = 200) -> None:
    """Replace page pno by a picture of it.  Its old resources go too, so nothing
    the page drew survives in the file once it is saved with garbage collection."""
    page = doc[pno]
    rotation = page.rotation
    page.set_rotation(0)
    pix = page.get_pixmap(dpi=dpi, annots=False)
    xref = doc.get_new_xref()
    doc.update_object(xref, "<<>>")
    doc.update_stream(xref, b"")
    doc.xref_set_key(page.xref, "Contents", f"{xref} 0 R")
    doc.xref_set_key(page.xref, "Resources", "<<>>")
    page = doc[pno]
    page.insert_image(page.rect, pixmap=pix)
    page.set_rotation(rotation)


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
        modes = {pg_num + 1: redact_page(self._doc, pg_num, rects, fill)
                 for pg_num, rects in by_page.items()}
        self._pending = []
        self._update_pending_lbl()
        whole = [str(p) for p, m in modes.items() if m == "whole"]
        image = [str(p) for p, m in modes.items() if m == "image"]
        note = ((f" · page {', '.join(whole)}: drawings under a box removed whole"
                 if whole else "")
                + (f" · page {', '.join(image)}: turned into an image (its text is no "
                   "longer selectable)" if image else ""))
        self.app._set_status(
            f"✓  {n} redaction(s) applied — save to write to disk{note}", SUCCESS)
        if image:
            messagebox.showwarning(
                "Redact",
                f"Page {', '.join(image)} holds drawings this tool cannot cut at a box "
                "edge (a gradient mesh, or a soft mask), so the page was replaced by "
                "an image of itself. Its text can no longer be selected or searched.")
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
