"""
paperknife.app
App shell — window, sidebar (collapsible sections + search), progress bar with
Cancel button, keyboard shortcuts, home screen, and shared UI helpers.

Tool views live in paperknife/tools/*.py and are imported by
paperknife/tools/__init__.py which populates tool_base.TOOLS.
"""
from __future__ import annotations

import gc
import sys
import time
import tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path

import customtkinter as ctk
import pymupdf as fitz

# ── Optional: drag & drop ─────────────────────────────────────────────────────
try:
    from tkinterdnd2 import TkinterDnD, DND_FILES as _DND_FILES
    _HAS_DND = True
except ImportError:
    _HAS_DND = False

# ── DPI awareness (Windows only) ──────────────────────────────────────────────
# app.manifest declares PerMonitorV2 for the PyInstaller build; this call
# covers running from source, where no manifest is embedded.
try:
    import ctypes as _ct
    _ct.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass

from .theme import (ACCENT, ACCENT_H, BG, SIDEBAR, CARD, CARD2,
                    TEXT, MUTED, DANGER, DANGER_H, SUCCESS, WARN, ON_ACCENT,
                    LB_BG, _tk_color, __version__)
from .recent import RECENT, thumb_image, time_ago, _THUMB_CACHE_MAX

# id(PIL image) -> (that image, its CTkImage); holding the image keeps its id unique.
_CTK_THUMBS: dict[int, tuple] = {}


def get_thumb(path: str, size=(100, 130)):
    """A recent file's first page as a CTkImage (None if it cannot be read);
    one CTkImage per cached thumbnail, as before the move to recent.thumb_image."""
    found = thumb_image(path, size)
    if found is None:
        return None
    img, fit = found
    hit = _CTK_THUMBS.get(id(img))
    if hit is None or hit[0] is not img:
        if len(_CTK_THUMBS) >= _THUMB_CACHE_MAX:
            _CTK_THUMBS.pop(next(iter(_CTK_THUMBS)))
        hit = _CTK_THUMBS[id(img)] = (img, ctk.CTkImage(img, size=fit))
    return hit[1]
from .prefs  import PREFS
from .job_queue import CancellableJob


# ══════════════════════════════════════════════════════════════════════════════
class App(ctk.CTk):

    def __init__(self):
        super().__init__()

        # _require adds the bundled tkdnd folder to Tcl's auto_path before
        # `package require`; a bare `package require tkdnd` cannot find it.
        # The widget methods (drop_target_register, dnd_bind) were patched
        # onto tkinter.BaseWidget by the import above.
        self._dnd_ok = False
        if _HAS_DND:
            try:
                self.TkdndVersion = TkinterDnD._require(self)
                self._dnd_ok = True
            except RuntimeError as exc:
                print(f"PaperKnife+: drag and drop disabled: {exc}",
                      file=sys.stderr)

        self.title(f"PaperKnife+ PC  v{__version__}")
        # Without an icon of its own, CTk puts its logo on the window and the
        # taskbar.  assets/ sits beside the package in the repo and the bundle.
        icon = Path(__file__).resolve().parents[1] / "assets" / "icon.ico"
        if icon.is_file():
            self.iconbitmap(str(icon))
        self.geometry("1380x900")
        self.minsize(1060, 720)
        self.configure(fg_color=BG)

        # Tooltip state
        self._tooltip_win:  tk.Toplevel | None = None
        self._last_hover_path = ""

        # Keyboard-action hooks (overridden by each tool view)
        self._cur_open_fn = None
        self._cur_save_fn = None
        self._cur_del_fn  = None
        self._cur_undo_fn = None

        # Job state
        self._current_job: CancellableJob | None = None
        # Bumped by every _set_status; run_job compares it to tell whether
        # the tool reported its own outcome while the job ran.
        self._status_seq = 0

        # The tool whose view is shown; told to release its files when left
        self._active_tool = None

        # Path queued for the Reader tool when opened via a Recent-file click
        self._reader_pending_path: str | None = None

        # Sidebar section open/closed state — populated in _build_layout
        self._section_open: dict[str, bool] = {}
        # Section-label widgets and their tool-button lists
        self._section_labels:  dict[str, ctk.CTkLabel]       = {}
        self._section_buttons: dict[str, list[ctk.CTkButton]] = {}
        self._nav_btns: dict[str, ctk.CTkButton] = {}

        self._build_layout()
        self._bind_keys()
        self.update_idletasks()
        self.show_home()

        # Restore window geometry
        if PREFS.window_geometry:
            try:
                self.geometry(PREFS.window_geometry)
            except tk.TclError:
                pass
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── Close ─────────────────────────────────────────────────────────────────
    def _on_close(self):
        job = self._current_job
        if job and job.is_running:
            if not messagebox.askyesno(
                    "Job running",
                    "A job is still running. Cancel it and quit?"):
                return
            job.cancel()
            self._set_status("Cancelling before exit…", WARN)
            self._close_when_idle(job, time.monotonic() + 15)
            return
        self._finish_close()

    def _close_when_idle(self, job, deadline: float):
        # Poll instead of join(): the worker's after() calls need the main
        # loop running, and a save in progress must be allowed to finish.
        if job.is_running and time.monotonic() < deadline:
            self.after(100, lambda: self._close_when_idle(job, deadline))
        else:
            self._finish_close()

    def _finish_close(self):
        PREFS.window_geometry = self.geometry()
        try:
            PREFS.save()
        except OSError:
            pass
        self.destroy()

    # ══════════════════════════════════════════════════════════════════════════
    # LAYOUT
    # ══════════════════════════════════════════════════════════════════════════
    def _build_layout(self):
        # ── Sidebar ──────────────────────────────────────────────────────────
        self.sidebar = ctk.CTkFrame(self, width=212, fg_color=SIDEBAR,
                                    corner_radius=0)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        # Logo header
        hdr = ctk.CTkFrame(self.sidebar, fg_color=SIDEBAR, height=84)
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        logo_row = ctk.CTkFrame(hdr, fg_color="transparent")
        logo_row.pack(pady=(18, 2), padx=14, fill="x")
        ctk.CTkLabel(logo_row, text="✂", font=ctk.CTkFont(size=26),
                     text_color=ACCENT).pack(side="left")
        ctk.CTkLabel(logo_row, text=" PaperKnife+",
                     font=ctk.CTkFont(size=19, weight="bold"),
                     text_color=TEXT).pack(side="left")
        ctk.CTkLabel(hdr, text="PC Edition  —  All-local PDF toolkit",
                     font=ctk.CTkFont(size=10), text_color=MUTED).pack()

        ctk.CTkFrame(self.sidebar, height=1, fg_color=CARD).pack(fill="x", padx=12)

        # ── Search bar ────────────────────────────────────────────────────────
        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", self._filter_nav)
        search_frame = ctk.CTkFrame(self.sidebar, fg_color=SIDEBAR)
        search_frame.pack(fill="x", padx=10, pady=(8, 4))
        self._search_entry = ctk.CTkEntry(
            search_frame,
            textvariable=self._search_var,
            placeholder_text="🔍  Search tools…",
            height=34,
            font=ctk.CTkFont(size=12),
        )
        self._search_entry.pack(fill="x")
        # ×  clear button — sits on top of the entry, appears when text present
        self._search_clear = ctk.CTkButton(
            search_frame, text="×", width=24, height=24,
            fg_color="transparent", hover_color=CARD,
            text_color=MUTED, font=ctk.CTkFont(size=14),
            command=self._clear_search,
        )

        # ── Scrollable nav ────────────────────────────────────────────────────
        self.nav_scroll = ctk.CTkScrollableFrame(self.sidebar, fg_color=SIDEBAR,
                                                  scrollbar_button_color=CARD)
        self.nav_scroll.pack(fill="both", expand=True)

        # Home button (always visible)
        home_btn = ctk.CTkButton(
            self.nav_scroll, text="🏠  Home & Recent",
            command=lambda: self._nav_click("🏠  Home & Recent", self.show_home),
            anchor="w", height=40, fg_color="transparent",
            hover_color=CARD, text_color=TEXT, corner_radius=8,
            font=ctk.CTkFont(size=13))
        home_btn.pack(fill="x", padx=8, pady=(4, 2))
        self._nav_btns["🏠  Home & Recent"] = home_btn

        # Build sections from tool registry
        from .tool_base import TOOLS
        # Group tools by section, preserving insertion order
        section_order: list[str] = []
        sections: dict[str, list] = {}
        for tool in TOOLS:
            if tool.section not in sections:
                section_order.append(tool.section)
                sections[tool.section] = []
            sections[tool.section].append(tool)

        for section in section_order:
            tools_in_section = sections[section]
            self._section_open[section] = True
            self._section_buttons[section] = []

            # Clickable section header
            sec_lbl = ctk.CTkLabel(
                self.nav_scroll,
                text=f"▾  {section}",
                font=ctk.CTkFont(size=9, weight="bold"),
                text_color=MUTED, anchor="w", cursor="hand2",
            )
            sec_lbl.pack(fill="x", padx=16, pady=(12, 2))
            sec_lbl.bind("<Button-1>",
                         lambda e, s=section: self._toggle_section(s))
            self._section_labels[section] = sec_lbl

            for tool in tools_in_section:
                btn = ctk.CTkButton(
                    self.nav_scroll, text=tool.label,
                    command=lambda t=tool: self._nav_click(t.label, t.activate),
                    anchor="w", height=40, fg_color="transparent",
                    hover_color=CARD, text_color=TEXT, corner_radius=8,
                    font=ctk.CTkFont(size=13))
                btn.pack(fill="x", padx=8, pady=1)
                self._nav_btns[tool.label]       = btn
                self._section_buttons[section].append(btn)

        # Footer
        ctk.CTkFrame(self.sidebar, height=1, fg_color=CARD).pack(fill="x", padx=12)
        ctk.CTkLabel(self.sidebar,
                     text=f"v{__version__}  ·  github/potatameister",
                     font=ctk.CTkFont(size=10), text_color=MUTED).pack(pady=6)

        # ── Main area ─────────────────────────────────────────────────────────
        right = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        right.pack(side="left", fill="both", expand=True)

        self.main = ctk.CTkFrame(right, fg_color=BG, corner_radius=0)
        self.main.pack(fill="both", expand=True)

        # Progress bar + Cancel button (hidden by default)
        self._prog_frame = ctk.CTkFrame(right, fg_color=SIDEBAR, height=34)
        self.progress = ctk.CTkProgressBar(self._prog_frame, height=6,
                                            progress_color=ACCENT)
        self.progress.set(0)
        self.progress.pack(fill="x", padx=0, pady=(14, 0))
        self._job_label = ctk.CTkLabel(
            self._prog_frame, text="", font=ctk.CTkFont(size=11),
            text_color=MUTED, anchor="w")
        self._job_label.pack(side="left", padx=10, pady=(0, 6))
        self._cancel_btn = ctk.CTkButton(
            self._prog_frame, text="✕  Cancel", width=90, height=22,
            fg_color=DANGER, hover_color=DANGER_H,
            font=ctk.CTkFont(size=11), command=self._cancel_job)
        self._cancel_btn.pack(side="right", padx=10, pady=(0, 6))
        # (don't pack _prog_frame yet — shown on demand)

        # Status bar
        self.status_var = tk.StringVar(value="  Ready")
        self.statusbar = ctk.CTkLabel(
            right, textvariable=self.status_var,
            fg_color=SIDEBAR, anchor="w", height=26,
            font=ctk.CTkFont(size=12), text_color=MUTED)
        self.statusbar.pack(side="bottom", fill="x")

    # ══════════════════════════════════════════════════════════════════════════
    # SIDEBAR SEARCH & SECTION TOGGLE
    # ══════════════════════════════════════════════════════════════════════════
    def _filter_nav(self, *_):
        query = self._search_var.get().strip().lower()

        # Show / hide the × clear button
        if query:
            self._search_clear.place(relx=1.0, rely=0.5,
                                     x=-4, anchor="e")
        else:
            self._search_clear.place_forget()

        self._layout_nav(query)

    def _layout_nav(self, query: str):
        # Re-pack every section in registry order.  pack(after=w) fails when
        # w is itself unpacked, so a section hidden by one query could not be
        # anchored back in place by the next.
        widgets = []
        for section, buttons in self._section_buttons.items():
            if query:
                shown = [b for b in buttons if query in b.cget("text").lower()]
                if shown:
                    widgets.append((self._section_labels[section], True))
                widgets += [(b, False) for b in shown]
            else:
                widgets.append((self._section_labels[section], True))
                if self._section_open[section]:
                    widgets += [(b, False) for b in buttons]
        for section, buttons in self._section_buttons.items():
            self._section_labels[section].pack_forget()
            for btn in buttons:
                btn.pack_forget()
        for w, is_header in widgets:
            if is_header:
                w.pack(fill="x", padx=16, pady=(12, 2))
            else:
                w.pack(fill="x", padx=8, pady=1)

    def _toggle_section(self, section: str):
        self._section_open[section] = not self._section_open[section]
        arrow = "▾" if self._section_open[section] else "▸"
        self._section_labels[section].configure(text=f"{arrow}  {section}")
        self._layout_nav(self._search_var.get().strip().lower())

    def _clear_search(self):
        self._search_var.set("")
        self._search_entry.focus_set()

    def _focus_search(self):
        self._search_entry.focus_set()
        self._search_entry.select_range(0, "end")

    # ══════════════════════════════════════════════════════════════════════════
    # KEYBOARD SHORTCUTS
    # ══════════════════════════════════════════════════════════════════════════
    def _bind_keys(self):
        # Caps Lock or Shift turns the keysym upper-case; bind both.
        def tool_key(name):
            def handler(_e):
                fn = getattr(self, name)
                if fn and not self._view_locked:
                    fn()
            return handler

        for key, fn in (
            ("o", tool_key("_cur_open_fn")),
            ("s", tool_key("_cur_save_fn")),
            ("z", tool_key("_cur_undo_fn")),
            # Ctrl+K / Ctrl+F focus the sidebar search
            ("k", lambda e: self._focus_search()),
            ("f", lambda e: self._focus_search()),
        ):
            self.bind(f"<Control-{key}>", fn)
            self.bind(f"<Control-{key.upper()}>", fn)
        self.bind("<Delete>", self._on_delete_key)
        self.bind("<Escape>", lambda e: self._clear_search())

    def _on_delete_key(self, event):
        # The toplevel binding also sees keys typed into entries; Delete
        # there edits text and must not remove the selected list item.
        if event.widget.winfo_class() in ("Entry", "Text", "TEntry", "Spinbox"):
            return
        if self._cur_del_fn and not self._view_locked:
            self._cur_del_fn()

    # ══════════════════════════════════════════════════════════════════════════
    # NAVIGATION
    # ══════════════════════════════════════════════════════════════════════════
    def _nav_click(self, active_label: str, cmd):
        """Highlight the active nav button; reset keyboard hooks; run cmd,
        which is show_home or a tool's bound activate."""
        if self._view_locked:   # the tool's document is in use by a running job
            return
        for lbl, btn in self._nav_btns.items():
            if lbl == active_label:
                btn.configure(fg_color=ACCENT, text_color=ON_ACCENT)
            else:
                btn.configure(fg_color="transparent", text_color=TEXT)
        self._cur_open_fn = None
        self._cur_save_fn = None
        self._cur_del_fn  = None
        self._cur_undo_fn = None
        if self._active_tool is not None:
            self._active_tool.deactivate()
        owner = getattr(cmd, "__self__", None)
        if owner is self:
            self._active_tool = None
            cmd()
        else:
            self._active_tool = owner
            cmd(self)

    def _clear_main(self):
        self._hide_tooltip()
        for w in self.main.winfo_children():
            w.destroy()

    # ══════════════════════════════════════════════════════════════════════════
    # JOB QUEUE  (progress bar + Cancel button lifecycle)
    # ══════════════════════════════════════════════════════════════════════════
    def run_job(self, worker_fn, label: str = "Working…", *, lock: bool = False,
                then=None) -> CancellableJob:
        """
        Run *worker_fn(stop)* in a background thread with full progress +
        cancel UI; stop is a threading.Event the worker checks with is_set().

        lock=True: the worker uses a document the window also shows, so until
        it ends every click goes to the progress bar (only Cancel works) and
        shortcuts and navigation are ignored.  then(kind, value), kind "done" /
        "error" / "cancel", runs on the Tk thread after the job has ended.

        Only one job runs at a time; while one is running this shows a
        warning and returns None.
        """
        if self._current_job and self._current_job.is_running:
            messagebox.showwarning(
                "Busy", "Another job is still running. Wait for it to finish "
                        "or cancel it first.")
            return None

        # Collect garbage here, on the Tk thread: a tool view left behind holds
        # Tk variables, and the collector running in the worker would delete
        # them there, a Tk call from the wrong thread that waits on this one.
        gc.collect()
        self._prog_show(0)
        self._job_label.configure(text=f"  {label}")
        seq_at_start = self._status_seq
        if lock:
            self._lock_view()

        def finish(kind, value):
            if self._current_job is job:
                self._prog_hide()
            if lock:
                self._unlock_view()
            if then is not None:
                then(kind, value)

        def on_done(result):
            if isinstance(result, str) and result:
                self._set_status(result, SUCCESS)
            # The worker posts its own outcome through after() before it
            # returns, so it is already showing; do not cover it.
            elif self._status_seq == seq_at_start:
                self._set_status("Done", SUCCESS)
            finish("done", result)

        def on_error(exc):
            finish("error", exc)
            self._set_status(f"Error: {exc}", DANGER)
            messagebox.showerror("Error", str(exc))

        def on_cancel():
            # A worker that reported an outcome got past its last stop check
            # and finished; "Cancelled" would contradict its saved message.
            if self._status_seq == seq_at_start:
                self._set_status("Cancelled", WARN)
            finish("cancel", None)

        job = CancellableJob(
            fn        = worker_fn,
            after_fn  = self.after,
            on_done   = on_done,
            on_error  = on_error,
            on_cancel = on_cancel,
        )
        self._current_job = job
        return job.start()

    def _cancel_job(self):
        if self._current_job and self._current_job.is_running:
            self._current_job.cancel()

    # A job that uses the shown document: input is held at the progress bar.
    _view_locked = False

    def _lock_view(self):
        self._view_locked = True
        try:
            self.update_idletasks()
            self._prog_frame.grab_set()
        except tk.TclError:
            pass        # not viewable (a hidden window): the flag still holds

    def _unlock_view(self):
        self._view_locked = False
        try:
            self._prog_frame.grab_release()
        except tk.TclError:
            pass

    # ══════════════════════════════════════════════════════════════════════════
    # PROGRESS BAR
    # ══════════════════════════════════════════════════════════════════════════
    def _prog_show(self, val: float = 0.0):
        self._prog_frame.pack(side="bottom", fill="x", before=self.statusbar)
        self.progress.set(val)

    def _prog_update(self, val: float):
        self.progress.set(max(0.0, min(1.0, val)))

    def _prog_hide(self):
        self._prog_frame.pack_forget()
        self.progress.set(0)
        self._job_label.configure(text="")

    # ══════════════════════════════════════════════════════════════════════════
    # STATUS BAR
    # ══════════════════════════════════════════════════════════════════════════
    def _set_status(self, msg: str, color=MUTED):
        self._status_seq += 1
        self.statusbar.configure(text_color=color)
        self.status_var.set(f"  {msg}")

    # ══════════════════════════════════════════════════════════════════════════
    # TOOLTIP
    # ══════════════════════════════════════════════════════════════════════════
    def _show_tooltip(self, x_root, y_root, path):
        self._hide_tooltip()
        thumb = get_thumb(path, size=(120, 155))
        if not thumb:
            return
        tip = tk.Toplevel(self)
        tip.overrideredirect(True)
        tip.attributes("-topmost", True)
        tip.wm_geometry(f"+{x_root + 24}+{y_root - 90}")
        fr = ctk.CTkFrame(tip, fg_color=CARD2, corner_radius=8,
                           border_color=ACCENT, border_width=1)
        fr.pack(padx=2, pady=2)
        ctk.CTkLabel(fr, image=thumb, text="").pack(padx=8, pady=(8, 2))
        name = Path(path).name
        if len(name) > 28:
            name = name[:25] + "…"
        ctk.CTkLabel(fr, text=name, font=ctk.CTkFont(size=10),
                     text_color=MUTED).pack(padx=8, pady=(0, 8))
        self._tooltip_win = tip

    def _hide_tooltip(self, _=None):
        if self._tooltip_win:
            try:
                self._tooltip_win.destroy()
            except Exception:
                pass
            self._tooltip_win = None
        self._last_hover_path = ""

    # ══════════════════════════════════════════════════════════════════════════
    # DnD HELPERS
    # ══════════════════════════════════════════════════════════════════════════
    @staticmethod
    def _parse_drop(event_data: str) -> list[str]:
        paths, raw = [], event_data.strip()
        while raw:
            if raw.startswith("{"):
                end = raw.index("}")
                paths.append(raw[1:end])
                raw = raw[end + 1:].strip()
            else:
                parts = raw.split(" ", 1)
                paths.append(parts[0])
                raw = parts[1].strip() if len(parts) > 1 else ""
        return [p for p in paths if p]

    # ══════════════════════════════════════════════════════════════════════════
    # SHARED UI BUILDERS
    # ══════════════════════════════════════════════════════════════════════════
    def _card_layout(self, title: str, subtitle: str = ""):
        self._clear_main()
        outer = ctk.CTkFrame(self.main, fg_color=BG, corner_radius=0)
        outer.pack(fill="both", expand=True)
        hdr = ctk.CTkFrame(outer, fg_color=SIDEBAR, corner_radius=0, height=70)
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text=title,
                     font=ctk.CTkFont(size=22, weight="bold"),
                     text_color=TEXT).pack(side="left", padx=26, pady=(12, 0),
                                           anchor="sw")
        if subtitle:
            ctk.CTkLabel(hdr, text=subtitle, font=ctk.CTkFont(size=12),
                         text_color=MUTED).pack(side="left", padx=8,
                                                pady=(20, 0), anchor="sw")
        body = ctk.CTkFrame(outer, fg_color=BG, corner_radius=0)
        body.pack(fill="both", expand=True)
        return body

    def _file_row(self, parent, var, btn_text="Open PDF", exts=(".pdf",)):
        hint = ("Drop a file here or click to browse…"
                if self._dnd_ok else "No file selected…")
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=24, pady=8)
        entry = ctk.CTkEntry(row, textvariable=var, state="readonly",
                             height=44)
        entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        # CTkEntry never draws placeholder_text when a textvariable is set,
        # so the hint is a label laid over the empty entry.
        hint_lbl = ctk.CTkLabel(entry, text=hint, text_color=MUTED,
                                fg_color="transparent", height=24)

        def _sync_hint(*_):
            # The tool's variable can outlive this view.
            if not hint_lbl.winfo_exists():
                var.trace_remove("write", trace_id)
            elif var.get():
                hint_lbl.place_forget()
            else:
                hint_lbl.place(x=10, rely=0.5, anchor="w")

        trace_id = var.trace_add("write", _sync_hint)
        _sync_hint()

        def pick():
            ft = [(e.lstrip(".").upper(), f"*{e}") for e in exts] + [("All", "*.*")]
            p  = filedialog.askopenfilename(title="Select file", filetypes=ft)
            if p:
                var.set(p)

        ctk.CTkButton(row, text=btn_text, width=136, height=44,
                      command=pick).pack(side="left")

        if self._dnd_ok:
            _DEFAULT_BORDER = ("gray65", "gray30")

            def _on_drop(event):
                for p in self._parse_drop(event.data):
                    if not exts or Path(p).suffix.lower() in exts:
                        var.set(p)
                        entry.configure(border_color=_DEFAULT_BORDER)
                        return
                entry.configure(border_color=_DEFAULT_BORDER)

            def _on_enter(event):
                entry.configure(border_color=ACCENT)
                return event.action

            def _on_leave(_event):
                entry.configure(border_color=_DEFAULT_BORDER)

            def _register(w):
                w.drop_target_register(_DND_FILES)
                w.dnd_bind("<<Drop>>",      _on_drop)
                w.dnd_bind("<<DragEnter>>", _on_enter)
                w.dnd_bind("<<DragLeave>>", _on_leave)

            _register(row)

            def _register_inner():
                if not entry.winfo_exists():
                    return
                for child in entry.winfo_children():
                    _register(child)

            self.after(50, _register_inner)

    def _listbox(self, parent, height=12):
        fr = ctk.CTkFrame(parent, fg_color=CARD2, corner_radius=8)
        lb = tk.Listbox(fr, bg=_tk_color(LB_BG), fg=_tk_color(TEXT), selectbackground=_tk_color(ACCENT),
                        font=("Segoe UI", 12), relief="flat", bd=0,
                        activestyle="none", highlightthickness=0,
                        selectforeground=ON_ACCENT, height=height)
        sb = tk.Scrollbar(fr, orient="vertical", command=lb.yview)
        lb.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        lb.pack(fill="both", expand=True, padx=6, pady=6)
        return fr, lb

    def _list_move(self, lb, d):
        sel = lb.curselection()
        if not sel:
            return
        i, ni = sel[0], sel[0] + d
        if 0 <= ni < lb.size():
            v = lb.get(i)
            lb.delete(i)
            lb.insert(ni, v)
            lb.selection_set(ni)

    def _list_remove(self, lb):
        sel = lb.curselection()
        if sel:
            lb.delete(sel[0])

    def _big_btn(self, parent, text, cmd, color=ACCENT, hover=ACCENT_H, **kw):
        return ctk.CTkButton(
            parent, text=text, command=cmd, height=50,
            font=ctk.CTkFont(size=16, weight="bold"),
            fg_color=color, hover_color=hover, **kw)

    def _save_as(self, default="output.pdf", ext=".pdf", filetypes=None):
        ft = filetypes or [(ext.lstrip(".").upper(), f"*{ext}")]
        return filedialog.asksaveasfilename(
            defaultextension=ext, filetypes=ft, initialfile=default,
            initialdir=PREFS.output_dir or None)

    def _ask_dir(self, title="Choose output folder"):
        return filedialog.askdirectory(title=title,
                                       initialdir=PREFS.output_dir or None)

    def _open_pdf_safe(self, path: str):
        try:
            doc = fitz.open(path)
        except Exception as e:
            messagebox.showerror("Error", f"Could not open PDF:\n{e}")
            return None
        if doc.is_encrypted:
            pw = ctk.CTkInputDialog(
                text="This PDF is password-protected. Enter the password:",
                title="Password Required").get_input()
            if not pw:
                doc.close()
                return None
            if not doc.authenticate(pw):
                messagebox.showerror("Error", "Incorrect password.")
                doc.close()
                return None
        RECENT.push(path, len(doc))
        return doc

    def _widget_set(self, widget, **kwargs):
        """Safely configure a widget — no-op if it was destroyed."""
        try:
            if widget is not None and widget.winfo_exists():
                widget.configure(**kwargs)
        except Exception:
            pass

    # ══════════════════════════════════════════════════════════════════════════
    # HOME SCREEN
    # ══════════════════════════════════════════════════════════════════════════
    def show_home(self):
        self._clear_main()
        outer = ctk.CTkFrame(self.main, fg_color=BG, corner_radius=0)
        outer.pack(fill="both", expand=True)

        # ── Header banner ─────────────────────────────────────────────────────
        hdr = ctk.CTkFrame(outer, fg_color=SIDEBAR, corner_radius=0, height=88)
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="✂  PaperKnife+ PC",
                     font=ctk.CTkFont(size=28, weight="bold"),
                     text_color=ACCENT).pack(side="left", padx=28, pady=18)
        ctk.CTkLabel(hdr, text="100 % local · no cloud · no tracking",
                     font=ctk.CTkFont(size=13), text_color=MUTED
                     ).pack(side="left", padx=4, pady=26)

        body = ctk.CTkScrollableFrame(outer, fg_color=BG, corner_radius=0)
        body.pack(fill="both", expand=True)

        # ── Quick actions ─────────────────────────────────────────────────────
        from .tool_base import TOOLS
        tool_map = {t.label: t for t in TOOLS}

        qa_labels = [
            "📖  Read / Preview",
            "📎  Merge",
            "✂   Split",
            "🔒  Password",
            "🗜   Compress",
            "📝  Annotate",
            "🤖  OCR",
        ]
        qa_frame = ctk.CTkFrame(body, fg_color="transparent")
        qa_frame.pack(fill="x", padx=24, pady=(20, 8))
        ctk.CTkLabel(qa_frame, text="Quick actions",
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=TEXT, anchor="w").pack(fill="x", pady=(0, 8))
        btn_row = ctk.CTkFrame(qa_frame, fg_color="transparent")
        btn_row.pack(fill="x")
        for lbl in qa_labels:
            t = tool_map.get(lbl)
            if not t:
                continue
            ctk.CTkButton(
                btn_row, text=lbl, height=44,
                fg_color=ACCENT, hover_color=ACCENT_H,
                font=ctk.CTkFont(size=13),
                command=lambda tl=t: self._nav_click(tl.label, tl.activate),
            ).pack(side="left", padx=4, expand=True, fill="x")

        # ── Recent files ──────────────────────────────────────────────────────
        recent = RECENT.all()
        rec_frame = ctk.CTkFrame(body, fg_color="transparent")
        rec_frame.pack(fill="both", expand=True, padx=24, pady=(16, 24))
        ctk.CTkLabel(rec_frame, text="Recent files",
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=TEXT, anchor="w").pack(fill="x", pady=(0, 8))

        if not recent:
            ctk.CTkLabel(rec_frame,
                         text="Open a PDF with any tool to see it here.",
                         font=ctk.CTkFont(size=13), text_color=MUTED,
                         anchor="w").pack(fill="x")
            return

        grid = ctk.CTkFrame(rec_frame, fg_color="transparent")
        grid.pack(fill="both", expand=True)
        COLS = 4
        for idx, entry in enumerate(recent):
            col, row = idx % COLS, idx // COLS
            path = entry["path"]
            card = ctk.CTkFrame(grid, fg_color=CARD2, corner_radius=8,
                                 cursor="hand2")
            card.grid(row=row, column=col, padx=6, pady=6, sticky="nsew")
            grid.columnconfigure(col, weight=1)

            thumb = get_thumb(path)
            if thumb:
                ctk.CTkLabel(card, image=thumb, text=""
                             ).pack(padx=8, pady=(8, 2))

            name = entry.get("name") or Path(path).name
            if len(name) > 22:
                name = name[:19] + "…"
            ctk.CTkLabel(card, text=name, font=ctk.CTkFont(size=11),
                         text_color=TEXT, anchor="w").pack(padx=8, fill="x")
            meta = []
            if entry.get("pages"): meta.append(f"{entry['pages']} pp")
            if entry.get("size_kb"): meta.append(f"{entry['size_kb']} KB")
            meta.append(time_ago(entry.get("accessed", "")))
            ctk.CTkLabel(card, text="  ".join(meta),
                         font=ctk.CTkFont(size=10), text_color=MUTED,
                         anchor="w").pack(padx=8, pady=(0, 8), fill="x")

            # Click anywhere on the card → open it in the Reader (front-facing)
            def _open_in_reader(e=None, p=path):
                self._reader_pending_path = p
                from .tool_base import TOOLS
                reader = next((t for t in TOOLS if t.label.startswith("📖")), None)
                if reader:
                    self._nav_click(reader.label, reader.activate)
            card.bind("<Button-1>", _open_in_reader)

            # Hover tooltip
            def _enter(e, p=path):
                if self._last_hover_path != p:
                    self._last_hover_path = p
                    self.after(400, lambda pp=p, x=e.x_root, y=e.y_root:
                               self._show_tooltip(x, y, pp)
                               if self._last_hover_path == pp else None)

            card.bind("<Enter>", _enter)
            card.bind("<Leave>", self._hide_tooltip)
            for child in card.winfo_children():
                child.bind("<Button-1>", _open_in_reader)
                child.bind("<Enter>", _enter)
                child.bind("<Leave>", self._hide_tooltip)

        # Clear recent button
        ctk.CTkButton(
            rec_frame, text="Clear history", width=130, height=30,
            fg_color="transparent", text_color=MUTED,
            hover_color=CARD, font=ctk.CTkFont(size=11),
            command=self._clear_recent,
        ).pack(anchor="e", pady=(8, 0))

    def _clear_recent(self):
        if messagebox.askyesno("Clear history",
                               "Remove all recent file entries?"):
            RECENT.clear()
            self.show_home()
