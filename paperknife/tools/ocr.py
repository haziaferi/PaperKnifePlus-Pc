from __future__ import annotations
import tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path
import customtkinter as ctk
from ..tool_base import ToolBase, register
from ..theme import ACCENT, ACCENT_H, CARD, TEXT, MUTED, SUCCESS, WARN_BG, WARN_TITLE, WARN_BODY
from ..prefs import PREFS, pref_dpi
from ..core import ocr as core
from ..core.ocr import (HAS_OCR as _HAS_OCR, MIN_CONF as _MIN_CONF,  # noqa: F401
                        TESS_DIRS as _TESS_DIRS, add_text_layer, ocr_words, tesseract)


@register
class OCRTool(ToolBase):
    section = "CONTENT"
    label   = "🤖  OCR"

    def show(self):
        app  = self.app
        body = self._card(
            "🤖  OCR — Optical Character Recognition",
            "Make a scanned or image-only PDF searchable · powered by Tesseract")

        if not _HAS_OCR:
            warn = ctk.CTkFrame(body, fg_color=WARN_BG, corner_radius=10)
            warn.pack(fill="x", padx=24, pady=24)
            ctk.CTkLabel(
                warn,
                text="⚠  pytesseract not installed",
                font=ctk.CTkFont(size=15, weight="bold"),
                text_color=WARN_TITLE).pack(padx=20, pady=(16, 4), anchor="w")
            ctk.CTkLabel(
                warn,
                text="Install it with:  pip install pytesseract\n"
                     "Then install the Tesseract binary from:\n"
                     "https://github.com/UB-Mannheim/tesseract/wiki",
                font=ctk.CTkFont(size=13), text_color=WARN_BODY,
                justify="left").pack(padx=20, pady=(0, 16), anchor="w")
            return

        self._path = tk.StringVar()
        self._file_row(body, self._path)

        card = ctk.CTkFrame(body, fg_color=CARD, corner_radius=8)
        card.pack(fill="x", padx=24, pady=8)

        r1 = ctk.CTkFrame(card, fg_color="transparent")
        r1.pack(fill="x", padx=16, pady=(14, 4))
        ctk.CTkLabel(r1, text="Language code:", width=160,
                     text_color=TEXT, anchor="w").pack(side="left")
        self._lang = ctk.CTkEntry(r1, width=120, height=40,
                                   placeholder_text="eng")
        self._lang.insert(0, PREFS.ocr_lang or "eng")
        self._lang.pack(side="left")
        ctk.CTkLabel(r1,
                     text="e.g.  eng  ·  ita  ·  deu  ·  fra  ·  eng+ita",
                     text_color=MUTED, font=ctk.CTkFont(size=12)
                     ).pack(side="left", padx=12)

        r2 = ctk.CTkFrame(card, fg_color="transparent")
        r2.pack(fill="x", padx=16, pady=4)
        ctk.CTkLabel(r2, text="Render DPI:", width=160,
                     text_color=TEXT, anchor="w").pack(side="left")
        self._dpi = ctk.CTkSlider(r2, from_=72, to=400, number_of_steps=328)
        dpi = pref_dpi(72, 400)
        self._dpi.set(dpi)
        self._dpi.pack(side="left", fill="x", expand=True)
        self._dpi_lbl = ctk.CTkLabel(r2, text=f"{dpi} DPI", width=80,
                                      text_color=TEXT, font=ctk.CTkFont(size=13))
        self._dpi_lbl.pack(side="left", padx=12)
        self._dpi.configure(
            command=lambda v: self._dpi_lbl.configure(text=f"{int(v)} DPI"))

        r3 = ctk.CTkFrame(card, fg_color="transparent")
        r3.pack(fill="x", padx=16, pady=(4, 14))
        ctk.CTkLabel(r3, text="Output mode:", width=160,
                     text_color=TEXT, anchor="w").pack(side="left")
        self._mode = ctk.CTkOptionMenu(
            r3,
            values=["Overlay (invisible text layer)", "Text-only PDF"],
            width=260, height=40)
        self._mode.set("Overlay (invisible text layer)")
        self._mode.pack(side="left")

        self._log = ctk.CTkLabel(card, text="",
                                  font=ctk.CTkFont(size=12), text_color=MUTED)
        self._log.pack(padx=16, pady=(0, 4))

        ctk.CTkButton(card, text="  Run OCR  →", command=self._run,
                      height=44, fg_color=ACCENT, hover_color=ACCENT_H,
                      font=ctk.CTkFont(size=14, weight="bold")
                      ).pack(fill="x", padx=16, pady=12)

        app._cur_open_fn = lambda: self._path.set(
            filedialog.askopenfilename(filetypes=[("PDF", "*.pdf")]) or self._path.get())

    def _run(self):
        src = self._path.get()
        if not src:
            return messagebox.showwarning("OCR", "Select a PDF first.")
        doc = self.app._open_pdf_safe(src)
        if doc is None:
            return
        out = self.app._save_as("ocr_output.pdf")
        if not out:
            return doc.close()
        lang = self._lang.get().strip() or "eng"
        dpi  = int(self._dpi.get())
        mode = self._mode.get()
        app  = self.app
        log  = self._log

        def work(stop):
            total = core.ocr_pdf(
                doc, out, lang, dpi, "Text-only" in mode, stop,
                lambda v: app.after(0, lambda: app._prog_update(v)),
                lambda n, t: app.after(
                    0, lambda: app._widget_set(log, text=f"OCR — page {n} / {t}")))
            if total is None:
                return

            def done():
                app._widget_set(log, text=f"✓  Done — {total} page(s) processed")
                app._set_status(f"✓  OCR complete — {total} page(s) → {Path(out).name}",
                                SUCCESS)
                messagebox.showinfo("OCR Complete",
                                    f"OCR PDF saved:\n{out}\n\n"
                                    f"Pages processed: {total}")
            app.after(0, done)

        app._set_status(f"Starting OCR ({lang}, {dpi} DPI)…")
        if app.run_job(work, f"OCR — {dpi} DPI · lang={lang}") is None:
            doc.close()
