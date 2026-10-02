from __future__ import annotations
import html
import os
import shutil
import tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path
import importlib.util as _ilu
import customtkinter as ctk
import pymupdf as fitz
from PIL import Image
from ..tool_base import ToolBase, register
from ..theme import ACCENT, ACCENT_H, CARD, TEXT, MUTED, SUCCESS, WARN_BG, WARN_TITLE, WARN_BODY
from ..prefs import PREFS, pref_dpi
from ..job_queue import atomic_output
from ..pages import render

_HAS_OCR = _ilu.find_spec("pytesseract") is not None
_MIN_CONF = 30
# Where the UB-Mannheim installer puts Tesseract; it does not add itself to PATH.
_TESS_DIRS = (("ProgramFiles", "Tesseract-OCR"), ("ProgramFiles(x86)", "Tesseract-OCR"),
              ("LOCALAPPDATA", r"Programs\Tesseract-OCR"))


def tesseract():
    """pytesseract, pointed at the Tesseract binary: PATH first, then its install folders."""
    import pytesseract
    pt = pytesseract.pytesseract
    if pt.tesseract_cmd == "tesseract" and not shutil.which("tesseract"):
        for var, sub in _TESS_DIRS:
            base = os.environ.get(var)
            if base and os.path.isfile(exe := os.path.join(base, sub, "tesseract.exe")):
                pt.tesseract_cmd = exe
                break
    return pytesseract


def ocr_words(img, lang: str, scale: float) -> list[tuple[fitz.Rect, str]]:
    """Tesseract words in *img* (a page rendered at *scale*) as (rect, text) in page.rect space."""
    pytesseract = tesseract()
    data = pytesseract.image_to_data(img, lang=lang, output_type=pytesseract.Output.DICT)
    to_page = fitz.Matrix(1 / scale, 1 / scale)
    words = []
    for text, conf, x, y, w, h in zip(data["text"], data["conf"], data["left"],
                                      data["top"], data["width"], data["height"],
                                      strict=True):
        text = text.strip()
        if text and float(conf) >= _MIN_CONF:
            words.append((fitz.Rect(x, y, x + w, y + h) * to_page, text))
    return words


def add_text_layer(page: fitz.Page, words) -> None:
    """Add *words* ((rect, text) in page.rect space) to *page* as invisible, searchable text."""
    if not words:
        return
    if page.rotation:
        # Text placed on a rotated page lands in unrotated space, and
        # remove_rotation() shifts the content of a cropped page; derotating
        # the uncropped page and re-applying the crop keeps both right.
        crop = page.cropbox
        page.set_cropbox(page.mediabox)
        mat = page.rotation_matrix
        page.remove_rotation()
        page.set_cropbox((crop * mat) & page.mediabox)
    layer = fitz.open()
    lp = layer.new_page(width=page.rect.width, height=page.rect.height)
    tw = fitz.TextWriter(lp.rect)
    font = fitz.Font("helv")      # TextWriter falls back to MuPDF's Noto fonts for other scripts
    for rect, text in words:
        tw.append(fitz.Point(rect.x0, rect.y1), text, font=font,
                  fontsize=max(1, rect.height * 0.85))
    tw.write_text(lp, render_mode=3)
    layer.subset_fonts()
    # TextWriter ignores a cropbox offset on the target page; show_pdf_page honours it.
    page.show_pdf_page(page.rect, layer, 0)
    layer.close()


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
            pytesseract = tesseract()

            try:
                pytesseract.get_tesseract_version()
            except pytesseract.TesseractNotFoundError:
                doc.close()
                raise RuntimeError(
                    "Tesseract not found on PATH or in Program Files\\Tesseract-OCR.\n"
                    "Install it from: https://github.com/UB-Mannheim/tesseract/wiki") from None

            text_only = "Text-only" in mode
            total = len(doc)
            scale = dpi / 72.0
            # doc is closed before the replace, so the output may be the input file.
            with atomic_output(out) as tmp, doc, fitz.open() as nd:
                for pg_i, page in enumerate(doc):
                    if stop.is_set():
                        return
                    label_txt = f"OCR — page {pg_i + 1} / {total}"
                    app.after(0, lambda t=label_txt: app._widget_set(log, text=t))
                    app.after(0,
                              lambda v=(pg_i + 1) / total: app._prog_update(v))

                    pix = render(page, scale)
                    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

                    if text_only:
                        text = pytesseract.image_to_string(img, lang=lang)
                        A4   = fitz.paper_rect("A4")
                        np   = nd.new_page(width=A4.width, height=A4.height)
                        np.insert_htmlbox(A4,
                                          f"<pre>{html.escape(text)}</pre>",
                                          css="pre { font-size: 10pt; }")
                    else:
                        add_text_layer(page, ocr_words(img, lang, scale))

                if text_only:
                    nd.save(tmp, deflate=True)
                else:
                    doc.save(tmp, garbage=3, deflate=True)

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
