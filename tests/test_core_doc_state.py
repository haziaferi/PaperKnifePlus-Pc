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
