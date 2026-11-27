"""Print (Ctrl+P): the open document through Windows' print dialog.

MuPDF draws each page at the printer's resolution (at most PRINT_DPI) and the
picture is fitted to the printable area, centred, its proportions kept: a
landscape page on portrait paper prints smaller, never cut.
"""
from __future__ import annotations

from PySide6.QtCore import QRectF
from PySide6.QtGui import QImage, QPainter

from . import dialogs

PRINT_DPI = 300


def page_range(printer, count: int) -> list[int]:
    """The 0-based pages the dialog chose: its From-To, else every page."""
    from PySide6.QtPrintSupport import QPrinter
    if printer.printRange() == QPrinter.PageRange:
        lo, hi = max(1, printer.fromPage()), min(count, printer.toPage() or count)
        return list(range(lo - 1, hi)) if lo <= hi else []
    return list(range(count))


def fit(src_w: float, src_h: float, box: QRectF) -> QRectF:
    """A src_w x src_h picture scaled into *box*, centred, proportions kept."""
    k = min(box.width() / src_w, box.height() / src_h)
    w, h = src_w * k, src_h * k
    return QRectF(box.x() + (box.width() - w) / 2, box.y() + (box.height() - h) / 2, w, h)


def print_document(window, doc, name: str) -> bool:
    """Ask (dialogs.ask_print), then print *doc*'s chosen pages; whether it printed."""
    from PySide6.QtPrintSupport import QPrinter
    printer = QPrinter(QPrinter.HighResolution)
    printer.setDocName(name or "PaperKnife+")
    if not dialogs.ask_print(printer, len(doc)):
        return False
    pages = page_range(printer, len(doc))
    if not pages:
        dialogs.warning("Print", "The page range has no pages of this document.")
        return False
    dpi = min(printer.resolution(), PRINT_DPI)
    painter = QPainter()
    if not painter.begin(printer):
        dialogs.error("Print", "The printer could not be started.")
        return False
    try:
        box = QRectF(painter.viewport())
        for n, i in enumerate(pages):
            if n:
                printer.newPage()
            window.set_status(f"Printing page {i + 1} ({n + 1} of {len(pages)})…", "muted")
            pix = doc[i].get_pixmap(dpi=dpi, alpha=False)
            img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
            painter.drawImage(fit(pix.width, pix.height, box), img)
    finally:
        painter.end()
    window.set_status(f"✓  Sent {len(pages)} page{'s' if len(pages) != 1 else ''} to the printer",
                      "success")
    return True
