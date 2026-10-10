"""The current document (owner's decisions, phase9/docui-brief.md section 1):
MainWindow holds one current document; every way of opening a PDF sets it,
the single-input screens follow it when shown, an editor with unsaved edits
keeps its file and asks, and the Open control lists the recent files."""
import pytest

from qt_harness import make_pdf, pump, wait_job

SINGLE_INPUT = ["CompressTool", "SplitTool", "PasswordTool", "PdfToolsTool", "CropTool",
                "WatermarkTool", "NormaliseTool", "HeaderFooterTool", "OCRTool",
                "Pdf2ImgTool", "ExtractTool", "Pdf2DocTool", "TocTool", "RotateTool",
                "BookmarksTool", "MetadataTool", "AnnotateTool", "EditTextTool",
                "FindReplaceTool", "RedactTool", "ReaderTool"]
# The eight that cleared their input on leave (memory inventory, behaviour 2).
CLEARED_ON_LEAVE = ["TocTool", "RotateTool", "BookmarksTool", "MetadataTool",
                    "AnnotateTool", "EditTextTool", "FindReplaceTool", "RedactTool"]


def _same(a, b):
    from paperknife.qt.pages import same_path
    return same_path(a, b)


def _open(window, tool, path=None):
    assert window.open_tool(tool, path)
    pump(0.05)
    return window.current_page()


# ── set by each way of opening a PDF ─────────────────────────────────────────
def test_a_pdf_dropped_on_home_opens_in_the_reader_and_becomes_current(window, tmp_path):
    src = make_pdf(tmp_path / "a.pdf")
    window.show_page("home")
    seen = []
    window.current_document_changed.connect(seen.append)
    assert window.forward_drop([src]) == 1
    pump(0.05)
    assert type(window.current_page()).__name__ == "ReaderPage"
    assert _same(window.current_document, src) and seen == [window.current_document]


def test_a_pdf_dropped_on_a_tool_becomes_current(window, tmp_path):
    src = make_pdf(tmp_path / "a.pdf")
    page = _open(window, "CompressTool")
    assert window.forward_drop([src]) == 1
    assert _same(window.current_document, src) and _same(page.file.path(), src)


def test_a_pdf_dropped_on_a_workspace_becomes_current(window, tmp_path):
    src = make_pdf(tmp_path / "a.pdf")
    page = _open(window, "AnnotateTool")
    assert window.forward_drop([src]) == 1
    assert _same(window.current_document, src) and page._doc is not None


def test_the_open_control_s_file_dialog_makes_the_file_current(window, dialogs, tmp_path):
    src = make_pdf(tmp_path / "a.pdf")
    page = _open(window, "SplitTool")
    dialogs.open(src)
    assert window.browse_document()
    assert _same(window.current_document, src) and _same(page.file.path(), src)


def test_choosing_a_file_in_a_single_input_tool_makes_it_current(window, dialogs, tmp_path):
    src, other = make_pdf(tmp_path / "a.pdf"), make_pdf(tmp_path / "b.pdf")
    page = _open(window, "WatermarkTool")
    page.file.set_path(src)                       # what the tool's own choice does
    assert _same(window.current_document, src)
    dialogs.open(other)
    page.open()                                   # Ctrl+O
    assert _same(window.current_document, other) and _same(page.file.path(), other)


def test_opening_in_the_reader_makes_the_file_current(window, tmp_path):
    src = make_pdf(tmp_path / "a.pdf")
    _open(window, "ReaderTool", src)
    assert _same(window.current_document, src)


def test_a_recent_file_chosen_from_the_open_control_becomes_current_and_loads(window, tmp_path):
    from paperknife.qt.docui import BROWSE_TEXT
    from paperknife.recent import RECENT
    old, new = make_pdf(tmp_path / "old.pdf"), make_pdf(tmp_path / "new.pdf")
    RECENT.push(old, 3)
    RECENT.push(new, 3)
    page = _open(window, "MetadataTool")
    control = page.doc_bar.open_control              # the one Open control
    menu = control.menu()
    acts = [a for a in menu.actions() if not a.isSeparator()]
    assert [a.text() for a in acts] == ["new.pdf", "old.pdf", BROWSE_TEXT]   # newest first
    acts[1].trigger()
    assert _same(window.current_document, old)
    assert _same(page.file.path(), old) and page._doc is not None


# ── the screens follow it ────────────────────────────────────────────────────
def test_a_tool_shown_switches_to_the_current_document(window, tmp_path):
    a, b = make_pdf(tmp_path / "a.pdf"), make_pdf(tmp_path / "b.pdf")
    compress = _open(window, "CompressTool")
    compress.file.set_path(a)
    split = _open(window, "SplitTool")
    assert _same(split.file.path(), a)            # starts with the current document
    split.file.set_path(b)
    assert _same(window.current_document, b)
    _open(window, "CompressTool")
    assert _same(compress.file.path(), b)         # held a, switched to the current one


@pytest.mark.parametrize("tool", SINGLE_INPUT)
def test_every_single_input_screen_starts_with_the_current_document(window, tmp_path, tool):
    src = make_pdf(tmp_path / "a.pdf")
    _open(window, "CompressTool").file.set_path(src)
    page = _open(window, tool)
    pump(0.05)
    assert _same(page.document_path(), src), tool


@pytest.mark.parametrize("tool", CLEARED_ON_LEAVE)
def test_leaving_keeps_the_document(window, tmp_path, tool):
    src = make_pdf(tmp_path / "a.pdf")
    page = _open(window, tool, src)
    assert page._doc is not None
    window.show_page("home")
    assert _same(page.document_path(), src), tool        # kept while away
    _open(window, tool)
    assert page._doc is not None and _same(page.document_path(), src), tool


def test_clearing_the_current_document_empties_the_screen(window, tmp_path):
    src = make_pdf(tmp_path / "a.pdf")
    page = _open(window, "RotateTool", src)
    assert window.clear_current_document()
    assert window.current_document is None and page._doc is None
    assert page.file.path() == "" and page.drop_target.isVisibleTo(page)


# ── unsaved edits keep their file, and ask ───────────────────────────────────
def test_an_editor_with_unsaved_edits_keeps_its_file_and_asks(window, dialogs, tmp_path):
    a, b = make_pdf(tmp_path / "a.pdf"), make_pdf(tmp_path / "b.pdf")
    page = _open(window, "MetadataTool", a)
    page.fields["title"].setText("Typed")
    assert page.is_dirty()
    # another file opened here: asked; Cancel keeps the file and the edit
    dialogs.unsaved.append("cancel")
    assert not window.open_document(b)
    assert dialogs.msgs[-1] == ("ask_unsaved", "Save changes to a.pdf?", "")
    assert _same(page.file.path(), a) and page.fields["title"].text() == "Typed"
    assert _same(window.current_document, a)
    # the current document moved elsewhere: shown again, the editor keeps its file
    window.set_current_document(b)
    window._follow(page)
    assert _same(page.file.path(), a) and page.fields["title"].text() == "Typed"
    # Discard: the switch goes ahead
    dialogs.unsaved.append("discard")
    assert window.open_document(b)
    assert _same(page.file.path(), b) and page.fields["title"].text() == ""
    assert not page.is_dirty()


def test_save_in_the_question_saves_then_switches(window, dialogs, tmp_path):
    import pymupdf as fitz
    a, b = make_pdf(tmp_path / "a.pdf"), make_pdf(tmp_path / "b.pdf")
    out = tmp_path / "saved.pdf"
    page = _open(window, "MetadataTool", a)
    page.fields["title"].setText("Kept")
    dialogs.unsaved.append("save")
    dialogs.save(out)
    window.open_document(b)
    wait_job(window)
    with fitz.open(str(out)) as d:
        assert d.metadata["title"] == "Kept"
    assert _same(page.file.path(), b) and _same(window.current_document, b)


# ── collections ──────────────────────────────────────────────────────────────
def test_adding_to_a_collection_leaves_the_current_document_alone(window, tmp_path):
    src = make_pdf(tmp_path / "a.pdf")
    m1, m2 = make_pdf(tmp_path / "m1.pdf"), make_pdf(tmp_path / "m2.pdf")
    _open(window, "CompressTool").file.set_path(src)
    merge = _open(window, "MergeTool")
    merge.add_paths([m1])
    assert window.forward_drop([m2]) == 1
    assert _same(window.current_document, src)
    window.show_page("home")
    _open(window, "MergeTool")
    assert [p for p in merge.paths()] == [m1, m2]          # kept while moving around
