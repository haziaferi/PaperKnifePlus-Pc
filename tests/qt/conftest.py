"""
Harness for the Qt shell (paperknife.qt).  Independent of tests/conftest.py
(the Tk harness): run with

    QT_QPA_PLATFORM=offscreen python -m pytest tests/qt --confcutdir=tests/qt -p no:cacheprovider

- HOME/USERPROFILE point at a temp folder before paperknife is imported,
  so prefs.json / recent.json never touch the user's real profile.
- One offscreen QApplication for the session.
- Dialogs are stubbed through the one seam, paperknife.qt.dialogs (helpers
  in qt_harness.py, imported by the tests as `from qt_harness import ...`): queue
  return values with dialogs.save(...) / .open(...) / .dirs / .asks /
  .passwords; every message is recorded in dialogs.msgs.
- The real pointer is never read or moved: every window gets a fixed
  simulated pointer (window centre) that tests may change.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

import pytest

_HOME = tempfile.mkdtemp(prefix="pk-home-")
os.environ["HOME"] = _HOME
os.environ["USERPROFILE"] = _HOME

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[2]
SRC = Path(os.environ.get("PAPERKNIFE_SRC", ROOT))
sys.path.insert(0, str(SRC))


from qt_harness import Dialogs, _install, pump, wait_job  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    import paperknife.tools  # noqa: F401  (fills TOOLS)
    from paperknife.qt import bridge, theme
    bridge.install()
    theme.setup_fonts(app)
    theme.apply_appearance("light")
    yield app


@pytest.fixture
def dialogs(monkeypatch):
    d = Dialogs()
    _install(monkeypatch, d)
    yield d


@pytest.fixture
def window(qapp, dialogs):
    """A fresh MainWindow, shown offscreen, with a simulated pointer at its
    centre (the edge watcher never reads the real cursor)."""
    from PySide6.QtCore import QPoint
    from paperknife.qt.shell import MainWindow
    w = MainWindow()
    w.move(0, 0)
    w.pointer_at = QPoint(w.width() // 2, w.height() // 2)
    w._pointer = lambda: w.mapToGlobal(w.pointer_at)
    w.show()
    pump(0.05)
    yield w
    if w._current_job is not None and w._current_job.is_running:
        w._current_job.cancel()
        wait_job(w)
    w._close_ok = True
    w._alive = False
    w._edge.stop()
    w.close()
    w.deleteLater()
    pump(0.02)
