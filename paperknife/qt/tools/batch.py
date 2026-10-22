"""Batch — a collection (group D): one operation applied to every PDF in a folder.

Prototype C (PK_BATCH=C, owner 2026-10-18): the operation is one of the four
tools, chosen in radio rows, with that tool's own full settings under them
(qt/tool_options panels) instead of the reduced copies."""
from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtWidgets import QVBoxLayout, QWidget
from qfluentwidgets import CaptionLabel, ComboBox, LineEdit, PushButton

from ...core import batch as core
from ...core import ocr as core_ocr
from ...prefs import DPI_RANGE, PREFS, pref_dpi
from .. import dialogs
from ..folder_mode import run_over_folder
from ..pages import (CollectionPage, LanguagePicker, batch_prototype, card, group_title,
                     labelled_slider, radio_rows, register_page, spin_box)
from ..tool_options import PANELS
from .compress import LEVELS

# Prototype C's operations: the tools, each with the line its screen shows.
TOOLS_C = [
    ("compress", "Compress", "Reduce file size by cleaning streams and downsampling images"),
    ("watermark", "Watermark", "Stamp a diagonal text watermark across every page"),
    ("ocr", "OCR", "Make a scanned or image-only PDF searchable · powered by Tesseract"),
    ("other", "PDF → Other", "Export to TXT · HTML · DOCX · PPTX · XLSX · XML · RTF · PNG · JPEG"),
]

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
        self.mode = batch_prototype()
        self.panels: dict = {}

        self.settings.addWidget(group_title("Operation"))
        group = card(padding=0)
        self.settings.addWidget(group)
        if self.mode == "C":
            self.tool_group = radio_rows(group, TOOLS_C, "compress", row=self.setting_row,
                                         parent=self)
            self.tool_radios = self.tool_group.buttons
        else:
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
        if self.mode == "C":
            for key, (cls, _label) in PANELS.items():
                self.panels[key] = cls(self.settings, self.setting_row, parent=self)
            self.tool_group.buttonToggled.connect(lambda *_: self._tool_changed())
            self._tool_changed()
        else:
            self._op_changed(self.op.currentText())
            self.op.currentTextChanged.connect(self._op_changed)
        self.settings.addStretch(1)
        self.primary("Run Batch", self.run)

    # ── folders ──
    def _folder_row(self, group, name, title, setter) -> CaptionLabel:
        row = self.setting_row(group, name, NOT_SET, path=True)
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
    def _tool_changed(self):
        """Prototype C: the chosen tool's panel shows, the others do not."""
        chosen = self.tool_group.value()
        for key, panel in self.panels.items():
            panel.box.setVisible(key == chosen)

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
            lang = LanguagePicker()
            row.layout().addWidget(lang)
            self.controls["lang"] = lang
            row = self.setting_row(group, "DPI")
            lo, hi = DPI_RANGE
            dpi = spin_box(lo, hi, pref_dpi(lo, hi, "ocr_dpi"), width=120)
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
            elif key == "lang":
                opts[key] = w.text().strip()
            elif isinstance(w, LineEdit):
                opts[key] = w.text()
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
        in_dir, out_dir = self.in_dir, self.out_dir
        if not in_dir or not out_dir:
            return dialogs.warning("Batch", "Set input and output folders.")
        if self._busy():
            return None
        files = self.refill()
        if not files:
            return dialogs.warning("Batch", "No PDF files found in input folder.")
        if self.mode == "C":
            key = self.tool_group.value()
            panel = self.panels[key]
            refused = panel.check()
            if refused:
                return dialogs.warning("Batch", refused)
            raw, fn, op = panel.options(), core.TOOL_OPS[key], PANELS[key][1]
        else:
            op = self.op.currentText()
            raw, fn = self.options(), core.OPS[op]
        try:
            opts = core.validate_options(raw)
        except ValueError as e:
            return dialogs.warning("Batch", str(e))
        if opts.get("lang"):
            core_ocr.remember_lang(opts["lang"])     # the next default (owner, 2026-10-22)
        run_over_folder(self.window_, files, list(self.rows), self._note, fn, out_dir, opts,
                        f"Batch {op}", self.clear_document)

    def clear_document(self):
        self._set_in_dir("")
