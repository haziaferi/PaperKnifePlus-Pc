"""SharedDocument: one open document, edits on one history, Save over its file, Save as."""
import pymupdf as fitz
import pytest

from conftest import make_pdf
from paperknife.core.document import SharedDocument
from paperknife.core.doc_state import UNDO_DEPTH
from paperknife.core.password import keep_open_password, open_password_of


def _texts(path):
    with fitz.open(path) as d:
        return [p.get_text().strip() for p in d]


def _opened(path):
    sd = SharedDocument()
    events = []
    sd.listen(events.append)
    sd.open(path, fitz.open(path))
    return sd, events


def _stamp(text):
    def fn(doc):
        doc[0].insert_text((72, 300), text, fontsize=12)
    return fn


def test_open_holds_the_file_clean(tmp_path):
    src = make_pdf(tmp_path / "in.pdf", pages=2)
    sd, events = _opened(src)
    assert sd.is_open() and sd.path == src and sd.name == "in.pdf"
    assert not sd.dirty and not sd.can_undo() and events == ["opened"]


def test_edits_pile_up_unsaved_on_one_history(tmp_path):
    src = make_pdf(tmp_path / "in.pdf", pages=2)
    sd, events = _opened(src)
    sd.edit("Watermark", _stamp("one"))
    sd.edit("Header", _stamp("two"))
    assert sd.dirty and sd.undo_label() == "Header" and events[-2:] == ["changed", "changed"]
    assert "two" in sd.doc[0].get_text() and _texts(src)[0] == "Page 1"   # the file is untouched


def test_undo_and_redo_walk_the_history(tmp_path):
    src = make_pdf(tmp_path / "in.pdf", pages=1)
    sd, _ = _opened(src)
    sd.edit("A", _stamp("one"), extra={"tool": "a"})
    sd.edit("B", _stamp("two"))
    step = sd.undo()
    assert step.label == "B" and "two" not in sd.doc[0].get_text() and "one" in sd.doc[0].get_text()
    assert sd.undo().extra == {"tool": "a"} and "one" not in sd.doc[0].get_text()
    assert sd.undo() is None
    assert sd.redo().label == "A" and "one" in sd.doc[0].get_text()
    sd.edit("C", _stamp("three"))
    assert not sd.can_redo()                       # a new edit drops what was undone


def test_history_keeps_the_last_ten(tmp_path):
    src = make_pdf(tmp_path / "in.pdf", pages=1)
    sd, _ = _opened(src)
    for i in range(UNDO_DEPTH + 3):
        sd.edit(f"e{i}", _stamp(str(i)))
    n = 0
    while sd.undo() is not None:
        n += 1
    assert n == UNDO_DEPTH


def test_a_failed_edit_leaves_the_document_as_it_was(tmp_path):
    src = make_pdf(tmp_path / "in.pdf", pages=1)
    sd, _ = _opened(src)

    def bad(doc):
        doc[0].insert_text((72, 300), "half", fontsize=12)
        raise ValueError("no")

    with pytest.raises(ValueError):
        sd.edit("Bad", bad)
    assert "half" not in sd.doc[0].get_text() and not sd.dirty and not sd.can_undo()


def test_replace_takes_a_tools_output_as_one_edit(tmp_path):
    src = make_pdf(tmp_path / "in.pdf", pages=3)
    other = make_pdf(tmp_path / "out.pdf", pages=1, text="Out")
    sd, _ = _opened(src)
    sd.replace(fitz.open("pdf", open(other, "rb").read()), "Compress")
    assert len(sd.doc) == 1 and sd.dirty
    sd.undo()
    assert len(sd.doc) == 3


def test_save_writes_over_the_file_and_clears_dirty(tmp_path):
    src = make_pdf(tmp_path / "in.pdf", pages=2)
    sd, events = _opened(src)
    sd.edit("A", _stamp("saved text"))
    assert sd.save(garbage=1, deflate=True) == "full"
    assert not sd.dirty and events[-1] == "saved" and "saved text" in _texts(src)[0]
    sd.edit("B", _stamp("again"))          # the document goes on after a save over itself
    sd.save()
    assert "again" in _texts(src)[0]


def test_save_appends_edits_that_only_add(tmp_path):
    src = make_pdf(tmp_path / "in.pdf", pages=1)
    before = open(src, "rb").read()
    sd, _ = _opened(src)
    sd.begin("Note")
    sd.doc[0].add_text_annot((72, 72), "a note")
    sd.changed(adds=True)
    assert sd.save() == "incremental"
    assert open(src, "rb").read().startswith(before)


def test_one_edit_that_does_not_only_add_writes_the_file_whole(tmp_path):
    src = make_pdf(tmp_path / "in.pdf", pages=1)
    sd, _ = _opened(src)
    sd.edit("Note", lambda d: d[0].add_text_annot((72, 72), "a note"), adds=True)
    sd.edit("Stamp", _stamp("x"))
    assert sd.save() == "full"
    sd.edit("Note", lambda d: d[0].add_text_annot((72, 90), "b"), adds=True)
    assert sd.adds_only                     # a save starts over


def test_abandon_takes_back_a_half_done_edit_quietly(tmp_path):
    src = make_pdf(tmp_path / "in.pdf", pages=1)
    sd, events = _opened(src)
    sd.begin("Half")
    sd.doc[0].insert_text((72, 300), "half", fontsize=12)
    sd.abandon()
    assert "half" not in sd.doc[0].get_text() and not sd.dirty and not sd.can_undo()
    assert events == ["opened"]


def test_forget_edits_is_clean_with_no_history(tmp_path):
    src = make_pdf(tmp_path / "in.pdf", pages=1)
    sd, _ = _opened(src)
    sd.edit("A", _stamp("x"))
    sd.forget_edits()
    assert not sd.dirty and not sd.can_undo()


def test_save_as_moves_the_document_to_the_new_file(tmp_path):
    src = make_pdf(tmp_path / "in.pdf", pages=1)
    out = str(tmp_path / "copy.pdf")
    sd, _ = _opened(src)
    sd.edit("A", _stamp("new"))
    sd.save_as(out)
    assert sd.path == out and sd.name == "copy.pdf" and not sd.dirty
    assert "new" in _texts(out)[0] and _texts(src)[0] == "Page 1"
    sd.edit("B", _stamp("later"))
    sd.save()                               # Save now writes the new file
    assert "later" in _texts(out)[0] and _texts(src)[0] == "Page 1"


def test_the_open_password_stays_through_edits_and_undo(tmp_path):
    src = make_pdf(tmp_path / "in.pdf", pages=1)
    sd, _ = _opened(src)
    keep_open_password(sd.doc, "in.pdf", "pw")
    sd.edit("A", _stamp("x"))
    sd.undo()
    assert open_password_of(sd.doc) is not None and open_password_of(sd.doc).user_pw == "pw"


def test_close_lets_the_document_go(tmp_path):
    src = make_pdf(tmp_path / "in.pdf", pages=1)
    sd, events = _opened(src)
    sd.edit("A", _stamp("x"))
    sd.close()
    assert not sd.is_open() and sd.path == "" and not sd.dirty and not sd.can_undo()
    assert events[-1] == "closed"


def test_marks_and_steps_share_one_counter(tmp_path):
    src = make_pdf(tmp_path / "in.pdf", pages=1)
    sd, _ = _opened(src)
    mark = sd.tick()
    sd.edit("A", _stamp("x"))
    assert sd.last_step_seq() > mark
    later = sd.tick()
    assert later > sd.last_step_seq()
    sd.undo()
    assert sd.last_step_seq() == 0


def test_undo_back_to_the_save_point_is_clean_and_redo_is_not(tmp_path):
    src = make_pdf(tmp_path / "in.pdf", pages=1)
    sd, _ = _opened(src)
    sd.edit("A", _stamp("x"))
    sd.undo()
    assert not sd.dirty                     # as opened
    sd.redo()
    assert sd.dirty
    sd.save()
    sd.edit("B", _stamp("y"))
    sd.undo()
    assert not sd.dirty                     # as saved
    sd.undo()
    assert sd.dirty                         # before the save point


def test_a_change_with_no_step_stays_unsaved_through_undo(tmp_path):
    src = make_pdf(tmp_path / "in.pdf", pages=1)
    sd, _ = _opened(src)
    sd.changed()                            # e.g. recovered edits: nothing to undo them by
    sd.edit("A", _stamp("x"))
    sd.undo()
    assert sd.dirty


def test_an_owner_password_file_stays_encrypted_through_edits_undo_and_save(tmp_path):
    src = str(tmp_path / "o.pdf")
    d = fitz.open()
    d.new_page()
    d.save(src, encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw="o",
           permissions=int(fitz.PDF_PERM_PRINT))
    d.close()
    sd, _ = _opened(src)
    sd.edit("A", _stamp("one"))
    sd.edit("B", _stamp("two"))
    sd.undo()
    sd.save(encryption=fitz.PDF_ENCRYPT_KEEP)
    with fitz.open(src) as d:
        assert d.metadata.get("encryption") and "one" in d[0].get_text()
