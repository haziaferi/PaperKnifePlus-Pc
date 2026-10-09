"""The shared modules load no user-interface toolkit: the Qt build ships without
tkinter and customtkinter, so anything they import must not pull them in."""
import subprocess
import sys

import pytest

from conftest import SRC

# Every module in paperknife/core is read from the folder, so a new one is
# covered without editing this list (core.settings and core.reader were missed
# while it was kept by hand).
CORE = sorted(f"paperknife.core.{p.stem}" for p in (SRC / "paperknife" / "core").glob("*.py")
              if p.stem != "__init__")
TOOLKIT_FREE = ["paperknife", "paperknife.core", *CORE,
                "paperknife.job_queue", "paperknife.prefs", "paperknife.recent",
                "paperknife.pages", "paperknife.lineart", "paperknife.tool_base"]


def test_every_core_module_is_probed():
    assert {"paperknife.core.settings", "paperknife.core.reader"} <= set(CORE)


@pytest.mark.parametrize("module", TOOLKIT_FREE)
def test_module_imports_without_a_toolkit(module):
    probe = (f"import sys; sys.path.insert(0, {str(SRC)!r}); import {module}; "
             "bad = [m for m in ('tkinter', 'customtkinter', 'tkinterdnd2') if m in sys.modules]; "
             "print(','.join(bad))")
    out = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True,
                         timeout=60)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "", f"{module} loads {out.stdout.strip()}"


# The Qt app's own start-up path (paperknife.qt.__main__.main up to a built and
# shown MainWindow, offscreen, with the event loop not entered): the leaf modules
# above being clean says nothing about what the Qt build itself imports.
_QT_START = (
    "import sys; sys.path.insert(0, {src!r})\n"
    "from PySide6.QtWidgets import QApplication\n"
    "QApplication.exec = lambda self: 0\n"
    "from paperknife.qt.__main__ import main\n"
    "assert main(['paperknife']) == 0\n"
    "bad = [m for m in ('tkinter', 'customtkinter', 'tkinterdnd2') if m in sys.modules]\n"
    "print('TOOLKITS=' + ','.join(bad))\n")


@pytest.mark.xfail(strict=True, reason=(
    "R6-43: the Qt start-up imports paperknife.tools (the TOOLS registry, written in "
    "the CTk tool modules) and paperknife.theme (for __version__), which load tkinter "
    "and customtkinter"))
def test_the_qt_app_starts_without_a_toolkit(tmp_path):
    import os
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", HOME=str(tmp_path),
               USERPROFILE=str(tmp_path), PYTHONUTF8="1")
    env.pop("PK_TITLEBAR", None)
    env.pop("PK_ACTION", None)
    out = subprocess.run([sys.executable, "-c", _QT_START.format(src=str(SRC))],
                         capture_output=True, text=True, timeout=120, env=env)
    assert out.returncode == 0, out.stderr
    loaded = [ln for ln in out.stdout.splitlines() if ln.startswith("TOOLKITS=")]
    assert loaded == ["TOOLKITS="], f"the Qt start-up loads {loaded}"
