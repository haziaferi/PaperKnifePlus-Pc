"""PDF → Images — every page as a PNG, bundled in a ZIP (group C)."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from qfluentwidgets import BodyLabel, Slider

from ...core import convert as core_convert
from ...prefs import pref_dpi
from .. import bridge, dialogs
from ..pages import ToolPage, card, file_card, group_title, register_page, setting_row

DPI_RANGE = (72, 300)


@register_page("Pdf2ImgTool")
class Pdf2ImgPage(ToolPage):
    def __init__(self, tool=None, window=None):
        super().__init__("PDF → Images", "Export every page as a PNG · bundled in a ZIP",
                         tool=tool, window=window)
        self.file = file_card()
        self.body.addWidget(self.file)
        self.body.addSpacing(16)
        self.body.addWidget(group_title("Options"))
        group = card(padding=0)
        self.body.addWidget(group)
        row = setting_row(group, "Resolution (DPI)",
                          "72=screen  ·  150=standard  ·  300=print quality")
        self.dpi_slider = Slider(Qt.Horizontal)
        self.dpi_slider.setRange(*DPI_RANGE)
        self.dpi_slider.setFixedWidth(220)
        self.dpi_label = BodyLabel()
        self.dpi_label.setFixedWidth(64)
        self.dpi_slider.valueChanged.connect(lambda v: self.dpi_label.setText(f"{v} DPI"))
        self.dpi_slider.setValue(pref_dpi(*DPI_RANGE))
        self.dpi_label.setText(f"{self.dpi} DPI")
        row.layout().addWidget(self.dpi_slider)
        row.layout().addWidget(self.dpi_label)
        self.body.addStretch(1)
        self.primary("Export as ZIP", self.run)

    @property
    def dpi(self) -> int:
        return int(self.dpi_slider.value())

    def open(self):
        self.file.choose()

    def run(self):
        src = self.file.path()
        if not src:
            return dialogs.warning("Export", "Select a PDF first.")
        dpi = self.dpi
        win = self.window_
        doc = win.open_pdf_safe(src)
        if doc is None:
            return
        out = dialogs.ask_save("pages.zip", ".zip", [("ZIP", "*.zip")])
        if not out:
            return doc.close()
        total = len(doc)

        def work(stop):
            # PNG pages in a ZIP, written atomically; closes doc; False if cancelled.
            return core_convert.pdf_to_doc(
                doc, "PNG", out, stop, lambda v: bridge.post(win.set_progress, v), dpi=dpi)

        def then(kind, ok):
            if kind != "done" or not ok:
                return
            win.set_status(f"✓  Exported {total} pages → {Path(out).name}", "success")
            dialogs.info("Done", f"Exported {total} pages to:\n{out}")

        win.set_status("Exporting pages…")
        if win.run_job(work, "Exporting pages to PNG…", then=then) is None:
            doc.close()
