"""
Headless harness: drives the real tool views inside a hidden App.

- HOME/USERPROFILE point at a temp folder before paperknife is imported,
  so prefs.json / recent.json never touch the user's real profile; the
  folder is removed at session end, whether the tests passed or not.
- PAPERKNIFE_SRC=<dir> runs the suite against another source tree
  (used to prove a test fails on the baseline before a fix).
- Dialogs are stubbed: queue return values with `dialogs.save(...)`,
  `dialogs.open(...)`; every messagebox call is recorded in `dialogs.msgs`.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

import pytest

_HOME = tempfile.mkdtemp(prefix="pk-home-")
os.environ["HOME"] = _HOME
os.environ["USERPROFILE"] = _HOME

ROOT = Path(__file__).resolve().parents[1]
SRC = Path(os.environ.get("PAPERKNIFE_SRC", ROOT))
sys.path.insert(0, str(SRC))


class Dialogs:
    def __init__(self):
        self.saves: list = []
        self.opens: list = []
        self.dirs: list = []
        self.asks: list = []          # answers for askyesno / askokcancel
        self.msgs: list[tuple[str, str, str]] = []

    def save(self, *paths):
        self.saves.extend(str(p) for p in paths)

    def open(self, *paths):
        self.opens.extend(paths)

    def reset(self):
        self.__init__()

    def errors(self):
        return [m for m in self.msgs if m[0] == "showerror"]


DIALOGS = Dialogs()


def _install_stubs():
    from tkinter import filedialog, messagebox, colorchooser

    def _pop(q, default=""):
        return q.pop(0) if q else default

    filedialog.asksaveasfilename = lambda *a, **k: _pop(DIALOGS.saves)
    filedialog.askopenfilename = lambda *a, **k: _pop(DIALOGS.opens)
    filedialog.askopenfilenames = lambda *a, **k: _pop(DIALOGS.opens, ())
    filedialog.askdirectory = lambda *a, **k: _pop(DIALOGS.dirs)
    colorchooser.askcolor = lambda *a, **k: (None, None)

    def _rec(kind, ret=None):
        def f(title="", message="", *a, **k):
            DIALOGS.msgs.append((kind, str(title), str(message)))
            return _pop(DIALOGS.asks, True) if kind.startswith("ask") else ret
        return f

    for kind in ("showinfo", "showwarning", "showerror"):
        setattr(messagebox, kind, _rec(kind))
    for kind in ("askyesno", "askokcancel", "askyesnocancel", "askquestion"):
        setattr(messagebox, kind, _rec(kind))


_install_stubs()


def pytest_sessionfinish(session, exitstatus):
    # The App fixture is torn down by now; retry briefly for a file a closing
    # worker still holds, and say so rather than leave the folder silently.
    for _ in range(5):
        shutil.rmtree(_HOME, ignore_errors=True)
        if not os.path.exists(_HOME):
            return
        time.sleep(0.2)
    print(f"warning: could not remove the test HOME {_HOME}", file=sys.stderr)


@pytest.fixture(scope="session")
def app():
    import customtkinter as ctk
    import paperknife.tools  # noqa: F401  (fills TOOLS)
    from paperknife.app import App
    # Tk on Windows cannot report a window's .ico back: record what was set.
    icons = []
    real_iconbitmap = ctk.CTk.iconbitmap

    def iconbitmap(self, bitmap=None, default=None):
        icons.append(str(bitmap or default))
        return real_iconbitmap(self, bitmap, default)

    ctk.CTk.iconbitmap = iconbitmap
    a = App()
    a._harness_icons = icons
    a.withdraw()
    # Without mainloop(), Tcl refuses after() calls from worker threads
    # ("main thread is not in main loop") and the callback is lost.  In the
    # running app mainloop marshals them; here we queue them and drain the
    # queue on the main thread from pump()/wait_job().
    import queue
    import threading
    real_after = a.after
    a._harness_q = queue.Queue()

    def after(ms, func=None, *args):
        if threading.current_thread() is threading.main_thread():
            return real_after(ms, func, *args)
        a._harness_q.put((func, args))
        return "harness-after"

    a.after = after
    yield a
    try:
        a.destroy()
    except Exception:
        pass


@pytest.fixture
def dialogs():
    DIALOGS.reset()
    yield DIALOGS


def tool(app, class_name: str):
    """Open a tool by class name exactly as a sidebar click does; return it."""
    from paperknife.tool_base import TOOLS
    t = next(t for t in TOOLS if type(t).__name__ == class_name)
    # A job on the shown document holds navigation until it ends; a user
    # waits for it too.
    wait_job(app)
    app._nav_click(t.label, t.activate)
    app.update()
    assert app._active_tool is t, f"navigation to {class_name} was refused"
    return t


def _drain(app):
    q = getattr(app, "_harness_q", None)
    while q is not None and not q.empty():
        func, args = q.get()
        if func is not None:
            func(*args)


def pump(app, seconds: float = 0.3):
    end = time.time() + seconds
    while time.time() < end:
        _drain(app)
        app.update()
        time.sleep(0.01)
    _drain(app)


def wait_job(app, timeout: float = 60.0):
    """Pump the Tk loop until the current background job has finished."""
    end = time.time() + timeout
    while time.time() < end:
        _drain(app)
        app.update()
        job = app._current_job
        if job is None or not job.is_running:
            pump(app, 0.2)          # let on_done / after() callbacks run
            return
        time.sleep(0.02)
    raise TimeoutError("job did not finish")


def make_pdf(path, pages: int = 3, text: str = "Page {n}", **page_kw) -> str:
    import pymupdf as fitz
    doc = fitz.open()
    for i in range(pages):
        p = doc.new_page(**page_kw)
        p.insert_text((72, 100), text.format(n=i + 1), fontsize=14)
    doc.save(str(path))
    doc.close()
    return str(path)
