"""Split by Bookmarks — a page organiser (group B) whose centre is the outline."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QVBoxLayout, QWidget
from qfluentwidgets import BodyLabel, SingleDirectionScrollArea, StrongBodyLabel

from ...core import organise
from .. import dialogs, theme
from ..pages import (HeldDoc, OrganiserPage, _clear_layout, card, group_title, muted_caption, radio_rows,
                     register_page)

SUBTITLE = "Split a PDF at its chapter / section bookmarks"
SHOWN = 60                  # outline entries listed, as the CTk tool
LEVELS = [("Top-level only (level 1)", False), ("All bookmark levels", True)]


@register_page("BookmarksTool")
class BookmarksPage(HeldDoc, OrganiserPage):
    def __init__(self, tool=None, window=None):
        super().__init__("Split by Bookmarks", SUBTITLE, tool=tool, window=window,
                         settings=True, drag_reorder=False, hint="")
        self._toc: list = []

        # Centre: the outline, read-only.
        area = SingleDirectionScrollArea(self, Qt.Vertical)
        area.setWidgetResizable(True)
        area.enableTransparentBackground()
        area.setFrameShape(QFrame.NoFrame)
        inner = QWidget()
        inner.setObjectName("bookmarkOutline")
        inner.setStyleSheet("QWidget#bookmarkOutline { background: transparent; }")
        self.outline = QVBoxLayout(inner)
        self.outline.setContentsMargins(8, 8, 8, 8)
        self.outline.setSpacing(2)
        area.setWidget(inner)
        self.set_centre(area)
        self._show_message("Open a PDF to see its bookmarks", "muted")

        # Settings: Split at.
        self.settings.addWidget(group_title("Split at"))
        group = card(padding=0)
        self.settings.addWidget(group)
        self.level_group = radio_rows(group, [(v, title, "") for title, v in LEVELS], False,
                                      row=self.setting_row, parent=self)
        self.radios = self.level_group.buttons
        self.settings.addStretch(1)

        self.primary("Split", self.run)

    @property
    def all_levels(self) -> bool:
        return self.level_group.value()

    # ── outline ──────────────────────────────────────────────────────────────
    def _show_message(self, text: str, role: str):
        _clear_layout(self.outline)
        lbl = BodyLabel(text)
        lbl.setTextColor(*theme.pair(role))
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setContentsMargins(0, 20, 0, 20)
        self.outline.addWidget(lbl)
        self.outline.addStretch(1)

    def _show_outline(self, toc):
        if not toc:
            return self._show_message("⚠  This PDF has no bookmarks.", "warning")
        _clear_layout(self.outline)
        for level, title, page, *_ in toc[:SHOWN]:
            indent = "  " * (level - 1) + ("▸ " if level == 1 else "  ")
            text = f"{indent}{title}  (p.{page})"
            if level == 1:
                lbl = StrongBodyLabel(text)
            else:
                lbl = BodyLabel(text)
                lbl.setTextColor(*theme.pair("muted"))
            self.outline.addWidget(lbl)
        if len(toc) > SHOWN:
            more = muted_caption(f"… and {len(toc) - SHOWN} more bookmarks")
            more.setAlignment(Qt.AlignCenter)
            more.setContentsMargins(0, 4, 0, 4)
            self.outline.addWidget(more)
        self.outline.addStretch(1)

    def outline_lines(self) -> list[str]:
        """The texts the outline shows, top to bottom."""
        out = []
        for i in range(self.outline.count()):
            w = self.outline.itemAt(i).widget()
            if w is not None:
                out.append(w.text())
        return out

    # ── document ─────────────────────────────────────────────────────────────
    def open_path(self, path: str):
        self.file.set_path(path)

    def load(self, path: str):
        if not path:
            return
        # Kept open so a password entered here also covers the split.
        doc = self.open_held(path, "Split by Bookmarks")
        if doc is None:
            return
        self._toc = doc.get_toc()
        self._show_outline(self._toc)

    def deactivate(self):
        self.release_held("Split by Bookmarks", SUBTITLE)
        self._toc = []
        self._show_message("Open a PDF to see its bookmarks", "muted")

    # ── split ────────────────────────────────────────────────────────────────
    def run(self):
        if not self.file.path() or self._doc is None:
            return dialogs.warning("Bookmarks", "Select a PDF first.")
        if not self._toc:
            return dialogs.warning("Bookmarks", "PDF has no bookmarks.")
        entries, skipped = organise.bookmark_chapters(self._toc, len(self._doc),
                                                      self.all_levels)
        if not entries:
            return dialogs.warning("Bookmarks", "No matching bookmarks point to a page.")
        out_dir = dialogs.ask_dir()
        if not out_dir:
            return
        win = self.window_

        def work(stop):
            return organise.split_chapters(
                self._doc, entries, out_dir, stop,
                win.progress_callback(), release=self._release)

        def then(kind, count):
            if kind != "done":
                return
            win.set_status(f"✓  Split into {count} chapter(s) → {out_dir}", "success")
            note = (f"\n\n{skipped} bookmark(s) with no page target were skipped."
                    if skipped else "")
            dialogs.info("Done", f"Split into {count} file(s):\n{out_dir}{note}")

        win.run_job(work, "Splitting by bookmarks…", lock=True, then=then)
