"""Erasing a word or a paragraph must not take letters from the lines next to it.

Character boxes run from the font's ascender to its descender, so on tightly
spaced lines they reach into the line above and below; a redaction with those
boxes removed whole words of the neighbouring lines (12 of 23 program-shipped
PDFs in _qt-2026-10-09/phase10/fr_probe.py).  core.reflow erases with
text.erase_box, the middle band of the letters."""
import pymupdf as fitz

from paperknife.core import reflow


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
    res = reflow.replace_all(doc, "verkaufe", "sells", unit=reflow.LINE)
    assert res.done == 1, res.skips
    got = " ".join(doc[0].get_text(sort=True).split())
    assert "Verkaufer fur den Betrag" in got and "Kaufer und Verkaufer" in got
    assert "hiermit sells an die" in got


def test_rewriting_a_line_keeps_the_next_line():
    doc = _tight_page(["First block line", "Second block stays"])
    page = doc[0]
    lines, _o = reflow.page_lines(page)
    first = [ln for ln in lines if ln.text.startswith("First")]
    assert reflow.rewrite_unit(doc, 0, first, "Rewritten", unit=reflow.LINE).done == 1
    got = _lines(page)
    assert "Second block stays" in got
    assert "Rewritten" in got and "First block line" not in got
