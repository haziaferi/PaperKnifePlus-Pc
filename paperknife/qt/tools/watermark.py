"""Watermark — a single-file transform (group C): diagonal text on every page."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QFrame
from qfluentwidgets import LineEdit, PushButton

from ...core import enhance as core_enhance
from .. import dialogs
from ..pages import (ToolPage, card, file_card, group_title, labelled_slider, register_page,
                     setting_row)

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
        self.size = labelled_slider(row, 18, 120, 60, " pt", width=200, label_width=52,
                                    fixed=False)
        self.size_label = self.size.value_label

        row = setting_row(group, "Opacity")
        self.opacity = labelled_slider(row, 5, 100, 25, "%", width=200, label_width=52,
                                       fixed=False)
        self.opacity_label = self.opacity.value_label

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

    # ── the action ──
    def run(self):
        src = self.chosen_file("Watermark")
        if not src:
            return
        text = self.text.text().strip()
        if not text:
            return dialogs.warning("Watermark", "Enter watermark text.")
        size = int(self.size.value())
        opacity = self.opacity.value() / 100.0
        color = tuple(c / 255 for c in self.color)

        def work(doc, out, stop, progress):
            return core_enhance.watermark_pdf(doc, out, text, size, opacity, color, stop,
                                              progress)

        self.run_on_file(
            "Watermark", work, "Applying watermark…",
            lambda _r, out: ("success", f"✓  Watermarked → {Path(out).name}",
                             "Done", f"Watermarked PDF saved:\n{out}"),
            src=src, save=("watermarked.pdf", ".pdf", [("PDF", "*.pdf")]))
