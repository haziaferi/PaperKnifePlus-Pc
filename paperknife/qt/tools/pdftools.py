"""PDF Tools — a single-file transform (group C): repair a damaged file."""
from __future__ import annotations

from pathlib import Path

from ...core import pdftools as core
from ..pages import ToolPage, card, file_card, group_title, register_page, setting_row


def repair_report(repaired: bool, out: str):
    """(status line, dialog text) for a finished repair."""
    msg = ("Repaired PDF saved" if repaired
           else "No damage found; cleaned copy saved")
    return f"✓  {msg} → {Path(out).name}", f"{msg}:\n{out}"


@register_page("PdfToolsTool")
class PdfToolsPage(ToolPage):
    def __init__(self, tool=None, window=None):
        super().__init__("PDF Tools", "Repair corrupt files", tool=tool, window=window)
        self.file = file_card()
        self.body.addWidget(self.file)
        self.body.addSpacing(16)
        # No PDF/A or Linearise: PyMuPDF 1.28 has no save(pdfa=) and
        # save(linear=True) raises "Linearisation is no longer supported".
        # One operation, so a row that explains it and no choice to make.
        self.body.addWidget(group_title("Operation"))
        group = card(padding=0)
        self.body.addWidget(group)
        setting_row(group, "Repair",
                    "Attempt to recover a corrupt or truncated PDF. Re-parses the file's "
                    "cross-reference table. Can rescue files that other tools refuse to "
                    "open. May not recover all pages.")
        self.body.addStretch(1)
        self.primary("Repair", self.run)

    def open(self):
        self.file.choose()

    def run(self):
        def report(repaired, out):
            status, text = repair_report(repaired, out)
            return "success", status, "Done", text

        self.run_on_file("PDF Tools", lambda doc, out, stop, _p: core.repair_pdf(doc, out),
                         "Repairing…", report,
                         save=("repaired.pdf", ".pdf", [("PDF", "*.pdf")]), cancellable=False)
