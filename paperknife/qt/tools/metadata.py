"""Metadata — a structured editor with fields only (group E, in the group C form).

The page holds the chosen PDF open from the moment it is
chosen until another file becomes the current document or it is cleared (leaving
the tool keeps it), so an encrypted file asks for its password once."""
from __future__ import annotations

from qfluentwidgets import LineEdit

from ...core import metadata as core
from .. import dialogs
from ..pages import HeldDoc, ToolPage, card, group_title, register_page, setting_row


@register_page("MetadataTool")
class MetadataPage(HeldDoc, ToolPage):
    save_name = "with_metadata.pdf"

    def __init__(self, tool=None, window=None):
        super().__init__("Metadata",
                         "View and edit the PDF's document properties · Ctrl+S to save",
                         tool=tool, window=window)
        self._loaded: dict[str, str] = {}
        self.doc_input(self._load)
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
        self._show_document_values()

    def _reset(self):
        self.release_held()
        self._loaded = {}
        self.clear()

    def clear_document(self):
        self._reset()
        self.refresh_document()

    def _meta(self) -> dict[str, str]:
        return {key: self.fields[key].text() for key, _ in core.FIELDS}

    def _show_document_values(self):
        self._loaded = core.read_metadata(self._doc)
        for key, _ in core.FIELDS:
            self.fields[key].setText(self._loaded[key])

    def has_pending(self) -> bool:
        """Fields typed and not applied to the document yet."""
        return self._doc is not None and self._meta() != {
            key: self._loaded.get(key, "") for key, _ in core.FIELDS}

    def commit_edits(self) -> bool:
        """The typed fields into the document, as one undoable edit."""
        if not self.has_pending():
            return True
        meta = self._meta()
        error = core.check_dates(meta)
        if error:
            dialogs.error("Metadata", error)
            return False
        # Filling empty fields of a file without XMP only adds: appended to
        # the file on Save (owner's choice 2026-10-12).  A value changed or
        # cleared, or an XMP stream dropped, is written whole, so the old text goes.
        adds = not self._doc.get_xml_metadata() and all(
            not self._loaded.get(k) for k in meta if meta[k] != self._loaded.get(k, ""))
        self.edit_document("Metadata", lambda d: core.apply_metadata(d, meta, True), adds=adds)
        self._loaded = dict(meta)
        return True

    def document_replaced(self):
        # Another tool's edit or an undo: the fields show the document, unless
        # typed here and not applied.
        if self._doc is not None and not self.has_pending():
            self._show_document_values()

    def recovery_extra(self) -> dict:
        """Fields typed and not applied: crash recovery copies them too."""
        return {"fields": self._meta()} if self.has_pending() else {}

    def restore_extra(self, state: dict) -> None:
        for key, value in (state.get("fields") or {}).items():
            if key in self.fields:
                self.fields[key].setText(str(value))

    def drop_marks(self):
        if self._doc is not None:
            self._show_document_values()

    def clear(self):
        for edit in self.fields.values():
            edit.setText("")

    # ── save (the window's: the fields are applied first) ─────────────────────
    def save(self, after=None):
        if self._doc is None:
            return dialogs.warning("Save", "Open a PDF first.")
        return self.window_.save(after)
