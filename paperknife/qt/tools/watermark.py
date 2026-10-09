"""Watermark — a single-file transform (group C): diagonal text on every page."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame
from qfluentwidgets import BodyLabel, LineEdit, PushButton, Slider

from ...core import enhance as core_enhance
from .. import bridge, dialogs
from ..pages import ToolPage, card, file_card, group_title, register_page, setting_row

DEFAULT_COLOR = (128, 128, 128)          # the CTk tool's #808080 swatch


def _hex(rgb) -> str:
    return "#%02x%02x%02x" % rgb


@register_page("WatermarkTool")
class WatermarkPage(ToolPage):
    def __init__(self, tool=None, window=None):
        super().__init__("Watermark", "Stamp a diagonal text watermark across every page",
                         tool=tool, window=window)
        self.file = file_card()
        self.body.addWidget(self.file)
        self.body.addSpacing(16)
        self.body.addWidget(group_title("Watermark"))
        group = card(padding=0)
        self.body.addWidget(group)

        row = setting_row(group, "Watermark text")
        self.text = LineEdit()
        self.text.setPlaceholderText("e.g. DRAFT · CONFIDENTIAL")
        self.text.setMinimumWidth(260)
        row.layout().addWidget(self.text)

        row = setting_row(group, "Font size")
        self.size = Slider(Qt.Horizontal)
        self.size.setRange(18, 120)
        self.size.setValue(60)
        self.size.setMinimumWidth(200)
        self.size_label = BodyLabel("60 pt")
        self.size_label.setFixedWidth(52)
        self.size.valueChanged.connect(lambda v: self.size_label.setText(f"{int(v)} pt"))
        row.layout().addWidget(self.size)
        row.layout().addWidget(self.size_label)

        row = setting_row(group, "Opacity")
        self.opacity = Slider(Qt.Horizontal)
        self.opacity.setRange(5, 100)
        self.opacity.setValue(25)
        self.opacity.setMinimumWidth(200)
        self.opacity_label = BodyLabel("25%")
        self.opacity_label.setFixedWidth(52)
        self.opacity.valueChanged.connect(lambda v: self.opacity_label.setText(f"{int(v)}%"))
        row.layout().addWidget(self.opacity)
        row.layout().addWidget(self.opacity_label)

        row = setting_row(group, "Colour")
        self.color = DEFAULT_COLOR
        self.swatch = QFrame()
        self.swatch.setObjectName("colorSwatch")
        self.swatch.setFixedSize(36, 26)
        self.pick_button = PushButton("Pick…")
        self.pick_button.clicked.connect(self.pick_color)
        row.layout().addWidget(self.swatch)
        row.layout().addWidget(self.pick_button)
        self._show_color()

        self.body.addStretch(1)
        self.primary("Apply Watermark", self.run)

    # ── options ──
    def _show_color(self):
        self.swatch.setStyleSheet(
            f"QFrame#colorSwatch {{ background: {_hex(self.color)}; border-radius: 4px; }}")

    def pick_color(self):
        rgb = dialogs.ask_color(self.color)
        if rgb:
            self.color = rgb
            self._show_color()

    # ── hooks ──
    def open(self):
        self.file.choose()

    # ── the action ──
    def run(self):
        src = self.file.path()
        text = self.text.text().strip()
        if not src:
            return dialogs.warning("Watermark", "Select a PDF first.")
        if not text:
            return dialogs.warning("Watermark", "Enter watermark text.")
        win = self.window_
        doc = win.open_pdf_safe(src)
        if doc is None:
            return
        out = dialogs.ask_save("watermarked.pdf", ".pdf", [("PDF", "*.pdf")])
        if not out:
            return doc.close()
        size = int(self.size.value())
        opacity = self.opacity.value() / 100.0
        color = tuple(c / 255 for c in self.color)

        def work(stop):
            return core_enhance.watermark_pdf(
                doc, out, text, size, opacity, color, stop,
                lambda v: bridge.post(win.set_progress, v)) is not None

        def then(kind, result):
            if kind != "done" or not result:
                return
            win.set_status(f"✓  Watermarked → {Path(out).name}", "success")
            dialogs.info("Done", f"Watermarked PDF saved:\n{out}")

        win.set_status("Applying watermark…")
        if win.run_job(work, "Applying watermark…", then=then) is None:
            doc.close()
