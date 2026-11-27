"""The settings of Compress, Watermark, OCR and PDF → Other as panels of their
own (Batch prototypes B and C, owner 2026-10-18): each tool's screen builds
its settings from its panel, and a folder of PDFs gets the same settings.

A panel builds its group titles and cards into a box (self.box) added to a
column's layout, with the column's own setting_row; options() gives what
core.batch.TOOL_OPS takes; check() the message that refuses a run, or None.

    PANELS  tool key -> (panel class, label)"""
from __future__ import annotations

from PySide6.QtWidgets import QFrame, QVBoxLayout, QWidget
from qfluentwidgets import CaptionLabel, ComboBox, LineEdit, PushButton

from ..core import convert as core_convert
from ..prefs import _DEFAULTS, PREFS, pref_dpi
from . import dialogs, theme
from .pages import CHOOSE_COLOUR, LanguagePicker, card, group_title, number_box, radio_rows


class Panel:
    """A tool's settings in a box of their own."""
    key = ""

    def __init__(self, layout, row, parent=None):
        self.row = row
        self.box = QWidget(parent)
        self.v = QVBoxLayout(self.box)
        self.v.setContentsMargins(0, 0, 0, 0)
        self.v.setSpacing(max(0, layout.spacing()))
        layout.addWidget(self.box)
        self.build()

    def build(self):
        raise NotImplementedError

    def options(self) -> dict:
        return {}

    def check(self) -> str | None:
        return None


# ── Compress ──────────────────────────────────────────────────────────────────
LEVELS = [
    ("light", "Light", "Clean and deflate only. Safe for every file."),
    ("medium", "Medium", "Also resample images to 150 DPI, JPEG quality 80%."),
    ("aggressive", "Aggressive", "Also scale images to 96 DPI. Visible quality loss."),
]


class CompressOptions(Panel):
    key = "compress"

    def build(self):
        self.v.addWidget(group_title("Compression level"))
        group = card(padding=0)
        self.v.addWidget(group)
        self.level_group = radio_rows(group, LEVELS, PREFS.compress_level or "medium",
                                      row=self.row, parent=self.box)
        self.radios = self.level_group.buttons

    def options(self) -> dict:
        return {"level": self.level_group.value()}


# ── Watermark ─────────────────────────────────────────────────────────────────
DEFAULT_COLOR = (128, 128, 128)


def _hex(rgb) -> str:
    return "#%02x%02x%02x" % rgb


class WatermarkOptions(Panel):
    key = "watermark"

    def build(self):
        self.v.addWidget(group_title("Watermark"))
        group = card(padding=0)
        self.v.addWidget(group)

        row = self.row(group, "Watermark text")
        self.text = LineEdit()
        self.text.setPlaceholderText("e.g. DRAFT · CONFIDENTIAL")
        self.text.setMinimumWidth(180)
        row.layout().addWidget(self.text)

        row = self.row(group, "Font size")
        self.size = number_box(row, 18, 120, 60, " pt")

        row = self.row(group, "Opacity")
        self.opacity = number_box(row, 5, 100, 25, "%")

        row = self.row(group, "Colour")
        self.color = DEFAULT_COLOR
        self.swatch = QFrame()
        self.swatch.setObjectName("colorSwatch")
        self.swatch.setFixedSize(32, 32)                # as Annotate's (critique 2026-11-21)
        self.pick_button = PushButton(CHOOSE_COLOUR)
        self.pick_button.clicked.connect(self.pick_color)
        row.layout().addWidget(self.swatch)
        row.layout().addWidget(self.pick_button)
        self._show_color()

    def _show_color(self):
        self.swatch.setStyleSheet(
            f"QFrame#colorSwatch {{ background: {_hex(self.color)}; border-radius: 4px; }}")

    def pick_color(self):
        rgb = dialogs.ask_color(self.color)
        if rgb:
            self.color = rgb
            self._show_color()

    def options(self) -> dict:
        return {"text": self.text.text().strip(), "size": int(self.size.value()),
                "opacity": self.opacity.value() / 100.0,
                "color": tuple(c / 255 for c in self.color)}

    def check(self) -> str | None:
        return None if self.text.text().strip() else "Enter watermark text."


# ── OCR ───────────────────────────────────────────────────────────────────────
OCR_MODES = [("overlay", "Overlay", "invisible text layer"),
             ("text", "Text-only PDF", "")]


class OcrOptions(Panel):
    key = "ocr"

    def build(self):
        self.v.addWidget(group_title("Recognition"))
        group = card(padding=0)
        self.v.addWidget(group)

        row = self.row(group, "Language", "the text's language · add one if mixed")
        self.lang = LanguagePicker()
        row.layout().addWidget(self.lang)

        row = self.row(group, "Render DPI")
        self.dpi = number_box(row, 72, 400, pref_dpi(72, 400, "ocr_dpi"), " DPI")

        self.v.addWidget(group_title("Output mode"))
        group = card(padding=0)
        self.v.addWidget(group)
        self.mode_group = radio_rows(group, OCR_MODES, "overlay", row=self.row, parent=self.box)
        self.modes = self.mode_group.buttons

    @property
    def text_only(self) -> bool:
        return self.mode_group.value() == "text"

    def options(self) -> dict:
        return {"lang": self.lang.text().strip() or "eng", "dpi": int(self.dpi.value()),
                "text_only": self.text_only}


# ── PDF → Other ───────────────────────────────────────────────────────────────
OTHER_INFO = {
    "TXT":  "Extracts all selectable text from the PDF into a plain .txt file.",
    "HTML": "Exports each page with HTML text structure — opens in any browser.",
    "XML":  "Exports the PDF's text and layout structure as an XML document.",
    "RTF":  "Converts PDF text to Rich Text Format, readable in Word/LibreOffice.",
    "DOCX": "Extracts text paragraph-by-paragraph into a Word document.  Requires: python-docx",
    "PPTX": "Renders each page as a slide image inside a PowerPoint file.  Requires: python-pptx",
    "XLSX": "Extracts text per page; each page goes to its own Excel sheet.  Requires: openpyxl",
    "PNG":  "Renders each page as a PNG image, bundled together in a ZIP.",
    "JPEG": "Renders each page as a JPEG image, bundled together in a ZIP.",
}
DPI_FORMATS = ("PNG", "JPEG", "PPTX")
DPI_RANGE = (72, 300)
QUALITY_RANGE, QUALITY_DEFAULT = (50, 100), 92


class OtherOptions(Panel):
    key = "other"

    def build(self):
        self.v.addWidget(group_title("Output"))
        group = card(padding=0)
        self.v.addWidget(group)
        row = self.row(group, "Output format", OTHER_INFO["TXT"])
        self.fmt_info = row.info_button
        self.fmt = ComboBox()
        self.fmt.addItems(core_convert.FORMATS)
        self.fmt.setCurrentText("TXT")
        self.fmt.setMinimumWidth(120)
        row.layout().addWidget(self.fmt)
        self.missing = CaptionLabel("")
        theme.label_role(self.missing, "warning")
        self.missing.setWordWrap(True)
        self.missing.setContentsMargins(0, 4, 0, 0)
        self.v.addWidget(self.missing)

        self.image_title = group_title("Image options")
        self.v.addWidget(self.image_title)
        self.image_card = card(padding=0)
        self.v.addWidget(self.image_card)
        row = self.row(self.image_card, "Resolution")
        self.dpi_box = number_box(row, *DPI_RANGE, pref_dpi(*DPI_RANGE, "export_dpi"), " DPI")
        row = self.row(self.image_card, "JPEG quality")
        self.quality_box = number_box(row, *QUALITY_RANGE, QUALITY_DEFAULT, "%")
        self.quality_row = row.parent()
        self._quality_divider = row.divider
        self.fmt.currentTextChanged.connect(self.fmt_changed)
        self.fmt_changed("TXT")

    def fmt_changed(self, fmt: str):
        self.fmt_info.set_info(OTHER_INFO.get(fmt, ""))
        lib, installed = core_convert.NEEDS.get(fmt, ("", True))
        self.missing.setText("" if installed else
                             f"⚠  '{lib}' is not installed.\nInstall it:  pip install {lib}")
        self.missing.setVisible(not installed)
        images = fmt in DPI_FORMATS
        self.image_title.setVisible(images)
        self.image_card.setVisible(images)
        self.quality_row.setVisible(fmt == "JPEG")
        self._quality_divider.setVisible(fmt == "JPEG")

    @property
    def format(self) -> str:
        return self.fmt.currentText()

    def dpi_quality(self) -> tuple[int, int]:
        """(dpi, quality): the slider values when the format shows them, else the export
        default (200) and 92."""
        fmt = self.format
        dpi = int(self.dpi_box.value()) if fmt in DPI_FORMATS else _DEFAULTS["export_dpi"]
        quality = int(self.quality_box.value()) if fmt == "JPEG" else QUALITY_DEFAULT
        return dpi, quality

    def options(self) -> dict:
        dpi, quality = self.dpi_quality()
        return {"fmt": self.format, "dpi": dpi, "quality": quality}


PANELS = {
    "compress":  (CompressOptions, "Compress"),
    "watermark": (WatermarkOptions, "Watermark"),
    "ocr":       (OcrOptions, "OCR"),
    "other":     (OtherOptions, "PDF → Other"),
}
