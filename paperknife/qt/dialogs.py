"""
paperknife.qt.dialogs
The ONE seam for every dialog the Qt interface shows.

Callers use the module, never the names:
    from paperknife.qt import dialogs
    path = dialogs.ask_open("Open PDF", [("PDF", "*.pdf")])
so tests can monkeypatch these functions (tests/qt/conftest.py does).

filters, wherever taken, is either a Qt filter string ("PDF (*.pdf)") or an
iterable of (label, patterns) pairs ([("PDF", "*.pdf")]);
"All files (*.*)" is appended to a pair list.
"""
from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QApplication, QColorDialog, QFileDialog, QLineEdit,
                               QMessageBox, QWidget)
from qfluentwidgets import (BodyLabel, MessageBox, MessageBoxBase, PasswordLineEdit,
                            SubtitleLabel)

_last_dir = ""          # the folder of the last file chosen, for the next dialog
_doc_dir = ""           # the current document's folder, when nothing else is known


# ── Helpers ───────────────────────────────────────────────────────────────────
def _parent() -> QWidget | None:
    w = QApplication.activeWindow()
    if w is not None:
        return w
    for top in QApplication.topLevelWidgets():
        if top.isWindow() and top.isVisible() and type(top).__name__ == "MainWindow":
            return top
    return None


def qt_filters(filters) -> str:
    if not filters:
        return "All files (*.*)"
    if isinstance(filters, str):
        return filters
    parts = [f"{label} ({pattern})" for label, pattern in filters]
    if not any("*.*" in p for p in parts):
        parts.append("All files (*.*)")
    return ";;".join(parts)


def _remember(path: str) -> None:
    global _last_dir
    if path:
        _last_dir = str(Path(path).parent if not os.path.isdir(path) else Path(path))


def note_document(path: str | None) -> None:
    """The current document changed: its folder is where a dialog starts when no
    other folder is known (a file opened from Recent files set none, and the first
    Save as opened in the app's own working folder, 2026-10-22)."""
    global _doc_dir
    _doc_dir = str(Path(path).parent) if path else ""


def _start_dir(prefer_output: bool) -> str:
    from ..prefs import PREFS
    out = PREFS.get("output_dir", "")
    if prefer_output and out and os.path.isdir(out):
        return out
    return (_last_dir or (out if out and os.path.isdir(out) else "")
            or (_doc_dir if _doc_dir and os.path.isdir(_doc_dir) else ""))


# ── Files and folders ─────────────────────────────────────────────────────────
def ask_open(title: str = "Open file", filters=None) -> str:
    """One existing file, or "" when cancelled."""
    path, _ = QFileDialog.getOpenFileName(_parent(), title, _start_dir(False),
                                          qt_filters(filters))
    _remember(path)
    return path or ""


def ask_open_many(title: str = "Open files", filters=None) -> list[str]:
    """Several existing files in the order chosen, or [] when cancelled."""
    paths, _ = QFileDialog.getOpenFileNames(_parent(), title, _start_dir(False),
                                            qt_filters(filters))
    if paths:
        _remember(paths[0])
    return list(paths or [])


def ask_save(default_name: str = "output.pdf", ext: str = ".pdf", filters=None) -> str:
    """A path to write, or "" when cancelled.  Starts in PREFS.output_dir when
    that is set; *ext* is added when the name typed has no extension."""
    filters = filters or [(ext.lstrip(".").upper(), f"*{ext}")]
    start = _start_dir(True)
    initial = os.path.join(start, default_name) if start else default_name
    path, _ = QFileDialog.getSaveFileName(_parent(), "Save as", initial, qt_filters(filters))
    if path and ext and not Path(path).suffix:
        path += ext
    _remember(path)
    return path or ""


def ask_print(printer, pages: int) -> bool:
    """Windows' print dialog for *printer*, pages 1..*pages* offered as its
    range; whether Print was pressed (the printer then holds the choices)."""
    from PySide6.QtPrintSupport import QAbstractPrintDialog, QPrintDialog
    dlg = QPrintDialog(printer, _parent())
    dlg.setMinMax(1, max(1, pages))
    dlg.setOption(QAbstractPrintDialog.PrintPageRange, True)
    dlg.setOption(QAbstractPrintDialog.PrintToFile, False)
    return dlg.exec() == QPrintDialog.Accepted


def ask_dir(title: str = "Choose output folder") -> str:
    """An existing folder, or "" when cancelled."""
    path = QFileDialog.getExistingDirectory(_parent(), title, _start_dir(True))
    if path:
        global _last_dir
        _last_dir = path
    return path or ""


def ask_color(initial=(255, 255, 0)):
    """(r, g, b) ints 0-255, or None when cancelled.  initial: (r, g, b),
    a hex string or a QColor."""
    if isinstance(initial, (tuple, list)):
        start = QColor(*[int(v) for v in initial[:3]])
    else:
        start = QColor(initial)
    c = QColorDialog.getColor(start, _parent(), "Choose colour")
    if not c.isValid():
        return None
    return (c.red(), c.green(), c.blue())


# ── Messages ──────────────────────────────────────────────────────────────────
def _fluent_box(title: str, msg: str, *, cancel: str | None, yes: str = "OK"):
    """A qfluentwidgets MessageBox over the main window; None when there is
    no window to lay it over (the mask dialog needs a parent)."""
    parent = _parent()
    if parent is None:
        return None
    box = MessageBox(title, msg, parent)
    box.yesButton.setText(yes)
    if cancel is None:
        box.hideCancelButton()
    else:
        box.cancelButton.setText(cancel)
    return box


def _exec_once(box) -> int:
    """exec() a dialog parented to the main window, then delete it: a closed
    box must not stay behind as a hidden child for the whole session."""
    try:
        return box.exec()
    finally:
        box.deleteLater()


def _message(kind, title: str, msg: str) -> None:
    box = _fluent_box(title, msg, cancel=None)
    if box is not None:
        _exec_once(box)
        return
    {"info": QMessageBox.information, "warning": QMessageBox.warning,
     "error": QMessageBox.critical}[kind](None, title, msg)


def info(title: str, msg: str) -> None:
    _message("info", title, msg)


def warning(title: str, msg: str) -> None:
    _message("warning", title, msg)


def error(title: str, msg: str) -> None:
    _message("error", title, msg)


def ask_yes_no(title: str, msg: str) -> bool:
    box = _fluent_box(title, msg, cancel="No", yes="Yes")
    if box is not None:
        return bool(_exec_once(box))
    return QMessageBox.question(None, title, msg) == QMessageBox.Yes


def ask_unsaved(name: str) -> str:
    """"Save changes to <name>?" with Save / Discard / Cancel: "save",
    "discard" or "cancel" (also when the box is closed)."""
    title = f"Save changes to {name}?"
    box = _fluent_box(title, "", cancel="Cancel", yes="Save")
    if box is None:
        r = QMessageBox.question(None, title, "", QMessageBox.Save | QMessageBox.Discard
                                 | QMessageBox.Cancel)
        return {QMessageBox.Save: "save", QMessageBox.Discard: "discard"}.get(r, "cancel")
    from PySide6.QtCore import Qt
    from qfluentwidgets import PushButton
    discard = PushButton("Discard", box.buttonGroup)
    discard.clicked.connect(lambda: box.done(2))
    box.buttonLayout.insertWidget(1, discard, 1, Qt.AlignVCenter)
    return {1: "save", 2: "discard"}.get(_exec_once(box), "cancel")


RECOVER_TITLE = "Recover unsaved changes?"
RECOVER_TEXT = "PaperKnife+ closed before these were saved:"


def ask_recover(lines: list[str]) -> bool | None:
    """At start, the edits an app that did not close left (owner's choice
    2026-10-12): *lines* ("report.pdf — Find & Replace, 14:32") under
    RECOVER_TEXT, with Discard / Recover.  True: Recover; False: Discard;
    None: the box was closed, the copies wait for the next start."""
    msg = RECOVER_TEXT + "\n" + "\n".join(f"    {s}" for s in lines)
    box = _fluent_box(RECOVER_TITLE, msg, cancel=None, yes="Recover")
    if box is None:
        r = QMessageBox.question(None, RECOVER_TITLE, msg, QMessageBox.Discard | QMessageBox.Yes)
        return {QMessageBox.Yes: True, QMessageBox.Discard: False}.get(r)
    from PySide6.QtCore import Qt
    from qfluentwidgets import PushButton
    discard = PushButton("Discard", box.buttonGroup)
    discard.clicked.connect(lambda: box.done(2))
    box.buttonLayout.insertWidget(0, discard, 1, Qt.AlignVCenter)
    return {1: True, 2: False}.get(_exec_once(box))


# ── Password ──────────────────────────────────────────────────────────────────
def ask_password(title: str = "Password required",
                 prompt: str = "This PDF is password-protected. Enter the password:"):
    """The password typed, or None when cancelled or left empty."""
    parent = _parent()
    if parent is None:
        from PySide6.QtWidgets import QInputDialog
        text, ok = QInputDialog.getText(None, title, prompt, QLineEdit.Password)
        return text if ok and text else None
    dlg = _PasswordDialog(title, prompt, parent)
    text = ""
    try:
        if _exec_once(dlg):
            text = dlg.edit.text()
    finally:
        # Emptied as well as deleted: no typed password stays behind.
        dlg.edit.clear()
    return text or None


class _PasswordDialog(MessageBoxBase):
    def __init__(self, title, prompt, parent):
        super().__init__(parent)
        self.viewLayout.addWidget(SubtitleLabel(title, self))
        self.viewLayout.addWidget(BodyLabel(prompt, self))
        self.edit = PasswordLineEdit(self)
        self.edit.setMinimumWidth(320)
        self.edit.returnPressed.connect(self.yesButton.click)
        self.viewLayout.addWidget(self.edit)
        self.yesButton.setText("Open")
        self.cancelButton.setText("Cancel")
        self.edit.setFocus()
