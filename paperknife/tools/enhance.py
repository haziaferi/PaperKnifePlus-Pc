from __future__ import annotations
import math
import tkinter as tk
from tkinter import messagebox, colorchooser
from pathlib import Path
import pymupdf as fitz
import customtkinter as ctk
from ..tool_base import ToolBase, register
from ..job_queue import atomic_output
from ..theme import ACCENT, ACCENT_H, CARD, TEXT, MUTED, SUCCESS, WARN


_COMPRESS_DPI = {"medium": 150, "aggressive": 96}


def _image_rewrite_options(dpi: int):
    # rewrite_images() hard-codes FZ_SUBSAMPLE_AVERAGE, which only divides by
    # whole factors (a 360-DPI image lands at 180, not 150); bicubic hits the
    # target exactly.  Bitonal images are left alone.
    opts = fitz.mupdf.PdfImageRewriterOptions()
    opts.recompress_when = fitz.mupdf.FZ_RECOMPRESS_WHEN_SMALLER
    for kind in ("color_lossless", "color_lossy", "gray_lossless", "gray_lossy"):
        setattr(opts, f"{kind}_image_recompress_method", fitz.mupdf.FZ_RECOMPRESS_JPEG)
        setattr(opts, f"{kind}_image_recompress_quality", "80")
        setattr(opts, f"{kind}_image_subsample_method", fitz.mupdf.FZ_SUBSAMPLE_BICUBIC)
        setattr(opts, f"{kind}_image_subsample_threshold", dpi + 1)
        setattr(opts, f"{kind}_image_subsample_to", dpi)
    return opts


# Both helpers take an open document and close it before the output is moved
# into place, so *out* may be the input file itself.

def compress_pdf(doc, out: str, level: str) -> None:
    """Light: clean + deflate.  Medium/aggressive: also resample embedded
    images above 150/96 DPI down to that DPI; page content is kept."""
    with atomic_output(out) as tmp, doc:
        dpi = _COMPRESS_DPI.get(level)
        if dpi:
            doc.rewrite_images(options=_image_rewrite_options(dpi))
        doc.save(tmp, deflate=True, garbage=4, clean=True)


def watermark_pdf(doc, out, text, size, opacity, color, stop, progress=None):
    """Stamp *text* at 45° through the centre of every page.  Returns *out*,
    or None when *stop* was set."""
    with atomic_output(out) as tmp, doc:
        total = len(doc)
        for i, page in enumerate(doc):
            if stop.is_set():
                return None
            r = page.rect
            # A 45° line of length L and height fs spans (L + fs) / sqrt(2) on
            # both axes; shrink the font until that fits inside the page.
            per_pt = fitz.get_text_length(text, fontname="helv", fontsize=1)
            fit = min(r.width, r.height) * 0.9 * math.sqrt(2) / (per_pt + 1)
            fs = min(size, fit)
            length = per_pt * fs
            # insert_text works in unrotated page space, so place the centre
            # there and add the page's /Rotate to keep the stamp at 45° on screen.
            centre = fitz.Point(r.width / 2, r.height / 2) * page.derotation_matrix
            page.insert_text(
                fitz.Point(centre.x - length / 2, centre.y + fs * 0.35),
                text, fontname="helv", fontsize=fs, color=color,
                fill_opacity=opacity, stroke_opacity=opacity,
                morph=(centre, fitz.Matrix(45 + page.rotation)),
            )
            if progress:
                progress(i + 1, total)
        doc.save(tmp, deflate=True)
    return out


# ══════════════════════════════════════════════════════════════════════════════
@register
class CompressTool(ToolBase):
    section = "ENHANCE"
    label   = "🗜   Compress"

    def show(self):
        body = self._card("🗜  Compress PDF",
                          "Reduce file size by cleaning streams and downsampling images")
        self._path = tk.StringVar()
        self._file_row(body, self._path)

        card = ctk.CTkFrame(body, fg_color=CARD, corner_radius=8)
        card.pack(fill="x", padx=24, pady=8)
        ctk.CTkLabel(card, text="Compression level",
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=TEXT, anchor="w").pack(padx=16, pady=(14, 6), fill="x")

        from ..prefs import PREFS
        self._level = tk.StringVar(value=PREFS.compress_level or "medium")
        for val, label, desc in [
            ("light",      "Light   —  clean & deflate only",
             "Removes redundant data, compresses streams. Safe."),
            ("medium",     "Medium  —  + resample images to 150 DPI",
             "Recompresses JPEG images at 80% quality."),
            ("aggressive", "Aggressive  —  + scale images to 96 DPI",
             "Maximum reduction; visible quality loss in images."),
        ]:
            rf = ctk.CTkFrame(card, fg_color="transparent")
            rf.pack(fill="x", padx=16, pady=2)
            ctk.CTkRadioButton(rf, text=label, variable=self._level, value=val,
                               font=ctk.CTkFont(size=13),
                               text_color=TEXT).pack(side="left")
            ctk.CTkLabel(rf, text=desc, font=ctk.CTkFont(size=11),
                         text_color=MUTED).pack(side="left", padx=12)

        ctk.CTkButton(card, text="  Compress PDF  →", command=self._run,
                      height=44, fg_color=ACCENT, hover_color=ACCENT_H,
                      font=ctk.CTkFont(size=14, weight="bold")
                      ).pack(fill="x", padx=16, pady=12)

    def _run(self):
        src = self._path.get()
        if not src:
            return messagebox.showwarning("Compress", "Select a PDF first.")
        doc = self._open_safe(src)
        if doc is None:
            return
        out = self.app._save_as("compressed.pdf")
        if not out:
            return doc.close()
        level = self._level.get()
        app   = self.app
        orig  = Path(src).stat().st_size

        def work(stop):
            compress_pdf(doc, out, level)
            new  = Path(out).stat().st_size
            orig_kb, new_kb = orig // 1024, new // 1024
            if new < orig:
                pct = round((1 - new / orig) * 100)
                app.after(0, lambda: [
                    app._set_status(
                        f"✓  {orig_kb} KB → {new_kb} KB (−{pct}%) → {Path(out).name}",
                        SUCCESS),
                    messagebox.showinfo(
                        "Compressed",
                        f"Compressed PDF saved:\n{out}\n\n"
                        f"Original: {orig_kb} KB  →  New: {new_kb} KB  ({pct}% smaller)"),
                ])
            else:
                app.after(0, lambda: [
                    app._set_status(
                        f"⚠  No size reduction: {orig_kb} KB → {new_kb} KB", WARN),
                    messagebox.showwarning(
                        "Compress",
                        f"The output is not smaller than the original:\n{out}\n\n"
                        f"Original: {orig_kb} KB  →  New: {new_kb} KB"),
                ])

        app._set_status("Compressing…")
        if app.run_job(work, "Compressing PDF…") is None:
            doc.close()


# ══════════════════════════════════════════════════════════════════════════════
@register
class WatermarkTool(ToolBase):
    section = "ENHANCE"
    label   = "💧  Watermark"

    def show(self):
        body = self._card("💧  Watermark PDF",
                          "Stamp a diagonal text watermark across every page")
        self._path = tk.StringVar()
        self._file_row(body, self._path)

        card = ctk.CTkFrame(body, fg_color=CARD, corner_radius=8)
        card.pack(fill="x", padx=24, pady=8)

        r1 = ctk.CTkFrame(card, fg_color="transparent")
        r1.pack(fill="x", padx=16, pady=(14, 4))
        ctk.CTkLabel(r1, text="Watermark text:", width=160,
                     text_color=TEXT, anchor="w").pack(side="left")
        self._text = ctk.CTkEntry(r1, height=40, placeholder_text="e.g. DRAFT · CONFIDENTIAL")
        self._text.pack(side="left", fill="x", expand=True)

        r2 = ctk.CTkFrame(card, fg_color="transparent")
        r2.pack(fill="x", padx=16, pady=4)
        ctk.CTkLabel(r2, text="Font size:", width=160,
                     text_color=TEXT, anchor="w").pack(side="left")
        self._size = ctk.CTkSlider(r2, from_=18, to=120, number_of_steps=102)
        self._size.set(60)
        self._size.pack(side="left", fill="x", expand=True)
        self._size_lbl = ctk.CTkLabel(r2, text="60 pt", width=60, text_color=TEXT)
        self._size_lbl.pack(side="left", padx=8)
        self._size.configure(command=lambda v: self._size_lbl.configure(
            text=f"{int(v)} pt"))

        r3 = ctk.CTkFrame(card, fg_color="transparent")
        r3.pack(fill="x", padx=16, pady=4)
        ctk.CTkLabel(r3, text="Opacity:", width=160,
                     text_color=TEXT, anchor="w").pack(side="left")
        self._opacity = ctk.CTkSlider(r3, from_=5, to=100, number_of_steps=95)
        self._opacity.set(25)
        self._opacity.pack(side="left", fill="x", expand=True)
        self._op_lbl = ctk.CTkLabel(r3, text="25%", width=60, text_color=TEXT)
        self._op_lbl.pack(side="left", padx=8)
        self._opacity.configure(command=lambda v: self._op_lbl.configure(
            text=f"{int(v)}%"))

        r4 = ctk.CTkFrame(card, fg_color="transparent")
        r4.pack(fill="x", padx=16, pady=(4, 16))
        ctk.CTkLabel(r4, text="Colour:", width=160,
                     text_color=TEXT, anchor="w").pack(side="left")
        self._color_rgb = (0.5, 0.5, 0.5)
        self._color_prev = ctk.CTkFrame(r4, width=36, height=26,
                                         corner_radius=4, fg_color="#808080")
        self._color_prev.pack(side="left", padx=(0, 8))
        ctk.CTkButton(r4, text="Pick…", width=72, height=28,
                      command=self._pick_color).pack(side="left")

        ctk.CTkButton(card, text="  Apply Watermark  →", command=self._run,
                      height=44, fg_color=ACCENT, hover_color=ACCENT_H,
                      font=ctk.CTkFont(size=14, weight="bold")
                      ).pack(fill="x", padx=16, pady=(0, 16))

    def _pick_color(self):
        rgb, hexc = colorchooser.askcolor(title="Watermark colour",
                                          initialcolor="#808080")
        if rgb:
            self._color_rgb = tuple(c / 255 for c in rgb)
            self._color_prev.configure(fg_color=hexc)

    def _run(self):
        src  = self._path.get()
        text = self._text.get().strip()
        if not src:
            return messagebox.showwarning("Watermark", "Select a PDF first.")
        if not text:
            return messagebox.showwarning("Watermark", "Enter watermark text.")
        doc = self._open_safe(src)
        if doc is None:
            return
        out = self.app._save_as("watermarked.pdf")
        if not out:
            return doc.close()
        size    = int(self._size.get())
        opacity = self._opacity.get() / 100.0
        color   = self._color_rgb
        app     = self.app

        def progress(n, total):
            app.after(0, lambda v=n / total: app._prog_update(v))

        def work(stop):
            if watermark_pdf(doc, out, text, size, opacity, color, stop, progress) is None:
                return
            app.after(0, lambda: [
                app._set_status(f"✓  Watermarked → {Path(out).name}", SUCCESS),
                messagebox.showinfo("Done", f"Watermarked PDF saved:\n{out}"),
            ])

        app._set_status("Applying watermark…")
        if app.run_job(work, "Applying watermark…") is None:
            doc.close()


# ══════════════════════════════════════════════════════════════════════════════
@register
class NormaliseTool(ToolBase):
    section = "ENHANCE"
    label   = "📐  Normalise Pages"

    _PAGE_SIZES = {
        "A4": (595, 842), "A3": (842, 1191), "A5": (420, 595),
        "Letter": (612, 792), "Legal": (612, 1008), "Tabloid": (792, 1224),
    }

    def show(self):
        body = self._card("📐  Normalise Pages",
                          "Resize all pages to a standard paper size")
        self._path = tk.StringVar()
        self._file_row(body, self._path)

        card = ctk.CTkFrame(body, fg_color=CARD, corner_radius=8)
        card.pack(fill="x", padx=24, pady=8)

        r1 = ctk.CTkFrame(card, fg_color="transparent")
        r1.pack(fill="x", padx=16, pady=(14, 4))
        ctk.CTkLabel(r1, text="Target size:", width=130,
                     text_color=TEXT, anchor="w").pack(side="left")
        self._size = ctk.CTkOptionMenu(
            r1, values=["A4", "A3", "A5", "Letter", "Legal", "Tabloid"],
            width=160, height=40)
        self._size.set("A4")
        self._size.pack(side="left")

        r2 = ctk.CTkFrame(card, fg_color="transparent")
        r2.pack(fill="x", padx=16, pady=4)
        ctk.CTkLabel(r2, text="Orientation:", width=130,
                     text_color=TEXT, anchor="w").pack(side="left")
        self._orient = ctk.CTkOptionMenu(
            r2, values=["Portrait", "Landscape", "Keep original"],
            width=160, height=40)
        self._orient.set("Portrait")
        self._orient.pack(side="left")

        r3 = ctk.CTkFrame(card, fg_color="transparent")
        r3.pack(fill="x", padx=16, pady=4)
        ctk.CTkLabel(r3, text="Scale mode:", width=130,
                     text_color=TEXT, anchor="w").pack(side="left")
        self._scale = ctk.CTkOptionMenu(
            r3, values=["Fit (keep ratio)", "Stretch (fill page)"],
            width=180, height=40)
        self._scale.set("Fit (keep ratio)")
        self._scale.pack(side="left")
        ctk.CTkLabel(r3, text="← recommended",
                     font=ctk.CTkFont(size=11), text_color=MUTED
                     ).pack(side="left", padx=8)

        ctk.CTkButton(card, text="  Normalise Pages  →", command=self._run,
                      height=44, fg_color=ACCENT, hover_color=ACCENT_H,
                      font=ctk.CTkFont(size=14, weight="bold")
                      ).pack(fill="x", padx=16, pady=(12, 16))

    def _run(self):
        src = self._path.get()
        if not src:
            return messagebox.showwarning("Normalise", "Select a PDF first.")
        doc = self._open_safe(src)
        if doc is None:
            return
        out = self.app._save_as("normalised.pdf")
        if not out:
            return doc.close()
        tw, th  = self._PAGE_SIZES[self._size.get()]
        orient  = self._orient.get()
        if orient == "Landscape":
            tw, th = th, tw
        stretch = "Stretch" in self._scale.get()
        try:
            with atomic_output(out) as tmp, doc, fitz.open() as nd:
                for page in doc:
                    pw, ph = page.rect.width, page.rect.height
                    if orient == "Keep original":
                        ftw, fth = (tw, th) if pw <= ph else (th, tw)
                    else:
                        ftw, fth = tw, th
                    np = nd.new_page(width=ftw, height=fth)
                    if stretch:
                        clip = fitz.Rect(0, 0, ftw, fth)
                    else:
                        sx = ftw / pw
                        sy = fth / ph
                        sc = min(sx, sy)
                        ox = (ftw - pw * sc) / 2
                        oy = (fth - ph * sc) / 2
                        clip = fitz.Rect(ox, oy, ox + pw * sc, oy + ph * sc)
                    np.show_pdf_page(clip, doc, page.number, keep_proportion=not stretch)
                nd.save(tmp, deflate=True)
            self.app._set_status(f"✓  Normalised → {Path(out).name}", SUCCESS)
            messagebox.showinfo("Done", f"Normalised PDF saved:\n{out}")
        except Exception as e:
            messagebox.showerror("Error", str(e))
