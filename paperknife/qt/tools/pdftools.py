"""PDF Tools — a single-file transform (group C): Repair, Sanitise, Flatten and
Remove blank pages (owner, 2026-10-18: a PDF is repaired without being
compressed, so Repair stays here, and the screen gains three tools).  One
tool is chosen in radio rows, as Compress's levels; its options show under
them; the one main action names the tool."""
from __future__ import annotations


from ...core import pdftools as core
from .. import dialogs
from ..pages import (APPLY, KEEP_ONE, SAVE_NOTE, ToolPage, card, group_title, pages_phrase, radio_rows,
                     register_page, setting_row, toggle_switch)

SUBTITLE = "Repair, sanitise or flatten a PDF · remove its blank pages"
TOOLS = [
    # Two lines each in the 200 px card (owner, 2026-10-22: they ran to 22 lines and
    # pushed the card past a maximized window)
    ("repair", "Repair",
     "Rebuild a damaged PDF so it opens again. Some pages may be lost."),
    ("sanitise", "Sanitise",
     "Remove scripts, attachments, hidden metadata and action links."),
    ("flatten", "Flatten",
     "Fix comments and form fields into the page."),
    ("blank", "Remove blank pages",
     "Find empty pages and remove the ones you confirm."),
]
ACTION = {"repair": "Repair", "sanitise": "Sanitise", "flatten": "Flatten",
          "blank": "Remove blank pages"}
SANITISE = [("javascript", "JavaScript"), ("embedded", "Embedded files"),
            ("xmp", "XMP metadata"), ("actions", "Links that run actions")]
FLATTEN = [("comments", "Comments"), ("fields", "Form fields")]
NO_BLANK = "No blank page was found."
SCANNED_BLANK = " Scanned pages count when they show only empty paper."


def repair_report(repaired: bool) -> str:
    """The status line for a finished repair (in place: Save writes it)."""
    msg = "Repaired" if repaired else "No damage found; cleaned"
    return f"✓  {msg}" + SAVE_NOTE


def _count(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def sanitise_text(found: dict) -> str:
    """What a sanitise removed, for the dialog."""
    parts = []
    if found.get("javascript"):
        parts.append(_count(found["javascript"], "script", "scripts"))
    if found.get("embedded"):
        parts.append(_count(found["embedded"], "embedded file", "embedded files"))
    if found.get("xmp"):
        parts.append("the XMP metadata")
    if found.get("actions"):
        parts.append(_count(found["actions"], "link that runs an action",
                            "links that run actions"))
    return ("Removed: " + ", ".join(parts)) if parts else "Nothing of the kind was found."


def flatten_text(found: dict) -> str:
    parts = []
    if found.get("comments"):
        parts.append(_count(found["comments"], "comment", "comments"))
    if found.get("fields"):
        parts.append(_count(found["fields"], "form field", "form fields"))
    return ("Flattened: " + ", ".join(parts)) if parts else "Nothing of the kind was found."


@register_page("PdfToolsTool")
class PdfToolsPage(ToolPage):
    def __init__(self, tool=None, window=None):
        super().__init__("PDF Tools", SUBTITLE, tool=tool, window=window)
        self.doc_input()
        self.body.addSpacing(16)
        # No PDF/A or Linearise: PyMuPDF 1.28 has no save(pdfa=) and
        # save(linear=True) raises "Linearisation is no longer supported".
        self.body.addWidget(group_title("Tool"))
        group = card(padding=0)
        self.body.addWidget(group)
        self.tool_group = radio_rows(group, TOOLS, "repair", parent=self)
        self.radios = self.tool_group.buttons
        self.switches: dict = {}
        self.option_boxes: dict = {}
        for key, title, rows in (("sanitise", "Sanitise", SANITISE),
                                 ("flatten", "Flatten", FLATTEN)):
            box = card(padding=0)
            for name, label in rows:
                sw = toggle_switch(True)
                setting_row(box, label).layout().addWidget(sw)
                self.switches[name] = sw
            heading = group_title(title)
            self.body.addWidget(heading)
            self.body.addWidget(box)
            self.option_boxes[key] = (heading, box)
        self.body.addStretch(1)
        self.action_btn = self.primary(APPLY, self.run)
        self.tool_group.buttonToggled.connect(lambda *_: self._tool_changed())
        self._tool_changed()

    @property
    def tool_choice(self) -> str:
        return self.tool_group.value()

    def _tool_changed(self):
        t = self.tool_choice
        for key, (heading, box) in self.option_boxes.items():
            heading.setVisible(key == t)
            box.setVisible(key == t)

    def _on(self, name: str) -> bool:
        return self.switches[name].isChecked()

    def run(self):
        t = self.tool_choice
        getattr(self, f"_run_{t}")()

    def _run_repair(self):
        damaged = [False]

        def prepare(_copy):
            # The job's copy is written from memory and so never looks broken:
            # whether MuPDF had to rebuild the file shows on the document opened.
            damaged[0] = bool(self.window_.document.doc.is_repaired)

        self.run_on_file("PDF Tools", lambda doc, out, stop, _p: core.repair_pdf(doc, out),
                         "Repairing…", None, prepare=prepare, cancellable=False,
                         in_place="Repair",
                         applied=lambda repaired: ("success", repair_report(repaired or damaged[0]),
                                                   None, True))

    def _run_sanitise(self):
        opts = {name: self._on(name) for name, _l in SANITISE}

        self.run_on_file("PDF Tools", lambda doc, out, stop, _p: core.sanitise_pdf(doc, out, **opts),
                         "Sanitising…", None, cancellable=False, in_place="Clean up",
                         applied=lambda found: ("success", "✓  Cleaned up" + SAVE_NOTE,
                                                sanitise_text(found), True))

    def _run_flatten(self):
        opts = {name: self._on(name) for name, _l in FLATTEN}

        self.run_on_file("PDF Tools", lambda doc, out, stop, _p: core.flatten_pdf(doc, out, **opts),
                         "Flattening…", None, cancellable=False, in_place="Flatten",
                         applied=lambda found: ("success", "✓  Flattened" + SAVE_NOTE,
                                                flatten_text(found), True))

    def _run_blank(self):
        blanks: list[int] = []

        def prepare(doc):
            blanks[:] = core.blank_pages(doc)
            if not blanks:
                dialogs.info(ACTION["blank"], NO_BLANK)
                return False
            if len(blanks) == len(doc):
                raise ValueError(KEEP_ONE)
            what = pages_phrase([i + 1 for i in blanks])
            why = "It has" if len(blanks) == 1 else "They have"
            # A scanned blank holds a picture: say what made it count (2026-11-27).
            scans = SCANNED_BLANK if any(core.is_scan(doc[i]) for i in blanks) else ""
            return dialogs.ask_yes_no(ACTION["blank"],
                                      f"Remove {what}? {why} no text or drawing.{scans}")

        self.run_on_file("PDF Tools",
                         lambda doc, out, stop, _p: core.remove_pages(doc, out, blanks),
                         "Removing blank pages…", None, prepare=prepare, cancellable=False,
                         in_place="Remove blank pages",
                         applied=lambda n: ("success", f"✓  Removed {n} blank page(s)"
                                            + SAVE_NOTE, None, True))
