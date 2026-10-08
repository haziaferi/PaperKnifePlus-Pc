"""Header / Footer: stamp a line of text into the margin of chosen pages."""
from __future__ import annotations

import pymupdf as fitz

from ..job_queue import atomic_output

def parse_style(size: str, margin: str) -> tuple[float, float]:
    """The font size and margin typed as text (blank = 10 and 20 pt).
    Raises ValueError with the message to show when either is not a number."""
    try:
        return float(size or "10"), float(margin or "20")
    except ValueError:
        raise ValueError("Enter numeric values for size and margin.") from None


def stamp_pdf(doc, out: str, pages, template: str, pos: str, font: str, size: float,
              margin: float, today: str, stop) -> bool:
    """Write *template* ({page}, {total} and {date} replaced, {date} by *today*)
    at *pos* on each 0-based page number in *pages* of *doc* (closed here).
    Returns False if cancelled, writing nothing."""
    total    = len(doc)
    is_top   = pos.startswith("top")
    is_left  = pos.endswith("left")
    is_right = pos.endswith("right")
    with atomic_output(out) as tmp, doc:
        for pg_num in pages:
            if stop.is_set():
                return False    # nothing written: atomic_output drops the file
            page = doc[pg_num]
            w, h = page.rect.width, page.rect.height
            text = (template
                    .replace("{page}",  str(pg_num + 1))
                    .replace("{total}", str(total))
                    .replace("{date}",  today))
            tw = fitz.get_text_length(text, fontname=font, fontsize=size)
            if is_left:
                x = margin
            elif is_right:
                x = w - margin - tw
            else:
                x = (w - tw) / 2

            y = margin + size if is_top else h - margin

            page.insert_text(
                fitz.Point(x, y), text,
                fontname=font, fontsize=size,
                color=(0, 0, 0),
            )

        doc.save(tmp, deflate=True)
    return True
