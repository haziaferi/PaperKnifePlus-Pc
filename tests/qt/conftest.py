"""
Harness for the Qt shell (paperknife.qt).  Independent of tests/conftest.py
(the Tk harness): run with

    QT_QPA_PLATFORM=offscreen python -m pytest tests/qt --confcutdir=tests/qt -p no:cacheprovider

- HOME/USERPROFILE point at a temp folder before paperknife is imported,
  so prefs.json / recent.json never touch the user's real profile; the
  folder is removed at session end, whether the tests passed or not.  Each
  test also gets its own prefs.json / recent.json in tmp_path, and PREFS /
  RECENT are put back afterwards, so no test inherits another's window
  geometry or file history.
- PK_TITLEBAR / PK_ACTION are cleared: the title bar and the action
  placement never depend on the developer's shell (a test that needs one
  uses monkeypatch.setenv).
- One offscreen QApplication for the session.
- Dialogs are stubbed through the one seam, paperknife.qt.dialogs (helpers
  in qt_harness.py, imported by the tests as `from qt_harness import ...`): queue
  return values with dialogs.save(...) / .open(...) / .dirs / .asks /
  .unsaved / .passwords; every message is recorded in dialogs.msgs.  An
  ask_yes_no or ask_unsaved with no queued answer, or a queued answer no
  prompt used, fails the test.
- The real pointer is never read or moved: every window gets a fixed
  simulated pointer (window centre) that tests may change.
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
os.environ.pop("PK_TITLEBAR", None)
os.environ.pop("PK_ACTION", None)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[2]
SRC = Path(os.environ.get("PAPERKNIFE_SRC", ROOT))
sys.path.insert(0, str(SRC))


from qt_harness import Dialogs, _install, pump, wait_job  # noqa: E402


def remove_home(home: str = _HOME) -> None:
    """Delete the session's temp HOME.  A file a closing worker still holds
    gets a few retries; a folder that survives them is reported, not
    left behind silently."""
    for _ in range(5):
        shutil.rmtree(home, ignore_errors=True)
        if not os.path.exists(home):
            return
        time.sleep(0.2)
    print(f"warning: could not remove the test HOME {home}", file=sys.stderr)


def pytest_sessionfinish(session, exitstatus):
    remove_home()


@pytest.fixture(autouse=True)
def isolated_store(tmp_path_factory, monkeypatch):
    """Per-test prefs.json and recent.json (in a folder of their own, not the
    test's tmp_path, which tests list); PREFS and RECENT restored after."""
    from paperknife import prefs, recent
    store = tmp_path_factory.mktemp("pk-store")
    monkeypatch.setattr(prefs, "PREFS_PATH", store / "prefs.json")
    monkeypatch.setattr(recent, "RECENT_PATH", store / "recent.json")
    saved_prefs = dict(prefs.PREFS._data)
    saved_recent = list(recent.RECENT._entries)
    yield
    prefs.PREFS._data.clear()
    prefs.PREFS._data.update(saved_prefs)
    recent.RECENT._entries = saved_recent


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    import paperknife.qt.tools  # noqa: F401  (registers the Qt pages)
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
    assert not d.unexpected, f"a question with no queued answer: {d.unexpected}"
    assert not d.asks, f"queued ask_yes_no answers no prompt used: {d.asks}"
    assert not d.unsaved, f"queued ask_unsaved answers no prompt used: {d.unsaved}"


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
