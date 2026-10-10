"""Erasing a word or a block must not take letters from the lines next to it.

Character boxes run from the font's ascender to its descender, so on tightly
spaced lines they reach into the line above and below; a redaction with those
boxes removed whole words of the neighbouring lines (12 of 23 program-shipped
PDFs in _qt-2026-10-09/phase10/fr_probe.py)."""
import threading

import pymupdf as fitz

from paperknife.core import text


def _tight_page(lines, size=12, leading=10.5):
    doc = fitz.open()
    page = doc.new_page()
    for i, line in enumerate(lines):
        page.insert_text((72, 100 + i * leading), line, fontsize=size, fontname="tiro")
    return doc


def _lines(page):
    return [ln for ln in page.get_text().splitlines() if ln.strip()]


def test_replacing_a_word_keeps_the_lines_above_and_below():
    doc = _tight_page(["Verkaufer fur den Betrag", "hiermit verkaufe an die", "Kaufer und Verkaufer"])
    found = text.find_all(doc, "verkaufe")
    assert len(found) == 1 and len(found[0][1]) == 1
    text.replace_matches(doc, found, "sells", text.unicode_font("sells"), stop=threading.Event())
    got = _lines(doc[0])
    assert "Verkaufer fur den Betrag" in got
    assert "Kaufer und Verkaufer" in got
    assert any("sells" in ln for ln in got) and not any("verkaufe " in ln for ln in got)


def test_rewriting_a_block_keeps_the_next_block():
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 100), "First block line", fontsize=12, fontname="tiro")
    page.insert_text((72, 110.5), "Second block stays", fontsize=12, fontname="tiro")
    blocks = text.text_blocks(page)
    first = next(b for _i, b in blocks if text.block_text(b).startswith("First"))
    if text.block_text(first).count("\n"):          # MuPDF made one block of both
        first["lines"] = first["lines"][:1]
        first["bbox"] = first["lines"][0]["bbox"]
    text.write_block(page, first, "Rewritten")
    got = _lines(page)
    assert "Second block stays" in got
    assert "Rewritten" in got and "First block line" not in got
