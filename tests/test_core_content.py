"""paperknife.core.annotate, .text and .redact without any user interface."""
import pymupdf as fitz
import pytest

from paperknife.core import annotate, redact, reflow, text


def _page_with(lines):
    doc = fitz.open()
    page = doc.new_page()
    for i, line in enumerate(lines):
        page.insert_text((72, 100 + i * 20), line, fontsize=12)
    return doc, page


@pytest.mark.parametrize("kind,type_name", [
    ("highlight", "Highlight"), ("underline", "Underline"), ("strikeout", "StrikeOut"),
    ("rect", "Square"), ("line", "Line"), ("note", "Text"), ("freetext", "FreeText")])
def test_annotate_add_makes_each_kind(kind, type_name):
    doc, page = _page_with(["Some words to mark"])
    ann = annotate.add(page, kind, (70, 88), (200, 104), (1, 0, 0), 0.5, "hello")
    assert ann is not None and ann.type[1] == type_name
    assert annotate.by_xref(page, ann.xref).xref == ann.xref
    if kind in ("note", "freetext"):
        assert ann.info["content"] == "hello"
    else:
        assert ann.opacity == pytest.approx(0.5, abs=0.01)


def test_annotate_unknown_kind_adds_nothing():
    doc, page = _page_with(["x"])
    assert annotate.add(page, "stamp", (0, 0), (10, 10), (0, 0, 0), 1.0) is None
    assert list(page.annots()) == []


def test_find_matches_is_case_sensitive_and_spans_lines():
    doc, page = _page_with(["Alpha beta", "gamma Beta"])
    assert len(text.find_matches(page, "beta")) == 1
    assert len(text.find_matches(page, "Beta")) == 1
    assert len(text.find_matches(page, "beta gamma")) == 1
    assert len(text.find_matches(page, "beta gamma")[0]["rects"]) == 2


def test_reflow_replace_all_rewrites_the_text():
    doc, page = _page_with(["The cat sat"])
    seen = []
    res = reflow.replace_all(doc, "cat", "dog", progress=seen.append)
    assert res.done == 1 and not res.skips
    assert "dog" in doc[0].get_text() and "cat" not in doc[0].get_text()
    assert seen == [1.0]


def test_reflow_rewrite_unit_rewrites_a_paragraph():
    doc, page = _page_with(["Original block text"])
    lines, _o = reflow.page_lines(page)
    unit = reflow.units(lines, reflow.PARAGRAPH)[0]
    assert reflow.rewrite_unit(doc, 0, unit, "Rewritten").done == 1
    assert "Rewritten" in page.get_text() and "Original" not in page.get_text()


def test_scrub_secrets_clears_metadata_bookmarks_and_notes():
    doc, page = _page_with(["Report for ACME Corp"])
    doc.set_metadata({"title": "ACME Corp plan", "author": "Someone"})
    doc.set_toc([[1, "About ACME Corp", 1], [1, "Other", 1]])
    note = page.add_text_annot((50, 50), "call ACME Corp")
    note.update()
    removed = redact.scrub_secrets(doc, {"ACME Corp": False})
    assert "document properties" in removed and "bookmarks" in removed
    assert "ACME Corp" not in (doc.metadata["title"] or "")
    assert [t for _, t, *_ in doc.get_toc()] == ["About ", "Other"]
    assert list(doc[0].annots()) == []
    assert redact.scrub_secrets(doc, {}) == []
