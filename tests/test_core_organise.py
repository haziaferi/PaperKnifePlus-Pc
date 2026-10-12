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


def _rich_pdf(path, pages=4):
    """Pages "Page N" with what belongs to the document: a bookmark per page
    (one by a named destination), a web-address bookmark, roman-then-arabic
    page labels, a text field per page, properties and XMP."""
    make_pdf(path, pages=pages)
    doc = fitz.open(path)
    for i, p in enumerate(doc):
        w = fitz.Widget()
        w.field_type, w.field_name = fitz.PDF_WIDGET_TYPE_TEXT, f"f{i + 1}"
        w.rect = fitz.Rect(72, 200, 272, 230)
        p.add_widget(w)
    doc.set_toc([[1, f"Chapter {i + 1}", i + 1] for i in range(pages)]
                + [[1, "Web", -1, {"kind": fitz.LINK_URI, "uri": "https://example.org"}]])
    doc.set_page_labels([{"startpage": 0, "prefix": "", "style": "r", "firstpagenum": 1},
                         {"startpage": 2, "prefix": "", "style": "D", "firstpagenum": 1}])
    doc.set_metadata({"title": "Rich", "author": "Tester"})
    doc.set_xml_metadata("<x:xmpmeta xmlns:x='adobe:ns:meta/'/>")
    doc.saveIncr()
    doc.close()
    return str(path)


def _parts(path):
    with fitz.open(path) as d:
        return {
            "text": [p.get_text().strip() for p in d],
            "labels": [p.get_label() for p in d],
            "toc": [(e[1], e[2]) for e in d.get_toc()],
            "fields": sorted(w.field_name for p in d for w in p.widgets()),
            "form": bool(d.is_form_pdf),
            "title": d.metadata["title"],
            "xmp": bool(d.get_xml_metadata()),
        }


def test_reorder_keeps_what_belongs_to_the_document(tmp_path):
    # insert_pdf into a new file, as before, lost all of this but the text.
    src = _rich_pdf(tmp_path / "in.pdf")
    out = tmp_path / "out.pdf"
    with fitz.open(src) as doc:
        organise.reorder(doc, [3, 0, 1, 2], {0: 0, 1: 0, 2: 0, 3: 0}, str(out))
    got = _parts(out)
    assert got["text"] == ["Page 4", "Page 1", "Page 2", "Page 3"]
    assert got["labels"] == ["2", "i", "ii", "1"]          # each page keeps its label
    assert got["toc"] == [("Chapter 1", 2), ("Chapter 2", 3), ("Chapter 3", 4),
                          ("Chapter 4", 1), ("Web", -1)]
    assert got["fields"] == ["f1", "f2", "f3", "f4"] and got["form"]
    assert got["title"] == "Rich" and got["xmp"]


def test_split_part_keeps_only_its_own_bookmarks_and_fields(tmp_path):
    src = _rich_pdf(tmp_path / "in.pdf")
    with fitz.open(src) as doc:
        organise.split_ranges(doc, [(1, 2)], str(tmp_path), "in", threading.Event(),
                              lambda v: None)
    got = _parts(tmp_path / "in_part01_p2-3.pdf")
    assert got["text"] == ["Page 2", "Page 3"]
    assert got["labels"] == ["ii", "1"]
    assert got["toc"] == [("Chapter 2", 1), ("Chapter 3", 2), ("Web", -1)]
    assert got["fields"] == ["f2", "f3"] and got["form"]
    with fitz.open(tmp_path / "in_part01_p2-3.pdf") as d:      # no orphan fields
        assert d.xref_get_key(d.pdf_catalog(), "AcroForm/Fields")[1].count(" 0 R") == 2
    assert got["title"] == "Rich" and got["xmp"]


def test_split_into_many_parts_each_keeps_its_own(tmp_path):
    # More parts than CUT_LEAF: the halves are cut first, the parts from them.
    n = 3 * organise.CUT_LEAF + 1
    src = _rich_pdf(tmp_path / "in.pdf", pages=n)
    seen = []
    with fitz.open(src) as doc:
        labels = [p.get_label() for p in doc]
        assert organise.split_ranges(doc, [(i, i) for i in range(n)], str(tmp_path), "in",
                                     threading.Event(), seen.append) == n
    assert seen[-1] == 1.0 and len(seen) == n
    for i in range(n):
        got = _parts(tmp_path / f"in_part{i + 1:02d}_p{i + 1}-{i + 1}.pdf")
        assert got["text"] == [f"Page {i + 1}"] and got["labels"] == [labels[i]]
        assert got["toc"] == [(f"Chapter {i + 1}", 1), ("Web", -1)]
        assert got["fields"] == [f"f{i + 1}"] and got["title"] == "Rich"


def test_split_cancelled_between_parts_stops(tmp_path):
    n = 3 * organise.CUT_LEAF
    src = make_pdf(tmp_path / "in.pdf", pages=n)
    stop = threading.Event()
    with fitz.open(src) as doc:
        assert organise.split_ranges(doc, [(i, i) for i in range(n)], str(tmp_path), "in",
                                     stop, lambda v: v >= 0.25 and stop.set()) is None
    assert 0 < len(list(tmp_path.glob("in_part*"))) < n


def test_split_part_drops_the_cut_pages_from_the_file(tmp_path):
    # The part is cut from a copy of the whole file: without garbage
    # collection the 39 pages left out would still be in it.  Each page
    # carries 4 KB of random text, which deflate cannot shrink away.
    import random
    rnd = random.Random(1)
    doc = fitz.open()
    for _ in range(40):
        p = doc.new_page()
        p.insert_textbox(p.rect, "".join(rnd.choice("abcdefghij ") for _ in range(4000)), fontsize=4)
    doc.save(tmp_path / "in.pdf", deflate=True)
    whole = (tmp_path / "in.pdf").stat().st_size
    organise.split_ranges(doc, [(0, 0)], str(tmp_path), "in", threading.Event(), lambda v: None)
    doc.close()
    assert (tmp_path / "in_part01_p1-1.pdf").stat().st_size * 10 < whole


def test_copy_pages_named_destination_bookmark_keeps_its_page(tmp_path):
    # set_toc loses a named destination's page; a part's kept bookmarks
    # (here through /Dests names, as LaTeX writes them) must still go to theirs.
    src = make_pdf(tmp_path / "in.pdf", pages=3)
    doc = fitz.open(src)
    names = [f"{p.xref} 0 R" for p in doc]
    dests = doc.get_new_xref()
    doc.update_object(dests, "<<" + "".join(f"/d{i} [{n} /XYZ 0 700 0]" for i, n in enumerate(names)) + ">>")
    doc.xref_set_key(doc.pdf_catalog(), "Dests", f"{dests} 0 R")
    outl = doc.get_new_xref()
    items = [doc.get_new_xref() for _ in names]
    for i, x in enumerate(items):
        nxt = f"/Next {items[i + 1]} 0 R" if i + 1 < len(items) else ""
        prv = f"/Prev {items[i - 1]} 0 R" if i else ""
        doc.update_object(x, f"<</Title (C{i + 1})/Parent {outl} 0 R/Dest /d{i}{nxt}{prv}>>")
    doc.update_object(outl, f"<</Type/Outlines/First {items[0]} 0 R/Last {items[-1]} 0 R/Count 3>>")
    doc.xref_set_key(doc.pdf_catalog(), "Outlines", f"{outl} 0 R")
    data = doc.tobytes()
    doc.close()
    with fitz.open("pdf", data) as d:
        assert [(e[1], e[2]) for e in d.get_toc()] == [("C1", 1), ("C2", 2), ("C3", 3)]
    with organise.copy_pages(data, [1, 2]) as part:
        assert [(e[1], e[2]) for e in part.get_toc()] == [("C2", 1), ("C3", 2)]


def test_copy_pages_keeps_links_through_the_catalog_dests(tmp_path):
    # select() drops /Dests and the links that use it.
    doc = fitz.open()
    for _ in range(3):
        doc.new_page()
    dests = doc.get_new_xref()
    doc.update_object(dests, f"<</three [{doc[2].xref} 0 R /XYZ 0 700 0]>>")
    doc.xref_set_key(doc.pdf_catalog(), "Dests", f"{dests} 0 R")
    annot = doc.get_new_xref()
    doc.update_object(annot, "<</Type/Annot/Subtype/Link/Rect[72 72 200 100]/Dest/three>>")
    doc.xref_set_key(doc[0].xref, "Annots", f"[{annot} 0 R]")
    data = doc.tobytes()
    with organise.copy_pages(data, [2, 0]) as part:
        assert [(lk["kind"], lk["page"]) for lk in part[1].get_links()] == [(fitz.LINK_GOTO, 0)]


def _with_layer_and_attachment(path, name):
    """A layer that is off, its text on page 1, and an attachment."""
    doc = fitz.open(path)
    x = doc.add_ocg(f"Layer {name}", on=False)
    doc[0].insert_text((72, 300), f"hidden {name}", oc=x)
    doc.embfile_add("notes.txt", f"notes {name}".encode())
    doc.saveIncr()
    doc.close()


def test_merge_bookmark_per_file_first_properties_plain_numbers(tmp_path):
    # Owner's choices 2026-10-12; insert_pdf alone lost the bookmarks.
    a = _rich_pdf(tmp_path / "a.pdf", pages=3)
    b = make_pdf(tmp_path / "b.pdf", pages=2, text="B{n}")
    with fitz.open(b) as d:
        d.set_toc([[1, "B intro", 2]])
        d.set_metadata({"title": "Other"})
        d.saveIncr()
    out = tmp_path / "out.pdf"
    organise.merge([(fitz.open(a), [(0, 0), (2, 2)]), (fitz.open(b), [(0, 1)])], str(out),
                   threading.Event(), lambda v: None)
    with fitz.open(out) as d:
        assert [(e[0], e[1], e[2]) for e in d.get_toc()] == [
            (1, "a.pdf", 1), (2, "Chapter 1", 1), (2, "Chapter 3", 2), (2, "Web", -1),
            (1, "b.pdf", 3), (2, "B intro", 4)]
        assert d.metadata["title"] == "Rich" and d.metadata["author"] == "Tester"
        assert d.get_xml_metadata()
        assert d.get_page_labels() == [] and [p.get_label() for p in d] == ["", "", "", ""]
        assert sorted(w.field_name for p in d for w in p.widgets()) == ["f1", "f3"]


def test_merge_keeps_layers_attachments_and_named_links(tmp_path):
    a = make_pdf(tmp_path / "a.pdf", pages=2, text="A{n}")
    b = make_pdf(tmp_path / "b.pdf", pages=1, text="B{n}")
    _with_layer_and_attachment(a, "A")
    _with_layer_and_attachment(b, "B")
    # a.pdf page 1 links to its page 2 through a named destination.
    doc = fitz.open(a)
    dests = doc.get_new_xref()
    doc.update_object(dests, f"<</two [{doc[1].xref} 0 R /XYZ 0 700 0]>>")
    doc.xref_set_key(doc.pdf_catalog(), "Dests", f"{dests} 0 R")
    annot = doc.get_new_xref()
    doc.update_object(annot, "<</Type/Annot/Subtype/Link/Rect[72 72 200 100]/Dest/two/Border[0 0 0]>>")
    doc.xref_set_key(doc[0].xref, "Annots", f"[{annot} 0 R]")
    data = doc.tobytes()
    doc.close()
    src = fitz.open("pdf", data)
    assert [lk["kind"] for lk in src[0].get_links()] == [fitz.LINK_NAMED]
    out = tmp_path / "out.pdf"
    organise.merge([(src, [(0, 1)]), (fitz.open(b), [(0, 0)])], str(out),
                   threading.Event(), lambda v: None)
    with fitz.open(out) as d:
        assert [(lk["kind"], lk["page"]) for lk in d[0].get_links()] == [(fitz.LINK_GOTO, 1)]
        ocgs = d.get_ocgs()
        assert sorted(v["name"] for v in ocgs.values()) == ["Layer A", "Layer B"]
        assert not any(v["on"] for v in ocgs.values())          # still off
        assert "hidden A" not in d[0].get_text() and "hidden B" not in d[2].get_text()
        assert sorted(d.embfile_names()) == ["notes.txt", "notes.txt (2)"]
        assert not any(d.xref_get_key(x, "PKsrc")[0] != "null" for x in range(1, d.xref_length()))


def test_merge_same_page_twice(tmp_path):
    a = _rich_pdf(tmp_path / "a.pdf", pages=2)
    out = tmp_path / "out.pdf"
    assert organise.merge([(fitz.open(a), [(0, 1), (0, 0)])], str(out),
                          threading.Event(), lambda v: None) == 3
    assert _texts(out) == ["Page 1", "Page 2", "Page 1"]


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


def test_split_chapters_over_its_own_source(tmp_path):
    # The source is named like its first chapter's output, in the output folder.
    # release() closes the open file as a tool's DocHolder does; the split must
    # go on from the content it had and write every chapter.
    src = make_pdf(tmp_path / "01_Intro.pdf", pages=4)
    doc = fitz.open(src)

    def release(path):
        if Path(path).resolve() == Path(src).resolve() and not doc.is_closed:
            doc.close()
    entries = [("Intro", 0), ("Body", 2), ("_END_", 4)]
    n = organise.split_chapters(doc, entries, str(tmp_path), threading.Event(),
                                lambda v: None, release=release)
    assert n == 2
    assert _texts(tmp_path / "01_Intro.pdf") == ["Page 1", "Page 2"]
    assert _texts(tmp_path / "02_Body.pdf") == ["Page 3", "Page 4"]


def test_toc_level_error_and_delete_entry():
    assert organise.toc_level_error([[1, "a", 1], [2, "b", 1], [3, "c", 1]]) is None
    msg = organise.toc_level_error([[1, "a", 1], [3, "c", 1]])
    assert "Bookmark 2 ('c') is level 3 but follows level 1" in msg
    toc = [[1, "a", 1], [2, "b", 1], [3, "c", 1], [2, "d", 1], [1, "e", 1]]
    organise.delete_entry(toc, 1)
    assert toc == [[1, "a", 1], [2, "c", 1], [2, "d", 1], [1, "e", 1]]
