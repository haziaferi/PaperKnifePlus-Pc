"""Normalise Pages — the selected pages onto one paper size.  The pages are on
screen (owner, 2026-10-17: the page-range tools show the document's pages);
the options sit in the column at the right, the pages not chosen keep their
size."""
from __future__ import annotations


from qfluentwidgets import ComboBox

from ...core import enhance as core_enhance
from ...pages import selected_pages
from ..pages import APPLY, SAVE_NOTE, PagePickPage, card, group_title, radio_rows, register_page

SIZES = ["A4", "A3", "A5", "Letter", "Legal", "Tabloid"]
ORIENTATIONS = ["Portrait", "Landscape", "Keep original"]
SCALES = [("fit", "Fit", "keep ratio · recommended"),
          ("stretch", "Stretch", "fill page")]


@register_page("NormaliseTool")
class NormalisePage(PagePickPage):
    def __init__(self, tool=None, window=None):
        super().__init__("Normalise Pages", "Resize the selected pages to a standard paper size",
                         tool=tool, window=window)
        s = self.settings
        s.addWidget(group_title("Page size"))
        group = card(padding=0)
        s.addWidget(group)
        row = self.setting_row(group, "Target size")
        self.size = ComboBox()
        self.size.addItems(SIZES)
        self.size.setCurrentText("A4")
        self.size.setMinimumWidth(140)
        row.layout().addWidget(self.size)

        s.addWidget(group_title("Orientation"))
        group = card(padding=0)
        s.addWidget(group)
        self.orient_group = radio_rows(group, [(v, v, "") for v in ORIENTATIONS], "Portrait",
                                       row=self.setting_row, parent=self)
        self.orients = self.orient_group.buttons

        s.addWidget(group_title("Scale mode"))
        group = card(padding=0)
        s.addWidget(group)
        self.scale_group = radio_rows(group, SCALES, "fit", row=self.setting_row, parent=self)
        self.scales = self.scale_group.buttons

        s.addWidget(group_title("Pages"))
        pages = card(padding=0)
        s.addWidget(pages)
        self.setting_row(pages, "Apply to", "or click the pages").layout().addWidget(
            self.make_range_field(width=140))
        s.addStretch(1)
        self.primary(APPLY, self.run)

    @property
    def orient(self) -> str:
        return self.orient_group.value()

    @property
    def stretch(self) -> bool:
        return self.scale_group.value() == "stretch"

    def run(self):
        src = self.chosen_file("Normalise")
        if not src or self._doc is None:
            return
        size, orient, stretch = self.size.currentText(), self.orient, self.stretch
        range_str = self.range_text()
        pages: list[int] = []

        def prepare(doc):
            pages[:] = selected_pages(range_str, len(doc))

        def work(doc, out, stop, progress):
            self._release(out)              # over the open file: let it go first
            return core_enhance.normalise_pdf(doc, out, size, orient, stretch, stop, progress,
                                              pages=pages)

        self.run_on_file(
            "Normalise", work, "Normalising pages…", None, src=src, prepare=prepare,
            open_doc=self.job_copy, in_place="Normalise pages",
            applied=lambda _r: ("success", "✓  Pages normalised" + SAVE_NOTE, None, True))
