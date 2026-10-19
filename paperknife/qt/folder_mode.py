"""A folder of PDFs as a tool's input (Batch prototypes, owner 2026-10-18).

run_over_folder: the batch loop, one file after another with each file's
result beside it (Batch's, shared by its prototypes A and C and by B).

FolderMode (prototype B): a "One file | A folder" switch at the left of a
page's document bar.  A folder replaces the page's centre (its page grid,
or Compress's file target) with the folder rows (Input folder, Output
folder) and the folder's file list; the page's own main action then runs on
every PDF in it with the page's own settings (tool_options panels)."""
from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QVBoxLayout, QWidget
from qfluentwidgets import PushButton, SegmentedWidget, SingleDirectionScrollArea

from ..core import batch as core
from . import bridge, dialogs
from .pages import CollectionRow, card, group_title, muted_caption, plain_card, setting_row

NOT_SET = "Not set…"
EMPTY_TEXT = ("Choose an input folder: its PDFs are listed here, "
              "and each file's result appears beside it during the run.")
ONE_FILE, A_FOLDER = "One file", "A folder"


def folder_pdfs(folder: str) -> list[str]:
    return (sorted(str(p) for p in Path(folder).glob("*.pdf"))
            if folder and os.path.isdir(folder) else [])


def run_over_folder(win, files, rows, note, fn, out_dir, opts, label, on_done):
    """Run fn(src, out_dir, opts, stop) on each of *files* in a job; note(row,
    text, role) shows each file's result on its row; on_done() after a run
    that went through every file (not after Cancel)."""
    finished: list = []

    def work(stop):
        ok = err = done = 0
        n_files = len(files)
        for i, (src, row) in enumerate(zip(files, rows, strict=True)):
            if stop.is_set():
                break
            name = Path(src).name
            bridge.post(note, row, f"⏳  {name}", "muted")
            bridge.post(win.set_progress, (i + 1) / n_files)
            try:
                if fn(src, out_dir, opts, stop):
                    ok += 1
                    bridge.post(note, row, f"✓  {name}", "success")
                else:
                    bridge.post(note, row, f"—  {name}  (cancelled)", "warning")
            except Exception as e:
                err += 1
                bridge.post(note, row, f"✗  {name}  — {e}", "danger")
            done = i + 1
        if stop.is_set():
            msg, role = (f"Batch cancelled after {done} of {n_files} file(s) — "
                         f"{ok} OK, {err} errors"), "warning"
        else:
            msg, role = (f"✓  Batch done — {ok} OK, {err} errors",
                         "success" if not err else "warning")
            finished.append(True)
        bridge.post(win.set_status, msg, role)

    def then(kind, _value):
        # A finished batch empties the list and its input folder (owner);
        # a cancelled one keeps them with each file's result.
        if kind == "done" and finished:
            on_done()

    win.set_status(f"{label} on {len(files)} file(s)…")
    return win.run_job(work, f"{label} · {len(files)} file(s)…", then=then)


class FolderPanel(QWidget):
    """The folder rows and the folder's file list (prototype B)."""

    def __init__(self, page, row=setting_row):
        super().__init__()
        self.page = page
        self.in_dir = self.out_dir = ""
        self.rows: list[CollectionRow] = []
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)
        v.addWidget(group_title("Folders"))
        group = card(padding=0)
        v.addWidget(group)
        self.in_label = self._folder_row(group, row, "Input folder", "Choose input folder",
                                         self.set_in_dir)
        self.out_label = self._folder_row(group, row, "Output folder", "Choose output folder",
                                          self.set_out_dir)
        self.list_card = plain_card()
        # Room for three files where the page gives it no height of its own
        # (Compress's body); the page grid's place gives it more.
        self.list_card.setMinimumHeight(3 * 52 + 24)
        lv = QVBoxLayout(self.list_card)
        lv.setContentsMargins(8, 8, 8, 8)
        area = SingleDirectionScrollArea(self.list_card, Qt.Vertical)
        area.setWidgetResizable(True)
        area.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        self.list_v = QVBoxLayout(inner)
        self.list_v.setContentsMargins(0, 0, 0, 0)
        self.list_v.setSpacing(2)
        self.empty_label = muted_caption(EMPTY_TEXT)
        self.empty_label.setWordWrap(True)
        self.list_v.addWidget(self.empty_label)
        self.list_v.addStretch(1)
        area.setWidget(inner)
        lv.addWidget(area)
        v.addWidget(self.list_card, 1)

    def _folder_row(self, group, row, name, title, setter):
        r = row(group, name, NOT_SET, path=True)
        btn = PushButton("Browse…")
        btn.clicked.connect(lambda: self.pick(title, setter))
        r.layout().addWidget(btn)
        return r.desc_label

    def pick(self, title, setter):
        d = dialogs.ask_dir(title)
        if d:
            setter(d)

    def set_in_dir(self, d: str):
        self.in_dir = str(d)
        self.in_label.setText(self.in_dir or NOT_SET)
        self.refill()

    def set_out_dir(self, d: str):
        self.out_dir = str(d)
        self.out_label.setText(self.out_dir or NOT_SET)

    def refill(self) -> list[str]:
        for r in self.rows:
            r.hide()
            self.list_v.removeWidget(r)
            r.deleteLater()
        self.rows = []
        files = folder_pdfs(self.in_dir)
        for i, f in enumerate(files):
            r = CollectionRow(self, f)
            r.set_number(i + 1)
            self.list_v.insertWidget(self.list_v.count() - 1, r)
            self.rows.append(r)
        self.empty_label.setVisible(not files)
        return files

    def select(self, _i):
        pass                            # the list is the folder's content

    def note(self, row, text, role):
        if row in self.rows:            # the list may have been refilled meanwhile
            row.set_note(text, role)

    def paths(self) -> list[str]:
        return [r.path for r in self.rows]


class FolderMode:
    """Prototype B on *page*: the switch in its document bar and the folder
    panel in place of *centre* (hidden while a folder is the input), put in
    *layout* at *centre*'s place.  *panel*: the page's tool_options panel;
    *key*: its core.batch.TOOL_OPS key; *label*: the run's label."""

    def __init__(self, page, panel, key: str, label: str, layout, centre, *, row=setting_row,
                 hide=()):
        self.page, self.panel, self.key, self.label = page, panel, key, label
        self.centre, self.hide = centre, tuple(hide)
        self.on = False
        self.switch = SegmentedWidget(page.doc_bar)
        self.switch.addItem("file", ONE_FILE, lambda: self.set_folder(False))
        self.switch.addItem("folder", A_FOLDER, lambda: self.set_folder(True))
        self.switch.setCurrentItem("file")
        page.doc_bar.layout().insertWidget(0, self.switch, 0, Qt.AlignLeft | Qt.AlignVCenter)
        self.folder = FolderPanel(page, row)
        self.folder.hide()
        layout.insertWidget(layout.indexOf(centre), self.folder, 1)
        page._folder_mode = self

    def set_folder(self, on: bool):
        self.on = on
        page = self.page
        self.switch.setCurrentItem("folder" if on else "file")
        self.folder.setVisible(on)
        self.centre.setVisible(not on and self._centre_wanted())
        for w in self.hide:
            if w is not None:
                w.setVisible(not on)
        db = page.doc_bar
        db.open_control.setVisible(not on)
        db.chip.setVisible(not on)
        for b in page._buttons:
            if getattr(b, "pk_primary", False):
                b.setEnabled(True if on else b.isEnabled())
        if not on and hasattr(page, "_selection_changed"):
            page._selection_changed()
        if not on and hasattr(page, "refresh_document"):
            page.refresh_document()

    def _centre_wanted(self) -> bool:
        # The drop target shows only while there is no document (its own rule).
        page = self.page
        if self.centre is getattr(page, "drop_target", None):
            return not page.document_path()
        return True

    def accept_drop(self, path: str) -> bool:
        if os.path.isdir(path):
            self.set_folder(True)
            self.folder.set_in_dir(path)
            return True
        return False

    def run(self) -> bool:
        """The page's main action while a folder is its input; whether it ran here."""
        if not self.on:
            return False
        f = self.folder
        if not f.in_dir or not f.out_dir:
            dialogs.warning(self.label, "Set input and output folders.")
            return True
        win = self.page.window_
        if win.job_running():
            from .shell import BUSY_MSG
            dialogs.warning("Busy", BUSY_MSG)
            return True
        files = f.refill()
        if not files:
            dialogs.warning(self.label, "No PDF files found in input folder.")
            return True
        refused = self.panel.check()
        if refused:
            dialogs.warning(self.label, refused)
            return True
        try:
            opts = core.validate_options(self.panel.options())
        except ValueError as e:
            dialogs.warning(self.label, str(e))
            return True
        run_over_folder(win, files, list(f.rows), f.note, core.TOOL_OPS[self.key], f.out_dir,
                        opts, self.label, lambda: f.set_in_dir(""))
        return True
