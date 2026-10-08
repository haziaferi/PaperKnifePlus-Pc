"""Normalise Pages — a single-file transform (group C): every page onto one paper size."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QButtonGroup
from qfluentwidgets import ComboBox, RadioButton

from ...core import enhance as core_enhance
from .. import bridge, dialogs
from ..pages import ToolPage, card, file_card, group_title, register_page, setting_row

SIZES = ["A4", "A3", "A5", "Letter", "Legal", "Tabloid"]     # the CTk menu's order
ORIENTATIONS = ["Portrait", "Landscape", "Keep original"]
SCALES = [("fit", "Fit", "keep ratio · recommended"),
          ("stretch", "Stretch", "fill page")]


@register_page("NormaliseTool")
class NormalisePage(ToolPage):
    def __init__(self, tool=None, window=None):
        super().__init__("Normalise Pages", "Resize all pages to a standard paper size",
                         tool=tool, window=window)
        self.file = file_card()
        self.body.addWidget(self.file)
        self.body.addSpacing(16)

        self.body.addWidget(group_title("Page size"))
        group = card(padding=0)
        self.body.addWidget(group)
        row = setting_row(group, "Target size")
        self.size = ComboBox()
        self.size.addItems(SIZES)
        self.size.setCurrentText("A4")
        self.size.setMinimumWidth(160)
        row.layout().addWidget(self.size)

        self.body.addWidget(group_title("Orientation"))
        group = card(padding=0)
        self.body.addWidget(group)
        self.orient_group = QButtonGroup(self)
        self.orients: dict[str, RadioButton] = {}
        for val in ORIENTATIONS:
            holder = setting_row(group, val)
            rb = RadioButton("")
            rb.setChecked(val == "Portrait")
            self.orient_group.addButton(rb)
            holder.layout().addWidget(rb)
            self.orients[val] = rb

        self.body.addWidget(group_title("Scale mode"))
        group = card(padding=0)
        self.body.addWidget(group)
        self.scale_group = QButtonGroup(self)
        self.scales: dict[str, RadioButton] = {}
        for val, name, desc in SCALES:
            holder = setting_row(group, name, desc)
            rb = RadioButton("")
            rb.setChecked(val == "fit")
            self.scale_group.addButton(rb)
            holder.layout().addWidget(rb)
            self.scales[val] = rb

        self.body.addStretch(1)
        self.primary("Normalise Pages", self.run)

    @property
    def orient(self) -> str:
        return next(v for v, rb in self.orients.items() if rb.isChecked())

    @property
    def stretch(self) -> bool:
        return self.scales["stretch"].isChecked()

    def open(self):
        self.file.choose()

    def run(self):
        src = self.file.path()
        if not src:
            return dialogs.warning("Normalise", "Select a PDF first.")
        win = self.window_
        doc = win.open_pdf_safe(src)
        if doc is None:
            return
        out = dialogs.ask_save("normalised.pdf", ".pdf", [("PDF", "*.pdf")])
        if not out:
            return doc.close()
        size, orient, stretch = self.size.currentText(), self.orient, self.stretch

        def work(stop):
            return core_enhance.normalise_pdf(doc, out, size, orient, stretch, stop,
                                              lambda v: bridge.post(win.set_progress, v))

        def then(kind, result):
            if kind != "done" or not result:
                return
            win.set_status(f"✓  Normalised → {Path(out).name}", "success")
            dialogs.info("Done", f"Normalised PDF saved:\n{out}")

        if win.run_job(work, "Normalising pages…", then=then) is None:
            doc.close()
