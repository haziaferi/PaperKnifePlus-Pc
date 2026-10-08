"""Helpers for the Qt shell tests (a module of its own, so `pytest tests`
with the Tk harness's tests/conftest.py loaded too cannot mix them up)."""
from __future__ import annotations

import time


def pump(seconds: float = 0.2):
    """Run the Qt event loop for *seconds* (timers, queued posts)."""
    from PySide6.QtCore import QEventLoop, QTimer
    loop = QEventLoop()
    QTimer.singleShot(max(0, int(seconds * 1000)), loop.quit)
    loop.exec()


def wait_job(window, timeout: float = 30.0):
    """Pump until the window's current job has ended and its callbacks ran."""
    from PySide6.QtWidgets import QApplication
    end = time.time() + timeout
    while time.time() < end:
        job = window._current_job
        if job is None or not job.is_running:
            pump(0.15)
            return
        QApplication.processEvents()
        time.sleep(0.01)
    raise TimeoutError("job did not finish")


class Dialogs:
    """Same API as tests/conftest.py's Dialogs, on paperknife.qt.dialogs."""

    def __init__(self):
        self.saves: list = []
        self.opens: list = []           # str for ask_open, list for ask_open_many
        self.dirs: list = []
        self.asks: list = []            # answers for ask_yes_no (default True)
        self.passwords: list = []       # answers for ask_password (default None)
        self.colors: list = []
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
        return bool(_pop(d.asks, True))

    def ask_password(title="", prompt="", *a, **k):
        d.msgs.append(("ask_password", str(title), str(prompt)))
        return _pop(d.passwords, None)

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
