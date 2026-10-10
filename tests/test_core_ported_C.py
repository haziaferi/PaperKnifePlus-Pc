"""Pure-logic checks ported from the CTk suites tests/test_redact_lineart.py and
tests/test_shell.py (phase 8, map C), so they outlive the CTk UI.

The line-art case builders and measurements are copied from
tests/test_redact_lineart.py (that file is deleted with the CTk UI); the checks
call paperknife.core.redact.redact_page, which the Qt Redact page runs."""
import json
import os
import struct
from pathlib import Path

import pymupdf as fitz
import pytest

from redact_cases import CASES, _box_pixels, _gray, _outlines_inside, _raw_page, case_soft_mask


def _mesh(doc):
    """A type 4 (free-form triangle) mesh shading over the middle of the page."""
    mesh = doc.get_new_xref()
    doc.update_object(mesh, "<</ShadingType 4/ColorSpace/DeviceRGB/BitsPerCoordinate 16"
                            "/BitsPerComponent 8/BitsPerFlag 8/Decode[0 595 0 842 0 1 0 1 0 1]>>")

    def v(x, y, r, g, b):
        return struct.pack(">BHHBBB", 0, round(x / 595 * 65535), round(y / 842 * 65535),
                           r, g, b)
    doc.update_stream(mesh, v(100, 300, 255, 0, 0) + v(500, 300, 0, 255, 0)
                      + v(300, 700, 0, 0, 255))
    return mesh


# ── test_redact_lineart.py: what redaction leaves under a box with no fill ────
@pytest.mark.parametrize("name", list(CASES))
def test_line_art_under_a_box_is_cut_with_no_fill_painted(name):
    # CTk test_line_art_is_cut_at_the_box_edge, its no-fill half: the Qt page
    # test paints a fill, which would hide ink left under the box.
    from paperknife.core.redact import redact_page
    doc, boxes = CASES[name]()
    src_bytes = doc.tobytes()
    doc.close()
    with fitz.open("pdf", src_bytes) as src:
        w, h, _ = _gray(src[0])
        inside = _box_pixels(src[0], boxes, w, h, grow=-3)
    with fitz.open("pdf", src_bytes) as bare:
        cut = redact_page(bare, 0, boxes, fill=None)
        assert cut == "cut", f"fell back: {cut}"
        bw, bh, after_bare = _gray(bare[0])
        assert (bw, bh) == (w, h)
        ink = [i for i in inside if after_bare[i] < 250]
        assert not ink, f"{len(ink)} ink pixels left under the boxes"
        assert _outlines_inside(bare[0], boxes) == []


def test_a_stream_read_differently_falls_back_without_leaking():
    # MuPDF reads '--300' as -300; lineart treats it as an unknown keyword, so
    # its cut follows a different line.  The MuPDF-side check must catch that.
    from paperknife.core.redact import redact_page
    from paperknife.lineart import residual
    doc = fitz.open()
    _raw_page(doc, b"0 0 1 RG 4 w 100 600 m 300 --300 l S")
    page = doc[0]
    seg = page.get_drawings()[0]["items"][0]
    mid = (seg[1] + seg[2]) / 2
    box = fitz.Rect(mid.x - 20, mid.y - 20, mid.x + 20, mid.y + 20)
    assert residual(page, [box])
    assert redact_page(doc, 0, [box], fill=None) == "whole"
    assert not residual(doc[0], [box])
    pix = doc[0].get_pixmap(clip=box + (3, 3, -3, -3), alpha=False)
    assert set(pix.samples) == {255}


@pytest.mark.parametrize("content", [
    b"q /E#31 gs 0 0 1 rg 100 300 400 400 re f Q",
    b"q 0 0 1 rg 100 300 m 500 300 l 500 700 l /E1 gs 100 700 l h f Q"])
def test_soft_mask_reached_through_an_escaped_name_or_inside_a_path_is_cut(content):
    from paperknife.core.redact import redact_page
    from paperknife.lineart import residual
    doc, boxes = case_soft_mask()
    doc.update_stream(doc[0].get_contents()[0], content)
    assert residual(doc[0], boxes), "the case must have mask shape in the box"
    assert redact_page(doc, 0, boxes, None) == "cut", content
    assert not residual(doc[0], boxes)


def test_an_edge_seen_only_inside_a_box_is_cut_even_with_its_vertices_off_page():
    from paperknife.core.redact import redact_page
    from paperknife.lineart import residual
    doc = fitz.open()
    _raw_page(doc, b"0 0 1 rg -100 480 m 695 500 l 695 0 l -100 0 l h f")
    box = [fitz.Rect(0, 300, 595, 400)]
    assert residual(doc[0], box)
    assert redact_page(doc, 0, box, None) == "cut"
    assert not residual(doc[0], box)
    edges = [it for d in doc[0].get_drawings() for it in d["items"] if it[0] == "l"]
    assert not any(fitz.Rect(it[1], it[2]).normalize().intersects(box[0] + (1, 1, -1, -1))
                   for it in edges)


def test_a_stream_nothing_can_read_turns_the_page_into_an_image(monkeypatch):
    # cut_line_art raising leaves no list of unsafe shapes, and residual() never
    # sees a mesh shading: with no fill the page stayed vector, mesh data and all.
    from paperknife.core import redact as core_redact
    doc = fitz.open()
    mesh = _mesh(doc)
    _raw_page(doc, b"/S1 sh", f"<</Shading<</S1 {mesh} 0 R>>>>")

    def unreadable(page, rects):
        raise ValueError("an operator sequence lineart cannot read")
    monkeypatch.setattr(core_redact, "cut_line_art", unreadable)
    box = [fitz.Rect(250, 250, 350, 350)]
    assert core_redact.redact_page(doc, 0, box, None) == "image"
    out = fitz.open("pdf", doc.tobytes(garbage=4, deflate=True))
    assert not any(b"ShadingType" in (out.xref_object(x) or "").encode()
                   for x in range(1, out.xref_length()))


# ── test_shell.py: recent store, prefs, atomic_output, thumbnails ─────────────
def _pdf(path, pages=1):
    doc = fitz.open()
    for i in range(pages):
        doc.new_page().insert_text((72, 100), f"Page {i + 1}", fontsize=14)
    doc.save(str(path))
    doc.close()
    return str(path)


def _store(tmp_path, monkeypatch, content):
    from paperknife import recent
    path = tmp_path / "recent.json"
    path.write_text(content, encoding="utf-8")
    monkeypatch.setattr(recent, "RECENT_PATH", path)
    store = recent.RecentFiles()
    monkeypatch.setattr(store, "_save", lambda: None)
    return store


@pytest.mark.parametrize("bad", ['{"a": 1}', '["x"]', '[{"path": 5}]', "same file"])
def test_recent_wrong_shape_does_not_break_push(tmp_path, monkeypatch, bad):
    src = _pdf(tmp_path / "a.pdf")
    if bad == "same file":
        bad = json.dumps([{"path": src}])          # no name, pages, size or time
    store = _store(tmp_path, monkeypatch, bad)
    store.all()
    store.push(src, 1)
    assert store.all()[0]["path"] == str(Path(src).resolve())


def test_recent_max_zero_keeps_history(tmp_path, monkeypatch):
    from paperknife.prefs import PREFS
    store = _store(tmp_path, monkeypatch, "[]")
    a = _pdf(tmp_path / "a.pdf")
    b = _pdf(tmp_path / "b.pdf")
    store.push(a)
    monkeypatch.setitem(PREFS._data, "max_recent", 0)
    store.push(b)
    assert len(store._entries) >= 1


def test_prefs_atomic_write_leaves_old_file_on_failure(monkeypatch, tmp_path):
    from paperknife import prefs
    path = tmp_path / "prefs.json"
    path.write_text('{"ocr_lang": "ita"}')
    monkeypatch.setattr(prefs, "PREFS_PATH", path)

    def boom(*a):
        raise OSError("disk full")
    p = prefs.Prefs()
    p.ocr_lang = "deu"
    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        p.save()
    assert json.loads(path.read_text()) == {"ocr_lang": "ita"}
    assert list(tmp_path.iterdir()) == [path]


def test_prefs_load_validates_shape(monkeypatch, tmp_path):
    from paperknife import prefs
    path = tmp_path / "prefs.json"
    monkeypatch.setattr(prefs, "PREFS_PATH", path)
    path.write_text('{"appearance": "blue", "max_recent": "7", "ocr_lang": "ita"}')
    p = prefs.Prefs()
    assert p.appearance == "light"
    assert p.max_recent == 12
    assert p.ocr_lang == "ita"
    path.write_text("[1, 2]")
    p = prefs.Prefs()
    assert p.ocr_lang == "eng"
    assert (tmp_path / "prefs.json.bad").exists()


def test_atomic_output_keeps_existing_file_when_writer_fails(tmp_path):
    from paperknife.job_queue import atomic_output
    out = tmp_path / "out.pdf"
    out.write_bytes(b"old")
    with pytest.raises(RuntimeError):
        with atomic_output(str(out)) as tmp:
            Path(tmp).write_bytes(b"half")
            raise RuntimeError("killed mid-write")
    assert out.read_bytes() == b"old"
    assert list(tmp_path.iterdir()) == [out]
    with atomic_output(str(out)) as tmp:
        Path(tmp).write_bytes(b"new")
    assert out.read_bytes() == b"new"
    assert list(tmp_path.iterdir()) == [out]


def test_the_thumbnail_of_an_unchanged_file_is_rendered_once(tmp_path):
    # CTk test_home_reuses_the_thumbnail_image_of_an_unchanged_file, its
    # shared half: the Qt Home renders through recent.thumb_image.
    from paperknife.recent import thumb_image
    src = _pdf(tmp_path / "t.pdf")
    first = thumb_image(src, (120, 155))
    assert first is not None
    assert thumb_image(src, (120, 155)) is first
