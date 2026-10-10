"""Find & Replace — a document workspace (group A): the find / replace fields
and the hit count in the context panel, the hits drawn over the page."""
from __future__ import annotations


from qfluentwidgets import BodyLabel, LineEdit, PushButton

from ...core import text as core_text
from .. import dialogs, theme
from ..pages import WorkspaceDoc, WorkspacePage, register_page

GLYPH_UNDO = 0xE7A7          # Segoe Fluent Icons
# Current hit, other hits, hit outline; the fills are see-through so the
# text under a hit stays readable.
HIT_CUR, HIT, HIT_EDGE = "#80FFD700", "#80FFFACD", "#CCCCCC"


@register_page("FindReplaceTool")
class FindReplacePage(WorkspaceDoc, WorkspacePage):
    save_name = "replaced.pdf"
    saved_what = "PDF"

    def __init__(self, tool=None, window=None):
        super().__init__("Find & Replace", "Open a PDF to start", tool=tool, window=window)
        self._undo_stack: list = []
        self._hits: list = []           # (page_num, [rect per line of the match])
        self._hit_idx = -1
        self.add_rail("undo", GLYPH_UNDO, "Undo (Ctrl+Z)", self.undo, toggle=False)
        self.secondary("Open", self.open)
        self.secondary("Find All", self.find_all)
        self.secondary("Replace All", self.replace_all)
        self.primary("Save", self.save)
        self.build_panel()
        self.show_current()

    # ── panel ────────────────────────────────────────────────────────────────
    def build_panel(self):
        self.panel_begin("Find & Replace",
                         "Search PDF text and replace across all pages · Ctrl+S to save")
        row = self.panel_field("Find")
        self.find_edit = LineEdit()
        self.find_edit.setPlaceholderText("Search text…")
        self.find_edit.returnPressed.connect(self.find_all)
        row.addWidget(self.find_edit, 1)
        row = self.panel_field("Replace")
        self.repl_edit = LineEdit()
        self.repl_edit.setPlaceholderText("Replacement text…")
        row.addWidget(self.repl_edit, 1)
        row = self.panel_field("Hits")
        self.prev_hit = PushButton("◀ Prev")
        self.next_hit = PushButton("Next ▶")
        self.prev_hit.clicked.connect(lambda: self.jump(-1))
        self.next_hit.clicked.connect(lambda: self.jump(1))
        row.addWidget(self.prev_hit)
        row.addWidget(self.next_hit)
        row.addStretch(1)
        self.hit_label = BodyLabel("")
        self.hit_label.setWordWrap(True)
        self.panel_body.addSpacing(8)
        self.panel_body.addWidget(self.hit_label)

    # ── document ─────────────────────────────────────────────────────────────
    def open_path(self, path: str):
        if self.open_document(path, "Find & Replace") is None:
            return
        self._hits, self._hit_idx = [], -1
        self.hit_label.setText("")
        self.show_current()

    def deactivate(self):
        self._close_doc()
        self._undo_stack, self._hits, self._hit_idx = [], [], -1
        self.hit_label.setText("")
        self.set_title("Find & Replace", "Open a PDF to start")
        self.show_current()

    # ── search ───────────────────────────────────────────────────────────────
    def find_all(self):
        if self._doc is None:
            return dialogs.warning("Find", "Open a PDF first.")
        needle = self.find_edit.text().strip()
        if not needle:
            return
        progress = self.window_.progress_callback()

        def work(stop):
            found = core_text.find_all(self._doc, needle, stop, progress)
            if found is None:
                return None
            return [(pg_num, m["rects"]) for pg_num, ms in found for m in ms]

        def then(kind, hits):
            if kind == "done" and hits is not None:
                self._hits = hits
                if hits:
                    self._hit_idx = 0
                    self._pg = hits[0][0]
                    self.hit_label.setText(f"Found {len(hits)} hit(s)")
                else:
                    self._hit_idx = -1
                    self.hit_label.setText("Not found")
                    dialogs.info("Find", f"'{needle}' not found.")
            self.show_current()

        self.window_.run_job(work, f"Searching for '{needle}'…", lock=True, then=then)

    def jump(self, d: int):
        if not self._hits:
            return
        self._hit_idx = (self._hit_idx + d) % len(self._hits)
        self._pg = self._hits[self._hit_idx][0]
        self.show_current()
        self.hit_label.setText(f"Hit {self._hit_idx + 1} / {len(self._hits)}")

    # ── replace ──────────────────────────────────────────────────────────────
    def replace_all(self):
        if self._doc is None:
            return dialogs.warning("Replace", "Open a PDF first.")
        needle = self.find_edit.text().strip()
        repl = self.repl_edit.text()
        if not needle:
            return dialogs.warning("Replace", "Enter search text.")
        if not dialogs.ask_yes_no(
                "Confirm Replace",
                f"Replace ALL occurrences of:\n  '{needle}'\nwith:\n  '{repl}'\n\n"
                "This modifies the PDF in memory (save to keep changes)."):
            return
        # insert_text(fontname="helv") encodes Latin-1 only and turns anything else
        # into "·"; an embedded built-in font keeps the characters.
        font = core_text.unicode_font(repl)
        if font is None:
            return dialogs.error(
                "Replace", "The replacement contains characters no built-in font can draw.")
        win = self.window_
        state = {"count": 0, "snapshot": False}
        first_half, second_half = win.progress_callback(0.5), win.progress_callback()

        def work(stop):
            found = core_text.find_all(self._doc, needle, stop, first_half)
            if not found or stop.is_set():
                return
            self._push_undo()
            state["snapshot"] = True
            try:
                core_text.replace_matches(self._doc, found, repl, font, stop, second_half)
            except Exception as e:
                raise RuntimeError(f"Nothing was replaced:\n{e}") from e
            state["count"] = sum(len(ms) for _, ms in found)

        def then(kind, _value):
            # All or nothing: pages already done would keep their text removed.
            if kind != "done" and state["snapshot"]:
                self._pop_undo()
            if kind == "done":
                count = state["count"]
                self._hits, self._hit_idx = [], -1
                self.hit_label.setText(f"Replaced {count} occurrence(s)")
                win.set_status(f"✓  Replaced {count} occurrence(s) · Save to write to disk",
                               "success")
            self.show_current()

        win.run_job(work, f"Replacing '{needle}'…", lock=True, then=then)

    # ── render ───────────────────────────────────────────────────────────────
    def draw_overlay(self, page):
        accent = theme.hex_color("accent")
        for hi, (pg_num, rects) in enumerate(self._hits):
            if pg_num != self._pg:
                continue
            cur = hi == self._hit_idx
            for rect in rects:
                self.view.add_rect(rect, accent if cur else HIT_EDGE,
                                   fill=HIT_CUR if cur else HIT)

    # ── undo / save ──────────────────────────────────────────────────────────
    def undo(self):
        """Restores the whole document as it was before the last Replace All."""
        if not self._undo_stack or self._doc is None:
            return
        self._pop_undo()
        self._hits, self._hit_idx = [], -1
        self.hit_label.setText("Replace undone")
        self.show_current()
