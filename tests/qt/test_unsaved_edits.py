"""Unsaved edits are never discarded silently (phase9/docui-brief.md section
4; memory inventory behaviour 3: every editing screen dropped them on leave
without asking).  The seven editors have a real dirty state; leaving, a new
document, Start over and closing the window ask "Save changes to <name>?"
with Save / Discard / Cancel."""
import pymupdf as fitz
import pytest

from qt_harness import make_pdf, pump, wait_job


def _edit_toc(window, dialogs, page):
    page.title_edit.setText("New")
    page.page_edit.setText("1")
    page._add()


def _edit_rotate(window, dialogs, page):
    page.select(0)
    page.rotate(90)


def _edit_metadata(window, dialogs, page):
    page.fields["title"].setText("Typed")


def _edit_annotate(window, dialogs, page):
    page.set_kind("rect")
    page._add_at((60, 60), (160, 120), False)


def _edit_text(window, dialogs, page):
    page.show_current()
    page.select_block(page._blocks[0]["bi"])
    page.edit_box.setPlainText("Changed words")
    page.apply_edit()


def _edit_find_replace(window, dialogs, page):
    page.find_edit.setText("Page")
    page.repl_edit.setText("Leaf")
    dialogs.asks.append(True)
    page.replace_all()
    wait_job(window)


def _edit_redact(window, dialogs, page):
    page._add_box((40, 40), (140, 90), False)


EDITORS = {
    "TocTool": _edit_toc, "RotateTool": _edit_rotate, "MetadataTool": _edit_metadata,
    "AnnotateTool": _edit_annotate, "EditTextTool": _edit_text,
    "FindReplaceTool": _edit_find_replace, "RedactTool": _edit_redact,
}


def _dirty_page(window, dialogs, tmp_path, tool):
    src = make_pdf(tmp_path / "doc.pdf", pages=3, text="Page {n} hello text")
    assert window.open_tool(tool, src)
    pump(0.1)
    page = window.current_page()
    assert not page.is_dirty(), "freshly opened"
    EDITORS[tool](window, dialogs, page)
    pump(0.05)
    assert page.is_dirty(), "the edit made no dirty state"
    return page, src


@pytest.mark.parametrize("tool", EDITORS)
def test_leaving_with_unsaved_edits_asks_and_cancel_stays(window, dialogs, tmp_path, tool):
    page, _src = _dirty_page(window, dialogs, tmp_path, tool)
    dialogs.unsaved.append("cancel")
    assert window.show_page("home") is False
    assert dialogs.msgs[-1] == ("ask_unsaved", "Save changes to doc.pdf?", "")
    assert window.current_page() is page and page.is_dirty()


@pytest.mark.parametrize("tool", EDITORS)
def test_discard_drops_the_edits_and_the_file_reopens_clean(window, dialogs, tmp_path, tool):
    page, src = _dirty_page(window, dialogs, tmp_path, tool)
    dialogs.unsaved.append("discard")
    assert window.show_page("home") is True
    assert window.open_tool(tool)
    pump(0.1)
    assert page._doc is not None and not page.is_dirty()


@pytest.mark.parametrize("tool", EDITORS)
def test_save_writes_the_edits_then_leaves(window, dialogs, tmp_path, tool):
    page, _src = _dirty_page(window, dialogs, tmp_path, tool)
    out = tmp_path / "saved.pdf"
    dialogs.unsaved.append("save")
    dialogs.save(out)
    if tool == "RedactTool":
        dialogs.asks.append(True)                 # its own "Permanently destroy…" question
    assert window.show_page("home") is False      # the save runs first
    wait_job(window)
    pump(0.05)
    with fitz.open(str(out)) as d:
        assert d.page_count == 3
    assert type(window.current_page()).__name__ == "HomePage"
    assert not page.is_dirty()


@pytest.mark.parametrize("tool", EDITORS)
def test_closing_the_window_asks(window, dialogs, tmp_path, tool):
    _dirty_page(window, dialogs, tmp_path, tool)
    dialogs.unsaved.append("cancel")
    window.close()
    pump(0.05)
    assert window.isVisible()
    assert dialogs.msgs[-1][0] == "ask_unsaved"


@pytest.mark.parametrize("tool", EDITORS)
def test_start_over_asks(window, dialogs, tmp_path, tool):
    page, _src = _dirty_page(window, dialogs, tmp_path, tool)
    page.offer_output(str(tmp_path / "other.pdf"))     # the question up, as after a job
    dialogs.unsaved.append("cancel")
    page.start_over()
    assert page.is_dirty() and page._doc is not None and window.current_document
    dialogs.unsaved.append("discard")
    page.start_over()
    assert page._doc is None and window.current_document is None


@pytest.mark.parametrize("tool", EDITORS)
def test_opening_another_document_asks(window, dialogs, tmp_path, tool):
    page, src = _dirty_page(window, dialogs, tmp_path, tool)
    other = make_pdf(tmp_path / "other.pdf")
    dialogs.unsaved.append("cancel")
    assert not window.open_document(other)
    assert page.is_dirty()
    from paperknife.qt.pages import same_path
    assert same_path(page.document_path(), src)
