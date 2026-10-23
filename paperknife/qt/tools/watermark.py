"""Watermark — diagonal text on the selected pages.  The pages are on screen
(owner, 2026-10-17: the page-range tools show the document's pages; Watermark
gains a page range); the options sit in the column at the right."""
from __future__ import annotations


from ...core import enhance as core_enhance
from ...pages import selected_pages
from .. import dialogs
from ..pages import SAVE_NOTE, PagePickPage, batch_prototype, card, group_title, register_page
from ..tool_options import DEFAULT_COLOR, WatermarkOptions  # noqa: F401


@register_page("WatermarkTool")
class WatermarkPage(PagePickPage):
    def __init__(self, tool=None, window=None):
        super().__init__("Watermark", "Stamp a diagonal text watermark across the selected pages",
                         tool=tool, window=window)
        s = self.settings
        o = self.opts = WatermarkOptions(s, self.setting_row, parent=self)
        self.text, self.size, self.size_label = o.text, o.size, o.size_label
        self.opacity, self.opacity_label = o.opacity, o.opacity_label
        self.swatch, self.pick_button = o.swatch, o.pick_button

        self.pages_title = group_title("Pages")
        s.addWidget(self.pages_title)
        pages = self.pages_card = card(padding=0)
        s.addWidget(pages)
        self.setting_row(pages, "Apply to", "or click the pages").layout().addWidget(
            self.make_range_field(width=140))
        s.addStretch(1)
        self.primary("Apply Watermark", self.run)
        if batch_prototype() == "B":
            from ..folder_mode import FolderMode
            FolderMode(self, self.opts, "watermark", "Watermark", self.columns, self.grid_card,
                       row=self.setting_row, hide=(self.context_bar_widget, self.drop_target,
                                 self.pages_title, self.pages_card))

    # ── options (the panel's) ──
    @property
    def color(self):
        return self.opts.color

    @color.setter
    def color(self, rgb):
        self.opts.color = rgb
        self.opts._show_color()

    def pick_color(self):
        self.opts.pick_color()

    # ── the action ──
    def run(self):
        fm = self.__dict__.get("_folder_mode")
        if fm is not None and fm.run():
            return                          # a folder is the input (prototype B)
        src = self.chosen_file("Watermark")
        if not src or self._doc is None:
            return
        refused = self.opts.check()
        if refused:
            return dialogs.warning("Watermark", refused)
        o = self.opts.options()
        text, size, opacity, color = o["text"], o["size"], o["opacity"], o["color"]
        range_str = self.range_text()
        pages: list[int] = []

        def prepare(doc):
            pages[:] = selected_pages(range_str, len(doc))

        def work(doc, out, stop, progress):
            self._release(out)              # over the open file: let it go first
            return core_enhance.watermark_pdf(doc, out, text, size, opacity, color, stop,
                                              progress, pages=pages)

        self.run_on_file(
            "Watermark", work, "Applying watermark…", None, src=src, prepare=prepare,
            open_doc=self.job_copy, in_place="Watermark",
            applied=lambda _r: ("success", "✓  Watermark applied" + SAVE_NOTE, None, True))
