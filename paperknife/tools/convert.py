from __future__ import annotations
import tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path
import pymupdf as fitz
import customtkinter as ctk
from ..tool_base import ToolBase, register
from ..theme import (ACCENT, ACCENT_H, CARD, TEXT, MUTED, DANGER, DANGER_H, SUCCESS, WARN,
                     WARN_BG, WARN_BODY)
from ..prefs import pref_dpi
from ..job_queue import atomic_output
from ..core import convert as core
from ..core.convert import (  # noqa: F401  (old names, used by tests and the tools below)
    NEEDS as _NEEDS, FORMATS as _FMTS, Cancelled as _Cancelled, require as _require,
    pages_to_zip as _pages_to_zip, image_page as _image_page, text_story as _text_story,
    write_story as _write_story, rtf_escape as _rtf_escape, _HAS_DOCX, _HAS_PPTX,
    _HAS_OPENPYXL, _XML_ILLEGAL)


# ══════════════════════════════════════════════════════════════════════════════
@register
class Img2PdfTool(ToolBase):
    section = "CONVERT"
    label   = "🖼   Image → PDF"

    def show(self):
        app  = self.app
        body = self._card("🖼  Image → PDF",
                          "Convert JPG · PNG · WEBP · BMP · TIFF images into a PDF")
        ctk.CTkLabel(body, text="Add images in the order they should appear:",
                     font=ctk.CTkFont(size=13), text_color=MUTED, anchor="w"
                     ).pack(padx=24, pady=(14, 4), fill="x")
        lf, self._lb = app._listbox(body)
        lf.pack(fill="both", expand=True, padx=24, pady=4)
        if app._dnd_ok:
            from tkinterdnd2 import DND_FILES
            try:
                self._lb.drop_target_register(DND_FILES)
                self._lb.dnd_bind("<<Drop>>", self._on_drop)
            except tk.TclError:
                pass     # the list still fills from "Add Images"
        row = ctk.CTkFrame(body, fg_color="transparent")
        row.pack(fill="x", padx=24, pady=8)
        ctk.CTkButton(row, text="＋ Add Images", width=130,
                      command=self._add).pack(side="left", padx=4)
        ctk.CTkButton(row, text="↑ Up", width=72,
                      command=lambda: app._list_move(self._lb, -1)).pack(side="left", padx=4)
        ctk.CTkButton(row, text="↓ Down", width=80,
                      command=lambda: app._list_move(self._lb, 1)).pack(side="left", padx=4)
        ctk.CTkButton(row, text="✕ Remove", width=100,
                      fg_color=DANGER, hover_color=DANGER_H,
                      command=lambda: app._list_remove(self._lb)).pack(side="left", padx=4)
        app._big_btn(body, "  Convert to PDF  →",
                     self._run).pack(fill="x", padx=24, pady=16)
        app._cur_open_fn = self._add
        app._cur_del_fn  = lambda: app._list_remove(self._lb)

    def _on_drop(self, event):
        for p in self.app._parse_drop(event.data):
            if Path(p).suffix.lower() in core.IMAGE_EXTS:
                self._lb.insert("end", p)

    def _add(self):
        for f in filedialog.askopenfilenames(
                title="Select Images",
                filetypes=[("Images", "*.jpg *.jpeg *.png *.bmp *.tiff *.tif *.webp *.gif"),
                            ("All", "*.*")]):
            self._lb.insert("end", f)

    def _run(self):
        paths = list(self._lb.get(0, "end"))
        if not paths:
            return messagebox.showwarning("Convert", "Add images first.")
        out = self.app._save_as("from_images.pdf")
        if not out:
            return
        app = self.app

        def work(stop):
            if not core.images_to_pdf(
                    paths, out, stop,
                    lambda v: app.after(0, lambda v=v: app._prog_update(v))):
                return

            def done():
                app._set_status(
                    f"✓  Converted {len(paths)} image(s) → {Path(out).name}", SUCCESS)
                messagebox.showinfo("Done", f"PDF saved:\n{out}")
            app.after(0, done)

        app._set_status(f"Converting {len(paths)} image(s)…")
        app.run_job(work, f"Converting {len(paths)} image(s)…")


# ══════════════════════════════════════════════════════════════════════════════
@register
class Pdf2ImgTool(ToolBase):
    section = "CONVERT"
    label   = "📸  PDF → Images"

    def show(self):
        app  = self.app
        body = self._card("📸  PDF → Images",
                          "Export every page as a PNG · bundled in a ZIP")
        self._path = tk.StringVar()
        self._file_row(body, self._path)
        opt = ctk.CTkFrame(body, fg_color=CARD, corner_radius=8)
        opt.pack(fill="x", padx=24, pady=8)
        ctk.CTkLabel(opt, text="Resolution (DPI)",
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=TEXT, anchor="w").pack(padx=16, pady=(14, 6), fill="x")
        sr = ctk.CTkFrame(opt, fg_color="transparent")
        sr.pack(fill="x", padx=16, pady=4)
        self._dpi = ctk.CTkSlider(sr, from_=72, to=300, number_of_steps=228)
        dpi = pref_dpi(72, 300)
        self._dpi.set(dpi)
        self._dpi.pack(side="left", fill="x", expand=True)
        self._dpi_lbl = ctk.CTkLabel(sr, text=f"{dpi} DPI", width=80,
                                      text_color=TEXT, font=ctk.CTkFont(size=13))
        self._dpi_lbl.pack(side="left", padx=12)
        self._dpi.configure(
            command=lambda v: self._dpi_lbl.configure(text=f"{int(v)} DPI"))
        ctk.CTkLabel(opt, text="72=screen  ·  150=standard  ·  300=print quality",
                     font=ctk.CTkFont(size=11), text_color=MUTED, anchor="w"
                     ).pack(padx=16, pady=(4, 14), fill="x")
        app._big_btn(body, "  Export as ZIP  →",
                     self._run).pack(fill="x", padx=24, pady=16)
        app._cur_open_fn = lambda: self._path.set(
            filedialog.askopenfilename(filetypes=[("PDF", "*.pdf")]) or self._path.get())

    def _run(self):
        src = self._path.get()
        if not src:
            return messagebox.showwarning("Export", "Select a PDF first.")
        dpi = int(self._dpi.get())
        app = self.app
        doc = app._open_pdf_safe(src)
        if doc is None:
            return
        out = app._save_as("pages.zip", ".zip", [("ZIP", "*.zip")])
        if not out:
            return doc.close()
        total = len(doc)

        def work(stop):
            try:
                with atomic_output(out) as tmp, doc:
                    _pages_to_zip(tmp, doc, dpi, "PNG", 0, stop,
                                  lambda v: app.after(0, lambda: app._prog_update(v)))
            except _Cancelled:
                return

            def done():
                app._set_status(
                    f"✓  Exported {total} pages → {Path(out).name}", SUCCESS)
                messagebox.showinfo("Done", f"Exported {total} pages to:\n{out}")
            app.after(0, done)

        app._set_status("Exporting pages…")
        if app.run_job(work, "Exporting pages to PNG…") is None:
            doc.close()


# ══════════════════════════════════════════════════════════════════════════════
@register
class ExtractTool(ToolBase):
    section = "CONVERT"
    label   = "🖼   Extract Images"

    def show(self):
        app  = self.app
        body = self._card("🖼  Extract Images",
                          "Pull every embedded image out of a PDF and save to a folder")
        self._path = tk.StringVar()
        self._file_row(body, self._path)
        card = ctk.CTkFrame(body, fg_color=CARD, corner_radius=8)
        card.pack(fill="x", padx=24, pady=8)
        r1 = ctk.CTkFrame(card, fg_color="transparent")
        r1.pack(fill="x", padx=16, pady=(14, 4))
        ctk.CTkLabel(r1, text="Minimum dimension:", width=170,
                     text_color=TEXT, anchor="w").pack(side="left")
        self._minpx = ctk.CTkEntry(r1, width=80, height=38, placeholder_text="50")
        self._minpx.insert(0, "50")
        self._minpx.pack(side="left")
        ctk.CTkLabel(r1, text="px  (skip smaller images)",
                     text_color=MUTED, font=ctk.CTkFont(size=12)
                     ).pack(side="left", padx=8)
        r2 = ctk.CTkFrame(card, fg_color="transparent")
        r2.pack(fill="x", padx=16, pady=(4, 14))
        ctk.CTkLabel(r2, text="Output format:", width=170,
                     text_color=TEXT, anchor="w").pack(side="left")
        self._fmt = ctk.CTkOptionMenu(
            r2, values=["Keep original", "PNG", "JPEG"], width=140, height=38)
        self._fmt.set("Keep original")
        self._fmt.pack(side="left")
        self._log = ctk.CTkLabel(card, text="",
                                  font=ctk.CTkFont(size=12), text_color=MUTED)
        self._log.pack(padx=16, pady=(0, 4))
        ctk.CTkButton(card, text="  Extract Images  →", command=self._run,
                      height=44, fg_color=ACCENT, hover_color=ACCENT_H,
                      font=ctk.CTkFont(size=14, weight="bold")
                      ).pack(fill="x", padx=16, pady=12)
        app._cur_open_fn = lambda: self._path.set(
            filedialog.askopenfilename(filetypes=[("PDF", "*.pdf")]) or self._path.get())

    def _run(self):
        src = self._path.get()
        if not src:
            return messagebox.showwarning("Extract", "Select a PDF first.")
        try:
            min_px = int(self._minpx.get() or "50")
        except ValueError:
            min_px = 50
        app = self.app
        doc = app._open_pdf_safe(src)
        if doc is None:
            return
        out_dir = app._ask_dir()
        if not out_dir:
            return doc.close()
        fmt = self._fmt.get()
        log = self._log

        def work(stop):
            res = core.extract_images(doc, out_dir, fmt, min_px, stop,
                                      lambda v: app.after(0, lambda: app._prog_update(v)))
            if res is None:
                return
            count, failed = res.count, res.failed
            msg = (f"Found and extracted {count} image(s)  "
                   f"({res.scanned} unique xrefs scanned)")
            fail_txt = f"\n{failed} image(s) could not be extracted." if failed else ""

            def done():
                app._widget_set(log, text=msg + fail_txt.replace("\n", "  ·  "))
                app._set_status(f"✓  Extracted {count} image(s) → {out_dir}",
                                WARN if failed else SUCCESS)
                messagebox.showinfo("Done",
                                    f"Extracted {count} image(s) to:\n{out_dir}{fail_txt}")
            app.after(0, done)

        if app.run_job(work, "Extracting images…") is None:
            doc.close()


# ══════════════════════════════════════════════════════════════════════════════
@register
class Pdf2DocTool(ToolBase):
    section = "CONVERT"
    label   = "📄  PDF → Doc / Text"

    _INFO = {
        "TXT":  "Extracts all selectable text from the PDF into a plain .txt file.",
        "HTML": "Exports each page with HTML text structure — opens in any browser.",
        "XML":  "Exports the PDF's text and layout structure as an XML document.",
        "RTF":  "Converts PDF text to Rich Text Format, readable in Word/LibreOffice.",
        "DOCX": "Extracts text paragraph-by-paragraph into a Word document.  Requires: python-docx",
        "PPTX": "Renders each page as a slide image inside a PowerPoint file.  Requires: python-pptx",
        "XLSX": "Extracts text per page; each page goes to its own Excel sheet.  Requires: openpyxl",
        "PNG":  "Renders every page as a PNG image, bundled together in a ZIP.",
        "JPEG": "Renders every page as a JPEG image, bundled together in a ZIP.",
    }
    _OUT = {
        "TXT":  (".txt",  "Text File",      "output.txt"),
        "HTML": (".html", "HTML File",      "output.html"),
        "XML":  (".xml",  "XML File",       "output.xml"),
        "RTF":  (".rtf",  "RTF File",       "output.rtf"),
        "DOCX": (".docx", "Word Document",  "output.docx"),
        "PPTX": (".pptx", "PowerPoint",     "output.pptx"),
        "XLSX": (".xlsx", "Excel Workbook", "output.xlsx"),
        "PNG":  (".zip",  "ZIP of PNGs",    "pages_png.zip"),
        "JPEG": (".zip",  "ZIP of JPEGs",   "pages_jpeg.zip"),
    }

    def show(self):
        app  = self.app
        body = self._card(
            "📄  PDF → Document / Text",
            "Export a PDF to TXT · HTML · DOCX · PPTX · XLSX · XML · RTF · PNG · JPEG")
        self._path = tk.StringVar()
        self._file_row(body, self._path)
        card = ctk.CTkFrame(body, fg_color=CARD, corner_radius=8)
        card.pack(fill="x", padx=24, pady=8)
        r1 = ctk.CTkFrame(card, fg_color="transparent")
        r1.pack(fill="x", padx=16, pady=(14, 4))
        ctk.CTkLabel(r1, text="Output format:", width=150,
                     text_color=TEXT, anchor="w").pack(side="left")
        self._fmt = ctk.CTkOptionMenu(
            r1, values=_FMTS, width=150, height=40,
            command=self._fmt_changed)
        self._fmt.set("TXT")
        self._fmt.pack(side="left")
        self._opts = ctk.CTkFrame(card, fg_color="transparent")
        self._opts.pack(fill="x", padx=16, pady=(0, 4))
        ctk.CTkButton(card, text="  Convert PDF  →", command=self._run,
                      height=44, fg_color=ACCENT, hover_color=ACCENT_H,
                      font=ctk.CTkFont(size=14, weight="bold")
                      ).pack(fill="x", padx=16, pady=(4, 12))
        self._dpi     = None
        self._quality = None
        self._fmt_changed("TXT")
        app._cur_open_fn = lambda: self._path.set(
            filedialog.askopenfilename(filetypes=[("PDF", "*.pdf")]) or self._path.get())

    def _fmt_changed(self, fmt):
        self._dpi     = None
        self._quality = None
        for w in self._opts.winfo_children():
            w.destroy()
        if fmt in _NEEDS:
            lib, installed = _NEEDS[fmt]
            if not installed:
                warn = ctk.CTkFrame(self._opts, fg_color=WARN_BG, corner_radius=8)
                warn.pack(fill="x", pady=(0, 6))
                ctk.CTkLabel(warn,
                             text=f"⚠  '{lib}' is not installed.\n"
                                  f"Install it:  pip install {lib}",
                             font=ctk.CTkFont(size=12), text_color=WARN_BODY,
                             justify="left").pack(padx=16, pady=10, anchor="w")
        if fmt in ("PNG", "JPEG", "PPTX"):
            dr = ctk.CTkFrame(self._opts, fg_color="transparent")
            dr.pack(fill="x", pady=4)
            ctk.CTkLabel(dr, text="Resolution:", width=140,
                         text_color=TEXT, anchor="w").pack(side="left")
            self._dpi = ctk.CTkSlider(dr, from_=72, to=300, number_of_steps=228)
            dpi = pref_dpi(72, 300)
            self._dpi.set(dpi)
            self._dpi.pack(side="left", fill="x", expand=True)
            dpi_lbl = ctk.CTkLabel(dr, text=f"{dpi} DPI", width=80, text_color=TEXT)
            dpi_lbl.pack(side="left", padx=8)
            self._dpi.configure(
                command=lambda v, l=dpi_lbl: l.configure(text=f"{int(v)} DPI"))
        if fmt == "JPEG":
            qr = ctk.CTkFrame(self._opts, fg_color="transparent")
            qr.pack(fill="x", pady=4)
            ctk.CTkLabel(qr, text="JPEG quality:", width=140,
                         text_color=TEXT, anchor="w").pack(side="left")
            self._quality = ctk.CTkSlider(qr, from_=50, to=100, number_of_steps=50)
            self._quality.set(92)
            self._quality.pack(side="left", fill="x", expand=True)
            q_lbl = ctk.CTkLabel(qr, text="92%", width=80, text_color=TEXT)
            q_lbl.pack(side="left", padx=8)
            self._quality.configure(
                command=lambda v, l=q_lbl: l.configure(text=f"{int(v)}%"))
        note = self._INFO.get(fmt, "")
        if note:
            ctk.CTkLabel(self._opts, text=note, font=ctk.CTkFont(size=12),
                         text_color=MUTED, anchor="w", justify="left",
                         wraplength=640).pack(fill="x", pady=(4, 0))

    def _run(self):
        src = self._path.get()
        if not src:
            return messagebox.showwarning("Convert", "Select a PDF first.")
        fmt = self._fmt.get()
        ext, desc, default = self._OUT[fmt]
        app = self.app
        doc = app._open_pdf_safe(src)
        if doc is None:
            return
        out = app._save_as(default, ext, [(desc, f"*{ext}"), ("All", "*.*")])
        if not out:
            return doc.close()
        dpi     = int(self._dpi.get())     if self._dpi     is not None else 150
        quality = int(self._quality.get()) if self._quality is not None else 92

        def work(stop):
            if not core.pdf_to_doc(doc, fmt, out, stop,
                                   lambda v: app.after(0, lambda: app._prog_update(v)),
                                   dpi=dpi, quality=quality):
                return

            def done():
                app._set_status(f"✓  PDF → {fmt}: {Path(out).name}", SUCCESS)
                messagebox.showinfo("Done", f"Saved:\n{out}")
            app.after(0, done)

        app._set_status(f"Converting PDF → {fmt}…")
        if app.run_job(work, f"Converting PDF → {fmt}…") is None:
            doc.close()


# ══════════════════════════════════════════════════════════════════════════════
@register
class Doc2PdfTool(ToolBase):
    section = "CONVERT"
    label   = "📤  Doc / Text → PDF"

    _EXTS = {
        "TXT":  [("Text Files",       "*.txt"),        ("All","*.*")],
        "HTML": [("HTML Files",       "*.html *.htm"), ("All","*.*")],
        "XML":  [("XML Files",        "*.xml"),        ("All","*.*")],
        "RTF":  [("RTF Files",        "*.rtf"),        ("All","*.*")],
        "DOCX": [("Word Documents",   "*.docx"),       ("All","*.*")],
        "PPTX": [("PowerPoint Files", "*.pptx"),       ("All","*.*")],
        "XLSX": [("Excel Workbooks",  "*.xlsx"),       ("All","*.*")],
        "PNG":  [("PNG Images",       "*.png"),        ("All","*.*")],
        "JPEG": [("JPEG Images",      "*.jpg *.jpeg"), ("All","*.*")],
    }
    _INFO = {
        "TXT":  "Text is typeset into A4 pages at 11pt with automatic line-wrapping.",
        "HTML": "HTML is rendered to PDF using PyMuPDF's built-in Story engine (supports basic CSS).",
        "XML":  "XML tag text is extracted and typeset into A4 pages.",
        "RTF":  "RTF content is converted to plain text and typeset into A4 pages.",
        "DOCX": "Paragraphs, headings, and tables are extracted from the Word document.",
        "PPTX": "Each slide's title and text content is typeset on its own PDF page.",
        "XLSX": "Each sheet is rendered as a plain-text table across A4 landscape pages.",
        "PNG":  "The PNG image is placed on a page sized to match the image exactly.",
        "JPEG": "The JPEG image is placed on a page sized to match the image exactly.",
    }
    _EXT2FMT = {
        ".txt": "TXT", ".html": "HTML", ".htm": "HTML", ".xml": "XML",
        ".rtf": "RTF", ".docx": "DOCX", ".pptx": "PPTX", ".xlsx": "XLSX",
        ".png": "PNG", ".jpg": "JPEG",  ".jpeg": "JPEG",
    }

    def show(self):
        app  = self.app
        body = self._card(
            "📤  Document / Text → PDF",
            "Convert TXT · HTML · DOCX · PPTX · XLSX · XML · RTF · PNG · JPEG to PDF")
        card = ctk.CTkFrame(body, fg_color=CARD, corner_radius=8)
        card.pack(fill="x", padx=24, pady=8)
        r1 = ctk.CTkFrame(card, fg_color="transparent")
        r1.pack(fill="x", padx=16, pady=(14, 4))
        ctk.CTkLabel(r1, text="Input format:", width=150,
                     text_color=TEXT, anchor="w").pack(side="left")
        self._fmt = ctk.CTkOptionMenu(
            r1, values=_FMTS, width=150, height=40,
            command=self._fmt_changed)
        self._fmt.set("TXT")
        self._fmt.pack(side="left")
        r2 = ctk.CTkFrame(card, fg_color="transparent")
        r2.pack(fill="x", padx=16, pady=4)
        self._path = tk.StringVar()
        self._entry = ctk.CTkEntry(r2, textvariable=self._path, state="readonly",
                                    placeholder_text="No file selected…", height=44)
        self._entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(r2, text="Open File", width=136, height=44,
                      command=self._pick).pack(side="left")
        if app._dnd_ok:
            from tkinterdnd2 import DND_FILES
            try:
                for w in (r2, self._entry, *self._entry.winfo_children()):
                    w.drop_target_register(DND_FILES)
                    w.dnd_bind("<<Drop>>", self._on_drop)
            except tk.TclError:
                pass     # the file still opens from "Open File"
        self._info_lbl = ctk.CTkLabel(card, text="",
                                       font=ctk.CTkFont(size=12), text_color=MUTED,
                                       justify="left", wraplength=640)
        self._info_lbl.pack(padx=16, pady=(4, 0), fill="x")
        self._warn_frame = ctk.CTkFrame(card, fg_color="transparent")
        self._warn_frame.pack(fill="x", padx=16, pady=4)
        ctk.CTkButton(card, text="  Convert to PDF  →", command=self._run,
                      height=44, fg_color=ACCENT, hover_color=ACCENT_H,
                      font=ctk.CTkFont(size=14, weight="bold")
                      ).pack(fill="x", padx=16, pady=(4, 12))
        self._fmt_changed("TXT")
        app._cur_open_fn = self._pick

    def _fmt_changed(self, fmt):
        for w in self._warn_frame.winfo_children():
            w.destroy()
        self._info_lbl.configure(text=self._INFO.get(fmt, ""))
        if fmt in _NEEDS:
            lib, installed = _NEEDS[fmt]
            if not installed:
                ctk.CTkLabel(self._warn_frame,
                             text=f"⚠  '{lib}' not installed — pip install {lib}",
                             font=ctk.CTkFont(size=12), text_color=WARN).pack(anchor="w")

    def _pick(self):
        fmt = self._fmt.get()
        f   = filedialog.askopenfilename(filetypes=self._EXTS.get(fmt, [("All","*.*")]))
        if f:
            self._set_file(f)

    def _on_drop(self, event):
        paths = self.app._parse_drop(event.data)
        if paths:
            self._set_file(paths[0])

    def _set_file(self, f):
        self._path.set(f)
        detected = self._EXT2FMT.get(Path(f).suffix.lower())
        if detected and detected != self._fmt.get():
            self._fmt.set(detected)
            self._fmt_changed(detected)

    def _run(self):
        src = self._path.get()
        if not src:
            return messagebox.showwarning("Convert", "Select a file first.")
        out = self.app._save_as("converted.pdf")
        if not out:
            return
        fmt = self._fmt.get()
        app = self.app

        def work(stop):
            notes = core.doc_to_pdf(src, fmt, out, stop)
            if notes is None:
                return

            def done():
                note = "\n\n" + "\n".join(notes) if notes else ""
                app._set_status(f"✓  {fmt} → PDF: {Path(out).name}",
                                WARN if notes else SUCCESS)
                messagebox.showinfo("Done", f"Converted PDF saved:\n{out}{note}")
            app.after(0, done)

        app._set_status(f"Converting {fmt} → PDF…")
        app.run_job(work, f"Converting {fmt} → PDF…")
