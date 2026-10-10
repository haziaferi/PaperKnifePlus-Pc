"""Leaving a document workspace closes its document and never leaves the
closed one on show: Annotate and Edit Text kept its title, page label and
page view, and the zoom then re-rendered a page of the closed file (review
R3-1/R3-7).  Since 2026-10-10 (owner) the workspace follows the current
document: coming back opens the same file again."""
import pytest

from qt_harness import make_pdf, pump

TOOLS = ["AnnotateTool", "EditTextTool", "FindReplaceTool", "RedactTool"]


def _names(page, name):
    """The page says it acts on *name*: its subtitle (PK_DOCUI=nav, or a
    subtitle that only said to open a file) or its bar chip (bar)."""
    chip = page.doc_bar.chip.name_label.text() if page.doc_bar is not None else ""
    return name in page.subtitle_label.text() or chip == name


@pytest.mark.parametrize("tool", TOOLS)
def test_coming_back_after_leaving_shows_the_document_again(window, tmp_path, tool):
    src = make_pdf(tmp_path / "doc.pdf", pages=2)
    assert window.open_tool(tool, src)
    pump(0.1)
    page = window.current_page()
    assert page.view._page is not None and _names(page, "doc.pdf")
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
    assert _names(page, "doc.pdf")

