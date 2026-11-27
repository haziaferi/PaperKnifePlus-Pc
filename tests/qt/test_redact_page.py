"""The Qt Redact page.  Redaction is a privacy feature: every check on redacted
text, images and line art is made here on the file the page saved, opened with
PyMuPDF.  The source PDFs and measurements are tests/redact_cases.py, which the
core tests share."""
import importlib.util
import io
from pathlib import Path

import pymupdf as fitz
import pytest
from PIL import Image

from qt_harness import make_pdf, pump, subtitle_with, wait_job

SUBTITLE = "Draw rectangles over sensitive content"

# Loaded by path, so tests/ (and its conftest) never joins sys.path.
_spec = importlib.util.spec_from_file_location(
    "pk_redact_cases", Path(__file__).resolve().parents[1] / "redact_cases.py")
CASES_MOD = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(CASES_MOD)
SECRET = CASES_MOD.SECRET


def _open(window, path):
    assert window.open_tool("RedactTool", str(path))
    pump(0.1)
    page = window.current_page()
    assert page._doc is not None
    return page


def _scene(page, x, y):
    """Scene position of the page point (x, y)."""
    r = page.view.page_to_scene(fitz.Rect(x, y, x, y))
    return r.x(), r.y()


def _drag(page, p0, p1):
    page._press(_scene(page, *p0))
    page._drag(_scene(page, *p1))
    page._mouse_up(_scene(page, *p1))


def _apply_save(window, dialogs, page, out, fill="Black"):
    page.set_fill(fill)
    dialogs.asks.append(True)
    dialogs.save(out)
    page.apply_redactions()
    wait_job(window)
    assert not dialogs.errors(), dialogs.errors()
    return out


# ── the page ─────────────────────────────────────────────────────────────────
def test_the_page_builds_with_its_rail_and_one_main_action(window):
    assert window.open_tool("RedactTool")
    page = window.current_page()
    assert type(page).__name__ == "RedactPage"
    assert page.title_label.text() == "Redact"
    keys = [getattr(page.rail.itemAt(i).widget(), "pk_key", None)
            for i in range(page.rail.count())]
    assert [k for k in keys if k] == ["box", "search", "pages", "undo"]
    assert [b.text() for b in page._buttons if b.pk_primary] == ["Save redacted copy…"]
    page.set_kind("search")
    pump(0.05)
    assert page.search_edit.isVisibleTo(page)


def test_apply_without_a_document_or_boxes_warns_and_writes_nothing(window, dialogs, tmp_path):
    assert window.open_tool("RedactTool")
    page = window.current_page()
    page.apply_redactions()
    assert dialogs.msgs == [("warning", "Apply", "Open a PDF first.")]
    page = _open(window, make_pdf(tmp_path / "in.pdf", pages=1))
    dialogs.msgs.clear()
    dialogs.save(tmp_path / "out.pdf")
    page.apply_redactions()
    assert dialogs.msgs == [("info", "Apply", "No redaction boxes drawn yet.")]
    assert not (tmp_path / "out.pdf").exists()


def test_mark_all_without_text_warns(window, dialogs, tmp_path):
    page = _open(window, make_pdf(tmp_path / "in.pdf", pages=1))
    page.set_kind("search")
    page.mark_search()
    assert dialogs.msgs == [("warning", "Mark", "Enter search text.")]


def test_a_drag_marks_a_box_undo_and_remove_take_it_back(window, tmp_path):
    page = _open(window, make_pdf(tmp_path / "in.pdf", pages=2))
    _drag(page, (60, 80), (200, 110))
    _drag(page, (60, 300), (200, 330))
    assert len(page._pending) == 2 and page.box_list.count() == 2
    assert page.pending_label.text() == "2 boxes pending"
    pg, r, phrase = page._pending[0]
    assert pg == 0 and phrase is None
    assert r.x0 == pytest.approx(60, abs=1) and r.y1 == pytest.approx(110, abs=1)
    page.undo()
    assert len(page._pending) == 1 and page._pending[0][1].y0 == pytest.approx(80, abs=1)
    page.box_list.setCurrentRow(0)
    page.delete()
    assert page._pending == [] and page.pending_label.text() == "0 boxes pending"
    # A click is not a box.
    xy = _scene(page, 100, 100)
    page._press(xy)
    page._mouse_up(xy)
    assert page._pending == []


# ── the main action end to end (test_content: whole-file scrub) ──────────────
def test_mark_all_then_apply_removes_the_secret_from_the_whole_file(window, dialogs, tmp_path):
    src, out = tmp_path / "secret.pdf", tmp_path / "redacted.pdf"
    CASES_MOD._secret_pdf(src)
    page = _open(window, src)
    page.set_kind("search")
    page.search_edit.setText(SECRET)
    page.mark_search()
    wait_job(window)
    n = len(page._pending)
    assert n >= 1 and {p[2] for p in page._pending} == {SECRET}
    assert window.status_text() == f"⚠  Marked {n} occurrence(s) of '{SECRET}' across all pages"
    assert window.status_role == "warning"
    _apply_save(window, dialogs, page, out)
    assert ("ask_yes_no", "Confirm Redaction",
            f"Permanently destroy content under {n} redaction box(es)?\n\n"
            "This cannot be undone once saved.") in dialogs.msgs
    saved = [m for m in dialogs.msgs if m[1] == "Saved"]
    assert saved and saved[0][2].startswith(f"Redacted PDF saved:\n{out}")
    assert "Also removed from: " in saved[0][2]
    assert len(page._pending) == n                 # the document here keeps its boxes
    assert window.status_text() == f"✓  {n} redaction(s) applied · Saved → redacted.pdf"

    raw = out.read_bytes()
    leaks = []
    with fitz.open(out) as doc:
        if any(SECRET in p.get_text() for p in doc):
            leaks.append("page text")
        if SECRET in (doc.metadata["title"] or ""):
            leaks.append("Info title")
        if SECRET in doc.get_xml_metadata():
            leaks.append("XMP")
        if any(SECRET in item[1] for item in doc.get_toc()):
            leaks.append("bookmark")
        if any(SECRET.encode() in doc.embfile_get(n) for n in doc.embfile_names()):
            leaks.append("attachment")
        if any(SECRET in (a.info["content"] or "") for p in doc for a in p.annots()):
            leaks.append("annotation")
        if any(SECRET in str(w.field_value) for p in doc for w in p.widgets()):
            leaks.append("form field")
        assert "Public paragraph" in doc[0].get_text()
        assert doc.metadata["author"] == "Alice"
        expanded = doc.tobytes(expand=255)
    for name, blob in (("file bytes", raw), ("expanded bytes", expanded)):
        if SECRET.encode() in blob or SECRET.encode("utf-16-be") in blob:
            leaks.append(name)
    assert leaks == []


def test_a_phrase_not_found_is_reported_and_marks_nothing(window, dialogs, tmp_path):
    page = _open(window, make_pdf(tmp_path / "in.pdf", pages=2))
    page.set_kind("search")
    page.search_edit.setText("nowhere")
    page.mark_search()
    wait_job(window)
    assert page._pending == []
    assert ("info", "Mark", "'nowhere' not found in this PDF.") in dialogs.msgs


def test_a_cancelled_mark_all_marks_nothing(window, dialogs, tmp_path):
    page = _open(window, CASES_MOD._long_pdf(tmp_path / "m.pdf", pages=200))
    page.set_kind("search")
    page.search_edit.setText("needle")
    page.mark_search()
    window._cancel_job()
    wait_job(window)
    assert page._pending == [], "half the matches would look like all of them"


def test_a_box_on_a_rotated_page_covers_the_drawn_content(window, dialogs, tmp_path):
    src, out = tmp_path / "rot.pdf", tmp_path / "out.pdf"
    doc = fitz.open()
    p = doc.new_page()
    p.insert_text((72, 100), "TOPSECRET", fontsize=14)
    p.insert_text((72, 400), "Visible", fontsize=14)
    p.set_rotation(90)
    doc.save(str(src))
    doc.close()
    page = _open(window, src)
    word = page._doc[0].search_for("TOPSECRET")[0]
    _drag(page, (word.x0 - 2, word.y0 - 2), (word.x1 + 2, word.y1 + 2))
    assert len(page._pending) == 1
    _apply_save(window, dialogs, page, out)
    assert "TOPSECRET" in page._doc[0].get_text()   # the copy is redacted, not the document
    with fitz.open(out) as d:
        assert d[0].rotation == 90
        assert "TOPSECRET" not in d[0].get_text() and "Visible" in d[0].get_text()
        assert b"TOPSECRET" not in d.tobytes(expand=255)


def test_a_box_over_short_text_leaves_unrelated_content(window, dialogs, tmp_path):
    src, out = tmp_path / "in.pdf", tmp_path / "out.pdf"
    doc = fitz.open()
    doc.new_page().insert_text((72, 100), "12", fontsize=14)
    p2 = doc.new_page()
    p2.insert_text((72, 100), "Keep me", fontsize=14)
    p2.add_text_annot((300, 300), "Unrelated reviewer note")
    doc.set_toc([[1, "Intro", 1], [1, "Chapter 12 overview", 2]])
    doc.set_metadata({"title": "Report 2012"})
    doc.save(str(src))
    doc.close()
    page = _open(window, src)
    _drag(page, (70, 85), (100, 105))
    _apply_save(window, dialogs, page, out)
    with fitz.open(str(out)) as d:
        assert "12" not in d[0].get_text()
        assert [a.info["content"] for a in d[1].annots()] == ["Unrelated reviewer note"]
        assert [e[1] for e in d.get_toc()] == ["Intro", "Chapter 12 overview"]
        assert d.metadata["title"] == "Report 2012"


def test_text_under_a_drawn_box_is_scrubbed_from_metadata_too(window, dialogs, tmp_path):
    src, out = tmp_path / "in.pdf", tmp_path / "out.pdf"
    doc = fitz.open()
    doc.new_page().insert_text((72, 100), "Codename Bluebird", fontsize=14)
    doc.set_metadata({"title": "About Codename Bluebird", "author": "Alice"})
    doc.set_toc([[1, "Codename Bluebird notes", 1]])
    doc.save(str(src))
    doc.close()
    page = _open(window, src)
    word = page._doc[0].search_for("Codename Bluebird")[0]
    _drag(page, (word.x0 - 2, word.y0 - 2), (word.x1 + 2, word.y1 + 2))
    _apply_save(window, dialogs, page, out)
    with fitz.open(out) as d:
        assert "Bluebird" not in d[0].get_text()
        assert "Bluebird" not in d.metadata["title"] and d.metadata["author"] == "Alice"
        assert all("Bluebird" not in e[1] for e in d.get_toc())
        assert b"Bluebird" not in d.tobytes(expand=255)


# ── options ──────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("fill,ink", [("Black", 0), ("White", 255)])
def test_the_fill_paints_the_box(window, dialogs, tmp_path, fill, ink):
    src, out = tmp_path / "in.pdf", tmp_path / "out.pdf"
    doc = fitz.open()
    p = doc.new_page()
    p.draw_rect(fitz.Rect(50, 50, 300, 300), color=None, fill=(0.2, 0.6, 0.9))
    doc.save(str(src))
    doc.close()
    page = _open(window, src)
    _drag(page, (100, 100), (200, 200))
    _apply_save(window, dialogs, page, out, fill=fill)
    with fitz.open(out) as d:
        inside = d[0].get_pixmap(clip=fitz.Rect(110, 110, 190, 190), alpha=False,
                                 colorspace=fitz.csGRAY)
        assert set(inside.samples) == {ink}
        outside = d[0].get_pixmap(clip=fitz.Rect(60, 60, 90, 90), alpha=False)
        assert outside.pixel(5, 5) != (ink, ink, ink)


def test_an_image_under_a_box_loses_those_pixels(window, dialogs, tmp_path):
    src, out = tmp_path / "img.pdf", tmp_path / "out.pdf"
    buf = io.BytesIO()
    Image.new("RGB", (200, 200), (200, 30, 30)).save(buf, "PNG")
    doc = fitz.open()
    doc.new_page().insert_image(fitz.Rect(100, 100, 300, 300), stream=buf.getvalue())
    doc.save(str(src))
    doc.close()
    page = _open(window, src)
    _drag(page, (100, 100), (200, 300))
    _apply_save(window, dialogs, page, out, fill="White")
    with fitz.open(out) as d:
        inside = d[0].get_pixmap(clip=fitz.Rect(110, 110, 190, 290), alpha=False)
        assert set(inside.samples) == {255}
        right = d[0].get_pixmap(clip=fitz.Rect(220, 120, 280, 280), alpha=False)
        assert right.pixel(10, 10) == (200, 30, 30)
        xref = d[0].get_images()[0][0]
        pix = fitz.Pixmap(d, xref)
        # The image's own data, not just its rendering: the left half is gone.
        assert pix.pixel(20, 100) != (200, 30, 30) and pix.pixel(180, 100) == (200, 30, 30)


# ── line art (test_redact_lineart, through the page) ─────────────────────────
class _without_fills:
    """The page's drawings less the white boxes the redaction itself painted
    (where two boxes overlap, one box's painted edge lies inside the other)."""

    def __init__(self, page, boxes):
        self.page, self.boxes = page, [fitz.Rect(b) for b in boxes]

    def get_drawings(self, **kw):
        return [d for d in self.page.get_drawings(**kw)
                if not (d.get("fill") == (1.0, 1.0, 1.0) and len(d["items"]) == 1
                        and any(max(abs(x - y) for x, y in zip(d["rect"], b, strict=True)) < 0.01
                                for b in self.boxes))]


@pytest.mark.parametrize("name", list(CASES_MOD.CASES))
def test_line_art_is_cut_at_the_box_edge(window, dialogs, tmp_path, name):
    doc, boxes = CASES_MOD.CASES[name]()
    src_bytes = doc.tobytes()
    doc.close()
    with fitz.open("pdf", src_bytes) as s:
        w, h, before = CASES_MOD._gray(s[0])
        inside = CASES_MOD._box_pixels(s[0], boxes, w, h, grow=-3)
        near = CASES_MOD._box_pixels(s[0], boxes, w, h, grow=2.5)
        words_before = CASES_MOD._words_outside(s[0], boxes)
    src = tmp_path / f"{name}.pdf"
    src.write_bytes(src_bytes)
    page = _open(window, src)
    page._pending = [(0, fitz.Rect(b), None) for b in boxes]
    # White fill: whatever was left under a box would show in the saved file.
    out = _apply_save(window, dialogs, page, tmp_path / f"{name}_redacted.pdf", fill="White")
    assert not dialogs.warnings(), "the page fell back to an image"
    with fitz.open(out) as red:
        bw, bh, after = CASES_MOD._gray(red[0])
        assert (bw, bh) == (w, h)
        ink = [i for i in inside if after[i] < 250]
        assert not ink, f"{len(ink)} ink pixels left under the boxes"
        assert CASES_MOD._outlines_inside(_without_fills(red[0], boxes), boxes) == []
        outside_ink = [i for i in range(w * h) if i not in near and before[i] < 250]
        changed = [i for i in outside_ink if abs(before[i] - after[i]) > 48]
        assert len(changed) <= max(2, len(outside_ink) // 1000), \
            f"{len(changed)} of {len(outside_ink)} ink pixels outside the boxes changed"
        assert set(words_before) <= set(CASES_MOD._words_outside(red[0], boxes))


def _redact_case(window, dialogs, tmp_path, name, doc, boxes, fill="Black"):
    src = tmp_path / f"{name}.pdf"
    src.write_bytes(doc.tobytes())
    page = _open(window, src)
    page._pending = [(0, fitz.Rect(b), None) for b in boxes]
    return _apply_save(window, dialogs, page, tmp_path / f"{name}_redacted.pdf", fill)


def test_curves_stay_curves(window, dialogs, tmp_path):
    doc, boxes = CASES_MOD.case_signature()
    out = _redact_case(window, dialogs, tmp_path, "sigc", doc, boxes)
    with fitz.open(out) as red:
        kinds = [it[0] for d in red[0].get_drawings() for it in d["items"]]
    assert kinds.count("c") == 2 and kinds.count("l") == 1, kinds


def test_form_shared_by_another_page_keeps_its_line_art(window, dialogs, tmp_path):
    doc, boxes = CASES_MOD.case_form()
    before = len(doc[1].get_drawings())
    pts_before = sorted(str(it) for d in doc[1].get_drawings() for it in d["items"])
    out = _redact_case(window, dialogs, tmp_path, "form2", doc, boxes)
    with fitz.open(out) as red:
        assert len(red[1].get_drawings()) == before
        assert sorted(str(it) for d in red[1].get_drawings() for it in d["items"]) == pts_before
        assert CASES_MOD._outlines_inside(red[0], boxes) == []


def test_drawing_order_is_kept(window, dialogs, tmp_path):
    doc, boxes = CASES_MOD.case_order()
    out = _redact_case(window, dialogs, tmp_path, "order2", doc, boxes)
    with fitz.open(out) as red:
        pg = red[0]
        sheet = pg.get_pixmap(dpi=CASES_MOD.DPI, clip=fitz.Rect(410, 290, 495, 310), alpha=False)
        assert set(sheet.samples) == {255}
        pix = pg.get_pixmap(dpi=CASES_MOD.DPI, clip=fitz.Rect(300, 209.5, 301, 210.5), alpha=False)
        r, g, b = pix.pixel(0, 0)
        assert r > 200 and g > 200 and b < 80, (r, g, b)


def test_a_mesh_shading_page_becomes_an_image_and_says_so(window, dialogs, tmp_path):
    import struct
    doc = fitz.open()
    mesh = doc.get_new_xref()
    doc.update_object(mesh, "<</ShadingType 4/ColorSpace/DeviceRGB/BitsPerCoordinate 16"
                            "/BitsPerComponent 8/BitsPerFlag 8/Decode[0 595 0 842 0 1 0 1 0 1]>>")

    def v(x, y, r, g, b):
        return struct.pack(">BHHBBB", 0, round(x / 595 * 65535), round(y / 842 * 65535),
                           r, g, b)
    doc.update_stream(mesh, v(100, 300, 255, 0, 0) + v(500, 300, 0, 255, 0)
                      + v(300, 700, 0, 0, 255))
    CASES_MOD._raw_page(doc, b"BT /F1 12 Tf 50 800 Td (Kept words) Tj ET /S1 sh",
                      f"<</Shading<</S1 {mesh} 0 R>>/Font<</F1<</Type/Font/Subtype/Type1"
                      f"/BaseFont/Helvetica>>>>>>")
    out = _redact_case(window, dialogs, tmp_path, "mesh", doc, [fitz.Rect(250, 250, 350, 350)])
    warn = dialogs.warnings()
    assert warn and warn[0][1] == "Redact" and warn[0][2].startswith("Page 1 holds drawings")
    with fitz.open(out) as d:
        assert len(d[0].get_images()) == 1
        assert b"sh" not in b" ".join(d.xref_stream(x) for x in d[0].get_contents())
        assert not any(b"ShadingType" in (d.xref_object(x) or "").encode()
                       for x in range(1, d.xref_length()))
        box = d[0].get_pixmap(clip=fitz.Rect(260, 260, 340, 340), alpha=False,
                              colorspace=fitz.csGRAY)
        assert max(box.samples) < 40          # black fill burned into the picture


# ── dialogs, files, lifetime ─────────────────────────────────────────────────
def test_declining_the_confirmation_changes_nothing(window, dialogs, tmp_path):
    src = make_pdf(tmp_path / "in.pdf", pages=1)
    page = _open(window, src)
    _drag(page, (60, 80), (200, 110))
    dialogs.asks.append(False)
    dialogs.save(tmp_path / "out.pdf")
    page.apply_redactions()
    # Redaction runs in a background job: a decline must not start one at all,
    # and the checks below mean something only once anything started has ended.
    assert window._current_job is None
    wait_job(window)
    assert len(page._pending) == 1 and not (tmp_path / "out.pdf").exists()
    assert "Page 1" in page._doc[0].get_text()
    assert dialogs.saves == [str(tmp_path / "out.pdf")]     # the save dialog never opened


def test_cancelling_the_save_dialog_applies_nothing_and_keeps_the_document(
        window, dialogs, tmp_path):
    src = make_pdf(tmp_path / "in.pdf", pages=1)
    page = _open(window, src)
    _drag(page, (60, 80), (200, 110))
    dialogs.asks.append(True)
    page.apply_redactions()           # no path queued: the save dialog is cancelled
    pump(0.1)
    assert window._current_job is None or not window._current_job.is_running
    assert len(page._pending) == 1
    assert page._doc is not None and "Page 1" in page._doc[0].get_text()


def test_apply_makes_a_new_copy_and_the_document_keeps_its_boxes(window, dialogs, tmp_path):
    # Owner, 2026-10-23: applying redactions makes a new redacted copy; the
    # document open here keeps its content and its marks.
    src = make_pdf(tmp_path / "in.pdf", pages=2)
    page = _open(window, src)
    _drag(page, (60, 80), (200, 110))
    out = _apply_save(window, dialogs, page, tmp_path / "copy.pdf")
    with fitz.open(out) as d:
        assert len(d) == 2 and "Page 1" not in d[0].get_text() and "Page 2" in d[1].get_text()
    assert "Page 1" in page._doc[0].get_text() and len(page._pending) == 1
    assert not window.document.dirty
    with fitz.open(src) as d:
        assert "Page 1" in d[0].get_text()


def test_apply_over_the_open_file_is_refused(window, dialogs, tmp_path):
    src = make_pdf(tmp_path / "in.pdf", pages=1)
    page = _open(window, src)
    _drag(page, (60, 80), (200, 110))
    dialogs.asks.append(True)
    dialogs.save(src)
    page.apply_redactions()
    assert ("warning", "Apply", "Choose another file: this one is the PDF open here.") \
        in dialogs.msgs
    assert window._current_job is None
    with fitz.open(src) as d:
        assert "Page 1" in d[0].get_text()


def test_drop_takes_pdfs_only(window, dialogs, tmp_path):
    page = _open(window, make_pdf(tmp_path / "in.pdf", pages=1))
    _drag(page, (60, 80), (200, 110))
    other = tmp_path / "x.txt"
    other.write_text("x", encoding="utf-8")
    assert page.accept_drop(str(other)) is False
    assert len(page._doc) == 1 and len(page._pending) == 1
    # Boxes are marks beside the document, not edits of it: another file opens
    # without the unsaved-edits question, and the marks go with the old one.
    assert page.accept_drop(make_pdf(tmp_path / "second.pdf", pages=3)) is True
    assert len(page._doc) == 3 and page._pending == []
    assert page.subtitle_label.text() == subtitle_with(SUBTITLE, "second.pdf")


def test_leaving_the_tool_keeps_the_document_and_its_boxes(window, dialogs, tmp_path):
    # One document per window (owner, 2026-10-23): another tool works on the
    # same document, and Redact's boxes are there when it comes back.
    page = _open(window, make_pdf(tmp_path / "in.pdf", pages=1))
    _drag(page, (60, 80), (200, 110))
    doc = page._doc
    window.show_page("home")
    assert not doc.is_closed and window.document.doc is doc
    assert window.open_tool("RedactTool")
    assert page._doc is doc and len(page._pending) == 1


def test_undo_takes_back_a_box_or_a_page_change_whichever_came_last(window, dialogs,
                                                                      tmp_path):
    page = _open(window, make_pdf(tmp_path / "in.pdf", pages=2))
    _drag(page, (60, 80), (200, 110))              # a box
    page.thumbs.setCurrentRow(1)
    page.rotate_pages(90)                          # then a page change
    _drag(page, (60, 300), (200, 330))             # then another box
    assert len(page._pending) == 2 and page._doc[1].rotation == 90
    page.undo()
    assert len(page._pending) == 1 and page._doc[1].rotation == 90
    page.undo()
    assert len(page._pending) == 1 and page._doc[1].rotation == 0
    page.undo()
    assert page._pending == []



def test_cancel_during_apply_writes_nothing_and_keeps_the_boxes(window, dialogs, tmp_path,
                                                                   monkeypatch):
    # The redaction is made on the job's own copy: Cancel, even on the last
    # page, writes no file, and the document and its boxes are as they were.
    import os
    from paperknife.core import redact as core_redact
    src = make_pdf(tmp_path / "doc.pdf", pages=1, text="SECRET {n}")
    assert window.open_tool("RedactTool", src)
    pump(0.1)
    page = window.current_page()
    page._pending.append((0, fitz.Rect(60, 80, 300, 110), None))
    orig = core_redact.redact_page

    def cancelled_mid_page(doc, pno, rects, fill):
        window._current_job.cancel()
        return orig(doc, pno, rects, fill)
    monkeypatch.setattr(core_redact, "redact_page", cancelled_mid_page)
    out = tmp_path / "out.pdf"
    dialogs.asks.append(True)
    dialogs.save(out)
    page.apply_redactions()
    wait_job(window)
    assert not os.path.exists(out)
    assert len(page._pending) == 1 and "SECRET" in page._doc[0].get_text()


def test_closing_with_unapplied_boxes_warns(window, dialogs, tmp_path):
    # Owner, 2026-10-23: boxes are not edits, so Save does not keep them; closing warns.
    page = _open(window, make_pdf(tmp_path / "in.pdf", pages=1))
    _drag(page, (60, 80), (200, 110))
    _drag(page, (60, 300), (200, 330))
    assert not window.has_unsaved() and window.unapplied_marks() == 2
    dialogs.asks.append(False)
    window.close()
    pump(0.05)
    assert window.isVisible()
    assert dialogs.msgs[-1] == ("ask_yes_no", "Close",
                                "2 redaction boxes drawn and not applied will be lost. "
                                "Close anyway?")
    page.box_list.setCurrentRow(0)
    page.delete()
    page.box_list.setCurrentRow(0)
    page.delete()
    assert window.unapplied_marks() == 0          # nothing left to warn about
