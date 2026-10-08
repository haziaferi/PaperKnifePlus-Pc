"""
paperknife.qt.dialogs
The ONE seam for every dialog the Qt interface shows.

Callers use the module, never the names:
    from paperknife.qt import dialogs
    path = dialogs.ask_open("Open PDF", [("PDF", "*.pdf")])
so tests can monkeypatch these functions (tests/qt/conftest.py does).

filters, wherever taken, is either a Qt filter string ("PDF (*.pdf)") or an
iterable of (label, patterns) pairs in the Tk style ([("PDF", "*.pdf")]);
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


def _start_dir(prefer_output: bool) -> str:
    from ..prefs import PREFS
    out = PREFS.get("output_dir", "")
    if prefer_output and out and os.path.isdir(out):
        return out
    return _last_dir or (out if out and os.path.isdir(out) else "")


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


def _message(kind, title: str, msg: str) -> None:
    box = _fluent_box(title, msg, cancel=None)
    if box is not None:
        box.exec()
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
        return bool(box.exec())
    return QMessageBox.question(None, title, msg) == QMessageBox.Yes


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
    if dlg.exec() and dlg.edit.text():
        return dlg.edit.text()
    return None


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
