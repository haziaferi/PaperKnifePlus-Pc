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
    assert pdftools.remove_pages(fitz.open(src), str(out), [1]) == 1
    with fitz.open(out) as d:
        assert len(d) == 2 and d.get_toc() == [[1, "Last", 2]]


def test_remove_pages_never_removes_every_page(tmp_path):
    src = _pages(tmp_path / "in.pdf", ["blank", "blank"])
    out = tmp_path / "out.pdf"
    with pytest.raises(ValueError, match="at least one page"):
        pdftools.remove_pages(fitz.open(src), str(out), [0, 1])
    assert not out.exists()
