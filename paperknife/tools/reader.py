"""
paperknife.tools.reader
📖  Read / Preview — front-facing, continuous smooth-scroll PDF viewer.

Pages are laid out in one tall scrollable Canvas. Only pages inside the
viewport (+ a small preload margin) are rasterised — page sizes are known
cheaply from page.rect, so the scrollregion is correct before anything is
rendered. Rasterisation runs on a background daemon thread so scrolling
never blocks the Tk event loop; PIL images are handed back to the main
thread via app.after(), where they become PhotoImages and are cached
(bounded, LRU) so re-visiting a page never re-renders it.

View-only: no save action, nothing here mutates the PDF.
"""
from __future__ import annotations
import os
import threading
import queue
from collections import OrderedDict

import tkinter as tk
from tkinter import filedialog
import customtkinter as ctk
from PIL import Image, ImageTk

from ..tool_base import ToolBase, register
from ..theme import TEXT, MUTED, CARD2, WARN, CANVAS_BG, _tk_color
from ..core import reader as core_reader

_PRELOAD   = core_reader.PRELOAD     # extra pages rendered beyond the visible window, each side
_CACHE_MAX = core_reader.CACHE_MAX   # bounded PhotoImage cache (pages currently displayed are exempt)
_GAP       = core_reader.GAP         # px between pages


@register
class ReaderTool(ToolBase):
    section = "READ"
    label   = "📖  Read / Preview"

    _doc  = None
    _path = ""
    _zoom = 1.25

    def show(self):
        app  = self.app
        body = self._card("📖  Read / Preview",
                          "Continuous smooth-scroll viewer — view-only")

        self._path_var = tk.StringVar()
        top = ctk.CTkFrame(body, fg_color="transparent")
        top.pack(fill="x", padx=24, pady=(8, 4))
        ctk.CTkEntry(top, textvariable=self._path_var, state="readonly",
                     placeholder_text="Open a PDF…", height=40
                     ).pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(top, text="Open PDF", width=120, height=40,
                      command=self._open).pack(side="left", padx=4)
        ctk.CTkLabel(top, text="Zoom:", text_color=TEXT,
                     font=ctk.CTkFont(size=12)).pack(side="left", padx=(16, 4))
        self._zoom_slider = ctk.CTkSlider(top, from_=0.5, to=3.0, number_of_steps=50,
                                          width=120, command=self._on_zoom)
        self._zoom_slider.set(self._zoom)
        self._zoom_slider.pack(side="left")
        self._pg_lbl = ctk.CTkLabel(top, text="—", width=80, text_color=MUTED)
        self._pg_lbl.pack(side="left", padx=(12, 0))

        cf = ctk.CTkFrame(body, fg_color=CARD2, corner_radius=8)
        cf.pack(fill="both", expand=True, padx=24, pady=4)
        vbar = tk.Scrollbar(cf, orient="vertical")
        vbar.pack(side="right", fill="y")
        self._canvas = tk.Canvas(cf, bg=_tk_color(CANVAS_BG), highlightthickness=0,
                                  yscrollcommand=vbar.set)
        self._canvas.pack(fill="both", expand=True)
        vbar.configure(command=self._yview)

        self._canvas.bind("<MouseWheel>", lambda e: self._scroll_px(-e.delta * 0.5))   # Win/macOS
        self._canvas.bind("<Button-4>",   lambda e: self._scroll_px(-60))              # Linux
        self._canvas.bind("<Button-5>",   lambda e: self._scroll_px(60))
        self._canvas.bind("<Configure>",  lambda e: self._update_viewport())

        first_run = not hasattr(self, "_worker") or not self._worker.is_alive()
        if first_run:
            self._req_q       = queue.Queue()
            self._cache       = OrderedDict()   # (page_idx, zoom) -> PhotoImage
            self._gen         = 0
            self._inflight    = set()           # (gen, page_idx, zoom) queued, not yet drawn
            self._window      = (0, -1)         # pages wanted now; the worker skips the rest
            self._doc_lock    = None
            self._page_rects  = []
            self._scroll_frac = 0.0
            self._worker_stop = threading.Event()
            self._worker = threading.Thread(target=self._render_worker, daemon=True)
            self._worker.start()

        self._items = {}        # page_idx -> canvas image item (current canvas only)
        self._gen  += 1          # invalidate any renders still in flight for the old canvas
        app._cur_open_fn = self._open

        pending = getattr(app, "_reader_pending_path", None)
        if pending:
            app._reader_pending_path = None
            self.open_path(pending)
        elif self._path and os.path.exists(self._path):
            # Re-entering the tool: reopen the document closed on leaving it
            # and restore the scroll position.
            frac = self._scroll_frac
            self._load(self._path)
            if self._doc:
                self._canvas.yview_moveto(frac)
                app.after(30, self._update_viewport)

    def deactivate(self):
        # Keep the path and scroll position for re-entry, but not the file open.
        if self._doc is not None:
            self._gen += 1
            self._close_off_thread(self._doc, self._doc_lock)
            self._doc = None

    # ── public: other parts of the app can open a file straight into the reader ──
    def open_path(self, path: str):
        self._load(path)

    # ── file ──────────────────────────────────────────────────────────────────
    def _open(self):
        f = filedialog.askopenfilename(filetypes=[("PDF", "*.pdf")])
        if f:
            self.open_path(f)

    def _load(self, path: str):
        doc = self.app._open_pdf_safe(path)
        if not doc:
            return
        old_doc, old_lock = self._doc, self._doc_lock
        # Sizes are read once here, before the worker can see this document, so
        # layout never walks the Document while a render holds it.
        self._page_rects = [page.rect for page in doc]
        self._gen += 1
        self._doc, self._doc_lock, self._path = doc, threading.Lock(), path
        self._path_var.set(path)

        self._cache.clear()
        self._items.clear()
        self._canvas.delete("all")
        self._layout_pages()
        self._canvas.yview_moveto(0)
        self._update_viewport()

        if old_doc is not None:
            self._close_off_thread(old_doc, old_lock)

    @staticmethod
    def _close_off_thread(doc, lock):
        # Holding the document's lock, so a render already in flight against
        # it finishes before close() runs.
        core_reader.close_when_idle(doc, lock)

    # ── layout: page geometry only — no rasterising ──────────────────────────
    def _layout_pages(self):
        self._page_tops, self._page_px, y, max_w = core_reader.layout(
            self._page_rects, self._zoom, _GAP)
        self._total_h = y
        self._canvas.configure(scrollregion=(0, 0, max_w + 2 * _GAP, y))

    def _on_zoom(self, v):
        if not self._doc:
            return
        self._zoom = float(v)
        self._gen += 1
        self._cache.clear()
        self._items.clear()
        self._canvas.delete("all")
        self._layout_pages()
        self._update_viewport()

    # ── scrolling ─────────────────────────────────────────────────────────────
    def _yview(self, *args):
        self._canvas.yview(*args)
        self._update_viewport()

    def _scroll_px(self, delta_px: float):
        """Pixel-accurate scroll — this (not a fixed-unit jump) is what makes
        multi-page scroll feel continuous rather than paged."""
        if not self._doc or self._total_h <= 0:
            return
        cur_top  = self._canvas.canvasy(0)
        view_h   = self._canvas.winfo_height()
        new_top  = min(max(0, cur_top + delta_px), max(0, self._total_h - view_h))
        self._canvas.yview_moveto(new_top / self._total_h)
        self._update_viewport()

    # ── viewport → request visible (+preload) pages ──────────────────────────
    def _update_viewport(self):
        if not self._doc:
            return
        top    = self._canvas.canvasy(0)
        bottom = top + self._canvas.winfo_height()
        seen = core_reader.visible_range(self._page_tops, self._page_px, top, bottom)
        if seen is None:
            return
        first, last = seen
        lo, hi = core_reader.preload_window(first, last, len(self._page_rects), _PRELOAD)
        self._window = (lo, hi)
        for i in range(lo, hi + 1):
            self._request_page(i)
        # Free canvas images that scrolled well outside the window; the
        # PhotoImage stays in _cache so scrolling back redraws instantly.
        for idx in list(self._items.keys()):
            if idx < lo or idx > hi:
                self._canvas.delete(self._items.pop(idx))

        self._scroll_frac = self._canvas.yview()[0]
        self._pg_lbl.configure(text=f"{first + 1}–{last + 1} / {len(self._page_rects)}")

    def _request_page(self, idx: int):
        key = (idx, self._zoom)
        cached = self._cache.get(key)
        if cached is not None:
            self._cache.move_to_end(key)
            if idx not in self._items:
                self._draw_page(idx, cached)
            return
        # The cache only fills when a render reaches the main thread, so without
        # this every scroll event would queue the same pages again.
        flight = (self._gen, idx, self._zoom)
        if flight in self._inflight:
            return
        self._inflight.add(flight)
        self._req_q.put((self._gen, self._doc, self._doc_lock, idx, self._zoom))

    def _draw_page(self, idx: int, photo):
        y0 = self._page_tops[idx]
        if idx in self._items:
            self._canvas.delete(self._items[idx])
        self._items[idx] = self._canvas.create_image(_GAP, y0, anchor="nw", image=photo)

    # ── background worker: rasterise off the Tk thread ───────────────────────
    def _render_worker(self):
        while not self._worker_stop.is_set():
            try:
                gen, doc, lock, idx, zoom = self._req_q.get(timeout=0.25)
            except queue.Empty:
                continue
            flight = (gen, idx, zoom)
            lo, hi = self._window
            if gen != self._gen or doc is None or not lo <= idx <= hi:
                # stale (doc/zoom changed) or scrolled out of view since it was queued
                self.app.after(0, lambda f=flight: self._inflight.discard(f))
                continue
            try:
                pix = core_reader.rasterise(doc, lock, idx, zoom)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            except Exception as e:
                self.app.after(0, lambda f=flight, i=idx, ex=e: self._on_failed(f, i, ex))
                continue
            self.app.after(0, lambda i=idx, z=zoom, g=gen, im=img: self._on_rendered(g, i, z, im))

    def _on_failed(self, flight, idx, exc):
        self._inflight.discard(flight)
        if flight[0] == self._gen:
            self.app._set_status(f"Page {idx + 1} could not be shown: {exc}", WARN)

    def _on_rendered(self, gen, idx, zoom, pil_img):
        self._inflight.discard((gen, idx, zoom))
        if gen != self._gen or not self._canvas.winfo_exists():
            return                # stale — canvas/doc/zoom changed while this rendered
        photo = ImageTk.PhotoImage(pil_img)
        key = (idx, zoom)
        self._cache[key] = photo                 # keep a strong ref — Tk drops GC'd images
        self._cache.move_to_end(key)
        while len(self._cache) > _CACHE_MAX:
            for k in list(self._cache.keys()):
                if k[0] not in self._items:       # never evict a page on screen right now
                    del self._cache[k]
                    break
            else:
                break
        self._draw_page(idx, photo)
