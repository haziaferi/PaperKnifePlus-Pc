from __future__ import annotations
import html
import tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path
import io, os, re, zipfile
import pymupdf as fitz
from PIL import Image, ImageOps
import customtkinter as ctk
from ..tool_base import ToolBase, register
from ..theme import (ACCENT, ACCENT_H, CARD, TEXT, MUTED, DANGER, DANGER_H, SUCCESS, WARN,
                     WARN_BG, WARN_BODY)
from ..prefs import pref_dpi
from ..job_queue import atomic_output
from ..pages import render
import importlib.util as _ilu

def _pkg(name): return _ilu.find_spec(name) is not None

_HAS_DOCX     = _pkg("docx")
_HAS_PPTX     = _pkg("pptx")
_HAS_OPENPYXL = _pkg("openpyxl")

_FMTS  = ["TXT", "HTML", "XML", "RTF", "DOCX", "PPTX", "XLSX", "PNG", "JPEG"]
# format -> (pip package, installed)
_NEEDS = {
    "DOCX": ("python-docx", _HAS_DOCX),
    "PPTX": ("python-pptx", _HAS_PPTX),
    "XLSX": ("openpyxl",    _HAS_OPENPYXL),
}

# Characters XML 1.0 forbids; python-docx and openpyxl refuse strings holding them.
_XML_ILLEGAL = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f]")
_STORY_CSS   = "pre { white-space: pre-wrap; font-size: 11pt; }"
_MARGIN      = (36, 36, -36, -36)


class _Cancelled(Exception):
    """Raised inside atomic_output on Cancel so the partial file is discarded."""


def _require(fmt: str) -> None:
    lib, installed = _NEEDS[fmt]
    if not installed:
        raise RuntimeError(f"{lib} not installed.\nRun: pip install {lib}")


def _pages_to_zip(path, doc, dpi, fmt, quality, stop, progress) -> None:
    """Write every page of *doc* into a ZIP at *path* as PNG or JPEG images."""
    total = len(doc)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for i, page in enumerate(doc):
            if stop.is_set():
                raise _Cancelled
            progress((i + 1) / total)
            pix = render(page, dpi / 72.0)
            if fmt == "JPEG":
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                buf = io.BytesIO()
                img.save(buf, "JPEG", quality=quality)
                zf.writestr(f"page_{i + 1:04d}.jpg", buf.getvalue())
            else:
                zf.writestr(f"page_{i + 1:04d}.png", pix.tobytes("png"))


def _image_page(doc, path) -> None:
    """Append a page sized to the image at *path*, upright, transparency flattened onto white."""
    with Image.open(path) as src:
        im = ImageOps.exif_transpose(src)
        if src.format == "JPEG" and src.getexif().get(0x0112, 1) == 1:
            data = Path(path).read_bytes()        # already upright: embed without recompressing
        else:
            if im.mode in ("RGBA", "LA", "PA") or "transparency" in im.info:
                im = im.convert("RGBA")
                flat = Image.new("RGB", im.size, "white")
                flat.paste(im, mask=im.getchannel("A"))
                im = flat
            elif im.mode not in ("1", "L", "RGB"):
                im = im.convert("RGB")
            buf = io.BytesIO()
            im.save(buf, "PNG")
            data = buf.getvalue()
        w, h = im.size
    page = doc.new_page(width=w, height=h)
    page.insert_image(page.rect, stream=data)


def _text_story(text: str):
    return fitz.Story(html=f"<pre>{html.escape(text)}</pre>", user_css=_STORY_CSS)


def _write_story(writer, story, page_rect, stop) -> bool:
    """Typeset *story* onto as many *page_rect* pages as it needs, inside the
    margins.  Returns False when the story cannot be laid out on pages."""
    where = page_rect + _MARGIN
    last = None
    while True:
        dev = writer.begin_page(page_rect)
        more, filled = story.place(where)
        story.draw(dev)
        writer.end_page()
        if not more or stop.is_set():
            return True
        # An element that cannot be split and is taller than the page (a long
        # table row) makes place() return more forever without consuming it;
        # it shows as the same overflowing area page after page.  A paragraph
        # margin overflows the area by a few points while the text still flows.
        filled = fitz.Rect(filled)
        if filled == last and filled.y1 - where.y1 > where.height * 0.05:
            return False
        last = filled


def _rtf_escape(text: str) -> str:
    out = []
    for ch in text:
        if ch in "\\{}":
            out.append("\\" + ch)
        elif ord(ch) < 128:
            out.append(ch)
        else:
            b = ch.encode("utf-16-le")
            for i in range(0, len(b), 2):
                unit = int.from_bytes(b[i:i + 2], "little", signed=True)
                out.append(f"\\u{unit}?")
    return "".join(out)


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
        IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".webp", ".gif"}
        for p in self.app._parse_drop(event.data):
            if Path(p).suffix.lower() in IMG_EXT:
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
            n = len(paths)
            with atomic_output(out) as tmp, fitz.open() as doc:
                for i, p in enumerate(paths):
                    if stop.is_set():
                        return
                    _image_page(doc, p)
                    app.after(0, lambda v=(i + 1) / n: app._prog_update(v))
                doc.save(tmp, deflate=True)

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
            seen, count, failed = set(), 0, 0
            total = len(doc)
            with doc:
                for pg_i, page in enumerate(doc):
                    if stop.is_set():
                        return
                    app.after(0, lambda v=(pg_i + 1) / total: app._prog_update(v))
                    for img_info in page.get_images(full=True):
                        xref = img_info[0]
                        if xref in seen:
                            continue
                        seen.add(xref)
                        try:
                            base = doc.extract_image(xref)
                            w, h = base["width"], base["height"]
                            if w < min_px or h < min_px:
                                continue
                            data = base["image"]
                            ext  = base["ext"]
                            if fmt == "PNG":
                                img = Image.open(io.BytesIO(data))
                                if img.mode not in ("1", "L", "LA", "I", "P", "RGB", "RGBA"):
                                    img = img.convert("RGB")      # PNG cannot store CMYK
                                buf = io.BytesIO()
                                img.save(buf, "PNG")
                                data = buf.getvalue()
                                ext  = "png"
                            elif fmt == "JPEG":
                                img = Image.open(io.BytesIO(data)).convert("RGB")
                                buf = io.BytesIO()
                                img.save(buf, "JPEG", quality=92)
                                data = buf.getvalue()
                                ext  = "jpg"
                            fname = os.path.join(out_dir, f"img_{xref:05d}.{ext}")
                            with atomic_output(fname) as tmp:
                                Path(tmp).write_bytes(data)
                            count += 1
                        except Exception:
                            failed += 1
            msg = (f"Found and extracted {count} image(s)  "
                   f"({len(seen)} unique xrefs scanned)")
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
            try:
                with atomic_output(out) as tmp, doc:
                    total = len(doc)

                    if fmt == "TXT":
                        parts = []
                        for i, page in enumerate(doc):
                            if stop.is_set(): raise _Cancelled
                            app.after(0, lambda v=(i+1)/total: app._prog_update(v))
                            parts.append(page.get_text())
                            if i < total - 1: parts.append("\n\n── Page Break ──\n\n")
                        Path(tmp).write_text("".join(parts), encoding="utf-8")

                    elif fmt == "HTML":
                        html_parts = ['<!DOCTYPE html>\n<html>\n<head>',
                                      '<meta charset="utf-8">',
                                      '<style>body{font-family:sans-serif;max-width:900px;margin:auto}',
                                      '.page{border-bottom:1px solid #ccc;padding-bottom:2em;'
                                      'margin-bottom:2em}</style>', '</head>\n<body>\n']
                        for i, page in enumerate(doc):
                            if stop.is_set(): raise _Cancelled
                            app.after(0, lambda v=(i+1)/total: app._prog_update(v))
                            html_parts.append(f'<div class="page" id="page-{i+1}">\n')
                            html_parts.append(page.get_text("html"))
                            html_parts.append("</div>\n")
                        html_parts.append("</body>\n</html>")
                        Path(tmp).write_text("".join(html_parts), encoding="utf-8")

                    elif fmt == "XML":
                        parts = ['<?xml version="1.0" encoding="utf-8"?>\n<document>\n']
                        for i, page in enumerate(doc):
                            if stop.is_set(): raise _Cancelled
                            app.after(0, lambda v=(i+1)/total: app._prog_update(v))
                            # get_text("xml") is already one <page id="pageN"> element, no prolog
                            parts.append(page.get_text("xml"))
                        parts.append("</document>")
                        Path(tmp).write_text("".join(parts), encoding="utf-8")

                    elif fmt == "RTF":
                        rtf = [r'{\rtf1\ansi\ansicpg1252\deff0',
                               r'{\fonttbl{\f0\froman\fcharset0 Times New Roman;}}',
                               r'\f0\fs22 ']
                        for i, page in enumerate(doc):
                            if stop.is_set(): raise _Cancelled
                            app.after(0, lambda v=(i+1)/total: app._prog_update(v))
                            for line in page.get_text().splitlines():
                                rtf.append(_rtf_escape(line) + r"\par" + "\n")
                            if i < total - 1: rtf.append(r"\page" + "\n")
                        rtf.append("}")
                        Path(tmp).write_bytes("".join(rtf).encode("ascii"))

                    elif fmt == "DOCX":
                        _require(fmt)
                        from docx import Document as _DocxDoc
                        wdoc = _DocxDoc()
                        for i, page in enumerate(doc):
                            if stop.is_set(): raise _Cancelled
                            app.after(0, lambda v=(i+1)/total: app._prog_update(v))
                            for block in page.get_text("dict")["blocks"]:
                                if block.get("type") != 0: continue
                                txt = " ".join(
                                    "".join(s.get("text", "") for s in line.get("spans", []))
                                    for line in block.get("lines", []))
                                txt = _XML_ILLEGAL.sub("", txt)
                                if txt.strip(): wdoc.add_paragraph(txt)
                            if i < total - 1: wdoc.add_page_break()
                        wdoc.save(tmp)

                    elif fmt == "PPTX":
                        _require(fmt)
                        from pptx import Presentation as _PptxPrs
                        scale = dpi / 72.0
                        prs   = _PptxPrs()
                        p0    = doc[0]
                        prs.slide_width  = int(p0.rect.width  * 12700)
                        prs.slide_height = int(p0.rect.height * 12700)
                        blank = prs.slide_layouts[6]
                        sw, sh = prs.slide_width, prs.slide_height
                        for i, page in enumerate(doc):
                            if stop.is_set(): raise _Cancelled
                            app.after(0, lambda v=(i+1)/total: app._prog_update(v))
                            pix  = render(page, scale)
                            buf  = io.BytesIO(pix.tobytes("png"))
                            slide = prs.slides.add_slide(blank)
                            # Pages of another size or orientation than page 1 are fitted, not stretched.
                            fit  = min(sw / page.rect.width, sh / page.rect.height)
                            w, h = int(page.rect.width * fit), int(page.rect.height * fit)
                            slide.shapes.add_picture(buf, (sw - w) // 2, (sh - h) // 2, w, h)
                        prs.save(tmp)

                    elif fmt == "XLSX":
                        _require(fmt)
                        import openpyxl as _openpyxl
                        wb = _openpyxl.Workbook()
                        wb.remove(wb.active)
                        for i, page in enumerate(doc):
                            if stop.is_set(): raise _Cancelled
                            app.after(0, lambda v=(i+1)/total: app._prog_update(v))
                            ws = wb.create_sheet(f"Page {i+1}")
                            for row_i, line in enumerate(page.get_text().splitlines(), 1):
                                cell = ws.cell(row=row_i, column=1, value=_XML_ILLEGAL.sub("", line))
                                cell.data_type = "s"      # text such as "=..." must not become a formula
                        wb.save(tmp)

                    elif fmt in ("PNG", "JPEG"):
                        _pages_to_zip(tmp, doc, dpi, fmt, quality, stop,
                                      lambda v: app.after(0, lambda: app._prog_update(v)))
            except _Cancelled:
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
            A4 = fitz.paper_rect("A4")
            notes = []      # fallbacks that changed what was typeset

            if fmt == "PPTX":
                _require(fmt)
                from pptx import Presentation as _PptxPrs
                prs = _PptxPrs(src)
                nd  = fitz.open()
                for slide in prs.slides:
                    if stop.is_set():
                        nd.close()
                        return
                    lines = []
                    for shape in slide.shapes:
                        if shape.has_text_frame:
                            for para in shape.text_frame.paragraphs:
                                lines.append(para.text)
                    page = nd.new_page(width=A4.width, height=A4.height)
                    page.insert_htmlbox(A4, "<br>".join(html.escape(l) for l in lines))
                with atomic_output(out) as tmp:
                    nd.save(tmp, deflate=True)
                nd.close()

            elif fmt in ("PNG", "JPEG"):
                nd = fitz.open()
                _image_page(nd, src)
                with atomic_output(out) as tmp:
                    nd.save(tmp, deflate=True)
                nd.close()

            else:
                stories = []          # (Story, page rect)
                if fmt == "TXT":
                    text = Path(src).read_text(encoding="utf-8", errors="replace")
                    stories.append((_text_story(text), A4))

                elif fmt == "HTML":
                    html_src = Path(src).read_text(encoding="utf-8", errors="replace")
                    # The archive lets relative <img>/<link> paths resolve next to the file.
                    stories.append((fitz.Story(html=html_src,
                                               archive=fitz.Archive(str(Path(src).parent))), A4))

                elif fmt == "XML":
                    import xml.etree.ElementTree as ET
                    try:
                        root = ET.parse(src).getroot()
                        text = " ".join(root.itertext())
                    except ET.ParseError as e:
                        text = Path(src).read_text(encoding="utf-8", errors="replace")
                        notes.append(f"The XML could not be parsed ({e}), "
                                     "so the file was typeset as raw text, tags included.")
                    stories.append((_text_story(text), A4))

                elif fmt == "RTF":
                    raw = Path(src).read_text(encoding="latin-1", errors="replace")
                    try:
                        from striprtf.striprtf import rtf_to_text
                    except ImportError:
                        text = raw
                        notes.append("striprtf is not installed (pip install striprtf), "
                                     "so the RTF markup was typeset as raw text.")
                    else:
                        text = rtf_to_text(raw)
                    stories.append((_text_story(text), A4))

                elif fmt == "DOCX":
                    _require(fmt)
                    from docx import Document as _DocxDoc
                    from docx.table import Table as _DocxTable
                    from docx.text.paragraph import Paragraph as _DocxPara
                    wdoc  = _DocxDoc(src)
                    parts = []
                    # Walk the body in document order so tables stay where they are.
                    for el in wdoc.element.body.iterchildren():
                        tag = el.tag.rsplit("}", 1)[-1]
                        if tag == "p":
                            para  = _DocxPara(el, wdoc)
                            style = para.style.name if para.style is not None else ""
                            text  = html.escape(para.text) or "&#160;"
                            if style == "Title" or style == "Heading 1":
                                parts.append(f"<h1>{text}</h1>")
                            elif style == "Heading 2":
                                parts.append(f"<h2>{text}</h2>")
                            elif style.startswith("Heading"):
                                parts.append(f"<h3>{text}</h3>")
                            else:
                                parts.append(f"<p>{text}</p>")
                        elif tag == "tbl":
                            rows = "".join(
                                "<tr>" + "".join(f"<td>{html.escape(c.text)}</td>"
                                                 for c in row.cells) + "</tr>"
                                for row in _DocxTable(el, wdoc).rows)
                            parts.append(f"<table>{rows}</table>")
                    stories.append((fitz.Story(
                        html="".join(parts),
                        user_css="table { border-collapse: collapse; } "
                                 "td { border: 1px solid #888; padding: 2px 4px; }"), A4))

                elif fmt == "XLSX":
                    _require(fmt)
                    import openpyxl as _openpyxl
                    wb   = _openpyxl.load_workbook(src, data_only=True)
                    LAND = fitz.paper_rect("A4-L")
                    for ws in wb.worksheets:
                        rows = ws.iter_rows(values_only=True)
                        text = "\n".join("\t".join("" if c is None else str(c) for c in row)
                                         for row in rows)
                        stories.append((_text_story(text), LAND))

                try:
                    with atomic_output(out) as tmp:
                        writer = fitz.DocumentWriter(tmp)
                        try:
                            for story, rect in stories:
                                # Raised here, not in _write_story, so no traceback
                                # frame keeps the writer (and its open file) alive.
                                if not _write_story(writer, story, rect, stop):
                                    raise RuntimeError(
                                        "The document contains an element, such as a table "
                                        "row, that is taller than a page and cannot be split "
                                        "across pages.")
                                if stop.is_set():
                                    raise _Cancelled
                        finally:
                            writer.close()
                            # The file stays open until the writer object is freed,
                            # and os.replace in atomic_output fails while it is.
                            del writer
                except _Cancelled:
                    return

            if stop.is_set():
                return

            def done():
                note = "\n\n" + "\n".join(notes) if notes else ""
                app._set_status(f"✓  {fmt} → PDF: {Path(out).name}",
                                WARN if notes else SUCCESS)
                messagebox.showinfo("Done", f"Converted PDF saved:\n{out}{note}")
            app.after(0, done)

        app._set_status(f"Converting {fmt} → PDF…")
        app.run_job(work, f"Converting {fmt} → PDF…")
