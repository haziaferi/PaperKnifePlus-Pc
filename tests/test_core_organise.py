"""paperknife.core.organise without any user interface."""
import threading
from pathlib import Path

import pymupdf as fitz

from conftest import make_pdf
from paperknife.core import organise


def _texts(path):
    with fitz.open(path) as d:
        return [p.get_text().strip() for p in d]


def test_split_ranges_writes_one_file_per_group(tmp_path):
    src = make_pdf(tmp_path / "in.pdf", pages=5)
    seen = []
    with fitz.open(src) as doc:
        n = organise.split_ranges(doc, [(0, 1), (2, 4)], str(tmp_path), "in",
                                  threading.Event(), seen.append)
    assert n == 2 and seen[-1] == 1.0
    assert _texts(tmp_path / "in_part01_p1-2.pdf") == ["Page 1", "Page 2"]
    assert _texts(tmp_path / "in_part02_p3-5.pdf") == ["Page 3", "Page 4", "Page 5"]


def test_split_ranges_cancelled_writes_nothing(tmp_path):
    src = make_pdf(tmp_path / "in.pdf", pages=3)
    stop = threading.Event()
    stop.set()
    with fitz.open(src) as doc:
        assert organise.split_ranges(doc, [(0, 0)], str(tmp_path), "in", stop,
                                     lambda v: None) is None
    assert not list(tmp_path.glob("in_part*"))


def test_merge_joins_groups_and_closes_inputs(tmp_path):
    a = make_pdf(tmp_path / "a.pdf", pages=3, text="A{n}")
    b = make_pdf(tmp_path / "b.pdf", pages=2, text="B{n}")
    da, db = fitz.open(a), fitz.open(b)
    out = tmp_path / "out.pdf"
    pages = organise.merge([(da, [(0, 0), (2, 2)]), (db, [(0, 1)])], str(out),
                           threading.Event(), lambda v: None)
    assert pages == 4
    assert _texts(out) == ["A1", "A3", "B1", "B2"]
    assert da.is_closed and db.is_closed


def test_merge_over_one_of_its_inputs(tmp_path):
    a = make_pdf(tmp_path / "a.pdf", pages=1, text="A{n}")
    b = make_pdf(tmp_path / "b.pdf", pages=1, text="B{n}")
    organise.merge([(fitz.open(a), [(0, 0)]), (fitz.open(b), [(0, 0)])], a,
                   threading.Event(), lambda v: None)
    assert _texts(a) == ["A1", "B1"]


def test_reorder_moves_and_rotates(tmp_path):
    src = make_pdf(tmp_path / "in.pdf", pages=3)
    out = tmp_path / "out.pdf"
    with fitz.open(src) as doc:
        organise.reorder(doc, [2, 0, 1], {0: 90, 1: 0, 2: 0}, str(out))
    with fitz.open(out) as d:
        assert [p.get_text().strip() for p in d] == ["Page 3", "Page 1", "Page 2"]
        assert [p.rotation for p in d] == [0, 90, 0]


def test_bookmark_chapters_sorts_by_page_and_skips_targetless():
    toc = [[1, "Two", 5], [1, "One", 1], [2, "Sub", 2], [1, "Nowhere", -1]]
    entries, skipped = organise.bookmark_chapters(toc, 10, all_levels=False)
    assert entries == [("One", 0), ("Two", 4), ("_END_", 10)] and skipped == 1
    entries, _ = organise.bookmark_chapters(toc, 10, all_levels=True)
    assert [t for t, _ in entries] == ["One", "Sub", "Two", "_END_"]
    assert organise.bookmark_chapters([[1, "x", -1]], 3, True) == ([], 1)


def test_split_chapters_names_files_and_releases_before_writing(tmp_path):
    src = make_pdf(tmp_path / "in.pdf", pages=4)
    released = []
    entries = [("Intro: a/b", 0), ("Body", 2), ("_END_", 4)]
    with fitz.open(src) as doc:
        n = organise.split_chapters(doc, entries, str(tmp_path), threading.Event(),
                                    lambda v: None, release=released.append)
    assert n == 2
    names = sorted(p.name for p in tmp_path.glob("0*_*.pdf"))
    assert names == ["01_Intro_ a_b.pdf", "02_Body.pdf"]
    assert [Path(p).name for p in released] == names
    assert _texts(tmp_path / "02_Body.pdf") == ["Page 3", "Page 4"]


def test_toc_level_error_and_delete_entry():
    assert organise.toc_level_error([[1, "a", 1], [2, "b", 1], [3, "c", 1]]) is None
    msg = organise.toc_level_error([[1, "a", 1], [3, "c", 1]])
    assert "Bookmark 2 ('c') is level 3 but follows level 1" in msg
    toc = [[1, "a", 1], [2, "b", 1], [3, "c", 1], [2, "d", 1], [1, "e", 1]]
    organise.delete_entry(toc, 1)
    assert toc == [[1, "a", 1], [2, "c", 1], [2, "d", 1], [1, "e", 1]]
