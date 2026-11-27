"""PDF Tools' new core tools (owner, 2026-10-18): sanitise, flatten, blank
pages; each checked on the file written, read back.  (Repair:
test_core_pdftools.py.)"""
import pymupdf as fitz
import pytest

from paperknife.core import pdftools


def _risky(path):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 100), "Visible text", fontsize=14)
    cat = doc.pdf_catalog()
    doc.xref_set_key(cat, "OpenAction", "<</S/JavaScript/JS(app.alert(1))>>")
    doc.xref_set_key(cat, "Names", "<</JavaScript<</Names[(init)<</S/JavaScript/JS(go())>>]>>>>")
    doc.embfile_add("secret.txt", b"hidden", filename="secret.txt")
    doc.set_xml_metadata("<x:xmpmeta xmlns:x='adobe:ns:meta/'><r>who</r></x:xmpmeta>")
    page.insert_link({"kind": fitz.LINK_LAUNCH, "from": fitz.Rect(72, 200, 200, 220),
                      "file": "calc.exe"})
    page.insert_link({"kind": fitz.LINK_URI, "from": fitz.Rect(72, 240, 200, 260),
                      "uri": "https://example.org"})
    doc.save(str(path))
    doc.close()
    return str(path)


def _raw(path) -> bytes:
    with fitz.open(path) as d:
        return b"".join(d.xref_object(x, compressed=True).encode("latin-1", "replace")
                        for x in range(1, d.xref_length()))


def test_sanitise_removes_what_runs_or_hides_and_keeps_the_page(tmp_path):
    src = _risky(tmp_path / "in.pdf")
    out = tmp_path / "out.pdf"
    found = pdftools.sanitise_pdf(fitz.open(src), str(out))
    assert found == {"javascript": 2, "embedded": 1, "xmp": 1, "actions": 1}
    with fitz.open(out) as d:
        assert "Visible text" in d[0].get_text()
        assert d.embfile_count() == 0
        assert not d.get_xml_metadata().strip()
        assert [ln["kind"] for ln in d[0].get_links()] == [fitz.LINK_URI]  # the web link stays
    raw = _raw(out)
    # The scripts and their actions are gone (an emptied key may stay, as null).
    assert b"app.alert" not in raw and b"go()" not in raw and b"/S/JavaScript" not in raw
    assert b"/S/Launch" not in raw and b"calc.exe" not in raw and b"hidden" not in raw


def test_sanitise_leaves_what_is_switched_off(tmp_path):
    src = _risky(tmp_path / "in.pdf")
    out = tmp_path / "out.pdf"
    found = pdftools.sanitise_pdf(fitz.open(src), str(out), embedded=False, xmp=False)
    assert found["embedded"] == 0 and found["xmp"] == 0
    with fitz.open(out) as d:
        assert d.embfile_count() == 1 and d.get_xml_metadata().strip()


def test_sanitise_of_a_clean_file_finds_nothing(tmp_path):
    doc = fitz.open()
    doc.new_page().insert_text((72, 100), "plain", fontsize=12)
    doc.save(str(tmp_path / "in.pdf"))
    doc.close()
    found = pdftools.sanitise_pdf(fitz.open(str(tmp_path / "in.pdf")), str(tmp_path / "o.pdf"))
    assert found == {"javascript": 0, "embedded": 0, "xmp": 0, "actions": 0}


def _with_forms(path):
    doc = fitz.open()
    page = doc.new_page()
    page.add_text_annot((100, 100), "a note")
    page.add_rect_annot(fitz.Rect(150, 150, 250, 200))
    w = fitz.Widget()
    w.field_type = fitz.PDF_WIDGET_TYPE_TEXT
    w.field_name = "name"
    w.field_value = "Ada"
    w.rect = fitz.Rect(72, 300, 272, 320)
    page.add_widget(w)
    doc.save(str(path))
    doc.close()
    return str(path)


def test_flatten_bakes_comments_and_fields(tmp_path):
    src = _with_forms(tmp_path / "in.pdf")
    out = tmp_path / "out.pdf"
    found = pdftools.flatten_pdf(fitz.open(src), str(out))
    assert found == {"comments": 2, "fields": 1}
    with fitz.open(out) as d:
        assert list(d[0].annots()) == [] and list(d[0].widgets()) == []
        assert "Ada" in d[0].get_text()                 # the field's value is page content now


def test_flatten_only_comments_keeps_the_fields(tmp_path):
    src = _with_forms(tmp_path / "in.pdf")
    out = tmp_path / "out.pdf"
    found = pdftools.flatten_pdf(fitz.open(src), str(out), fields=False)
    assert found == {"comments": 2, "fields": 0}
    with fitz.open(out) as d:
        assert list(d[0].annots()) == [] and len(list(d[0].widgets())) == 1


def _pages(path, kinds):
    doc = fitz.open()
    for k in kinds:
        p = doc.new_page()
        if k == "text":
            p.insert_text((72, 100), "words", fontsize=12)
        elif k == "line":
            p.draw_line((72, 72), (300, 72))
        elif k == "white":
            p.draw_rect(p.rect, color=None, fill=(1, 1, 1))
        elif k == "note":
            p.add_text_annot((100, 100), "x")
    doc.save(str(path))
    doc.close()
    return str(path)


def test_blank_pages_are_those_with_nothing_that_shows(tmp_path):
    src = _pages(tmp_path / "in.pdf", ["text", "blank", "line", "white", "note", "blank"])
    with fitz.open(src) as d:
        assert pdftools.blank_pages(d) == [1, 3, 5]


def test_remove_pages_keeps_the_rest_in_order(tmp_path):
    src = _pages(tmp_path / "in.pdf", ["text", "blank", "text"])
    d = fitz.open(src)
    d.set_toc([[1, "Last", 3]])
    d.saveIncr()
    d.close()
    out = tmp_path / "out.pdf"
    removed = pdftools.remove_pages(fitz.open(src), str(out), [1])   # closes the document
    assert removed == 1
    with fitz.open(out) as d:
        assert len(d) == 2 and d.get_toc() == [[1, "Last", 2]]


def test_remove_pages_never_removes_every_page(tmp_path):
    src = _pages(tmp_path / "in.pdf", ["blank", "blank"])
    out = tmp_path / "out.pdf"
    with pytest.raises(ValueError, match="at least one page"):
        pdftools.remove_pages(fitz.open(src), str(out), [0, 1])
    assert not out.exists()


def _scan(doc, level=248, marks=(), dpi=150):
    """A page holding one JPEG of A4 paper at *dpi*: grain around *level*, and
    each (box, grey) of *marks* drawn on it."""
    import io
    from PIL import Image, ImageDraw
    size = (round(8.27 * dpi), round(11.69 * dpi))
    im = Image.effect_noise(size, 3).point(lambda v: max(0, min(255, v - 128 + level)))
    draw = ImageDraw.Draw(im)
    for box, grey in marks:
        draw.rectangle(box, fill=grey)
    buf = io.BytesIO()
    im.convert("RGB").save(buf, "JPEG", quality=75)
    page = doc.new_page(width=595.28, height=841.89)
    page.insert_image(page.rect, stream=buf.getvalue())


def test_a_scanned_page_of_empty_paper_is_blank_and_one_with_a_mark_is_not(tmp_path):
    """2026-11-27: every page holding an image was refused, so the back of a
    scanned sheet was never found.  A short pen stroke (about 0.5 x 3.6 mm) keeps
    its page."""
    doc = fitz.open()
    _scan(doc)                                              # empty paper
    _scan(doc, level=205)                                   # grey recycled paper
    _scan(doc, marks=[((600, 800, 602, 820), 40)])          # one short pen stroke
    _scan(doc, marks=[((560, 800, 640, 806), 165)])         # a light pencil line
    _scan(doc, level=40)                                    # a dark page: not paper
    _scan(doc, marks=[((200, 300, 1000, 1400), 120)])       # a picture on the page
    assert pdftools.blank_pages(doc) == [0, 1]
    plain = doc.new_page()                                  # no image: not a scan
    assert pdftools.is_scan(doc[0]) and not pdftools.is_scan(plain)
    doc.close()


def test_a_mark_near_the_edge_keeps_its_page_and_an_edge_shadow_does_not(tmp_path):
    """A footer 1.6 % from the bottom edge was cut off with the edge band; a
    scanner's shadow is a strip along the whole edge, a footer has gaps."""
    w = round(8.27 * 150)
    words = [((x, 1726, x + 40, 1738), 30) for x in range(200, 900, 60)]
    doc = fitz.open()
    _scan(doc, marks=words)                                 # a footer near the bottom edge
    _scan(doc, marks=[((0, 0, round(w * 0.012), 1754), 70)])   # a shadow down the left edge
    _scan(doc, marks=[((0, 0, w, 15), 60), ((0, 0, 15, 1754), 60)])   # two dark scan borders
    assert pdftools.blank_pages(doc) == [1, 2]
    doc.close()


def test_a_very_large_page_holding_an_image_is_read_without_running_out(tmp_path):
    import io
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (40, 40), "white").save(buf, "PNG")
    doc = fitz.open()
    page = doc.new_page(width=14400, height=14400)          # the largest a PDF page may be
    page.insert_image(fitz.Rect(0, 0, 200, 200), stream=buf.getvalue())
    assert pdftools.blank_pages(doc) == [0]
    doc.close()


def test_blank_pages_reports_progress_and_stops_when_asked(tmp_path):
    import threading
    doc = fitz.open()
    for _ in range(4):
        doc.new_page()
    seen = []
    assert pdftools.blank_pages(doc, progress=seen.append) == [0, 1, 2, 3]
    assert seen == [0.25, 0.5, 0.75, 1.0]
    stop = threading.Event()
    stop.set()
    assert pdftools.blank_pages(doc, stop) == []
    doc.close()
