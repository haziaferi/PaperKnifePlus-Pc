"""
Harness for the core, logic and packaging tests (the Qt pages have their own,
tests/qt/conftest.py; the two folders are collected in separate runs).

- HOME/USERPROFILE point at a temp folder before paperknife is imported,
  so prefs.json / recent.json never touch the user's real profile; the
  folder is removed at session end, whether the tests passed or not.
- PAPERKNIFE_SRC=<dir> runs the suite against another source tree
  (used to prove a test fails on the baseline before a fix).
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

_HOME = tempfile.mkdtemp(prefix="pk-home-")
os.environ["HOME"] = _HOME
os.environ["USERPROFILE"] = _HOME

ROOT = Path(__file__).resolve().parents[1]
SRC = Path(os.environ.get("PAPERKNIFE_SRC", ROOT))
sys.path.insert(0, str(SRC))


def pytest_sessionfinish(session, exitstatus):
    # Retry briefly for a file a closing worker still holds, and say so rather
    # than leave the folder silently.
    for _ in range(5):
        shutil.rmtree(_HOME, ignore_errors=True)
        if not os.path.exists(_HOME):
            return
        time.sleep(0.2)
    print(f"warning: could not remove the test HOME {_HOME}", file=sys.stderr)


def make_pdf(path, pages: int = 3, text: str = "Page {n}", **page_kw) -> str:
    import pymupdf as fitz
    doc = fitz.open()
    for i in range(pages):
        p = doc.new_page(**page_kw)
        p.insert_text((72, 100), text.format(n=i + 1), fontsize=14)
    doc.save(str(path))
    doc.close()
    return str(path)
