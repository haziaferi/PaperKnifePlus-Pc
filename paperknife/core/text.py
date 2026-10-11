"""Text on PDF pages: find, the fonts that can draw a replacement, span
colours, and the erase box.  Replacing and rewriting text is core.reflow."""
from __future__ import annotations

import pymupdf as fitz



def span_rgb(color: int) -> tuple[float, float, float]:
    """A get_text span colour (0xRRGGBB) as an RGB tuple of 0-1 floats."""
    return ((color >> 16) / 255, ((color >> 8) & 0xFF) / 255, (color & 0xFF) / 255)


def erase_box(bbox, origin, size: float, horizontal: bool = True) -> fitz.Rect:
    """The box that erases one run of letters and nothing of its neighbours.

    A character box runs from the font's ascender to its descender, so on
    tightly spaced lines it reaches into the line above and below, and a
    redaction with it takes their letters too; the middle band of the letters
    (0.15 to 0.55 of the size above the baseline) is clear of both.  Text that
    does not run left to right keeps its box."""
    r = fitz.Rect(bbox)
    if not horizontal:
        return r
    return fitz.Rect(r.x0, origin[1] - 0.55 * size, r.x1, origin[1] - 0.15 * size)


def find_matches(page, needle: str) -> list[dict]:
    """Case-sensitive matches of *needle* in the page text.

    Each match is {"rects": one rect per text line it covers, "origin": baseline
    point of its first character, "span": the span that character belongs to}.
    page.search_for is case-insensitive and returns a wrapped match as several
    unrelated rects, so the page characters are searched directly.
    """
    chars = []   # (c, bbox | None, origin, span, line_no); bbox None = line break
    raw = page.get_text("rawdict", flags=fitz.TEXT_PRESERVE_WHITESPACE | fitz.TEXT_MEDIABOX_CLIP)
    line_no = 0
    for block in raw.get("blocks", []):
        for line in block.get("lines", []):
            if chars and not chars[-1][0].isspace():
                chars.append((" ", None, None, None, line_no))
            for span in line["spans"]:
                for ch in span["chars"]:
                    chars.append((ch["c"], fitz.Rect(ch["bbox"]), ch["origin"], span, line_no))
            line_no += 1
    text = "".join(c[0] for c in chars)
    matches = []
    i = text.find(needle)
    while i >= 0 and needle:
        part = [c for c in chars[i:i + len(needle)] if c[1] is not None]
        by_line: dict[int, fitz.Rect] = {}
        for _, bbox, _, _, ln in part:
            by_line[ln] = by_line[ln] | bbox if ln in by_line else fitz.Rect(bbox)
        matches.append({"rects": list(by_line.values()),
                        "origin": fitz.Point(part[0][2]), "span": part[0][3]})
        i = text.find(needle, i + len(needle))
    return matches


def find_all(doc, needle: str, stop=None, progress=lambda v: None) -> list | None:
    """[(page number, find_matches of that page)] for every page with a match,
    or None when *stop* was set.  progress(fraction) after each page."""
    found, total = [], len(doc)
    for pg_num in range(total):
        if stop is not None and stop.is_set():
            return None
        if ms := find_matches(doc[pg_num], needle):
            found.append((pg_num, ms))
        progress((pg_num + 1) / total)
    return found


def unicode_font(text: str):
    """A built-in font with a glyph for every character of *text*, or None."""
    for name in ("helv", "cjk"):
        font = fitz.Font(name)
        if all(font.has_glyph(ord(c)) for c in text if not c.isspace()):
            return font
    return None
