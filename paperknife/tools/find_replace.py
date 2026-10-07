from __future__ import annotations
import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk
import pymupdf as fitz
from ..page_canvas import PageCanvasTool, span_rgb
from ..tool_base import register
from ..theme import ACCENT, ACCENT_H, CARD, TEXT, MUTED, SUCCESS, HIT, HIT_CUR, HIT_EDGE, _tk_color
from ..pages import textwriter_point


def _find_matches(page, needle: str) -> list[dict]:
    """Case-sensitive matches of *needle* in the page text.

    Each match is {"rects": one rect per text line it covers, "origin": baseline
    point of its first character, "span": the span that character belongs to}.
    page.search_for is case-insensitive and returns a wrapped match as several
    unrelated rects, so the page characters are searched directly.
    """
    chars = []   # (c, bbox | None, origin, span, line_no); bbox None = line break
    raw = page.get_text("rawdict", flags=fitz.TEXT_PRESERVE_WHITESPACE | fitz.TEXT_MEDIABOX_CLIP)
    line_no = 0
    for block in raw.get("blocks", []):
        for line in block.get("lines", []):
            if chars and not chars[-1][0].isspace():
                chars.append((" ", None, None, None, line_no))
            for span in line["spans"]:
                for ch in span["chars"]:
                    chars.append((ch["c"], fitz.Rect(ch["bbox"]), ch["origin"], span, line_no))
            line_no += 1
    text = "".join(c[0] for c in chars)
    matches = []
    i = text.find(needle)
    while i >= 0 and needle:
        part = [c for c in chars[i:i + len(needle)] if c[1] is not None]
        by_line: dict[int, fitz.Rect] = {}
        for _, bbox, _, _, ln in part:
            by_line[ln] = by_line[ln] | bbox if ln in by_line else fitz.Rect(bbox)
        matches.append({"rects": list(by_line.values()),
                        "origin": fitz.Point(part[0][2]), "span": part[0][3]})
        i = text.find(needle, i + len(needle))
    return matches


def _unicode_font(text: str):
    """A built-in font with a glyph for every character of *text*, or None."""
    for name in ("helv", "cjk"):
        font = fitz.Font(name)
        if all(font.has_glyph(ord(c)) for c in text if not c.isspace()):
            return font
    return None


@register
class FindReplaceTool(PageCanvasTool):
    section = "CONTENT"
    label   = "🔍  Find & Replace"
    save_name  = "replaced.pdf"
    saved_what = "PDF"

    _hit_idx:  int   = -1

    def show(self):
        app  = self.app
        body = self._card("🔍  Find & Replace",
                          "Search PDF text and replace across all pages · Ctrl+S to save")
        # Pages are reached through the hits, so there are no page buttons.
        self._viewer_file_row(body, pady=8, height=44, button_width=136, page_buttons=False)

        # ── search / replace ──────────────────────────────────────────────────
        sr_card = ctk.CTkFrame(body, fg_color=CARD, corner_radius=8)
        sr_card.pack(fill="x", padx=24, pady=8)
        r1 = ctk.CTkFrame(sr_card, fg_color="transparent")
        r1.pack(fill="x", padx=16, pady=(14, 4))
        ctk.CTkLabel(r1, text="Find:", width=90, text_color=TEXT,
                     anchor="w").pack(side="left")
        self._find_var = tk.StringVar()
        self._find_ent = ctk.CTkEntry(r1, textvariable=self._find_var,
                                       height=40, placeholder_text="Search text…")
        self._find_ent.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(r1, text="Find All", width=90, height=40,
                      command=self._find_all).pack(side="left")
        r2 = ctk.CTkFrame(sr_card, fg_color="transparent")
        r2.pack(fill="x", padx=16, pady=(4, 14))
        ctk.CTkLabel(r2, text="Replace:", width=90, text_color=TEXT,
                     anchor="w").pack(side="left")
        self._repl_var = tk.StringVar()
        self._repl_ent = ctk.CTkEntry(r2, textvariable=self._repl_var,
                                       height=40, placeholder_text="Replacement text…")
        self._repl_ent.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(r2, text="Replace All", width=110, height=40,
                      fg_color=ACCENT, hover_color=ACCENT_H,
                      command=self._replace_all).pack(side="left")

        # ── hit counter & nav ─────────────────────────────────────────────────
        nav = ctk.CTkFrame(body, fg_color="transparent")
        nav.pack(fill="x", padx=24, pady=4)
        ctk.CTkButton(nav, text="◀ Prev", width=90,
                      command=lambda: self._jump(-1)).pack(side="left", padx=4)
        ctk.CTkButton(nav, text="Next ▶", width=90,
                      command=lambda: self._jump(1)).pack(side="left", padx=4)
        self._hit_lbl = ctk.CTkLabel(nav, text="",
                                      text_color=MUTED, font=ctk.CTkFont(size=13))
        self._hit_lbl.pack(side="left", padx=12)

        self._viewer_canvas(body, frame_color=CARD)

        ctk.CTkButton(body, text="  Save PDF  →", height=46,
                      command=self._save,
                      fg_color=ACCENT, hover_color=ACCENT_H,
                      font=ctk.CTkFont(size=15, weight="bold")
                      ).pack(fill="x", padx=24, pady=8)

        app._cur_open_fn = self._open
        app._cur_save_fn = self._save
        app._cur_undo_fn = self._undo
        # Undo restores the whole document as it was before each Replace All.
        self._viewer_reset()

    def _on_open(self):
        self._hits: list = []   # (page_num, [rect per line of the match])
        self._hit_idx = -1

    # ── search ────────────────────────────────────────────────────────────────
    def _find_all(self):
        if not self._doc:
            return messagebox.showwarning("Find", "Open a PDF first.")
        needle = self._find_var.get().strip()
        if not needle:
            return
        self._hits = []
        for pg_num in range(len(self._doc)):
            for m in _find_matches(self._doc[pg_num], needle):
                self._hits.append((pg_num, m["rects"]))
        if self._hits:
            self._hit_idx = 0
            self._pg      = self._hits[0][0]
            self._hit_lbl.configure(
                text=f"Found {len(self._hits)} hit(s)")
            self._render()
        else:
            self._hit_lbl.configure(text="Not found")
            messagebox.showinfo("Find", f"'{needle}' not found.")

    def _jump(self, d):
        if not self._hits:
            return
        self._hit_idx = (self._hit_idx + d) % len(self._hits)
        self._pg      = self._hits[self._hit_idx][0]
        self._render()
        self._hit_lbl.configure(
            text=f"Hit {self._hit_idx + 1} / {len(self._hits)}")

    # ── replace ───────────────────────────────────────────────────────────────
    def _replace_all(self):
        if not self._doc:
            return messagebox.showwarning("Replace", "Open a PDF first.")
        needle = self._find_var.get().strip()
        repl   = self._repl_var.get()
        if not needle:
            return messagebox.showwarning("Replace", "Enter search text.")
        if not messagebox.askyesno(
                "Confirm Replace",
                f"Replace ALL occurrences of:\n  '{needle}'\nwith:\n  '{repl}'\n\n"
                "This modifies the PDF in memory (save to keep changes)."):
            return
        # insert_text(fontname="helv") encodes Latin-1 only and turns anything else
        # into "·"; an embedded built-in font keeps the characters.
        font = _unicode_font(repl)
        if font is None:
            return messagebox.showerror(
                "Replace", "The replacement contains characters no built-in font can draw.")
        found = [(pg_num, ms) for pg_num in range(len(self._doc))
                 if (ms := _find_matches(self._doc[pg_num], needle))]
        count = sum(len(ms) for _, ms in found)
        if found:
            self._push_undo()
            try:
                self._replace(found, repl, font)
            except Exception as e:
                # Pages already done would keep the text removed; put it all back.
                self._pop_undo()
                self._render()
                return messagebox.showerror("Replace", f"Nothing was replaced:\n{e}")
        self._hits = []
        self._hit_idx = -1
        self._hit_lbl.configure(text=f"Replaced {count} occurrence(s)")
        self.app._set_status(
            f"✓  Replaced {count} occurrence(s) · Save to write to disk", SUCCESS)
        self._render()

    def _replace(self, found: list, repl: str, font):
        for pg_num, matches in found:
            page = self._doc[pg_num]
            for m in matches:
                for r in m["rects"]:
                    page.add_redact_annot(r)
            page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE,
                                  graphics=fitz.PDF_REDACT_LINE_ART_NONE)
            for m in matches:
                if not repl:
                    continue
                tw = fitz.TextWriter(page.rect, color=span_rgb(m["span"]["color"]))
                tw.append(textwriter_point(page, m["origin"]), repl,
                          font=font, fontsize=m["span"]["size"])
                tw.write_text(page)

    # ── render ────────────────────────────────────────────────────────────────
    def _draw_overlay(self, page):
        for hi, (pg_num, rects) in enumerate(self._hits):
            if pg_num != self._pg:
                continue
            is_cur = hi == self._hit_idx
            fill   = HIT_CUR if is_cur else HIT
            for rect in rects:
                x0, y0, x1, y1 = self._page_to_screen(rect, page)
                self._canvas.create_rectangle(
                    x0, y0, x1, y1,
                    fill=fill, outline=_tk_color(ACCENT) if is_cur else HIT_EDGE,
                    stipple="gray50" if not is_cur else "", width=2)

    # ── undo ──────────────────────────────────────────────────────────────────
    def _undo(self):
        if not self._undo_stack or not self._doc:
            return
        self._pop_undo()
        self._hits = []
        self._hit_idx = -1
        self._hit_lbl.configure(text="Replace undone")
        self._render()
