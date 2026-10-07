from __future__ import annotations
from tkinter import messagebox
import customtkinter as ctk
import pymupdf as fitz
from ..page_canvas import PageCanvasTool, span_rgb
from ..tool_base import register
from ..theme import ACCENT, ACCENT_H, CARD, MUTED, SUCCESS, WARN, _tk_color
from ..pages import textwriter_point


def _block_font(name: str) -> tuple[fitz.Font, bool]:
    """(font, True) for a font MuPDF has built in, else (Helvetica, False)."""
    try:
        return fitz.Font(name), True
    except fitz.mupdf.FzErrorBase:
        return fitz.Font("helv"), False


@register
class EditTextTool(PageCanvasTool):
    section = "CONTENT"
    label   = "✏️   Edit Text"
    save_name  = "edited.pdf"
    saved_what = "Edited PDF"

    _sel_bi:   int | None = None
    _edit_box: ctk.CTkTextbox | None = None

    def show(self):
        app  = self.app
        body = self._card("✏️  Edit Text",
                          "Click any text block to select it · edit the span · Ctrl+S to save")
        self._viewer_file_row(body)

        zoom_row = ctk.CTkFrame(body, fg_color="transparent")
        zoom_row.pack(fill="x", padx=24, pady=(0, 4))
        ctk.CTkLabel(zoom_row, text="Zoom:", text_color=MUTED,
                     font=ctk.CTkFont(size=12)).pack(side="left")
        self._viewer_zoom(zoom_row).pack(side="left", fill="x", expand=True, padx=8)

        self._viewer_canvas(body, frame_color=CARD).bind("<Button-1>", self._on_click)

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
        # Undo restores the whole document as it was before each edit (ToolBase).
        self._viewer_reset()

    # A selection belongs to one page of one document: drop it when either changes,
    # or Apply Edit would write it into another file's block.
    def _on_open(self):
        self._blocks = []
        self._clear_selection()

    def _on_page(self):
        self._clear_selection()

    def _clear_selection(self):
        self._sel_bi = None
        if self._edit_box is not None and self._edit_box.winfo_exists():
            self._edit_box.configure(state="normal")
            self._edit_box.delete("1.0", "end")
            self._edit_box.configure(state="disabled")
            self._apply_btn.configure(state="disabled")

    # ── render ────────────────────────────────────────────────────────────────
    def _draw_overlay(self, page):
        self._blocks = []
        # "dict" spans carry their 'text'; "rawdict" spans only have per-char entries.
        raw = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)
        for bi, block in enumerate(raw.get("blocks", [])):
            if block.get("type") != 0:
                continue
            bx0, by0, bx1, by1 = self._page_to_screen(block["bbox"], page)
            rid = self._canvas.create_rectangle(
                bx0, by0, bx1, by1,
                outline=_tk_color(ACCENT) if bi == self._sel_bi else "",
                fill="", width=2)
            self._blocks.append({
                "bi": bi, "block": block, "rid": rid,
                "bbox": (bx0, by0, bx1, by1),
            })

    def _on_click(self, event):
        cx, cy = self._event_point(event)
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
            return font, size, span_rgb(c)
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

        self._clear_selection()
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
        self._clear_selection()
        self._render()
        self.app._set_status("Undo applied", SUCCESS)
