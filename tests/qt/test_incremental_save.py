"""Saving over the open file (owner's choice 2026-10-12): edits that only add
are appended to it, so its bytes before stay as they are (a signature over
them still holds); edits that remove or replace text write it whole, so the
old text is not left readable inside the file."""
import pymupdf as fitz

from qt_harness import make_pdf, pump, wait_job


def _bytes(path):
    with open(path, "rb") as f:
        return f.read()


def _holds_text(path, text: str) -> bool:
    """Whether *text* is anywhere in the file, referenced or not: its raw
    bytes or any stream, as text or as the hex PyMuPDF writes page text in."""
    b = text.encode()
    forms = [b, b.hex().encode(), b.hex().upper().encode(),
             ("﻿" + text).encode("utf-16-be").hex().encode()]
    blobs = [_bytes(path)]
    with fitz.open(path) as d:
        for x in range(1, d.xref_length()):
            try:
                if d.xref_is_stream(x):
                    blobs.append(d.xref_stream(x) or b"")
            except Exception:
                continue
    return any(f in blob for blob in blobs for f in forms)


def test_the_text_check_finds_page_text(tmp_path):
    # The control: written as hex in the content stream, it is still found.
    src = make_pdf(tmp_path / "c.pdf", pages=1, text="the confidential plan")
    assert _holds_text(src, "confidential") and not _holds_text(src, "absent")


def _save_over(window, dialogs, page, src):
    dialogs.save(src)
    page.save()
    wait_job(window)
    assert not dialogs.errors(), dialogs.errors()
    assert not page.is_dirty()


def _with_note(path, note="a secret note"):
    make_pdf(path, pages=2)
    with fitz.open(path) as d:
        d[0].add_text_annot((100, 100), note)
        d.saveIncr()
    return str(path)


def test_annotate_added_notes_are_appended(window, dialogs, tmp_path):
    src = make_pdf(tmp_path / "a.pdf", pages=2)
    before = _bytes(src)
    assert window.open_tool("AnnotateTool", src)
    page = window.current_page()
    page._doc[0].add_text_annot((72, 72), "new note")
    page._dirty = True
    _save_over(window, dialogs, page, src)
    assert _bytes(src).startswith(before) and len(_bytes(src)) > len(before)
    # The page goes on with the file: a second save appends again.
    second = _bytes(src)
    page._doc[1].add_text_annot((72, 72), "and another")
    page._dirty = True
    _save_over(window, dialogs, page, src)
    assert _bytes(src).startswith(second)
    with fitz.open(src) as d:
        assert sum(1 for p in d for _ in p.annots()) == 2


def test_annotate_a_removed_note_is_written_whole_and_gone(window, dialogs, tmp_path):
    src = _with_note(tmp_path / "a.pdf")
    before = _bytes(src)
    assert window.open_tool("AnnotateTool", src)
    page = window.current_page()
    page.sel_xref = next(page._doc[0].annots()).xref
    page.delete()
    _save_over(window, dialogs, page, src)
    assert not _bytes(src).startswith(before)
    assert not _holds_text(src, "a secret note")


def test_annotate_saved_elsewhere_is_a_whole_file(window, dialogs, tmp_path):
    src = make_pdf(tmp_path / "a.pdf", pages=1)
    before = _bytes(src)
    assert window.open_tool("AnnotateTool", src)
    page = window.current_page()
    page._doc[0].add_text_annot((72, 72), "n")
    page._dirty = True
    out = tmp_path / "out.pdf"
    _save_over(window, dialogs, page, str(out))
    assert _bytes(src) == before and not _bytes(out).startswith(before)


def test_find_replace_is_written_whole_and_the_old_word_is_gone(window, dialogs, tmp_path):
    src = make_pdf(tmp_path / "f.pdf", pages=1, text="the confidential plan")
    assert window.open_tool("FindReplaceTool", src)
    page = window.current_page()
    page.find_edit.setText("confidential")
    page.repl_edit.setText("public")
    dialogs.asks.append(True)
    page.replace_all()
    wait_job(window)
    before = _bytes(src)
    _save_over(window, dialogs, page, src)
    assert not _bytes(src).startswith(before)
    with fitz.open(src) as d:
        assert "public" in d[0].get_text()
    assert not _holds_text(src, "confidential")


def test_rotate_turns_and_moves_are_appended(window, dialogs, tmp_path):
    src = make_pdf(tmp_path / "r.pdf", pages=3)
    before = _bytes(src)
    assert window.open_tool("RotateTool", src)
    pump(0.05)
    page = window.current_page()
    page.select(2)
    page.rotate(90)
    page.select(2)
    page.move_pages(-1)
    _save_over(window, dialogs, page, src)
    assert _bytes(src).startswith(before)
    with fitz.open(src) as d:
        assert [p.get_text().strip() for p in d] == ["Page 1", "Page 3", "Page 2"]
        assert [p.rotation for p in d] == [0, 90, 0]
    # The page now shows the file as it is: in order, unturned, nothing unsaved.
    assert page.order() == [0, 1, 2] and page._extra == {0: 0, 1: 0, 2: 0}
    page.select(0)
    page.rotate(180)
    _save_over(window, dialogs, page, src)
    with fitz.open(src) as d:
        assert [p.rotation for p in d] == [180, 90, 0]
        assert [p.get_text().strip() for p in d] == ["Page 1", "Page 3", "Page 2"]


def test_toc_added_bookmarks_append_a_renamed_one_rewrites(window, dialogs, tmp_path):
    src = make_pdf(tmp_path / "t.pdf", pages=3)
    with fitz.open(src) as d:
        d.set_toc([[1, "Secret chapter", 1]])
        d.saveIncr()
    before = _bytes(src)
    assert window.open_tool("TocTool", src)
    page = window.current_page()
    page.title_edit.setText("Added")
    page.page_edit.setText("2")
    page._add()
    _save_over(window, dialogs, page, src)
    assert _bytes(src).startswith(before)
    page.select(0)
    page.title_edit.setText("Plain chapter")
    page._update_sel()
    assert page.is_dirty()
    before = _bytes(src)
    _save_over(window, dialogs, page, src)
    assert not _bytes(src).startswith(before)
    with fitz.open(src) as d:
        assert [e[1] for e in d.get_toc()] == ["Plain chapter", "Added"]
    assert not _holds_text(src, "Secret chapter")


def test_metadata_filling_empty_fields_appends_replacing_rewrites(window, dialogs, tmp_path):
    src = make_pdf(tmp_path / "m.pdf", pages=1)
    with fitz.open(src) as d:
        d.set_metadata({"author": "Old Author"})
        d.saveIncr()
    assert window.open_tool("MetadataTool", src)
    page = window.current_page()
    before = _bytes(src)
    page.fields["title"].setText("A title")            # was empty
    _save_over(window, dialogs, page, src)
    assert _bytes(src).startswith(before)
    page.fields["author"].setText("")                  # cleared
    before = _bytes(src)
    _save_over(window, dialogs, page, src)
    assert not _bytes(src).startswith(before)
    assert not _holds_text(src, "Old Author")
