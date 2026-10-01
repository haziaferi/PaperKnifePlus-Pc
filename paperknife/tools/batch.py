from __future__ import annotations
import html
import tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path
import io, os
import fitz
from PIL import Image
import customtkinter as ctk
from ..tool_base import ToolBase, register
from ..theme import ACCENT, ACCENT_H, CARD, CARD2, TEXT, MUTED, SUCCESS, WARN, DANGER
from ..prefs import PREFS

# ── Per-operation worker functions ────────────────────────────────────────────
# Each accepts (src_path, out_dir, opts, stop) → out_path or raises.

def _do_compress(src, out_dir, opts, stop):
    level = opts.get("level", "medium")
    out   = os.path.join(out_dir, Path(src).stem + "_compressed.pdf")
    with fitz.open(src) as doc:
        if level == "light":
            doc.save(out, deflate=True, garbage=4, clean=True)
        else:
            dpi   = 96 if level == "aggressive" else 150
            scale = dpi / 72.0
            nd    = fitz.open()
            for page in doc:
                if stop.is_set(): return None
                pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                buf = io.BytesIO()
                img.save(buf, "JPEG", quality=80)
                buf.seek(0)
                np = nd.new_page(width=page.rect.width, height=page.rect.height)
                np.insert_image(np.rect, stream=buf.read())
            nd.save(out, deflate=True, garbage=4)
            nd.close()
    return out

def _do_watermark(src, out_dir, opts, stop):
    text    = opts.get("text", "DRAFT")
    size    = opts.get("size", 60)
    opacity = opts.get("opacity", 0.25)
    out     = os.path.join(out_dir, Path(src).stem + "_watermarked.pdf")
    with fitz.open(src) as doc:
        for page in doc:
            if stop.is_set(): return None
            w, h = page.rect.width, page.rect.height
            page.insert_text(fitz.Point(w * 0.1, h * 0.55), text,
                             fontsize=size, color=(0.5, 0.5, 0.5), rotate=45)
        doc.save(out, deflate=True)
    return out

def _do_ocr(src, out_dir, opts, stop):
    import pytesseract
    from PIL import Image as _PIL
    lang  = opts.get("lang", "eng")
    dpi   = opts.get("dpi", 150)
    out   = os.path.join(out_dir, Path(src).stem + "_ocr.pdf")
    scale = dpi / 72.0
    with fitz.open(src) as doc:
        nd = fitz.open()
        for page in doc:
            if stop.is_set(): return None
            pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
            img = _PIL.frombytes("RGB", [pix.width, pix.height], pix.samples)
            np  = nd.new_page(width=page.rect.width, height=page.rect.height)
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=90)
            buf.seek(0)
            np.insert_image(np.rect, stream=buf.read())
            text = pytesseract.image_to_string(img, lang=lang)
            np.insert_htmlbox(np.rect, f"<pre>{html.escape(text)}</pre>",
                              css="pre{font-size:10pt;color:transparent}")
        nd.save(out, deflate=True)
        nd.close()
    return out

def _do_pdf2txt(src, out_dir, opts, stop):
    out = os.path.join(out_dir, Path(src).stem + ".txt")
    with fitz.open(src) as doc:
        parts = []
        for i, page in enumerate(doc):
            if stop.is_set(): return None
            parts.append(page.get_text())
            if i < len(doc) - 1:
                parts.append("\n\n── Page Break ──\n\n")
    Path(out).write_text("".join(parts), encoding="utf-8")
    return out

_OPS = {
    "Compress":      (_do_compress,  ["level"]),
    "Watermark":     (_do_watermark, ["text", "size", "opacity"]),
    "OCR":           (_do_ocr,       ["lang", "dpi"]),
    "PDF → TXT":     (_do_pdf2txt,   []),
}


@register
class BatchTool(ToolBase):
    section = "ORGANISE"
    label   = "⚙   Batch"

    def show(self):
        app  = self.app
        body = self._card("⚙  Batch Operations",
                          "Apply one operation to every PDF in a folder")
        top = ctk.CTkFrame(body, fg_color="transparent")
        top.pack(fill="x", padx=24, pady=8)

        # ── Operation ─────────────────────────────────────────────────────────
        ctk.CTkLabel(top, text="Operation:", width=110, text_color=TEXT,
                     anchor="w").pack(side="left")
        self._op = ctk.CTkOptionMenu(top, values=list(_OPS.keys()),
                                      width=180, height=40,
                                      command=self._op_changed)
        self._op.set("Compress")
        self._op.pack(side="left", padx=(0, 16))

        # ── Folders ───────────────────────────────────────────────────────────
        for attr, label, btn_lbl in [
            ("_in_dir",  "Input folder:",  "Browse…"),
            ("_out_dir", "Output folder:", "Browse…"),
        ]:
            row = ctk.CTkFrame(body, fg_color="transparent")
            row.pack(fill="x", padx=24, pady=4)
            ctk.CTkLabel(row, text=label, width=130, text_color=TEXT,
                         anchor="w").pack(side="left")
            var = tk.StringVar()
            setattr(self, attr + "_var", var)
            ctk.CTkEntry(row, textvariable=var, state="readonly",
                         height=40, placeholder_text="Not set…"
                         ).pack(side="left", fill="x", expand=True, padx=(0, 8))
            a = attr
            ctk.CTkButton(row, text=btn_lbl, width=100, height=40,
                          command=lambda a=a: self._pick_dir(a)
                          ).pack(side="left")

        # ── Options card (dynamic) ────────────────────────────────────────────
        self._opts_frame = ctk.CTkFrame(body, fg_color=CARD, corner_radius=8)
        self._opts_frame.pack(fill="x", padx=24, pady=8)
        self._opt_widgets: dict[str, tk.Variable] = {}
        self._op_changed("Compress")

        # ── Results table ─────────────────────────────────────────────────────
        lf, self._lb = app._listbox(body, height=8)
        lf.pack(fill="both", expand=True, padx=24, pady=4)
        ctk.CTkLabel(body, text="File results appear here during the run",
                     font=ctk.CTkFont(size=11), text_color=MUTED, anchor="w"
                     ).pack(padx=28, fill="x")

        app._big_btn(body, "  Run Batch  →", self._run).pack(fill="x", padx=24, pady=12)

    def _pick_dir(self, attr):
        d = filedialog.askdirectory()
        if d:
            getattr(self, attr + "_var").set(d)

    def _op_changed(self, op):
        for w in self._opts_frame.winfo_children():
            w.destroy()
        self._opt_widgets = {}
        ctk.CTkLabel(self._opts_frame, text=f"Options — {op}",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=TEXT, anchor="w").pack(padx=16, pady=(12, 6), fill="x")
        if op == "Compress":
            from ..prefs import PREFS
            self._make_opt("level", "Level:", "optionmenu",
                           ["light", "medium", "aggressive"], PREFS.compress_level or "medium")
        elif op == "Watermark":
            self._make_opt("text",    "Text:",    "entry", default="DRAFT")
            self._make_opt("size",    "Size:",    "entry", default="60")
            self._make_opt("opacity", "Opacity:", "entry", default="0.25")
        elif op == "OCR":
            self._make_opt("lang", "Language:", "entry", default=PREFS.ocr_lang)
            self._make_opt("dpi",  "DPI:",      "entry", default=str(PREFS.default_dpi))
        # PDF→TXT has no options
        ctk.CTkFrame(self._opts_frame, height=8, fg_color="transparent").pack()

    def _make_opt(self, key, label, kind, choices=None, default=""):
        row = ctk.CTkFrame(self._opts_frame, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=3)
        ctk.CTkLabel(row, text=label, width=110, text_color=TEXT,
                     anchor="w").pack(side="left")
        if kind == "optionmenu":
            var = tk.StringVar(value=default)
            ctk.CTkOptionMenu(row, variable=var, values=choices,
                              width=160, height=34).pack(side="left")
        else:
            var = tk.StringVar(value=default)
            ctk.CTkEntry(row, textvariable=var, width=160, height=34).pack(side="left")
        self._opt_widgets[key] = var

    def _run(self):
        in_dir  = self._in_dir_var.get()
        out_dir = self._out_dir_var.get()
        op      = self._op.get()
        if not in_dir or not out_dir:
            return messagebox.showwarning("Batch", "Set input and output folders.")
        files = [str(p) for p in Path(in_dir).glob("*.pdf")]
        if not files:
            return messagebox.showwarning("Batch", "No PDF files found in input folder.")
        opts = {k: v.get() for k, v in self._opt_widgets.items()}
        # Coerce numeric opts
        for k in ("size", "dpi"):
            if k in opts:
                try: opts[k] = int(opts[k])
                except: pass
        for k in ("opacity",):
            if k in opts:
                try: opts[k] = float(opts[k])
                except: pass
        fn, _ = _OPS[op]
        app   = self.app
        lb    = self._lb
        lb.delete(0, "end")

        def work(stop):
            ok = err = 0
            for i, src in enumerate(files):
                if stop.is_set():
                    break
                name = Path(src).name
                app.after(0, lambda n=name: lb.insert("end", f"⏳  {n}"))
                app.after(0, lambda v=(i+1)/len(files): app._prog_update(v))
                try:
                    result = fn(src, out_dir, opts, stop)
                    if result:
                        ok += 1
                        app.after(0, lambda n=name: (
                            lb.delete("end"),
                            lb.insert("end", f"✓  {n}")))
                    else:
                        app.after(0, lambda n=name: (
                            lb.delete("end"),
                            lb.insert("end", f"—  {n}  (cancelled)")))
                except Exception as e:
                    err += 1
                    app.after(0, lambda n=name, ex=e: (
                        lb.delete("end"),
                        lb.insert("end", f"✗  {n}  — {ex}")))
            app.after(0, lambda: app._set_status(
                f"✓  Batch done — {ok} OK, {err} errors", SUCCESS if not err else WARN))

        app._set_status(f"Batch {op} on {len(files)} file(s)…")
        app.run_job(work, f"Batch {op} · {len(files)} file(s)…")
