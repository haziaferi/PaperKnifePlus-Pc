from __future__ import annotations
import tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path
from PIL import Image
import customtkinter as ctk
import fitz
from ..tool_base import ToolBase, register
from ..theme import ACCENT, ACCENT_H, CARD, TEXT, MUTED, SUCCESS, CANVAS_BG, _tk_color
from ..recent import RECENT


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
class FindReplaceTool(ToolBase):
    section = "CONTENT"
    label   = "🔍  Find & Replace"

    _doc:      fitz.Document | None = None
    _pg:       int = 0
    _zoom:     float = 1.5
    _hits:     list  = []   # list of (page_num, [rect per line of the match])
    _hit_idx:  int   = -1

    def show(self):
        app  = self.app
        body = self._card("🔍  Find & Replace",
                          "Search PDF text and replace across all pages · Ctrl+S to save")
        # ── file row ──────────────────────────────────────────────────────────
        self._path_var = tk.StringVar()
        top = ctk.CTkFrame(body, fg_color="transparent")
        top.pack(fill="x", padx=24, pady=8)
        ctk.CTkEntry(top, textvariable=self._path_var, state="readonly",
                     placeholder_text="Open a PDF…", height=44
                     ).pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(top, text="Open PDF", width=136, height=44,
                      command=self._open).pack(side="left")

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
        # Leaving the tool destroys the view; close the document so the file is not left locked.
        self._canvas.bind("<Destroy>", lambda e: self._close_doc())
        self._canvas.bind("<MouseWheel>",
                          lambda e: self._canvas.yview_scroll(
                              -1 * (e.delta // 120), "units"))

        ctk.CTkButton(body, text="  Save PDF  →", height=46,
                      command=self._save,
                      fg_color=ACCENT, hover_color=ACCENT_H,
                      font=ctk.CTkFont(size=15, weight="bold")
                      ).pack(fill="x", padx=24, pady=8)

        app._cur_open_fn = self._open
        app._cur_save_fn = self._save
        app._cur_undo_fn = self._undo
        self._doc  = None
        self._hits = []
        self._pg   = 0
        self._undo_stack: list = []

    # ── file ──────────────────────────────────────────────────────────────────
    def _close_doc(self):
        if self._doc:
            self._doc.close()
            self._doc = None

    def _open(self):
        f = filedialog.askopenfilename(filetypes=[("PDF", "*.pdf")])
        if not f:
            return
        self._close_doc()
        self._doc = self.app._open_pdf_safe(f)
        if not self._doc:
            return
        self._doc.journal_enable()
        self._undo_stack = []
        self._path_var.set(f)
        self._pg = 0
        self._hits = []
        RECENT.push(f, len(self._doc))
        self._render()

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
            self._replace(found, repl, font)
            self._undo_stack.append(self._pg)
        self._hits = []
        self._hit_idx = -1
        self._hit_lbl.configure(text=f"Replaced {count} occurrence(s)")
        self.app._set_status(
            f"✓  Replaced {count} occurrence(s) · Save to write to disk", SUCCESS)
        self._render()

    def _replace(self, found: list, repl: str, font):
        self._doc.journal_start_op("Replace all")
        try:
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
                    c = m["span"]["color"]
                    rgb = ((c >> 16) / 255, ((c >> 8) & 0xFF) / 255, (c & 0xFF) / 255)
                    tw = fitz.TextWriter(page.rect, color=rgb)
                    tw.append(m["origin"], repl, font=font, fontsize=m["span"]["size"])
                    tw.write_text(page)
        finally:
            self._doc.journal_stop_op()

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
        from PIL import ImageTk as _ITK
        self._raw_img = _ITK.PhotoImage(img)
        c.create_image(0, 0, anchor="nw", image=self._raw_img)
        c.configure(scrollregion=(0, 0, pix.width, pix.height))
        # Draw hit highlights on current page; hit rects are unrotated page space.
        to_screen = page.rotation_matrix * mat
        for hi, (pg_num, rects) in enumerate(self._hits):
            if pg_num != self._pg:
                continue
            is_cur = hi == self._hit_idx
            fill   = "#FFD700" if is_cur else "#FFFACD"
            for rect in rects:
                x0, y0, x1, y1 = rect * to_screen
                c.create_rectangle(x0, y0, x1, y1,
                                   fill=fill, outline=_tk_color(ACCENT) if is_cur else "#CCC",
                                   stipple="gray50" if not is_cur else "",
                                   width=2)

    # ── undo ──────────────────────────────────────────────────────────────────
    def _undo(self):
        if not self._undo_stack or not self._doc:
            return
        self._pg = self._undo_stack.pop()
        self._doc.journal_undo()
        self._hits = []
        self._hit_idx = -1
        self._hit_lbl.configure(text="Replace undone")
        self._render()

    # ── save ──────────────────────────────────────────────────────────────────
    def _save(self):
        if not self._doc:
            return messagebox.showwarning("Save", "Open a PDF first.")
        out = self.app._save_as("replaced.pdf")
        if not out:
            return
        try:
            self._doc.save(out, deflate=True)
            self.app._set_status(f"✓  Saved → {Path(out).name}", SUCCESS)
            messagebox.showinfo("Saved", f"PDF saved:\n{out}")
        except Exception as e:
            messagebox.showerror("Save Error", str(e))
