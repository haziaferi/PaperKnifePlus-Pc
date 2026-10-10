"""Metadata — a structured editor with fields only (group E, in the group C form).

The page holds the chosen PDF open from the moment it is
chosen until another file is chosen or the tool is left, so an encrypted file
asks for its password once."""
from __future__ import annotations

from pathlib import Path

from qfluentwidgets import LineEdit

from ...core import metadata as core
from .. import dialogs
from ..pages import (HeldDoc, ToolPage, ask_keep_password, card, file_card, group_title,
                     register_page, setting_row)


@register_page("MetadataTool")
class MetadataPage(HeldDoc, ToolPage):
    save_name = "with_metadata.pdf"

    def __init__(self, tool=None, window=None):
        super().__init__("Metadata",
                         "View and edit the PDF's document properties · Ctrl+S to save",
                         tool=tool, window=window)
        self._loaded: dict[str, str] = {}
        self.file = file_card(on_change=self._load)
        self.body.addWidget(self.file)
        self.body.addSpacing(16)
        self.body.addWidget(group_title("Document properties"))
        group = card(padding=0)
        self.body.addWidget(group)
        self.fields: dict[str, LineEdit] = {}
        for key, label in core.FIELDS:
            holder = setting_row(group, label)
            edit = LineEdit()
            edit.setMinimumWidth(320)
            edit.setClearButtonEnabled(True)
            holder.layout().addWidget(edit)
            self.fields[key] = edit
        self.body.addStretch(1)
        self.secondary("Clear all fields", self.clear)
        self.primary("Save", self.save)

    # ── document ─────────────────────────────────────────────────────────────
    def _load(self, path: str):
        if not path:
            return
        doc = self.open_held(path)
        if doc is None:
            # Keep what was open and the fields typed; the card goes back to it.
            if self._doc is None:
                self._reset()
            return
        self._loaded = core.read_metadata(doc)
        for key, _ in core.FIELDS:
            self.fields[key].setText(self._loaded[key])

    def _reset(self):
        self.release_held()
        self._loaded = {}
        self.clear()

    def deactivate(self):
        self._reset()

    def clear(self):
        for edit in self.fields.values():
            edit.setText("")

    # ── save ─────────────────────────────────────────────────────────────────
    def save(self):
        if self._doc is None:
            return dialogs.warning("Save", "Open a PDF first.")
        meta = {key: self.fields[key].text() for key, _ in core.FIELDS}
        error = core.check_dates(meta)
        if error:
            return dialogs.error("Metadata", error)
        out = dialogs.ask_save(self.save_name, ".pdf", [("PDF", "*.pdf")])
        if not out:
            return
        kept = ask_keep_password(self._doc)
        changed = meta != self._loaded
        win = self.window_

        def work(stop):
            core.apply_metadata(self._doc, meta, changed)
            # garbage=1 drops the replaced Info and XMP objects from the file
            # (levels 2-3 cost the square of the page count: tests/test_save_settings.py).
            self._save_doc(out, garbage=1, deflate=True)

        def then(kind, _value):
            if kind == "done":
                win.set_status(f"✓  Saved → {Path(out).name}", "success")
                dialogs.info("Saved", f"PDF with updated metadata saved:\n{out}")

        win.run_job(work, f"Saving {Path(out).name}…", lock=True, then=then, cancellable=False,
                    keep_password=(kept, [out]))
