"""Leaving a document workspace and coming back shows an empty page, not the
closed document: Annotate and Edit Text kept its title, page label and page
view, and the zoom then re-rendered a page of the closed file (review R3-1/R3-7)."""
import pytest

from qt_harness import make_pdf, pump

TOOLS = ["AnnotateTool", "EditTextTool", "FindReplaceTool", "RedactTool"]


@pytest.mark.parametrize("tool", TOOLS)
def test_coming_back_after_leaving_shows_no_document(window, tmp_path, tool):
    src = make_pdf(tmp_path / "doc.pdf", pages=2)
    assert window.open_tool(tool, src)
    pump(0.1)
    page = window.current_page()
    assert page.view._page is not None and "doc.pdf" in page.subtitle_label.text()
    window.show_page("home")
    pump(0.05)
    assert window.open_tool(tool)
    pump(0.05)
    assert page._doc is None
    assert page.view._page is None, "the page view still shows the closed document"
    assert page.page_label.text() == "–"
    assert "doc.pdf" not in page.subtitle_label.text()
    page.view.set_zoom(1.5)                  # used to raise AssertionError('page is None')
    page.show_current()
    pump(0.05)
