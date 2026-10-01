from __future__ import annotations
import html
import tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path
import importlib.util as _ilu
import customtkinter as ctk
import fitz
from ..tool_base import ToolBase, register
from ..theme import ACCENT, ACCENT_H, CARD, TEXT, MUTED, SUCCESS, WARN, DANGER
from ..recent import RECENT

_HAS_OCR = _ilu.find_spec("pytesseract") is not None


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
            warn = ctk.CTkFrame(body, fg_color="#FEF3C7", corner_radius=10)
            warn.pack(fill="x", padx=24, pady=24)
            ctk.CTkLabel(
                warn,
                text="⚠  pytesseract not installed",
                font=ctk.CTkFont(size=15, weight="bold"),
                text_color="#92400E").pack(padx=20, pady=(16, 4), anchor="w")
            ctk.CTkLabel(
                warn,
                text="Install it with:  pip install pytesseract\n"
                     "Then install the Tesseract binary from:\n"
                     "https://github.com/UB-Mannheim/tesseract/wiki",
                font=ctk.CTkFont(size=13), text_color="#78350F",
                justify="left").pack(padx=20, pady=(0, 16), anchor="w")
            return

        self._path = tk.StringVar()
        self._file_row(body, self._path)

        card = ctk.CTkFrame(body, fg_color=CARD, corner_radius=8)
        card.pack(fill="x", padx=24, pady=8)

        # Language
        r1 = ctk.CTkFrame(card, fg_color="transparent")
        r1.pack(fill="x", padx=16, pady=(14, 4))
        ctk.CTkLabel(r1, text="Language code:", width=160,
                     text_color=TEXT, anchor="w").pack(side="left")
        self._lang = ctk.CTkEntry(r1, width=120, height=40,
                                   placeholder_text="eng")
        self._lang.insert(0, "eng")
        self._lang.pack(side="left")
        ctk.CTkLabel(r1,
                     text="e.g.  eng  ·  ita  ·  deu  ·  fra  ·  eng+ita",
                     text_color=MUTED, font=ctk.CTkFont(size=12)
                     ).pack(side="left", padx=12)

        # DPI
        r2 = ctk.CTkFrame(card, fg_color="transparent")
        r2.pack(fill="x", padx=16, pady=4)
        ctk.CTkLabel(r2, text="Render DPI:", width=160,
                     text_color=TEXT, anchor="w").pack(side="left")
        self._dpi = ctk.CTkSlider(r2, from_=72, to=400, number_of_steps=328)
        self._dpi.set(300)
        self._dpi.pack(side="left", fill="x", expand=True)
        self._dpi_lbl = ctk.CTkLabel(r2, text="300 DPI", width=80,
                                      text_color=TEXT, font=ctk.CTkFont(size=13))
        self._dpi_lbl.pack(side="left", padx=12)
        self._dpi.configure(
            command=lambda v: self._dpi_lbl.configure(text=f"{int(v)} DPI"))

        # Mode
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

        # Log
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
        out = self.app._save_as("ocr_output.pdf")
        if not out:
            return
        lang = self._lang.get().strip() or "eng"
        dpi  = int(self._dpi.get())
        mode = self._mode.get()
        app  = self.app
        log  = self._log

        def work(stop):
            import pytesseract
            from PIL import Image as _PIL_Image

            try:
                pytesseract.get_tesseract_version()
            except Exception:
                raise RuntimeError(
                    "Tesseract binary not found on PATH.\n"
                    "Install it from: https://github.com/UB-Mannheim/tesseract/wiki")

            with fitz.open(src) as doc:
                total  = len(doc)
                scale  = dpi / 72.0
                mat    = fitz.Matrix(scale, scale)
                nd     = fitz.open()

                for pg_i, page in enumerate(doc):
                    if stop.is_set():
                        return
                    label_txt = f"OCR — page {pg_i + 1} / {total}"
                    app.after(0, lambda t=label_txt: app._widget_set(log, text=t))
                    app.after(0,
                              lambda v=(pg_i + 1) / total: app._prog_update(v))

                    pix = page.get_pixmap(matrix=mat, alpha=False)
                    img = _PIL_Image.frombytes(
                        "RGB", [pix.width, pix.height], pix.samples)

                    if "Text-only" in mode:
                        text = pytesseract.image_to_string(img, lang=lang)
                        A4   = fitz.paper_rect("A4")
                        np   = nd.new_page(width=A4.width, height=A4.height)
                        np.insert_htmlbox(A4,
                                          f"<pre>{html.escape(text)}</pre>",
                                          css="pre { font-size: 10pt; }")
                    else:
                        # Invisible text overlay on the rendered image page
                        np = nd.new_page(
                            width=page.rect.width, height=page.rect.height)
                        import io
                        buf = io.BytesIO()
                        img.save(buf, "JPEG", quality=90)
                        buf.seek(0)
                        np.insert_image(np.rect, stream=buf.read())
                        # OCR with hOCR output → parse bboxes → insert invisible spans
                        hocr = pytesseract.image_to_pdf_or_hocr(
                            img, lang=lang, extension="hocr").decode("utf-8", errors="ignore")
                        # Parse hOCR word boxes
                        import re
                        for m in re.finditer(
                                r"bbox (\d+) (\d+) (\d+) (\d+)[^>]*>([^<]+)<",
                                hocr):
                            bx0, by0, bx1, by1 = [int(m.group(i)) / scale
                                                   for i in range(1, 5)]
                            word = m.group(5).strip()
                            if not word:
                                continue
                            try:
                                np.insert_text(
                                    fitz.Point(bx0, by1),
                                    word,
                                    fontsize=max(1, (by1 - by0) * 0.85),
                                    render_mode=3,  # invisible
                                )
                            except Exception:
                                pass

            nd.save(out, deflate=True)
            nd.close()
            RECENT.push(src, total)
            done_msg = f"✓  OCR complete — {total} page(s) → {Path(out).name}"
            app.after(0, lambda: [
                app._widget_set(log, text=f"✓  Done — {total} page(s) processed"),
                app._set_status(done_msg, SUCCESS),
                messagebox.showinfo("OCR Complete",
                                    f"OCR PDF saved:\n{out}\n\n"
                                    f"Pages processed: {total}"),
            ])

        app._set_status(f"Starting OCR ({lang}, {dpi} DPI)…")
        app.run_job(work, f"OCR — {dpi} DPI · lang={lang}")
