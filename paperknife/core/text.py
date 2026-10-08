"""Text on PDF pages: find and replace, rewrite a block, span colours."""
from __future__ import annotations

import pymupdf as fitz

from ..pages import textwriter_point


def span_rgb(color: int) -> tuple[float, float, float]:
    """A get_text span colour (0xRRGGBB) as an RGB tuple of 0-1 floats."""
    return ((color >> 16) / 255, ((color >> 8) & 0xFF) / 255, (color & 0xFF) / 255)


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


def replace_matches(doc, found: list, repl: str, font, stop=None,
                    progress=lambda v: None):
    """Redact each match in *found* [(page number, matches)] and write
    *repl* at its origin in the span's colour and size."""
    n = len(found)
    for i, (pg_num, matches) in enumerate(found):
        if stop is not None and stop.is_set():
            return                  # the job reports a cancel; settle() undoes
        if stop is not None:
            progress(0.5 + (i + 1) / n * 0.5)
        page = doc[pg_num]
        for m in matches:
            for r in m["rects"]:
                page.add_redact_annot(r)
        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE,
                              graphics=fitz.PDF_REDACT_LINE_ART_NONE)
        for m in matches:
            if not repl:
                continue
            tw = fitz.TextWriter(page.rect, color=span_rgb(m["span"]["color"]))
            tw.append(textwriter_point(page, m["origin"]), repl,
                      font=font, fontsize=m["span"]["size"])
            tw.write_text(page)


def block_font(name: str) -> tuple[fitz.Font, bool]:
    """(font, True) for a font MuPDF has built in, else (Helvetica, False)."""
    try:
        return fitz.Font(name), True
    except fitz.mupdf.FzErrorBase:
        return fitz.Font("helv"), False


def text_blocks(page) -> list[tuple[int, dict]]:
    """(index, block) for each text block of *page*, in page space.

    "dict" spans carry their 'text'; "rawdict" spans only have per-char entries."""
    raw = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)
    return [(bi, b) for bi, b in enumerate(raw.get("blocks", [])) if b.get("type") == 0]


def block_text(block: dict) -> str:
    """The block's text with its line breaks kept, for editing.

    Spans are consecutive runs of one line; their text already holds the spaces."""
    return "\n".join("".join(s["text"] for s in line.get("spans", []))
                     for line in block.get("lines", []))


def block_style(block: dict) -> tuple:
    """Return (font_name, font_size, rgb) from the first span of the block."""
    try:
        span  = block["lines"][0]["spans"][0]
        size  = span.get("size", 11)
        c     = span.get("color", 0)
        font  = span.get("font", "helv")
        return font, size, span_rgb(c)
    except (IndexError, KeyError):
        return "helv", 11, (0, 0, 0)

def word_wrap(text: str, font: fitz.Font, font_size: float,
               max_width: float) -> list:
    """Lines of *text* that fit within *max_width* points; a newline in
    *text* is a hard break."""
    result = []
    for paragraph in text.split("\n"):
        words = paragraph.split()
        if not words:
            result.append("")
            continue
        current = ""
        for word in words:
            candidate = f"{current} {word}".lstrip() if current else word
            if font.text_length(candidate, fontsize=font_size) <= max_width:
                current = candidate
            else:
                if current:
                    result.append(current)
                current = word   # single overlong word goes on its own line
        if current:
            result.append(current)
    return result or [""]


def write_block(page, block: dict, new_tx: str) -> bool:
    """Replace *block*'s text with *new_tx*.  Returns False when the
    block's font is not built in and Helvetica was used instead."""
    bx0, by0, bx1, _ = block["bbox"]
    block_width = bx1 - bx0

    font_name, font_size, rgb = block_style(block)
    font, own_font = block_font(font_name)

    # Derive line height from original spacing; fall back to 1.2× size.
    lines_raw = block.get("lines", [])
    if len(lines_raw) >= 2:
        tops = [ln["bbox"][1] for ln in lines_raw]
        line_height = sum(tops[i+1] - tops[i]
                          for i in range(len(tops) - 1)) / (len(tops) - 1)
    else:
        line_height = font_size * 1.2

    for line in lines_raw:
        for span in line.get("spans", []):
            page.add_redact_annot(fitz.Rect(span["bbox"]))
    # Defaults would also blank image pixels and line art under each span box.
    page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE,
                          graphics=fitz.PDF_REDACT_LINE_ART_NONE)

    wrapped = word_wrap(new_tx, font, font_size, block_width)

    tw = fitz.TextWriter(page.rect)
    # by0 is the top of the first line; add font_size to get the baseline.
    baseline_y = by0 + font_size
    for i, wline in enumerate(wrapped):
        if wline:
            tw.append(textwriter_point(page, (bx0, baseline_y + i * line_height)),
                      wline, font=font, fontsize=font_size)

    tw.write_text(page, color=rgb)
    return own_font
