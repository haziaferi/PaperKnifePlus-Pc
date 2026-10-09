"""Batch — a collection (group D): one operation applied to every PDF in a folder."""
from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtWidgets import QVBoxLayout, QWidget
from qfluentwidgets import CaptionLabel, ComboBox, LineEdit, PushButton

from ...core import batch as core
from ...prefs import DPI_RANGE, PREFS, pref_dpi
from .. import bridge, dialogs
from ..pages import (CollectionPage, card, group_title, labelled_slider, radio_rows,
                     register_page, spin_box)
from .compress import LEVELS

EMPTY_TEXT = ("Choose an input folder: its PDFs are listed here, "
              "and each file's result appears beside it during the run.")
NOT_SET = "Not set…"


@register_page("BatchTool")
class BatchPage(CollectionPage):
    def __init__(self, tool=None, window=None):
        super().__init__("Batch", "Apply one operation to every PDF in a folder",
                         tool=tool, window=window, toolbar=False, empty_text=EMPTY_TEXT)
        self.in_dir = ""
        self.out_dir = ""
        self.controls: dict[str, QWidget] = {}

        self.settings.addWidget(group_title("Operation"))
        group = card(padding=0)
        self.settings.addWidget(group)
        row = self.setting_row(group, "Operation")
        self.op = ComboBox()
        self.op.addItems(list(core.OPS.keys()))
        self.op.setCurrentText("Compress")
        self.op.setMinimumWidth(150)
        row.layout().addWidget(self.op)

        self.settings.addWidget(group_title("Folders"))
        group = card(padding=0)
        self.settings.addWidget(group)
        self.in_label = self._folder_row(group, "Input folder", "Choose input folder",
                                         self._set_in_dir)
        self.out_label = self._folder_row(group, "Output folder", "Choose output folder",
                                          self._set_out_dir)

        self.opts_box = None
        self._op_changed(self.op.currentText())
        self.op.currentTextChanged.connect(self._op_changed)
        self.settings.addStretch(1)
        self.primary("Run Batch", self.run)

    # ── folders ──
    def _folder_row(self, group, name, title, setter) -> CaptionLabel:
        row = self.setting_row(group, name, NOT_SET)
        btn = PushButton("Browse…")
        btn.clicked.connect(lambda: self._pick_dir(title, setter))
        row.layout().addWidget(btn)
        return row.desc_label

    def _pick_dir(self, title, setter):
        if setter == self._set_in_dir and self._busy():
            return                      # a new input folder would refill the list
        d = dialogs.ask_dir(title)
        if d:
            setter(d)

    def _set_in_dir(self, d: str):
        self.in_dir = str(d)
        self.in_label.setText(self.in_dir or NOT_SET)
        self.refill()

    def _set_out_dir(self, d: str):
        self.out_dir = str(d)
        self.out_label.setText(self.out_dir or NOT_SET)

    def refill(self) -> list[str]:
        """List the input folder's PDFs (what a run works on)."""
        self.clear_rows()
        files = (sorted(str(p) for p in Path(self.in_dir).glob("*.pdf"))
                 if self.in_dir and os.path.isdir(self.in_dir) else [])
        self.add_paths(files)
        return files

    # ── options ──
    def _op_changed(self, op: str):
        if self.opts_box is not None:
            self.opts_box.hide()
            self.settings.removeWidget(self.opts_box)
            self.opts_box.setParent(None)
            self.opts_box.deleteLater()
        self.controls = {}
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)
        idx = self.settings.count() - (1 if self.opts_box is not None else 0)
        self.opts_box = box
        self.settings.insertWidget(idx, box)
        if op == "PDF → TXT":           # no options
            return
        v.addWidget(group_title(f"Options — {op}"))
        group = card(padding=0)
        v.addWidget(group)
        if op == "Compress":
            self.level_group = radio_rows(group, LEVELS, PREFS.compress_level or "medium",
                                          row=self.setting_row, parent=box)
            self.radios = self.level_group.buttons
            self.controls["level"] = self.level_group
        elif op == "Watermark":
            row = self.setting_row(group, "Text")
            text = LineEdit()
            text.setText("DRAFT")
            text.setFixedWidth(150)
            row.layout().addWidget(text)
            self.controls["text"] = text
            row = self.setting_row(group, "Size")
            size = spin_box(1, 999, 60, width=120)
            row.layout().addWidget(size)
            self.controls["size"] = size
            row = self.setting_row(group, "Opacity")
            opacity = labelled_slider(row, 1, 100, 25, "%", width=110, label_width=40,
                                      fixed=False)
            self.controls["opacity"] = opacity
        elif op == "OCR":
            row = self.setting_row(group, "Language")
            lang = LineEdit()
            lang.setPlaceholderText("eng")
            lang.setText(PREFS.ocr_lang or "eng")
            lang.setFixedWidth(120)
            row.layout().addWidget(lang)
            self.controls["lang"] = lang
            row = self.setting_row(group, "DPI")
            lo, hi = DPI_RANGE
            dpi = spin_box(lo, hi, pref_dpi(lo, hi), width=120)
            row.layout().addWidget(dpi)
            self.controls["dpi"] = dpi

    def options(self) -> dict:
        """The chosen operation's options, as core.batch's workers take them."""
        opts = {}
        for key, w in self.controls.items():
            if key == "level":
                opts[key] = w.value()
            elif key == "opacity":
                opts[key] = w.value() / 100.0
            elif isinstance(w, LineEdit):
                opts[key] = w.text().strip() if key == "lang" else w.text()
            else:
                opts[key] = int(w.value())
        if opts.get("lang") == "":
            opts["lang"] = "eng"
        return opts

    # ── shell hooks ──
    def _busy(self) -> bool:
        """A batch (or another job) is running: say so instead of refilling
        the list, which holds the running batch's per-file results."""
        win = self.window_
        if win is not None and win.job_running():
            from ..shell import BUSY_MSG
            dialogs.warning("Busy", BUSY_MSG)
            return True
        return False

    def open(self):
        self._pick_dir("Choose input folder", self._set_in_dir)

    def accept_drop(self, path: str) -> bool:
        """A dropped folder becomes the input folder; files are refused."""
        if os.path.isdir(path):
            if not self._busy():
                self._set_in_dir(path)
            return True
        return False

    def delete(self):
        pass                            # the list is the folder's content

    # ── run ──
    def _note(self, row, text, role):
        if row in self.rows:            # the list may have been refilled meanwhile
            row.set_note(text, role)

    def run(self):
        in_dir, out_dir, op = self.in_dir, self.out_dir, self.op.currentText()
        if not in_dir or not out_dir:
            return dialogs.warning("Batch", "Set input and output folders.")
        if self._busy():
            return None
        files = self.refill()
        if not files:
            return dialogs.warning("Batch", "No PDF files found in input folder.")
        try:
            opts = core.validate_options(self.options())
        except ValueError as e:
            return dialogs.warning("Batch", str(e))
        fn = core.OPS[op]
        win = self.window_
        rows = list(self.rows)

        def work(stop):
            ok = err = done = 0
            n_files = len(files)
            for i, (src, row) in enumerate(zip(files, rows, strict=True)):
                if stop.is_set():
                    break
                name = Path(src).name
                bridge.post(self._note, row, f"⏳  {name}", "muted")
                bridge.post(win.set_progress, (i + 1) / n_files)
                try:
                    if fn(src, out_dir, opts, stop):
                        ok += 1
                        bridge.post(self._note, row, f"✓  {name}", "success")
                    else:
                        bridge.post(self._note, row, f"—  {name}  (cancelled)", "warning")
                except Exception as e:
                    err += 1
                    bridge.post(self._note, row, f"✗  {name}  — {e}", "danger")
                done = i + 1
            if stop.is_set():
                msg, role = (f"Batch cancelled after {done} of {n_files} file(s) — "
                             f"{ok} OK, {err} errors"), "warning"
            else:
                msg, role = (f"✓  Batch done — {ok} OK, {err} errors",
                             "success" if not err else "warning")
            bridge.post(win.set_status, msg, role)

        win.set_status(f"Batch {op} on {len(files)} file(s)…")
        win.run_job(work, f"Batch {op} · {len(files)} file(s)…")
