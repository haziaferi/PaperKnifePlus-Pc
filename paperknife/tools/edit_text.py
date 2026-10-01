from __future__ import annotations
import tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path
from PIL import Image
import customtkinter as ctk
import fitz
from ..tool_base import ToolBase, register
from ..theme import ACCENT, ACCENT_H, CARD, CARD2, TEXT, MUTED, DANGER, DANGER_H, SUCCESS, WARN, CANVAS_BG
from ..recent import RECENT


@register
class EditTextTool(ToolBase):
    section = "CONTENT"
    label   = "✏️   Edit Text"

    # ── Instance state ────────────────────────────────────────────────────────
    _doc:      fitz.Document | None = None
    _pg:       int = 0
    _zoom:     float = 1.5
    _blocks:   list = []
    _sel_bi:   int | None = None
    _sel_span: int | None = None
    _tk_img:   ImageTk.PhotoImage | None = None
    _canvas:   tk.Canvas | None = None
    _edit_box: ctk.CTkEntry | None = None
    _edit_var: tk.StringVar | None = None

    def show(self):
        import tkinter.font as tkfont
        from tkinter import PhotoImage
        app  = self.app
        body = self._card("✏️  Edit Text",
                          "Click any text block to select it · edit the span · Ctrl+S to save")
        # ── toolbar ───────────────────────────────────────────────────────────
        tb = ctk.CTkFrame(body, fg_color="transparent")
        tb.pack(fill="x", padx=24, pady=(8, 4))
        self._path_var = tk.StringVar()
        ctk.CTkEntry(tb, textvariable=self._path_var, state="readonly",
                     placeholder_text="Open a PDF…", height=40
                     ).pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(tb, text="Open PDF", width=128, height=40,
                      command=self._open).pack(side="left", padx=4)
        ctk.CTkButton(tb, text="◀", width=40, height=40,
                      command=lambda: self._nav(-1)).pack(side="left", padx=2)
        self._pg_lbl = ctk.CTkLabel(tb, text="—", width=60, text_color=TEXT)
        self._pg_lbl.pack(side="left", padx=2)
        ctk.CTkButton(tb, text="▶", width=40, height=40,
                      command=lambda: self._nav(1)).pack(side="left", padx=2)

        zoom_row = ctk.CTkFrame(body, fg_color="transparent")
        zoom_row.pack(fill="x", padx=24, pady=(0, 4))
        ctk.CTkLabel(zoom_row, text="Zoom:", text_color=MUTED,
                     font=ctk.CTkFont(size=12)).pack(side="left")
        self._zoom_sl = ctk.CTkSlider(zoom_row, from_=0.5, to=3.0, number_of_steps=50)
        self._zoom_sl.set(1.5)
        self._zoom_sl.configure(command=self._on_zoom)
        self._zoom_sl.pack(side="left", fill="x", expand=True, padx=8)

        # ── canvas ────────────────────────────────────────────────────────────
        cf = ctk.CTkFrame(body, fg_color=CARD, corner_radius=8)
        cf.pack(fill="both", expand=True, padx=24, pady=4)
        vbar = tk.Scrollbar(cf, orient="vertical")
        vbar.pack(side="right", fill="y")
        hbar = tk.Scrollbar(cf, orient="horizontal")
        hbar.pack(side="bottom", fill="x")
        self._canvas = tk.Canvas(cf, bg=CANVAS_BG, highlightthickness=0,
                                  yscrollcommand=vbar.set, xscrollcommand=hbar.set)
        self._canvas.pack(fill="both", expand=True)
        vbar.configure(command=self._canvas.yview)
        hbar.configure(command=self._canvas.xview)
        self._canvas.bind("<Button-1>", self._on_click)
        self._canvas.bind("<MouseWheel>",
                          lambda e: self._canvas.yview_scroll(-1 * (e.delta // 120), "units"))

        # ── edit row ──────────────────────────────────────────────────────────
        er = ctk.CTkFrame(body, fg_color="transparent")
        er.pack(fill="x", padx=24, pady=4)
        self._edit_var = tk.StringVar()
        self._edit_box = ctk.CTkEntry(er, textvariable=self._edit_var,
                                       state="disabled", height=40,
                                       placeholder_text="Select a text block to edit…",
                                       font=ctk.CTkFont(size=14))
        self._edit_box.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self._apply_btn = ctk.CTkButton(
            er, text="Apply Edit", width=120, height=40,
            state="disabled", command=self._apply_edit)
        self._apply_btn.pack(side="left")

        ctk.CTkButton(body, text="  Save PDF  →", height=46,
                      command=self._save,
                      fg_color=ACCENT, hover_color=ACCENT_H,
                      font=ctk.CTkFont(size=15, weight="bold")
                      ).pack(fill="x", padx=24, pady=8)

        app._cur_open_fn = self._open
        app._cur_save_fn = self._save
        app._cur_undo_fn = self._undo

        self._undo_stack: list = []
        self._doc = None
        self._pg = 0

    # ── file / page navigation ────────────────────────────────────────────────
    def _open(self):
        f = filedialog.askopenfilename(filetypes=[("PDF", "*.pdf")])
        if not f:
            return
        if self._doc:
            self._doc.close()
        self._doc = self.app._open_pdf_safe(f)
        if not self._doc:
            return
        self._path_var.set(f)
        self._pg = 0
        RECENT.push(f, len(self._doc))
        self._render()

    def _nav(self, d):
        if not self._doc:
            return
        new = self._pg + d
        if 0 <= new < len(self._doc):
            self._pg = new
            self._sel_bi   = None
            self._sel_span = None
            self._render()

    def _on_zoom(self, v):
        self._zoom = float(v)
        self._render()

    # ── render ────────────────────────────────────────────────────────────────
    def _render(self):
        if not self._doc:
            return
        c = self._canvas
        c.delete("all")
        page = self._doc[self._pg]
        mat  = fitz.Matrix(self._zoom, self._zoom)
        pix  = page.get_pixmap(matrix=mat, alpha=False)
        img  = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        self._tk_img = ctk.CTkImage(img, size=(pix.width, pix.height))
        # Use raw PhotoImage for canvas (CTkImage doesn't work directly on canvas)
        from PIL import ImageTk as _ITK
        self._raw_img = _ITK.PhotoImage(img)
        c.create_image(0, 0, anchor="nw", image=self._raw_img)
        c.configure(scrollregion=(0, 0, pix.width, pix.height))

        # Collect & draw block overlays
        self._blocks = []
        raw = page.get_text("rawdict", flags=fitz.TEXT_PRESERVE_WHITESPACE)
        z = self._zoom
        for bi, block in enumerate(raw.get("blocks", [])):
            if block.get("type") != 0:
                continue
            bx0, by0, bx1, by1 = [v * z for v in block["bbox"]]
            outline = ACCENT if bi == self._sel_bi else ""
            rid = c.create_rectangle(
                bx0, by0, bx1, by1,
                outline=outline if outline else "transparent",
                fill="", width=2)
            self._blocks.append({
                "bi": bi, "block": block, "rid": rid,
                "bbox": (bx0, by0, bx1, by1),
            })
        self._pg_lbl.configure(text=f"{self._pg + 1} / {len(self._doc)}")

    def _on_click(self, event):
        cx = self._canvas.canvasx(event.x)
        cy = self._canvas.canvasy(event.y)
        for item in self._blocks:
            x0, y0, x1, y1 = item["bbox"]
            if x0 <= cx <= x1 and y0 <= cy <= y1:
                self._select_block(item["bi"])
                return

    def _select_block(self, bi):
        self._sel_bi = bi
        # Redraw outlines
        for item in self._blocks:
            self._canvas.itemconfigure(
                item["rid"],
                outline=ACCENT if item["bi"] == bi else "")
        # Build the full text of the block — preserve original line breaks
        # so the user can see and edit multi-line content explicitly.
        block = next((it["block"] for it in self._blocks if it["bi"] == bi), None)
        if not block:
            return
        lines_text = []
        for line in block.get("lines", []):
            line_str = " ".join(s.get("text", "") for s in line.get("spans", []))
            lines_text.append(line_str)
        self._edit_var.set("\n".join(lines_text))
        self._edit_box.configure(state="normal")
        self._apply_btn.configure(state="normal")
        self._edit_box.focus_set()

    # ── style / layout helpers ────────────────────────────────────────────────

    @staticmethod
    def _block_style(block: dict) -> tuple:
        """Return (font_name, font_size, rgb) from the first span of the block."""
        try:
            span  = block["lines"][0]["spans"][0]
            size  = span.get("size", 11)
            c     = span.get("color", 0)
            font  = span.get("font", "helv")
            rgb   = ((c >> 16) / 255, ((c >> 8) & 0xFF) / 255, (c & 0xFF) / 255)
            return font, size, rgb
        except (IndexError, KeyError):
            return "helv", 11, (0, 0, 0)

    @staticmethod
    def _text_width(text: str, font_name: str, font_size: float) -> float:
        """Measure text width in points using PyMuPDF font metrics."""
        try:
            return fitz.Font(font_name).text_length(text, fontsize=font_size)
        except Exception:
            return len(text) * font_size * 0.6   # safe fallback

    @staticmethod
    def _word_wrap(text: str, font_name: str, font_size: float,
                   max_width: float) -> list:
        """
        Break *text* into lines that fit within *max_width* points.
        Explicit \\n in the input are treated as hard line breaks.
        Returns a list of strings, one per output line.
        """
        result = []
        for paragraph in text.split("\n"):
            words = paragraph.split()
            if not words:
                result.append("")
                continue
            current = ""
            for word in words:
                candidate = f"{current} {word}".lstrip() if current else word
                if EditTextTool._text_width(candidate, font_name, font_size) <= max_width:
                    current = candidate
                else:
                    if current:
                        result.append(current)
                    current = word   # single overlong word goes on its own line
            if current:
                result.append(current)
        return result or [""]

    def _apply_edit(self):
        if self._sel_bi is None or not self._doc:
            return
        block = next((it["block"] for it in self._blocks if it["bi"] == self._sel_bi), None)
        if not block:
            return

        page   = self._doc[self._pg]
        new_tx = self._edit_var.get()

        # Snapshot for undo
        self._undo_stack.append((self._pg, page.read_contents()))

        # ── Block geometry (all in PDF points, no zoom) ───────────────────────
        bx0, by0, bx1, by1 = block["bbox"]
        block_width = bx1 - bx0

        font_name, font_size, rgb = self._block_style(block)

        # Derive line height from original spacing; fall back to 1.2× size.
        lines_raw = block.get("lines", [])
        if len(lines_raw) >= 2:
            tops = [ln["bbox"][1] for ln in lines_raw]
            line_height = sum(tops[i+1] - tops[i]
                              for i in range(len(tops) - 1)) / (len(tops) - 1)
        else:
            line_height = font_size * 1.2

        # ── Redact all original spans ─────────────────────────────────────────
        for line in lines_raw:
            for span in line.get("spans", []):
                page.add_redact_annot(fitz.Rect(span["bbox"]))
        page.apply_redactions()

        # ── Word-wrap the new text to fit the block width ─────────────────────
        wrapped = self._word_wrap(new_tx, font_name, font_size, block_width)

        # ── Re-insert with TextWriter for precise baseline control ────────────
        tw = fitz.TextWriter(page.rect)
        try:
            f = fitz.Font(font_name)
        except Exception:
            f = fitz.Font("helv")

        # by0 is the top of the first line; add font_size to get the baseline.
        baseline_y = by0 + font_size
        for i, wline in enumerate(wrapped):
            if wline:
                tw.append(fitz.Point(bx0, baseline_y + i * line_height),
                          wline, font=f, fontsize=font_size)

        tw.write_text(page, color=rgb)

        self._sel_bi = None
        self._edit_box.configure(state="disabled")
        self._apply_btn.configure(state="disabled")
        self.app._set_status("Edit applied — use Save to write to disk", SUCCESS)
        self._render()

    def _undo(self):
        if not self._undo_stack or not self._doc:
            return
        pg_num, contents = self._undo_stack.pop()
        page = self._doc[pg_num]
        # Restore the saved content stream via the low-level xref API
        xref = page.get_contents()
        if xref:
            self._doc.update_stream(xref[0], contents)
        else:
            xref = self._doc.get_new_xref()
            self._doc.update_stream(xref, contents)
            page.set_contents(xref)
        self._render()
        self.app._set_status("Undo applied", SUCCESS)

    def _save(self):
        if not self._doc:
            return messagebox.showwarning("Save", "Open a PDF first.")
        out = self.app._save_as("edited.pdf")
        if not out:
            return
        try:
            self._doc.save(out, deflate=True)
            self.app._set_status(f"✓  Saved → {Path(out).name}", SUCCESS)
            messagebox.showinfo("Saved", f"Edited PDF saved:\n{out}")
        except Exception as e:
            messagebox.showerror("Save Error", str(e))
