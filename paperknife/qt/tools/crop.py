"""Crop / Trim — cut margins off the crop box of selected pages.  The pages are on
screen (owner, 2026-10-17: the page-range tools show the document's pages,
every page selected at first, the selection and the range field in step);
the margins and the range sit in the column at the right."""
from __future__ import annotations


from qfluentwidgets import ComboBox, LineEdit

from ...core import crop as core
from ...pages import selected_pages
from .. import dialogs
from ..pages import (APPLY, SAVE_NOTE, PagePickPage, Refusal, card, group_title, register_page,
                     toggle_switch)

# (key, row name), in the order the rows are shown
EDGES = [("top", "Top"), ("left", "Left"), ("right", "Right"), ("bottom", "Bottom")]
UNITS = {"mm": 72 / 25.4, "pt": 1.0}     # points per unit


def crop_report(cropped: int, wanted: int):
    """(role, status line) for a finished crop of *wanted* pages."""
    skipped = wanted - cropped
    note = (f" · {skipped} skipped (margins larger than the page)"
            if skipped else "")
    return ("warning" if skipped else "success",
            f"✓  Cropped {cropped} page(s){note}" + SAVE_NOTE)


@register_page("CropTool")
class CropPage(PagePickPage):
    def __init__(self, tool=None, window=None):
        super().__init__("Crop / Trim",
                         "Cut margins off the selected pages",
                         tool=tool, window=window)
        s = self.settings
        # Millimetres by default, points by choice (critique 2026-11-21: points only,
        # with a table of paper sizes in points to work from).
        s.addWidget(group_title("Margins to remove"))
        margins = card(padding=0)
        s.addWidget(margins)
        self.unit = ComboBox()
        self.unit.addItems(list(UNITS))
        self.unit.setCurrentText("mm")
        self._unit = "mm"
        self.unit.currentTextChanged.connect(self._unit_changed)
        self.setting_row(margins, "Unit", "How much to cut from each edge, in "
                         "millimetres or points (72 pt = 25.4 mm)").layout().addWidget(self.unit)
        self.margins: dict[str, LineEdit] = {}
        for key, name in EDGES:
            e = LineEdit()
            e.setText("0")
            e.setFixedWidth(120)
            self.setting_row(margins, name).layout().addWidget(e)
            self.margins[key] = e

        s.addWidget(group_title("Pages"))
        pages = card(padding=0)
        s.addWidget(pages)
        self.setting_row(pages, "Apply to", "or click the pages").layout().addWidget(
            self.make_range_field(width=140))
        self.reset = toggle_switch(False)
        self.setting_row(pages, "Reset to full media box first",
                         "undo previous crops").layout().addWidget(self.reset)
        s.addStretch(1)
        self.primary(APPLY, self.run)

    def _unit_changed(self, unit: str):
        """The same margins in the new unit: a number typed stays the same length."""
        f = UNITS[self._unit] / UNITS[unit]
        for e in self.margins.values():
            try:
                v = float(e.text() or "0") * f
            except ValueError:
                continue                    # left as typed; Apply says what is wrong
            e.setText(f"{v:.1f}".rstrip("0").rstrip("."))
        self._unit = unit

    def run(self):
        src = self.chosen_file("Crop")
        if not src or self._doc is None:
            return
        try:
            margins = core.parse_margins(*(self.margins[k].text()
                                           for k in ("top", "right", "bottom", "left")))
        except ValueError as e:
            return dialogs.warning("Crop", str(e))
        margins = tuple(m * UNITS[self._unit] for m in margins)      # in points
        range_str = self.range_text()
        reset = self.reset.isChecked()
        pages: list[int] = []

        def prepare(doc):
            pages[:] = selected_pages(range_str, len(doc))
            if not core.croppable(doc, pages, margins, reset):
                raise Refusal("No page was cropped: the margins are larger "
                              "than every selected page.")

        def applied(cropped):
            role, status = crop_report(cropped, len(pages))
            return role, status, None, True

        def work(doc, out, stop, _p):
            self._release(out)              # a crop over the open file: let it go first
            return core.crop_pdf(doc, out, pages, margins, reset, stop)

        self.run_on_file(
            "Crop", work,
            lambda: f"Cropping {len(pages)} page(s)…", None, src=src, prepare=prepare,
            open_doc=self.job_copy, in_place="Crop", applied=applied)
