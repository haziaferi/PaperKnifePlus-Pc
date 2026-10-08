"""Merge / Split / Rotate / Split-by-Bookmarks / TOC."""
from pathlib import Path

import pymupdf as fitz
import pytest

from conftest import make_pdf, tool, wait_job


def _texts(path):
    with fitz.open(path) as doc:
        return [p.get_text().strip() for p in doc]


# ── shared page-range parser (L2-12..15) ─────────────────────────────────────
@pytest.mark.parametrize("text, groups", [
    ("1-3, 5", [(0, 2), (4, 4)]),
    ("2-end", [(1, 4)]),
    ("END", [(4, 4)]),
    (" 1 - 2 ,, 4 ", [(0, 1), (3, 3)]),
    ("3-3", [(2, 2)]),
])
def test_parse_ranges_accepts(text, groups):
    from paperknife.pages import parse_ranges
    assert parse_ranges(text, 5) == groups


@pytest.mark.parametrize("text, words", [
    ("99", "does not exist"),
    ("7-9", "does not exist"),
    ("4-6", "does not exist"),
    ("0", "start at 1"),
    ("5-3", "backwards"),
    ("abc", "not a page"),
    ("1-", "not a page"),
    ("-2", "not a page"),
    ("1.5", "not a page"),
    (" , ", "No pages"),
])
def test_parse_ranges_rejects(text, words):
    from paperknife.pages import PageRangeError, parse_ranges
    with pytest.raises(PageRangeError, match=words):
        parse_ranges(text, 5)


# ── Split (L2-12, L2-13, L2-14) ──────────────────────────────────────────────
def _split(app, dialogs, src, ranges, out_dir):
    t = tool(app, "SplitTool")
    t._path.set(src)
    t._ranges.insert(0, ranges)
    dialogs.dirs.append(str(out_dir))
    t._run()
    wait_job(app)


def test_split_rejects_pages_past_the_end(app, dialogs, tmp_path):
    src = make_pdf(tmp_path / "in.pdf", pages=5)
    out = tmp_path / "out"
    out.mkdir()
    _split(app, dialogs, src, "99, 7-9", out)
    assert list(out.iterdir()) == [], [p.name for p in out.iterdir()]
    assert dialogs.errors(), "no error shown for pages that do not exist"


def test_split_writes_the_pages_it_names(app, dialogs, tmp_path):
    src = make_pdf(tmp_path / "in.pdf", pages=5)
    out = tmp_path / "out"
    out.mkdir()
    _split(app, dialogs, src, "2-3, end", out)
    assert not dialogs.errors(), dialogs.errors()
    assert _texts(out / "in_part01_p2-3.pdf") == ["Page 2", "Page 3"]
    assert _texts(out / "in_part02_p5-5.pdf") == ["Page 5"]


# ── Merge (L2-15, L2-18) ─────────────────────────────────────────────────────
def test_merge_reports_a_reversed_range_instead_of_dropping_it(app, dialogs, tmp_path):
    a = make_pdf(tmp_path / "a.pdf", pages=5, text="A{n}")
    b = make_pdf(tmp_path / "b.pdf", pages=2, text="B{n}")
    out = tmp_path / "merged.pdf"
    t = tool(app, "MergeTool")
    t._add_entry(a)
    t._add_entry(b)
    t._entries[0]["range_var"].set("5-3")
    dialogs.save(out)
    t._run()
    wait_job(app)
    assert not out.exists(), f"merged without file a: {_texts(out)}"
    assert any("a.pdf" in m[2] for m in dialogs.errors()), dialogs.msgs


def test_merge_uses_each_files_range(app, dialogs, tmp_path):
    a = make_pdf(tmp_path / "a.pdf", pages=5, text="A{n}")
    b = make_pdf(tmp_path / "b.pdf", pages=2, text="B{n}")
    out = tmp_path / "merged.pdf"
    t = tool(app, "MergeTool")
    t._add_entry(a)
    t._add_entry(b)
    t._entries[0]["range_var"].set("4-end, 1")
    dialogs.save(out)
    t._run()
    wait_job(app)
    assert not dialogs.errors(), dialogs.errors()
    assert _texts(out) == ["A4", "A5", "A1", "B1", "B2"]


def test_merge_name_click_selects_the_file_after_a_remove(app, dialogs, tmp_path):
    import customtkinter as ctk
    paths = [make_pdf(tmp_path / f"{n}.pdf", pages=1) for n in "ABC"]
    t = tool(app, "MergeTool")
    for p in paths:
        t._add_entry(p)
    t._select(0)
    t._remove()
    row_b = t._entries[0]["row"]
    name_btn = next(w for w in row_b.winfo_children() if isinstance(w, ctk.CTkButton))
    name_btn.invoke()
    t._remove()
    assert [Path(e["path"]).name for e in t._entries] == ["C.pdf"]


# ── Split by bookmarks (L2-19) ───────────────────────────────────────────────
def test_bookmark_split_skips_untargeted_entries(app, dialogs, tmp_path):
    src = tmp_path / "book.pdf"
    make_pdf(src, pages=4)
    with fitz.open(src) as doc:
        doc.set_toc([[1, "A", 1], [1, "Loose", -1], [1, "B", 3]])
        doc.saveIncr()
    out = tmp_path / "out"
    out.mkdir()
    t = tool(app, "BookmarksTool")
    dialogs.open(str(src))
    t._open()
    dialogs.dirs.append(str(out))
    t._run()
    wait_job(app)
    assert not dialogs.errors(), dialogs.errors()
    files = {p.name: _texts(p) for p in out.iterdir()}
    assert files == {"01_A.pdf": ["Page 1", "Page 2"],
                     "02_B.pdf": ["Page 3", "Page 4"]}, files


def test_bookmark_split_cuts_in_page_order(app, dialogs, tmp_path):
    src = tmp_path / "book.pdf"
    make_pdf(src, pages=3)
    with fitz.open(src) as doc:
        doc.set_toc([[1, "A", 1], [2, "A2", 3], [2, "A1", 2]])
        doc.saveIncr()
    out = tmp_path / "out"
    out.mkdir()
    t = tool(app, "BookmarksTool")
    dialogs.open(str(src))
    t._open()
    t._level_var.set("All bookmark levels")
    dialogs.dirs.append(str(out))
    t._run()
    wait_job(app)
    pages = sorted(page for p in out.iterdir() for page in _texts(p))
    assert pages == ["Page 1", "Page 2", "Page 3"], {
        p.name: _texts(p) for p in out.iterdir()}


# ── TOC editor (L2-20, L2-21, L2-22) ─────────────────────────────────────────
def _toc(app, dialogs, src):
    t = tool(app, "TocTool")
    dialogs.open(str(src))
    t._open()
    return t


def test_toc_saves_over_the_open_input(app, dialogs, tmp_path):
    src = make_pdf(tmp_path / "in.pdf", pages=3)
    t = _toc(app, dialogs, src)
    t._title_var.set("Chapter")
    t._page_var.set("2")
    t._add()
    dialogs.save(src)
    t._save()
    wait_job(app)
    assert not dialogs.errors(), dialogs.errors()
    t._doc.close()
    t._doc = None
    with fitz.open(src) as doc:
        assert doc.get_toc() == [[1, "Chapter", 2]]


def test_toc_delete_parent_promotes_children(app, dialogs, tmp_path):
    src = tmp_path / "in.pdf"
    make_pdf(src, pages=3)
    with fitz.open(src) as doc:
        doc.set_toc([[1, "A", 1], [2, "A1", 2], [3, "A1a", 2], [1, "B", 3]])
        doc.saveIncr()
    out = tmp_path / "out.pdf"
    t = _toc(app, dialogs, src)
    t._lb.selection_set(0)
    t._delete()
    dialogs.save(out)
    t._save()
    wait_job(app)
    assert not dialogs.errors(), dialogs.errors()
    with fitz.open(out) as doc:
        assert doc.get_toc() == [[1, "A1", 2], [2, "A1a", 2], [1, "B", 3]]


def test_toc_rejects_page_past_the_end(app, dialogs, tmp_path):
    src = make_pdf(tmp_path / "in.pdf", pages=3)
    t = _toc(app, dialogs, src)
    t._page_var.set("99")
    t._add()
    assert t._toc == []
    assert any(m[0] == "showwarning" for m in dialogs.msgs), dialogs.msgs


# ── Rotate (L2-24, L2-25) ────────────────────────────────────────────────────
def test_rotate_keeps_document_when_reopen_fails(app, dialogs, tmp_path):
    src = make_pdf(tmp_path / "in.pdf", pages=2)
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"not a pdf")
    t = tool(app, "RotateTool")
    dialogs.open(src)
    t._open()
    dialogs.open(str(bad))
    t._open()
    assert len(t._doc) == 2


def test_rotate_thumbnail_keeps_aspect(app, dialogs, tmp_path):
    src = make_pdf(tmp_path / "in.pdf", pages=1, width=842, height=595)
    t = tool(app, "RotateTool")
    dialogs.open(src)
    t._open()
    w, h = t._thumb(0, 0).cget("size")
    assert w > h
    w, h = t._thumb(0, 90).cget("size")
    assert h > w


@pytest.mark.parametrize("name", ["TocTool", "RotateTool", "BookmarksTool", "MetadataTool",
                                  "EditTextTool", "FindReplaceTool", "AnnotateTool",
                                  "RedactTool"])
def test_navigating_away_closes_the_open_documents(app, dialogs, tmp_path, name):
    src = make_pdf(tmp_path / "in.pdf", pages=2)
    t = tool(app, name)
    dialogs.open(src)
    t._open()
    held = t._doc
    tool(app, "CropTool")
    assert held.is_closed
