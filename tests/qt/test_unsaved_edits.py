"""Unsaved edits are never discarded silently (phase9/docui-brief.md section
4; memory inventory behaviour 3).  Since 2026-10-23 (owner) the edits are the
window's one document's: changing tool takes them along, unasked; a new
document, Start over and closing the window ask "Save changes to <name>?"
with Save / Discard / Cancel, and Save writes over the file."""
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


# Each editor's edit, and how the saved file shows it.
EDITORS = {
    "TocTool": (_edit_toc, lambda d: d.get_toc() == [[1, "New", 1]]),
    "RotateTool": (_edit_rotate, lambda d: d[0].rotation == 90),
    "MetadataTool": (_edit_metadata, lambda d: d.metadata["title"] == "Typed"),
    "AnnotateTool": (_edit_annotate, lambda d: len(list(d[0].annots())) == 1),
    "EditTextTool": (_edit_text, lambda d: "Changed words" in d[0].get_text()),
    "FindReplaceTool": (_edit_find_replace, lambda d: "Leaf" in d[0].get_text()),
}


def _dirty_page(window, dialogs, tmp_path, tool):
    src = make_pdf(tmp_path / "doc.pdf", pages=3, text="Page {n} hello text")
    assert window.open_tool(tool, src)
    pump(0.1)
    page = window.current_page()
    assert not page.is_dirty(), "freshly opened"
    EDITORS[tool][0](window, dialogs, page)
    pump(0.05)
    assert page.is_dirty(), "the edit made no dirty state"
    return page, src


@pytest.mark.parametrize("tool", EDITORS)
def test_changing_tool_takes_the_edits_along_unasked(window, dialogs, tmp_path, tool):
    page, _src = _dirty_page(window, dialogs, tmp_path, tool)
    assert window.show_page("home") is True        # nothing asked (the harness would fail)
    assert window.has_unsaved()
    assert window.open_tool(tool)
    pump(0.05)
    assert window.current_page() is page and page.is_dirty()


@pytest.mark.parametrize("tool", EDITORS)
def test_the_title_names_the_file_and_marks_unsaved_edits(window, dialogs, tmp_path, tool):
    page, _src = _dirty_page(window, dialogs, tmp_path, tool)
    if tool in ("MetadataTool", "TocTool"):
        # typed in the tool, not applied yet: the document has no edit
        assert page.has_pending() and window.windowTitle().startswith("doc.pdf — ")
        assert page.commit_edits()
    assert window.windowTitle().startswith("doc.pdf* — ")
    assert window.windowTitle().endswith("v4.0.0")


@pytest.mark.parametrize("tool", EDITORS)
def test_save_writes_over_the_file_unasked(window, dialogs, tmp_path, tool):
    page, src = _dirty_page(window, dialogs, tmp_path, tool)
    window.save()
    wait_job(window)
    pump(0.05)
    with fitz.open(src) as d:
        assert d.page_count == 3 and EDITORS[tool][1](d)
    assert not page.is_dirty() and not window.has_unsaved()
    assert window.windowTitle().startswith("doc.pdf — ")
    assert window.status_text() == "✓  Saved → doc.pdf"


@pytest.mark.parametrize("tool", EDITORS)
def test_save_as_writes_a_new_file_the_document_then_belongs_to(window, dialogs, tmp_path,
                                                                tool):
    page, src = _dirty_page(window, dialogs, tmp_path, tool)
    out = tmp_path / "copy.pdf"
    dialogs.save(out)
    window.save_as()
    wait_job(window)
    pump(0.05)
    with fitz.open(out) as d:
        assert EDITORS[tool][1](d)
    with fitz.open(src) as d:
        assert not EDITORS[tool][1](d)              # the first file is as it was
    from paperknife.qt.pages import same_path
    assert same_path(window.document.path, out) and same_path(window.current_document, out)
    assert same_path(page.document_path(), out)
    assert window.windowTitle().startswith("copy.pdf — ")


@pytest.mark.parametrize("tool", EDITORS)
def test_opening_another_document_asks_and_cancel_keeps_the_edits(window, dialogs, tmp_path,
                                                                  tool):
    page, src = _dirty_page(window, dialogs, tmp_path, tool)
    other = make_pdf(tmp_path / "other.pdf")
    dialogs.unsaved.append("cancel")
    assert not window.open_document(other)
    assert dialogs.msgs[-1] == ("ask_unsaved", "Save changes to doc.pdf?", "")
    assert page.is_dirty()
    from paperknife.qt.pages import same_path
    assert same_path(page.document_path(), src)


@pytest.mark.parametrize("tool", EDITORS)
def test_discard_opens_the_other_document_clean(window, dialogs, tmp_path, tool):
    page, src = _dirty_page(window, dialogs, tmp_path, tool)
    other = make_pdf(tmp_path / "other.pdf", pages=2)
    dialogs.unsaved.append("discard")
    assert window.open_document(other)
    pump(0.05)
    assert len(window.document.doc) == 2 and not page.is_dirty()
    with fitz.open(src) as d:
        assert not EDITORS[tool][1](d)              # nothing was written


@pytest.mark.parametrize("tool", EDITORS)
def test_save_in_the_question_writes_then_opens_the_other(window, dialogs, tmp_path, tool):
    page, src = _dirty_page(window, dialogs, tmp_path, tool)
    other = make_pdf(tmp_path / "other.pdf", pages=2)
    dialogs.unsaved.append("save")
    assert window.open_document(other) is False     # the save runs first
    wait_job(window)
    pump(0.05)
    with fitz.open(src) as d:
        assert EDITORS[tool][1](d)
    assert len(window.document.doc) == 2 and not window.has_unsaved()


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
    assert not window.document.is_open()


def test_an_edit_in_one_tool_shows_in_the_next(window, dialogs, tmp_path):
    src = make_pdf(tmp_path / "doc.pdf", pages=3)
    assert window.open_tool("RotateTool", src)
    pump(0.1)
    rot = window.current_page()
    rot.select(0)
    rot.rotate(90)
    assert window.open_tool("AnnotateTool")
    pump(0.1)
    ann = window.current_page()
    assert ann._doc is rot._doc is window.document.doc and ann._doc[0].rotation == 90


def test_undo_takes_back_the_last_edit_whichever_tool_made_it(window, dialogs, tmp_path):
    src = make_pdf(tmp_path / "doc.pdf", pages=3)
    assert window.open_tool("RotateTool", src)
    pump(0.1)
    rot = window.current_page()
    rot.select(0)
    rot.rotate(90)
    assert window.open_tool("AnnotateTool")
    pump(0.1)
    ann = window.current_page()
    _edit_annotate(window, dialogs, ann)
    assert len(list(ann._doc[0].annots())) == 1
    assert window.undo()                            # the note goes
    assert len(list(window.document.doc[0].annots())) == 0
    assert window.document.doc[0].rotation == 90
    assert window.undo()                            # then Rotate's turn
    assert window.document.doc[0].rotation == 0
    assert window.status_text() == "✓  Undone: Rotate pages"
    assert not window.undo() and window.status_text() == "Nothing to undo"


def test_print_sends_the_chosen_pages_with_the_unsaved_edits(window, dialogs, tmp_path):
    src = make_pdf(tmp_path / "doc.pdf", pages=4)
    assert window.open_tool("RotateTool", src)
    pump(0.1)
    page = window.current_page()
    page.select(1)
    page.rotate(90)
    dialogs.print_file = tmp_path / "printed.pdf"
    dialogs.prints.append((2, 3))
    assert window.print_document()
    with fitz.open(dialogs.print_file) as d:
        assert d.page_count == 2
        # page 2 turned: drawn landscape inside the portrait sheet
        img = d[0].get_pixmap(dpi=20)
        assert img.width < img.height
    assert window.status_text() == "✓  Sent 2 pages to the printer"
    dialogs.prints.append(False)                    # Cancel prints nothing
    assert not window.print_document()


def test_print_and_save_without_a_document_warn(window, dialogs):
    assert not window.print_document()
    window.save()
    window.save_as()
    assert [m[1] for m in dialogs.warnings()] == ["Print", "Save", "Save as"]
