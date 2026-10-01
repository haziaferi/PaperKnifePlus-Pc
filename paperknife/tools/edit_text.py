from __future__ import annotations
import tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path
from PIL import Image, ImageTk
import customtkinter as ctk
import pymupdf as fitz
from ..tool_base import ToolBase, register
from ..theme import ACCENT, ACCENT_H, CARD, TEXT, MUTED, SUCCESS, WARN, CANVAS_BG, _tk_color
from ..pages import render, textwriter_point


def _block_font(name: str) -> tuple[fitz.Font, bool]:
    """(font, True) for a font MuPDF has built in, else (Helvetica, False)."""
    try:
        return fitz.Font(name), True
    except fitz.mupdf.FzErrorBase:
        return fitz.Font("helv"), False


@register
class EditTextTool(ToolBase):
    section = "CONTENT"
    label   = "✏️   Edit Text"

    _doc:      fitz.Document | None = None
    _pg:       int = 0
    _zoom:     float = 1.5
    _sel_bi:   int | None = None
    _canvas:   tk.Canvas | None = None
    _edit_box: ctk.CTkTextbox | None = None

    def show(self):
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
        self._canvas = tk.Canvas(cf, bg=_tk_color(CANVAS_BG), highlightthickness=0,
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
        # Multi-line: a block keeps its line breaks while it is edited.
        self._edit_box = ctk.CTkTextbox(er, height=90, wrap="word",
                                         font=ctk.CTkFont(size=14))
        self._edit_box.configure(state="disabled")
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

        self._undo_stack: list = []   # (page, document bytes) before each edit
        self._blocks: list = []
        self._doc = None
        self._pg = 0

    # ── file / page navigation ────────────────────────────────────────────────
    def _open(self):
        f = filedialog.askopenfilename(filetypes=[("PDF", "*.pdf")])
        if not f:
            return
        self._close_doc()
        self._doc = self.app._open_pdf_safe(f)
        if not self._doc:
            return
        self._undo_stack = []
        self._path_var.set(f)
        self._pg = 0
        self._render()

    def _nav(self, d):
        if not self._doc:
            return
        new = self._pg + d
        if 0 <= new < len(self._doc):
            self._pg = new
            self._sel_bi = None
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
        pix  = render(page, self._zoom, shrink=True)
        img  = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        self._raw_img = ImageTk.PhotoImage(img)
        c.create_image(0, 0, anchor="nw", image=self._raw_img)
        c.configure(scrollregion=(0, 0, pix.width, pix.height))

        self._blocks = []
        # "dict" spans carry their 'text'; "rawdict" spans only have per-char entries.
        raw = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)
        # Text bboxes are unrotated; the pixmap shows the page rotated.
        to_screen = page.rotation_matrix * fitz.Matrix(self._zoom, self._zoom)
        for bi, block in enumerate(raw.get("blocks", [])):
            if block.get("type") != 0:
                continue
            bx0, by0, bx1, by1 = fitz.Rect(block["bbox"]) * to_screen
            rid = c.create_rectangle(
                bx0, by0, bx1, by1,
                outline=_tk_color(ACCENT) if bi == self._sel_bi else "",
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
        for item in self._blocks:
            self._canvas.itemconfigure(
                item["rid"],
                outline=_tk_color(ACCENT) if item["bi"] == bi else "")
        # Keep the block's line breaks so multi-line content can be edited as such.
        block = next((it["block"] for it in self._blocks if it["bi"] == bi), None)
        if not block:
            return
        lines_text = []
        for line in block.get("lines", []):
            # Spans are consecutive runs of one line; their text already holds the spaces.
            lines_text.append("".join(s["text"] for s in line.get("spans", [])))
        self._edit_box.configure(state="normal")
        self._edit_box.delete("1.0", "end")
        self._edit_box.insert("1.0", "\n".join(lines_text))
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
    def _word_wrap(text: str, font: fitz.Font, font_size: float,
                   max_width: float) -> list:
        """Lines of *text* that fit within *max_width* points; a newline in
        *text* is a hard break."""
        result = []
        for paragraph in text.split("\n"):
            words = paragraph.split()
            if not words:
                result.append("")
                continue
            current = ""
            for word in words:
                candidate = f"{current} {word}".lstrip() if current else word
                if font.text_length(candidate, fontsize=font_size) <= max_width:
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
        new_tx = self._edit_box.get("1.0", "end-1c")

        self._push_undo()
        try:
            own_font = self._write_block(self._doc[self._pg], block, new_tx)
        except Exception as e:
            # The original text may already be redacted away; put it back.
            self._pop_undo()
            self._render()
            return messagebox.showerror("Edit Text", f"The edit could not be applied:\n{e}")

        self._sel_bi = None
        self._edit_box.delete("1.0", "end")
        self._edit_box.configure(state="disabled")
        self._apply_btn.configure(state="disabled")
        if own_font:
            self.app._set_status("Edit applied — use Save to write to disk", SUCCESS)
        else:
            self.app._set_status(
                f"Edit applied in Helvetica: the block's font "
                f"'{self._block_style(block)[0]}' is not built in — use Save to write to disk",
                WARN)
        self._render()

    def _write_block(self, page, block: dict, new_tx: str) -> bool:
        """Replace *block*'s text with *new_tx*.  Returns False when the
        block's font is not built in and Helvetica was used instead."""
        bx0, by0, bx1, _ = block["bbox"]
        block_width = bx1 - bx0

        font_name, font_size, rgb = self._block_style(block)
        font, own_font = _block_font(font_name)

        # Derive line height from original spacing; fall back to 1.2× size.
        lines_raw = block.get("lines", [])
        if len(lines_raw) >= 2:
            tops = [ln["bbox"][1] for ln in lines_raw]
            line_height = sum(tops[i+1] - tops[i]
                              for i in range(len(tops) - 1)) / (len(tops) - 1)
        else:
            line_height = font_size * 1.2

        for line in lines_raw:
            for span in line.get("spans", []):
                page.add_redact_annot(fitz.Rect(span["bbox"]))
        # Defaults would also blank image pixels and line art under each span box.
        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE,
                              graphics=fitz.PDF_REDACT_LINE_ART_NONE)

        wrapped = self._word_wrap(new_tx, font, font_size, block_width)

        tw = fitz.TextWriter(page.rect)
        # by0 is the top of the first line; add font_size to get the baseline.
        baseline_y = by0 + font_size
        for i, wline in enumerate(wrapped):
            if wline:
                tw.append(textwriter_point(page, (bx0, baseline_y + i * line_height)),
                          wline, font=font, fontsize=font_size)

        tw.write_text(page, color=rgb)
        return own_font

    def _undo(self):
        if not self._undo_stack or not self._doc:
            return
        self._pop_undo()
        self._sel_bi = None
        self._render()
        self.app._set_status("Undo applied", SUCCESS)

    def _save(self):
        if not self._doc:
            return messagebox.showwarning("Save", "Open a PDF first.")
        out = self.app._save_as("edited.pdf")
        if not out:
            return
        try:
            self._save_doc(out, deflate=True)
            self.app._set_status(f"✓  Saved → {Path(out).name}", SUCCESS)
            messagebox.showinfo("Saved", f"Edited PDF saved:\n{out}")
        except Exception as e:
            messagebox.showerror("Save Error", str(e))
