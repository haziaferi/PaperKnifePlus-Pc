"""PageCanvasTool: the page viewer shared by Annotate, Edit Text, Find & Replace
and Redact (RS-07, RS-22, L3-51).

It owns the open document, the current page and zoom, the canvas with its
scrollbars, rendering, and the one mapping between page and screen.  A tool
builds its own controls with the _viewer_* helpers, then fills three hooks:

    _on_open()      a new document is open: forget per-document state
    _on_page()      the page changed: forget per-page state (selections)
    _draw_overlay(page)  draw the tool's marks after the page image

Page space is the unrotated page; the canvas shows the page rotated and zoomed.
"""
from __future__ import annotations
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk
import pymupdf as fitz
from PIL import Image, ImageTk

from .pages import render
from .theme import CANVAS_BG, SUCCESS, TEXT, _tk_color
from .tool_base import ToolBase
from .core.text import span_rgb  # noqa: F401  (tools import it from here)


class PageCanvasTool(ToolBase):
    _doc: fitz.Document | None = None
    _pg: int = 0
    _zoom: float = 1.5
    _canvas: tk.Canvas | None = None
    _pg_lbl = None

    save_name = "document.pdf"      # suggested by the Save dialog
    saved_what = "PDF"              # "<saved_what> saved:" after saving

    # ── building the view ─────────────────────────────────────────────────────
    def _viewer_file_row(self, parent, *, pady=(8, 4), height=40, button_width=128,
                         page_buttons=True):
        """Path entry and Open button, with ◀ page ▶ unless page_buttons is False."""
        self._path_var = tk.StringVar()
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=24, pady=pady)
        ctk.CTkEntry(row, textvariable=self._path_var, state="readonly",
                     placeholder_text="Open a PDF…", height=height
                     ).pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(row, text="Open PDF", width=button_width, height=height,
                      command=self._open).pack(side="left", padx=4 if page_buttons else 0)
        self._pg_lbl = None
        if page_buttons:
            ctk.CTkButton(row, text="◀", width=40, height=height,
                          command=lambda: self._nav(-1)).pack(side="left", padx=2)
            self._pg_lbl = ctk.CTkLabel(row, text="—", width=60, text_color=TEXT)
            self._pg_lbl.pack(side="left", padx=2)
            ctk.CTkButton(row, text="▶", width=40, height=height,
                          command=lambda: self._nav(1)).pack(side="left", padx=2)
        return row

    def _viewer_zoom(self, parent, **slider_opts):
        """The zoom slider (0.5x-3x, starting at the tool's zoom); packing is the caller's."""
        self._zoom_sl = ctk.CTkSlider(parent, from_=0.5, to=3.0, number_of_steps=50,
                                      **slider_opts)
        self._zoom_sl.set(self._zoom)
        self._zoom_sl.configure(command=self._on_zoom)
        return self._zoom_sl

    def _viewer_canvas(self, parent, *, frame_color, cursor=""):
        """The scrollable canvas the page is drawn on."""
        frame = ctk.CTkFrame(parent, fg_color=frame_color, corner_radius=8)
        frame.pack(fill="both", expand=True, padx=24, pady=4)
        vbar = tk.Scrollbar(frame, orient="vertical")
        vbar.pack(side="right", fill="y")
        hbar = tk.Scrollbar(frame, orient="horizontal")
        hbar.pack(side="bottom", fill="x")
        c = tk.Canvas(frame, bg=_tk_color(CANVAS_BG), highlightthickness=0, cursor=cursor,
                      yscrollcommand=vbar.set, xscrollcommand=hbar.set)
        c.pack(fill="both", expand=True)
        vbar.configure(command=c.yview)
        hbar.configure(command=c.xview)
        c.bind("<MouseWheel>", lambda e: c.yview_scroll(-1 * (e.delta // 120), "units"))
        self._canvas = c
        return c

    def _viewer_reset(self):
        """Called at the end of show(): no document yet."""
        self._doc = None
        self._pg = 0
        self._undo_stack = []
        self._on_open()

    # ── hooks ─────────────────────────────────────────────────────────────────
    def _on_open(self) -> None:
        pass

    def _on_page(self) -> None:
        pass

    def _draw_overlay(self, page: fitz.Page) -> None:
        pass

    # ── document and page ─────────────────────────────────────────────────────
    def _open(self):
        f = filedialog.askopenfilename(filetypes=[("PDF", "*.pdf")])
        if not f:
            return
        self._close_doc()
        self._doc = self.app._open_pdf_safe(f)
        self._pg = 0
        self._undo_stack = []
        self._on_open()
        if not self._doc:
            return
        self._path_var.set(f)
        self._render()

    def _nav(self, d):
        if not self._doc:
            return
        new = self._pg + d
        if 0 <= new < len(self._doc):
            self._pg = new
            self._on_page()
            self._render()

    def _on_zoom(self, v):
        self._zoom = float(v)
        self._render()

    # ── page <-> screen ───────────────────────────────────────────────────────
    def _screen_matrix(self, page: fitz.Page | None = None) -> fitz.Matrix:
        """Page space -> canvas: rotate as the page is shown, then zoom."""
        page = page if page is not None else self._doc[self._pg]
        return page.rotation_matrix * fitz.Matrix(self._zoom, self._zoom)

    def _page_to_screen(self, rect, page: fitz.Page | None = None) -> fitz.Rect:
        return fitz.Rect(rect) * self._screen_matrix(page)

    def _screen_to_page(self, point, page: fitz.Page | None = None) -> fitz.Point:
        return fitz.Point(point) * ~self._screen_matrix(page)

    def _screen_rect_to_page(self, x0, y0, x1, y1) -> fitz.Rect:
        return fitz.Rect(self._screen_to_page((x0, y0)),
                         self._screen_to_page((x1, y1))).normalize()

    def _event_point(self, event) -> tuple[float, float]:
        """Canvas coordinates of a mouse event, scrolling included."""
        return self._canvas.canvasx(event.x), self._canvas.canvasy(event.y)

    # ── drawing ───────────────────────────────────────────────────────────────
    def _render(self):
        if not self._doc:
            return
        c = self._canvas
        c.delete("all")
        page = self._doc[self._pg]
        pix = render(page, self._zoom, shrink=True)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        self._raw_img = ImageTk.PhotoImage(img)
        c.create_image(0, 0, anchor="nw", image=self._raw_img)
        c.configure(scrollregion=(0, 0, pix.width, pix.height))
        self._draw_overlay(page)
        if self._pg_lbl is not None:
            self._pg_lbl.configure(text=f"{self._pg + 1} / {len(self._doc)}")

    # ── saving ────────────────────────────────────────────────────────────────
    def _save(self):
        if not self._doc:
            return messagebox.showwarning("Save", "Open a PDF first.")
        out = self.app._save_as(self.save_name)
        if not out:
            return

        def done(_):
            self.app._set_status(f"✓  Saved → {Path(out).name}", SUCCESS)
            messagebox.showinfo("Saved", f"{self.saved_what} saved:\n{out}")
        self._run_on_doc(lambda stop: self._save_doc(out, deflate=True),
                         f"Saving {Path(out).name}…", done)

    def _after_job(self, kind):
        # A save over the open file goes on from an in-memory copy of it.
        self._render()
