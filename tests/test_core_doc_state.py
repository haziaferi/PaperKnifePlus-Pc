"""DocHolder: saving the open document over itself, more than once."""
import threading

import pymupdf as fitz

from conftest import make_pdf
from paperknife.core import organise
from paperknife.core.doc_state import DocHolder


def _texts(path):
    with fitz.open(path) as d:
        return [p.get_text().strip() for p in d]


def test_saves_over_the_source_twice(tmp_path):
    # After the first save the holder goes on with an in-memory copy, whose
    # doc.name is not a path; the second save must not ask the OS about it.
    src = make_pdf(tmp_path / "in.pdf", pages=2, text="A{n}")
    h = DocHolder()
    h._doc = fitz.open(src)
    h._save_doc(src, deflate=True)
    h._doc[0].insert_text((72, 200), "second", fontsize=12)
    h._save_doc(src, deflate=True)
    assert _texts(src)[0].startswith("A1") and "second" in _texts(src)[0]


def test_release_then_save_onto_an_existing_file(tmp_path):
    src = make_pdf(tmp_path / "in.pdf", pages=1)
    other = make_pdf(tmp_path / "other.pdf", pages=3)
    h = DocHolder()
    h._doc = fitz.open(src)
    h._release(src)                       # now an in-memory copy
    assert not h._holds(other)
    h._save_doc(other)
    assert len(_texts(other)) == 1


def test_split_twice_into_the_same_folder_from_a_copy(tmp_path):
    src = make_pdf(tmp_path / "in.pdf", pages=4)
    with fitz.open(src) as d:
        doc = fitz.open("pdf", d.tobytes())   # as a tool holds it after a save
    entries = [("One", 0), ("Two", 2), ("_END_", 4)]
    for _ in range(2):
        assert organise.split_chapters(doc, entries, str(tmp_path), threading.Event(),
                                       lambda v: None) == 2
    assert _texts(tmp_path / "02_Two.pdf") == ["Page 3", "Page 4"]


# ── incremental saves (owner's choice 2026-10-12: append edits that only add) ──
def _annotated(src):
    h = DocHolder()
    h._doc = fitz.open(src)
    h._doc[0].add_text_annot((72, 72), "a note")
    return h


def test_incremental_save_appends_and_keeps_the_bytes_before(tmp_path):
    src = make_pdf(tmp_path / "in.pdf", pages=2)
    before = open(src, "rb").read()
    h = _annotated(src)
    assert h._save_doc(src, incremental=True, deflate=True) == "incremental"
    after = open(src, "rb").read()
    assert after.startswith(before) and len(after) > len(before)   # signatures still hold
    assert not list(tmp_path.glob(".*.bak"))                        # the copy is gone
    with fitz.open(src) as d:
        assert [a.info["content"] for a in d[0].annots()] == ["a note"]
    # The holder stays on the file: the next save appends again.
    h._doc[1].add_text_annot((72, 72), "another")
    assert h._save_doc(src, incremental=True) == "incremental"
    assert open(src, "rb").read().startswith(after)


def test_incremental_falls_back_to_a_whole_file(tmp_path):
    src = make_pdf(tmp_path / "in.pdf", pages=1)
    other = tmp_path / "other.pdf"
    h = _annotated(src)
    assert h._save_doc(str(other), incremental=True) == "full"     # another file
    h._close_doc()
    enc = tmp_path / "enc.pdf"
    with fitz.open(src) as d:
        d.save(enc, encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw="o", user_pw="u")
    h2 = DocHolder()
    h2._doc = fitz.open(enc)
    h2._doc.authenticate("u")
    h2._doc[0].add_text_annot((72, 72), "x")
    assert h2._save_doc(str(enc), incremental=True,
                        encryption=fitz.PDF_ENCRYPT_KEEP) == "full"    # encrypted
    h3 = _annotated(src)
    assert h3._save_doc(src, deflate=True) == "full"               # not asked for


def test_a_failed_append_puts_the_file_back(tmp_path, monkeypatch):
    src = make_pdf(tmp_path / "in.pdf", pages=1)
    before = open(src, "rb").read()
    h = _annotated(src)

    def broken(self=None):
        with open(src, "ab") as f:
            f.write(b"half an update")
        raise RuntimeError("disk full")
    monkeypatch.setattr(h._doc, "saveIncr", broken)
    try:
        h._save_doc(src, incremental=True)
    except RuntimeError as e:
        assert "disk full" in str(e)
    else:
        raise AssertionError("the failure was swallowed")
    assert open(src, "rb").read() == before
    assert not list(tmp_path.glob(".*.bak"))


def test_an_encrypted_file_is_never_appended_to_even_after_a_snapshot(tmp_path):
    # tobytes() (an undo snapshot) clears the trailer's /Encrypt that
    # can_append read: an append then wrote the edits unencrypted (2026-10-23).
    from paperknife.core.doc_state import can_append
    src = str(tmp_path / "e.pdf")
    d = fitz.open()
    d.new_page()
    d.save(src, encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="u", owner_pw="o")
    d.close()
    with fitz.open(src) as doc:
        assert doc.authenticate("u")
        assert not can_append(doc)
        doc.tobytes()
        assert not can_append(doc)
