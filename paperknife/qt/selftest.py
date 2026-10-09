"""
paperknife.qt.selftest
Check a build from the inside:  PaperKnifePlusPC.exe --selftest <report.txt>

The window opens off-screen, every tool page is built and shown, every
optional library is imported, a PDF is made, saved and read back, and one
line per check goes to the report ("ok ..." / "FAIL ..."), then the app quits.
Exit code 0 only when every check passed.  It catches what a frozen bundle
can lose that the source tree cannot: a module, a Qt plugin, a data file.
"""
from __future__ import annotations

import importlib
import os
import tempfile
import traceback

OPTIONAL = ("docx", "pptx", "openpyxl", "striprtf", "pytesseract")


def run(win, report_path: str) -> int:
    """Run the checks against the shown MainWindow *win*; write *report_path*."""
    from PySide6.QtGui import QImageReader
    from PySide6.QtWidgets import QApplication

    from .pages import QT_PAGES

    lines, failed = [], 0

    def check(name, fn):
        nonlocal failed
        try:
            detail = fn()
            lines.append(f"ok   {name}" + (f": {detail}" if detail else ""))
        except Exception:                       # the report is the point: keep going
            failed += 1
            last = traceback.format_exc().strip().splitlines()[-1]
            lines.append(f"FAIL {name}: {last}")

    def page(tool):
        if not win.open_tool(tool):
            raise RuntimeError("open_tool returned False")
        QApplication.processEvents()
        p = win.current_page()
        if not p.isVisible():
            raise RuntimeError("page not shown")
        return type(p).__name__

    for tool in QT_PAGES:
        check(f"page {tool}", lambda t=tool: page(t))
    for mod in OPTIONAL:
        check(f"import {mod}", lambda m=mod: importlib.import_module(m).__name__ and None)

    def pdf_round_trip():
        import pymupdf as fitz
        path = os.path.join(tempfile.mkdtemp(prefix="pk-selftest-"), "t.pdf")
        doc = fitz.open()
        doc.new_page().insert_text((72, 72), "selftest")
        doc.save(path)
        doc.close()
        with fitz.open(path) as back:
            text = back[0].get_text().strip()
        os.remove(path)
        os.rmdir(os.path.dirname(path))
        if text != "selftest":
            raise RuntimeError(f"read back {text!r}")
        return f"PyMuPDF {fitz.VersionBind}"
    check("PDF save and read", pdf_round_trip)

    def image_formats():
        have = {bytes(f).decode() for f in QImageReader.supportedImageFormats()}
        missing = {"png", "jpg", "svg", "ico"} - have
        if missing:
            raise RuntimeError(f"Qt cannot read {sorted(missing)}")
        return None
    check("Qt image formats", image_formats)

    def platform():
        name = QApplication.platformName()
        if name != "windows":
            raise RuntimeError(f"platform plugin {name!r}, not 'windows'")
        return None
    check("Qt platform", platform)

    with open(report_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + f"\n{'PASS' if not failed else 'FAIL'} "
                f"{len(lines) - failed}/{len(lines)}\n")
    return 1 if failed else 0
