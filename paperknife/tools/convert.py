from __future__ import annotations
import html
import tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path
import io, os, zipfile
import fitz
from PIL import Image
import customtkinter as ctk
from ..tool_base import ToolBase, register
from ..theme import ACCENT, ACCENT_H, CARD, CARD2, TEXT, MUTED, DANGER, DANGER_H, SUCCESS, WARN, CANVAS_BG
from ..recent import RECENT
import importlib.util as _ilu

def _pkg(name): return _ilu.find_spec(name) is not None

_HAS_DOCX     = _pkg("docx")
_HAS_PPTX     = _pkg("pptx")
_HAS_OPENPYXL = _pkg("openpyxl")


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
            try:
                from tkinterdnd2 import DND_FILES
                self._lb.drop_target_register(DND_FILES)
                self._lb.dnd_bind("<<Drop>>", self._on_drop)
            except Exception:
                pass
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
            doc = fitz.open()
            for i, p in enumerate(paths):
                if stop.is_set():
                    return
                with Image.open(p) as im:
                    im  = im.convert("RGB")
                    w, h = im.size
                    buf  = io.BytesIO()
                    im.save(buf, "JPEG", quality=94)
                    buf.seek(0)
                page = doc.new_page(width=w, height=h)
                page.insert_image(page.rect, stream=buf.read())
                app.after(0, lambda v=(i + 1) / len(paths): app._prog_update(v))
            doc.save(out, deflate=True)
            doc.close()
            app.after(0, lambda: [
                app._set_status(
                    f"✓  Converted {len(paths)} image(s) → {Path(out).name}", SUCCESS),
                messagebox.showinfo("Done", f"PDF saved:\n{out}"),
            ])

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
        self._dpi.set(150)
        self._dpi.pack(side="left", fill="x", expand=True)
        self._dpi_lbl = ctk.CTkLabel(sr, text="150 DPI", width=80,
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
        out = filedialog.asksaveasfilename(
            defaultextension=".zip",
            filetypes=[("ZIP", "*.zip")], initialfile="pages.zip")
        if not out:
            return
        app = self.app

        def work(stop):
            scale = dpi / 72
            mat   = fitz.Matrix(scale, scale)
            with fitz.open(src) as doc:
                total = len(doc)
                with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
                    for i, page in enumerate(doc):
                        if stop.is_set():
                            return
                        pix = page.get_pixmap(matrix=mat, alpha=False)
                        zf.writestr(f"page_{i + 1:04d}.png", pix.tobytes("png"))
                        app.after(0, lambda v=(i + 1) / total: app._prog_update(v))
            RECENT.push(src, total)
            app.after(0, lambda: [
                app._set_status(
                    f"✓  Exported {total} pages → {Path(out).name}", SUCCESS),
                messagebox.showinfo("Done", f"Exported {total} pages to:\n{out}"),
            ])

        app._set_status("Exporting pages…")
        app.run_job(work, "Exporting pages to PNG…")


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

    def _run(self):
        src = self._path.get()
        if not src:
            return messagebox.showwarning("Extract", "Select a PDF first.")
        try:
            min_px = int(self._minpx.get() or "50")
        except ValueError:
            min_px = 50
        out_dir = filedialog.askdirectory(title="Choose output folder")
        if not out_dir:
            return
        fmt = self._fmt.get()
        app = self.app
        log = self._log

        def work(stop):
            doc  = fitz.open(src)
            seen, count = set(), 0
            total = len(doc)
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
                        Path(fname).write_bytes(data)
                        count += 1
                    except Exception:
                        pass
            doc.close()
            msg = (f"Found and extracted {count} image(s)  "
                   f"({len(seen)} unique xrefs scanned)")
            app.after(0, lambda m=msg, c=count: [
                app._widget_set(log, text=m),
                app._set_status(f"✓  Extracted {c} image(s) → {out_dir}", SUCCESS),
                messagebox.showinfo("Done", f"Extracted {c} image(s) to:\n{out_dir}"),
            ])

        app.run_job(work, "Extracting images…")


# ══════════════════════════════════════════════════════════════════════════════
@register
class Pdf2DocTool(ToolBase):
    section = "CONVERT"
    label   = "📄  PDF → Doc / Text"

    _FMTS = ["TXT", "HTML", "XML", "RTF", "DOCX", "PPTX", "XLSX", "PNG", "JPEG"]
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
    _NEEDS = {
        "DOCX": ("python-docx", lambda: _HAS_DOCX),
        "PPTX": ("python-pptx", lambda: _HAS_PPTX),
        "XLSX": ("openpyxl",    lambda: _HAS_OPENPYXL),
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
            r1, values=self._FMTS, width=150, height=40,
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
        if fmt in self._NEEDS:
            lib, ok_fn = self._NEEDS[fmt]
            if not ok_fn():
                warn = ctk.CTkFrame(self._opts, fg_color="#FEF3C7", corner_radius=8)
                warn.pack(fill="x", pady=(0, 6))
                ctk.CTkLabel(warn,
                             text=f"⚠  '{lib}' is not installed.\n"
                                  f"Install it:  pip install {lib}",
                             font=ctk.CTkFont(size=12), text_color="#78350F",
                             justify="left").pack(padx=16, pady=10, anchor="w")
        if fmt in ("PNG", "JPEG", "PPTX"):
            dr = ctk.CTkFrame(self._opts, fg_color="transparent")
            dr.pack(fill="x", pady=4)
            ctk.CTkLabel(dr, text="Resolution:", width=140,
                         text_color=TEXT, anchor="w").pack(side="left")
            self._dpi = ctk.CTkSlider(dr, from_=72, to=300, number_of_steps=228)
            self._dpi.set(150)
            self._dpi.pack(side="left", fill="x", expand=True)
            dpi_lbl = ctk.CTkLabel(dr, text="150 DPI", width=80, text_color=TEXT)
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
        out = filedialog.asksaveasfilename(
            defaultextension=ext,
            filetypes=[(desc, f"*{ext}"), ("All", "*.*")],
            initialfile=default)
        if not out:
            return
        dpi     = int(self._dpi.get())     if self._dpi     is not None else 150
        quality = int(self._quality.get()) if self._quality is not None else 92
        app = self.app

        def work(stop):
            with fitz.open(src) as doc:
                total = len(doc)

                if fmt == "TXT":
                    parts = []
                    for i, page in enumerate(doc):
                        if stop.is_set(): return
                        app.after(0, lambda v=(i+1)/total: app._prog_update(v))
                        parts.append(page.get_text())
                        if i < total - 1: parts.append("\n\n── Page Break ──\n\n")
                    Path(out).write_text("".join(parts), encoding="utf-8")

                elif fmt == "HTML":
                    html = ['<!DOCTYPE html>\n<html>\n<head>',
                            '<meta charset="utf-8">',
                            '<style>body{font-family:sans-serif;max-width:900px;margin:auto}',
                            '.page{border-bottom:1px solid #ccc;padding-bottom:2em;'
                            'margin-bottom:2em}</style>', '</head>\n<body>\n']
                    for i, page in enumerate(doc):
                        if stop.is_set(): return
                        app.after(0, lambda v=(i+1)/total: app._prog_update(v))
                        html.append(f'<div class="page" id="page-{i+1}">\n')
                        html.append(page.get_text("html"))
                        html.append("</div>\n")
                    html.append("</body>\n</html>")
                    Path(out).write_text("".join(html), encoding="utf-8")

                elif fmt == "XML":
                    parts = ['<?xml version="1.0" encoding="utf-8"?>\n<document>\n']
                    for i, page in enumerate(doc):
                        if stop.is_set(): return
                        app.after(0, lambda v=(i+1)/total: app._prog_update(v))
                        # Strip the per-page XML prolog (only legal at doc start)
                        page_xml = page.get_text("xml")
                        page_xml = page_xml.split("?>", 1)[-1].lstrip() if "?>" in page_xml else page_xml
                        # Also strip any wrapping <page> root element PyMuPDF may emit
                        parts.append(f'  <page number="{i+1}">\n')
                        parts.append(page_xml)
                        parts.append("  </page>\n")
                    parts.append("</document>")
                    Path(out).write_text("".join(parts), encoding="utf-8")

                elif fmt == "RTF":
                    rtf = [r'{\rtf1\ansi\ansicpg1252\deff0',
                           r'{\fonttbl{\f0\froman\fcharset0 Times New Roman;}}',
                           r'\f0\fs22 ']
                    for i, page in enumerate(doc):
                        if stop.is_set(): return
                        app.after(0, lambda v=(i+1)/total: app._prog_update(v))
                        txt = (page.get_text()
                               .replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}"))
                        for line in txt.splitlines():
                            rtf.append(line + r"\par" + "\n")
                        if i < total - 1: rtf.append(r"\page" + "\n")
                    rtf.append("}")
                    Path(out).write_bytes("".join(rtf).encode("latin-1", errors="replace"))

                elif fmt == "DOCX":
                    if not _HAS_DOCX:
                        raise RuntimeError("python-docx not installed.\nRun: pip install python-docx")
                    from docx import Document as _DocxDoc
                    wdoc = _DocxDoc()
                    for i, page in enumerate(doc):
                        if stop.is_set(): return
                        app.after(0, lambda v=(i+1)/total: app._prog_update(v))
                        for block in page.get_text("dict")["blocks"]:
                            if block.get("type") != 0: continue
                            for line in block.get("lines", []):
                                txt = "".join(s.get("text","") for s in line.get("spans",[]))
                                if txt.strip(): wdoc.add_paragraph(txt)
                        if i < total - 1: wdoc.add_page_break()
                    wdoc.save(out)

                elif fmt == "PPTX":
                    if not _HAS_PPTX:
                        raise RuntimeError("python-pptx not installed.\nRun: pip install python-pptx")
                    from pptx import Presentation as _PptxPrs
                    scale = dpi / 72.0
                    prs   = _PptxPrs()
                    p0    = doc[0]
                    prs.slide_width  = int(p0.rect.width  * 12700)
                    prs.slide_height = int(p0.rect.height * 12700)
                    blank = prs.slide_layouts[6]
                    for i, page in enumerate(doc):
                        if stop.is_set(): return
                        app.after(0, lambda v=(i+1)/total: app._prog_update(v))
                        pix  = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
                        buf  = io.BytesIO(pix.tobytes("png"))
                        slide = prs.slides.add_slide(blank)
                        slide.shapes.add_picture(buf, 0, 0,
                                                  prs.slide_width, prs.slide_height)
                    prs.save(out)

                elif fmt == "XLSX":
                    if not _HAS_OPENPYXL:
                        raise RuntimeError("openpyxl not installed.\nRun: pip install openpyxl")
                    import openpyxl as _openpyxl
                    wb = _openpyxl.Workbook()
                    wb.remove(wb.active)
                    for i, page in enumerate(doc):
                        if stop.is_set(): return
                        app.after(0, lambda v=(i+1)/total: app._prog_update(v))
                        ws = wb.create_sheet(f"Page {i+1}")
                        for row_i, line in enumerate(page.get_text().splitlines(), 1):
                            ws.cell(row=row_i, column=1, value=line)
                    wb.save(out)

                elif fmt in ("PNG", "JPEG"):
                    mat = fitz.Matrix(dpi / 72.0, dpi / 72.0)
                    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
                        for i, page in enumerate(doc):
                            if stop.is_set(): return
                            app.after(0, lambda v=(i+1)/total: app._prog_update(v))
                            pix = page.get_pixmap(matrix=mat, alpha=False)
                            if fmt == "JPEG":
                                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                                buf = io.BytesIO()
                                img.save(buf, "JPEG", quality=quality)
                                zf.writestr(f"page_{i+1:04d}.jpg", buf.getvalue())
                            else:
                                zf.writestr(f"page_{i+1:04d}.png", pix.tobytes("png"))

            app.after(0, lambda: [
                app._set_status(f"✓  PDF → {fmt}: {Path(out).name}", SUCCESS),
                messagebox.showinfo("Done", f"Saved:\n{out}"),
            ])

        app._set_status(f"Converting PDF → {fmt}…")
        app.run_job(work, f"Converting PDF → {fmt}…")


# ══════════════════════════════════════════════════════════════════════════════
@register
class Doc2PdfTool(ToolBase):
    section = "CONVERT"
    label   = "📤  Doc / Text → PDF"

    _FMTS = ["TXT", "HTML", "XML", "RTF", "DOCX", "PPTX", "XLSX", "PNG", "JPEG"]
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
    _NEEDS = {
        "DOCX": ("python-docx", lambda: _HAS_DOCX),
        "PPTX": ("python-pptx", lambda: _HAS_PPTX),
        "XLSX": ("openpyxl",    lambda: _HAS_OPENPYXL),
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
            r1, values=self._FMTS, width=150, height=40,
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

    def _fmt_changed(self, fmt):
        for w in self._warn_frame.winfo_children():
            w.destroy()
        self._info_lbl.configure(text=self._INFO.get(fmt, ""))
        if fmt in self._NEEDS:
            lib, ok_fn = self._NEEDS[fmt]
            if not ok_fn():
                ctk.CTkLabel(self._warn_frame,
                             text=f"⚠  '{lib}' not installed — pip install {lib}",
                             font=ctk.CTkFont(size=12), text_color=WARN).pack(anchor="w")

    def _pick(self):
        fmt = self._fmt.get()
        f   = filedialog.askopenfilename(filetypes=self._EXTS.get(fmt, [("All","*.*")]))
        if f:
            self._path.set(f)
            detected = self._EXT2FMT.get(Path(f).suffix.lower())
            if detected and detected != fmt:
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
            nd = fitz.open()
            A4 = fitz.paper_rect("A4")

            if fmt == "TXT":
                text = Path(src).read_text(encoding="utf-8", errors="replace")
                story = fitz.Story(html=f"<pre>{html.escape(text)}</pre>")
                writer = fitz.DocumentWriter(out)
                while True:
                    dev, more = writer.begin_page(A4), False
                    _, more = story.place(A4)
                    story.draw(dev, None)
                    writer.end_page()
                    if not more: break
                writer.close()

            elif fmt == "HTML":
                html_src = Path(src).read_text(encoding="utf-8", errors="replace")
                story = fitz.Story(html=html_src)
                writer = fitz.DocumentWriter(out)
                while True:
                    dev, more = writer.begin_page(A4), False
                    _, more = story.place(A4)
                    story.draw(dev, None)
                    writer.end_page()
                    if not more: break
                writer.close()

            elif fmt == "XML":
                import xml.etree.ElementTree as ET
                try:
                    root = ET.parse(src).getroot()
                    text = " ".join(root.itertext())
                except Exception:
                    text = Path(src).read_text(encoding="utf-8", errors="replace")
                story = fitz.Story(html=f"<pre>{html.escape(text)}</pre>")
                writer = fitz.DocumentWriter(out)
                while True:
                    dev, more = writer.begin_page(A4), False
                    _, more = story.place(A4)
                    story.draw(dev, None)
                    writer.end_page()
                    if not more: break
                writer.close()

            elif fmt == "RTF":
                try:
                    from striprtf.striprtf import rtf_to_text
                    text = rtf_to_text(Path(src).read_text(encoding="latin-1", errors="replace"))
                except Exception:
                    text = Path(src).read_text(encoding="latin-1", errors="replace")
                story = fitz.Story(html=f"<pre>{html.escape(text)}</pre>")
                writer = fitz.DocumentWriter(out)
                while True:
                    dev, more = writer.begin_page(A4), False
                    _, more = story.place(A4)
                    story.draw(dev, None)
                    writer.end_page()
                    if not more: break
                writer.close()

            elif fmt == "DOCX":
                if not _HAS_DOCX:
                    raise RuntimeError("python-docx not installed.\nRun: pip install python-docx")
                from docx import Document as _DocxDoc
                wdoc = _DocxDoc(src)
                lines = []
                for para in wdoc.paragraphs:
                    lines.append(para.text)
                for tbl in wdoc.tables:
                    for row in tbl.rows:
                        lines.append("\t".join(c.text for c in row.cells))
                story = fitz.Story(html="<br>".join(html.escape(l) for l in lines))
                writer = fitz.DocumentWriter(out)
                while True:
                    dev, more = writer.begin_page(A4), False
                    _, more = story.place(A4)
                    story.draw(dev, None)
                    writer.end_page()
                    if not more: break
                writer.close()

            elif fmt == "PPTX":
                if not _HAS_PPTX:
                    raise RuntimeError("python-pptx not installed.\nRun: pip install python-pptx")
                from pptx import Presentation as _PptxPrs
                prs = _PptxPrs(src)
                for slide in prs.slides:
                    lines = []
                    for shape in slide.shapes:
                        if shape.has_text_frame:
                            for para in shape.text_frame.paragraphs:
                                lines.append(para.text)
                    page = nd.new_page(width=A4.width, height=A4.height)
                    page.insert_htmlbox(A4, "<br>".join(html.escape(l) for l in lines))
                nd.save(out, deflate=True)
                nd.close()
                app.after(0, lambda: [
                    app._set_status(f"✓  PPTX → PDF: {Path(out).name}", SUCCESS),
                    messagebox.showinfo("Done", f"Converted PDF saved:\n{out}"),
                ])
                return

            elif fmt == "XLSX":
                if not _HAS_OPENPYXL:
                    raise RuntimeError("openpyxl not installed.\nRun: pip install openpyxl")
                import openpyxl as _openpyxl
                wb   = _openpyxl.load_workbook(src, data_only=True)
                LAND = fitz.paper_rect("A4-L")
                writer = fitz.DocumentWriter(out)
                for ws in wb.worksheets:
                    rows = list(ws.iter_rows(values_only=True))
                    text = "\n".join("\t".join(str(c or "") for c in row) for row in rows)
                    story = fitz.Story(html=f"<pre>{html.escape(text)}</pre>")
                    while True:
                        dev  = writer.begin_page(LAND)
                        _, more = story.place(LAND)
                        story.draw(dev, None)
                        writer.end_page()
                        if not more: break
                writer.close()
                app.after(0, lambda: [
                    app._set_status(f"✓  XLSX → PDF: {Path(out).name}", SUCCESS),
                    messagebox.showinfo("Done", f"Converted PDF saved:\n{out}"),
                ])
                return

            elif fmt in ("PNG", "JPEG"):
                with Image.open(src) as im:
                    im = im.convert("RGB")
                    w, h = im.size
                    buf  = io.BytesIO()
                    im.save(buf, "JPEG", quality=95)
                    buf.seek(0)
                page = nd.new_page(width=w, height=h)
                page.insert_image(page.rect, stream=buf.read())
                nd.save(out, deflate=True)
                nd.close()
                app.after(0, lambda: [
                    app._set_status(f"✓  {fmt} → PDF: {Path(out).name}", SUCCESS),
                    messagebox.showinfo("Done", f"Converted PDF saved:\n{out}"),
                ])
                return

            app.after(0, lambda: [
                app._set_status(f"✓  {fmt} → PDF: {Path(out).name}", SUCCESS),
                messagebox.showinfo("Done", f"Converted PDF saved:\n{out}"),
            ])

        app._set_status(f"Converting {fmt} → PDF…")
        app.run_job(work, f"Converting {fmt} → PDF…")
