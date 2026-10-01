from __future__ import annotations
import tkinter as tk
from tkinter import filedialog, messagebox, colorchooser
from pathlib import Path
import io
import fitz
from PIL import Image
import customtkinter as ctk
from ..tool_base import ToolBase, register
from ..theme import ACCENT, ACCENT_H, CARD, TEXT, MUTED, DANGER, DANGER_H, SUCCESS, WARN


# ══════════════════════════════════════════════════════════════════════════════
@register
class CompressTool(ToolBase):
    section = "ENHANCE"
    label   = "🗜   Compress"

    def show(self):
        app  = self.app
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
        out = self.app._save_as("compressed.pdf")
        if not out:
            return
        level = self._level.get()
        app   = self.app

        def work(stop):
            with fitz.open(src) as doc:
                total = len(doc)
                if level in ("medium", "aggressive"):
                    dpi    = 96 if level == "aggressive" else 150
                    scale  = dpi / 72.0
                    nd     = fitz.open()
                    for i, page in enumerate(doc):
                        if stop.is_set():
                            return
                        pix = page.get_pixmap(
                            matrix=fitz.Matrix(scale, scale), alpha=False)
                        img = Image.frombytes(
                            "RGB", [pix.width, pix.height], pix.samples)
                        buf = io.BytesIO()
                        img.save(buf, "JPEG", quality=80)
                        buf.seek(0)
                        np = nd.new_page(
                            width=page.rect.width, height=page.rect.height)
                        np.insert_image(np.rect, stream=buf.read())
                        app.after(0, lambda v=(i + 1) / total: app._prog_update(v))
                    nd.save(out, deflate=True, garbage=4)
                    nd.close()
                else:
                    doc.save(out, deflate=True, garbage=4, clean=True)

            orig_kb = Path(src).stat().st_size // 1024
            new_kb  = Path(out).stat().st_size // 1024
            pct     = 100 - int(new_kb / max(orig_kb, 1) * 100)
            app.after(0, lambda: [
                app._set_status(
                    f"✓  {orig_kb} KB → {new_kb} KB (−{pct}%) → {Path(out).name}",
                    SUCCESS),
                messagebox.showinfo(
                    "Compressed",
                    f"Compressed PDF saved:\n{out}\n\n"
                    f"Original: {orig_kb} KB  →  New: {new_kb} KB  ({pct}% smaller)"),
            ])

        app._set_status("Compressing…")
        app.run_job(work, "Compressing PDF…")


# ══════════════════════════════════════════════════════════════════════════════
@register
class WatermarkTool(ToolBase):
    section = "ENHANCE"
    label   = "💧  Watermark"

    def show(self):
        app  = self.app
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
        out = self.app._save_as("watermarked.pdf")
        if not out:
            return
        size    = int(self._size.get())
        opacity = self._opacity.get() / 100.0
        color   = self._color_rgb
        app     = self.app

        def work(stop):
            with fitz.open(src) as doc:
                total = len(doc)
                for i, page in enumerate(doc):
                    if stop.is_set():
                        return
                    w, h = page.rect.width, page.rect.height
                    page.insert_text(
                        fitz.Point(w * 0.1, h * 0.55),
                        text, fontsize=size,
                        color=color, rotate=45,
                        render_mode=0,
                    )
                    page.draw_rect(page.rect, color=None, fill=None)
                    app.after(0, lambda v=(i + 1) / total: app._prog_update(v))
                doc.save(out, deflate=True)
            app.after(0, lambda: [
                app._set_status(f"✓  Watermarked → {Path(out).name}", SUCCESS),
                messagebox.showinfo("Done", f"Watermarked PDF saved:\n{out}"),
            ])

        app._set_status("Applying watermark…")
        app.run_job(work, "Applying watermark…")


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
        app  = self.app
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
        out = self.app._save_as("normalised.pdf")
        if not out:
            return
        try:
            tw, th  = self._PAGE_SIZES[self._size.get()]
            orient  = self._orient.get()
            if orient == "Landscape":
                tw, th = th, tw
            stretch = "Stretch" in self._scale.get()
            doc = fitz.open(src)
            nd  = fitz.open()
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
                np.show_pdf_page(clip, doc, page.number)
            nd.save(out, deflate=True)
            nd.close()
            doc.close()
            self.app._set_status(f"✓  Normalised → {Path(out).name}", SUCCESS)
            messagebox.showinfo("Done", f"Normalised PDF saved:\n{out}")
        except Exception as e:
            messagebox.showerror("Error", str(e))
