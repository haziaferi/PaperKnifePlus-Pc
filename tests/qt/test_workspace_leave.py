"""Leaving a document workspace closes its document and never leaves the
closed one on show: Annotate and Edit Text kept its title, page label and
page view, and the zoom then re-rendered a page of the closed file (review
R3-1/R3-7).  Since 2026-10-10 (owner) the workspace follows the current
document: coming back opens the same file again."""
import pytest

from qt_harness import make_pdf, pump

TOOLS = ["AnnotateTool", "EditTextTool", "FindReplaceTool", "RedactTool"]


@pytest.mark.parametrize("tool", TOOLS)
def test_coming_back_after_leaving_shows_the_document_again(window, tmp_path, tool):
    src = make_pdf(tmp_path / "doc.pdf", pages=2)
    assert window.open_tool(tool, src)
    pump(0.1)
    page = window.current_page()
    assert page.view._page is not None and "doc.pdf" in page.subtitle_label.text()
    old = page._doc
    window.show_page("home")
    pump(0.05)
    assert old.is_closed and page._doc is None
    assert page.view._page is None, "the page view still shows the closed document"
    assert page.page_label.text() == "–"
    page.view.set_zoom(1.5)                  # used to raise AssertionError('page is None')
    page.show_current()
    assert window.open_tool(tool)
    pump(0.05)
    assert page._doc is not None and page._doc is not old
    assert page.view._page is not None and page.page_label.text() == "1 / 2"
    assert "doc.pdf" in page.subtitle_label.text()
