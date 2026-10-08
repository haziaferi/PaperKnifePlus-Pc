"""PDF Tools: repair a damaged file."""
from __future__ import annotations

from ..job_queue import atomic_output


def repair_pdf(doc, out: str) -> bool:
    """Write a fresh, consistent copy of *doc* (closed here) to *out*.
    Returns True when MuPDF had to rebuild a broken xref to open it."""
    # MuPDF rebuilds a broken xref while opening; the garbage/clean save
    # then writes a fresh, consistent file from what it recovered.
    with atomic_output(out) as tmp, doc:
        repaired = doc.is_repaired
        doc.save(tmp, deflate=True, garbage=4, clean=True)
    return repaired
