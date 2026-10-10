"""Redaction's line-art engine on malformed and edge-case content streams (L3-18).

The case corpus (tests/redact_cases.py) is redacted through the Qt Redact page
in tests/qt/test_redact_page.py and with no fill in tests/test_core_ported_C.py.
"""

import pymupdf as fitz
import pytest

from redact_cases import _outlines_inside, _raw_page


@pytest.mark.parametrize("content", [
    b"0 0 1 RG 3 w 60 600 m 360 640 y 460 600 l S",          # too few: zeros fill in
    b"0 0 1 RG 3 w 60 600 m 300 700 9 9 l 200 100 500 200 600 400 7 c S",  # too many
])
def test_wrong_operand_counts_are_read_as_mupdf_reads_them(content):
    from paperknife.lineart import cut_line_art
    doc = fitz.open()
    page = _raw_page(doc, content)
    boxes = [fitz.Rect(150, 150, 260, 320), fitz.Rect(330, 500, 420, 760)]
    assert _outlines_inside(page, boxes), "the case must draw into the boxes"
    cut_line_art(page, boxes)
    assert _outlines_inside(page, boxes) == []


@pytest.mark.parametrize("content", [
    b"EI BI /W -35 /H 1 /BPC 8 /CS /G ID x\nEI",                     # used to hang
    b"BI /W 1 ",                                                     # IndexError
    b"BI [1] 2 ID x EI",                                             # TypeError
    b"BI /W " + b"9" * 400 + b" /H 1 /BPC 8 /CS /G ID x EI",        # OverflowError
])
def test_malformed_inline_images_do_not_crash(content):
    from paperknife.lineart import cut_line_art
    doc = fitz.open()
    cut_line_art(_raw_page(doc, content + b" 0 g 10 10 m 300 300 l S"),
                 [fitz.Rect(100, 500, 200, 600)])


def test_a_dash_set_outside_a_form_keeps_its_phase_inside_it():
    from paperknife.lineart import cut_line_art
    doc = fitz.open()
    fm = doc.get_new_xref()
    doc.update_object(fm, "<</Type/XObject/Subtype/Form/BBox[0 0 595 842]>>")
    doc.update_stream(fm, b"0 g 2 w 100 100 m 500 100 l S")
    _raw_page(doc, b"[6 3] 0 d /Fm1 Do", f"<</XObject<</Fm1 {fm} 0 R>>>>")
    src = doc.tobytes()
    a, b = fitz.open("pdf", src), fitz.open("pdf", src)
    cut_line_art(b[0], [fitz.Rect(250, 730, 300, 760)])
    right = fitz.Rect(310, 735, 500, 750)
    pa = a[0].get_pixmap(dpi=144, clip=right, alpha=False).samples
    pb = b[0].get_pixmap(dpi=144, clip=right, alpha=False).samples
    assert sum(1 for x, y in zip(pa, pb, strict=True) if abs(x - y) > 48) == 0


