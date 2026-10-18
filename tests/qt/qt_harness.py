"""Helpers for the Qt shell tests (a module of its own, so `pytest tests`
with the Tk harness's tests/conftest.py loaded too cannot mix them up)."""
from __future__ import annotations

import importlib.util
import time
from pathlib import Path

# The toolkit-neutral builders both harnesses share (tests/pdf_builders.py),
# loaded by path so tests/ (and the Tk conftest there) never joins sys.path.
_spec = importlib.util.spec_from_file_location(
    "pk_pdf_builders", Path(__file__).resolve().parents[1] / "pdf_builders.py")
_builders = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_builders)
image_pdf = _builders.image_pdf
truncated_pdf = _builders.truncated_pdf


def subtitle_with(base: str, name: str) -> str:
    """A page's subtitle while it acts on the file *name* (owner, 2026-10-10):
    its own (the document bar's chip names the file); a base that only says
    to open a file gives way to the name."""
    from paperknife.qt.pages import HINT_SUBTITLE
    return name if base == HINT_SUBTITLE else base


def pump(seconds: float = 0.2):
    """Run the Qt event loop for *seconds* (timers, queued posts)."""
    from PySide6.QtCore import QEventLoop, QTimer
    loop = QEventLoop()
    QTimer.singleShot(max(0, int(seconds * 1000)), loop.quit)
    loop.exec()


def wait_job(window, timeout: float = 30.0):
    """Pump until the window's current job has ended and its callbacks ran.

    CancellableJob clears is_running before its worker thread posts
    on_done / on_error / on_cancel, so is_running alone says nothing about
    the callback: wait for the worker thread itself to end (by then the post
    is queued on the event loop), then pump so the queued callback runs."""
    from PySide6.QtWidgets import QApplication
    end = time.time() + timeout
    while time.time() < end:
        job = window._current_job
        thread = getattr(job, "_thread", None)
        if job is None or (not job.is_running
                           and not (thread is not None and thread.is_alive())):
            pump(0.15)
            return
        QApplication.processEvents()
        time.sleep(0.01)
    raise TimeoutError("job did not finish")


def spy_open(window, monkeypatch) -> list:
    """Record every document a job opens for itself: what window.open_pdf_safe
    returns, and the copy a page-range tool (pages.PagePickPage, which holds
    its document open since 2026-10-17) gives its job.  The real calls still
    run; undone by monkeypatch at the end of the test."""
    from paperknife.qt import pages
    opened = []
    real = window.open_pdf_safe

    def spy(*a, **k):
        doc = real(*a, **k)
        opened.append(doc)
        return doc
    monkeypatch.setattr(window, "open_pdf_safe", spy)
    real_copy = pages.PagePickPage.job_copy

    def spy_copy(self, *a, **k):
        doc = real_copy(self, *a, **k)
        opened.append(doc)
        return doc
    monkeypatch.setattr(pages.PagePickPage, "job_copy", spy_copy)
    return opened


def tesseract_ok() -> bool:
    """True when the app's own Tesseract lookup finds a binary that runs."""
    try:
        from paperknife.core.ocr import tesseract
        tesseract().get_tesseract_version()
        return True
    except Exception:
        return False


def requires_tesseract(fn):
    """Skip a test that needs the real Tesseract binary when there is none."""
    import pytest
    return pytest.mark.skipif(not tesseract_ok(),
                              reason="Tesseract is not installed on this machine")(fn)


class Dialogs:
    """Same API as tests/conftest.py's Dialogs, on paperknife.qt.dialogs."""

    def __init__(self):
        self.saves: list = []
        self.opens: list = []           # str for ask_open, list for ask_open_many
        self.dirs: list = []
        self.asks: list = []            # answers for ask_yes_no: queue one per prompt
        self.unexpected: list = []      # ask_yes_no / ask_unsaved calls nobody queued an answer for
        self.passwords: list = []       # answers for ask_password (default None)
        self.unsaved: list = []         # answers for ask_unsaved: "save" / "discard" / "cancel"
        self.colors: list = []
        self.recovers: list = []        # answers for ask_recover: True / False / None
        self.msgs: list[tuple[str, str, str]] = []

    def save(self, *paths):
        self.saves.extend(str(p) for p in paths)

    def open(self, *paths):
        self.opens.extend(paths)

    def reset(self):
        self.__init__()

    def errors(self):
        return [m for m in self.msgs if m[0] == "error"]

    def warnings(self):
        return [m for m in self.msgs if m[0] == "warning"]


def _pop(q, default):
    return q.pop(0) if q else default


def _install(mp, d: Dialogs):
    from paperknife.qt import dialogs as dmod

    def rec(kind):
        def f(title="", msg="", *a, **k):
            d.msgs.append((kind, str(title), str(msg)))
        return f

    def ask_yes_no(title="", msg="", *a, **k):
        d.msgs.append(("ask_yes_no", str(title), str(msg)))
        if not d.asks:
            # Answering Yes silently would let a page start (or stop) asking
            # a confirmation without any test noticing.  The dialogs fixture
            # also fails the test at teardown, in case a caller swallowed this.
            d.unexpected.append((str(title), str(msg)))
            raise AssertionError(f"unexpected ask_yes_no: {title!r}: {msg!r}")
        return bool(d.asks.pop(0))

    def ask_unsaved(name="", *a, **k):
        d.msgs.append(("ask_unsaved", f"Save changes to {name}?", ""))
        if not d.unsaved:
            d.unexpected.append((f"Save changes to {name}?", ""))
            raise AssertionError(f"unexpected ask_unsaved: {name!r}")
        return d.unsaved.pop(0)

    def ask_password(title="", prompt="", *a, **k):
        d.msgs.append(("ask_password", str(title), str(prompt)))
        return _pop(d.passwords, None)

    def ask_recover(lines=(), *a, **k):
        d.msgs.append(("ask_recover", dmod.RECOVER_TITLE, "\n".join(lines)))
        if not d.recovers:
            d.unexpected.append((dmod.RECOVER_TITLE, "\n".join(lines)))
            raise AssertionError(f"unexpected ask_recover: {lines!r}")
        return d.recovers.pop(0)

    def ask_open_many(*a, **k):
        v = _pop(d.opens, [])
        return [str(p) for p in (v if isinstance(v, (list, tuple)) else [v])]

    mp.setattr(dmod, "ask_open", lambda *a, **k: str(_pop(d.opens, "")))
    mp.setattr(dmod, "ask_open_many", ask_open_many)
    mp.setattr(dmod, "ask_save", lambda *a, **k: _pop(d.saves, ""))
    mp.setattr(dmod, "ask_dir", lambda *a, **k: str(_pop(d.dirs, "")))
    mp.setattr(dmod, "ask_color", lambda *a, **k: _pop(d.colors, None))
    mp.setattr(dmod, "ask_yes_no", ask_yes_no)
    mp.setattr(dmod, "ask_password", ask_password)
    mp.setattr(dmod, "ask_unsaved", ask_unsaved, raising=False)   # (absent before 2026-10-10)
    mp.setattr(dmod, "ask_recover", ask_recover, raising=False)   # (absent before 2026-10-12)
    for kind in ("info", "warning", "error"):
        mp.setattr(dmod, kind, rec(kind))


def make_pdf(path, pages: int = 3, text: str = "Page {n}", password: str | None = None) -> str:
    import pymupdf as fitz
    doc = fitz.open()
    for i in range(pages):
        p = doc.new_page()
        p.insert_text((72, 100), text.format(n=i + 1), fontsize=14)
    if password:
        doc.save(str(path), encryption=fitz.PDF_ENCRYPT_AES_256,
                 user_pw=password, owner_pw=password)
    else:
        doc.save(str(path))
    doc.close()
    return str(path)
