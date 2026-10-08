"""Preferences — app settings (group F): setting rows grouped as the CTk tool
groups them, and one Save that writes them all to PREFS."""
from __future__ import annotations

from qfluentwidgets import ComboBox, LineEdit, PushButton

from ...core import settings as core
from ...prefs import PREFS
from .. import dialogs, theme
from ..pages import ToolPage, card, group_title, register_page, setting_row, spin_box

APPEARANCES = ["light", "dark", "system"]
COMPRESS_LEVELS = ["light", "medium", "aggressive"]


@register_page("SettingsTool")
class SettingsPage(ToolPage):
    def __init__(self, tool=None, window=None):
        super().__init__("Preferences", "Click Save Preferences to keep changes",
                         tool=tool, window=window)
        # General
        self.body.addWidget(group_title("General"))
        general = card(padding=0)
        self.body.addWidget(general)
        row = setting_row(general, "Default output folder")
        self.output_dir = LineEdit()
        self.output_dir.setReadOnly(True)
        self.output_dir.setMinimumWidth(260)
        row.layout().addWidget(self.output_dir)
        browse = PushButton("Browse…")
        browse.clicked.connect(self.pick_output_dir)
        row.layout().addWidget(browse)
        row = setting_row(general, "Max recent files shown")
        self.max_recent = spin_box(*core.INT_RANGES["max_recent"][1:], PREFS.max_recent)
        row.layout().addWidget(self.max_recent)

        # Appearance
        self.body.addWidget(group_title("Appearance"))
        look = card(padding=0)
        self.body.addWidget(look)
        row = setting_row(look, "Colour mode")
        self.appearance = ComboBox()
        self.appearance.addItems(APPEARANCES)
        self.appearance.setMinimumWidth(160)
        row.layout().addWidget(self.appearance)

        # PDF operations
        self.body.addWidget(group_title("PDF operations"))
        ops = card(padding=0)
        self.body.addWidget(ops)
        row = setting_row(ops, "Default DPI (OCR / export)")
        self.default_dpi = spin_box(*core.INT_RANGES["default_dpi"][1:], PREFS.default_dpi)
        row.layout().addWidget(self.default_dpi)
        row = setting_row(ops, "Default compress level")
        self.compress_level = ComboBox()
        self.compress_level.addItems(COMPRESS_LEVELS)
        self.compress_level.setMinimumWidth(160)
        row.layout().addWidget(self.compress_level)
        row = setting_row(ops, "OCR language code")
        self.ocr_lang = LineEdit()
        self.ocr_lang.setMinimumWidth(160)
        row.layout().addWidget(self.ocr_lang)

        self.body.addStretch(1)
        self.secondary("Restore defaults", self.restore)
        self.primary("Save Preferences", self.save)
        self.fill()

    # ── controls ⇄ PREFS ─────────────────────────────────────────────────────
    def fill(self):
        """Show the values PREFS holds now (unsaved changes are dropped)."""
        self.output_dir.setText(str(PREFS.get("output_dir", "")))
        self.max_recent.setValue(int(PREFS.max_recent))
        self.appearance.setCurrentText(str(PREFS.get("appearance", APPEARANCES[0])))
        self.default_dpi.setValue(int(PREFS.default_dpi))
        self.compress_level.setCurrentText(str(PREFS.get("compress_level", COMPRESS_LEVELS[0])))
        self.ocr_lang.setText(str(PREFS.get("ocr_lang", "")))

    def values(self) -> dict:
        return {
            "output_dir": self.output_dir.text(),
            "max_recent": self.max_recent.value(),
            "appearance": self.appearance.currentText(),
            "default_dpi": self.default_dpi.value(),
            "compress_level": self.compress_level.currentText(),
            "ocr_lang": self.ocr_lang.text(),
        }

    def activate(self):
        # The CTk tool rebuilds from PREFS each time it is shown.
        self.fill()

    def pick_output_dir(self):
        d = dialogs.ask_dir()
        if d:
            self.output_dir.setText(d)

    # ── actions ──────────────────────────────────────────────────────────────
    def save(self):
        values = self.values()
        warning = core.check_values(values)
        if warning:
            return dialogs.warning("Not saved", warning)
        core.apply_values(PREFS, values)
        theme.apply_appearance(PREFS.appearance)
        self._persist("✓  Preferences saved", "Preferences saved.")

    def restore(self):
        if not dialogs.ask_yes_no("Restore", "Reset all preferences to defaults?"):
            return
        core.restore_defaults(PREFS)
        theme.apply_appearance(PREFS.appearance)
        self._persist("✓  Preferences restored to defaults", None)
        self.fill()

    def _persist(self, status, info):
        try:
            PREFS.save()
        except OSError as exc:
            dialogs.error("Not saved", f"Could not write the preferences file:\n{exc}")
            return
        if self.window_ is not None:
            self.window_.set_status(status, "success")
        if info:
            dialogs.info("Saved", info)
