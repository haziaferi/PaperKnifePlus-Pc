"""Redact, Edit Text, Find & Replace and Annotate through the real views."""
import io
from types import SimpleNamespace

import pymupdf as fitz
from PIL import Image

from conftest import tool

SECRET = "SECRET-ALPHA-42"
BG_RGB = (230, 230, 120)


def _ev(x, y):
    return SimpleNamespace(x=x, y=y)


def _drag(t, x0, y0, x1, y1):
    t._press(_ev(x0, y0))
    t._drag(_ev(x1, y1))
    t._release(_ev(x1, y1))


def _open(t, dialogs, path):
    dialogs.open(str(path))
    t._open()
    assert t._doc is not None


def _screen_rect(page, rect, zoom):
    return rect * page.rotation_matrix * fitz.Matrix(zoom, zoom)


def _bg_image_png():
    buf = io.BytesIO()
    Image.new("RGB", (60, 80), BG_RGB).save(buf, "PNG")
    return buf.getvalue()


# ── Redact ───────────────────────────────────────────────────────────────────

def _secret_pdf(path):
    doc = fitz.open()
    p = doc.new_page()
    p.insert_text((72, 100), f"Name: {SECRET}", fontsize=12)
    p.insert_text((72, 400), "Public paragraph", fontsize=12)
    p.add_text_annot((400, 600), f"note: {SECRET}")
    w = fitz.Widget()
    w.field_type = fitz.PDF_WIDGET_TYPE_TEXT
    w.field_name = "ref"
    w.field_value = SECRET
    w.rect = fitz.Rect(72, 650, 300, 670)
    p.add_widget(w)
    doc.set_metadata({"title": f"Report {SECRET}", "author": "Alice"})
    doc.set_xml_metadata(
        '<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF '
        'xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
        '<rdf:Description xmlns:dc="http://purl.org/dc/elements/1.1/">'
        f'<dc:title>{SECRET}</dc:title></rdf:Description></rdf:RDF></x:xmpmeta>')
    doc.set_toc([[1, f"Chapter {SECRET}", 1]])
    doc.embfile_add("notes.txt", f"attached {SECRET}".encode())
    doc.save(str(path))
    doc.close()


def test_redact_removes_secret_from_whole_file(app, dialogs, tmp_path):
    src, out = tmp_path / "secret.pdf", tmp_path / "redacted.pdf"
    _secret_pdf(src)
    t = tool(app, "RedactTool")
    _open(t, dialogs, src)
    t._search_var.set(SECRET)
    t._mark_search()
    t._apply()
    dialogs.save(out)
    t._save()
    assert not dialogs.errors(), dialogs.errors()

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


def test_redact_box_on_rotated_page_covers_drawn_content(app, dialogs, tmp_path):
    src = tmp_path / "rot.pdf"
    doc = fitz.open()
    p = doc.new_page()
    p.insert_text((72, 100), "TOPSECRET", fontsize=14)
    p.set_rotation(90)
    doc.save(str(src))
    doc.close()
    t = tool(app, "RedactTool")
    _open(t, dialogs, src)
    page = t._doc[0]
    word = page.search_for("TOPSECRET")[0]
    x0, y0, x1, y1 = _screen_rect(page, word, t._zoom)
    _drag(t, x0 - 2, y0 - 2, x1 + 2, y1 + 2)
    t._apply()
    assert "TOPSECRET" not in t._doc[0].get_text()


def test_leaving_tool_closes_document(app, dialogs, tmp_path):
    from conftest import make_pdf
    src = make_pdf(tmp_path / "in.pdf", pages=1)
    t = tool(app, "RedactTool")
    _open(t, dialogs, src)
    doc = t._doc
    tool(app, "AnnotateTool")
    assert doc.is_closed


# ── Edit Text ────────────────────────────────────────────────────────────────

def _edit_pdf(path):
    doc = fitz.open()
    p = doc.new_page()
    p.insert_image(p.rect, stream=_bg_image_png())
    p.insert_text((72, 100), "Hello world", fontsize=14)
    p.insert_text((72, 300), "Other block", fontsize=14)
    doc.save(str(path))
    doc.close()


# The baseline used a single-line CTkEntry; these read/write either widget.
def _box_text(t):
    box = t._edit_box
    return box.get("1.0", "end-1c") if hasattr(box, "_textbox") else box.get()


def _set_box(t, text):
    if hasattr(t._edit_box, "_textbox"):
        t._edit_box.delete("1.0", "end")
        t._edit_box.insert("1.0", text)
    else:
        t._edit_var.set(text)


def _select_hello(t):
    item = next(it for it in t._blocks if it["block"]["bbox"][1] < 150)
    t._select_block(item["bi"])
    return fitz.Rect(item["block"]["bbox"])


def _pixel(page, x, y):
    pix = page.get_pixmap(clip=fitz.Rect(x, y, x + 1, y + 1), alpha=False)
    return tuple(pix.pixel(0, 0))


def test_edit_select_shows_block_text(app, dialogs, tmp_path):
    _edit_pdf(tmp_path / "e.pdf")
    t = tool(app, "EditTextTool")
    _open(t, dialogs, tmp_path / "e.pdf")
    _select_hello(t)
    assert _box_text(t) == "Hello world"


def test_edit_apply_unchanged_keeps_text(app, dialogs, tmp_path):
    _edit_pdf(tmp_path / "e.pdf")
    t = tool(app, "EditTextTool")
    _open(t, dialogs, tmp_path / "e.pdf")
    _select_hello(t)
    t._apply_edit()
    text = t._doc[0].get_text()
    assert "Hello world" in text and "Other block" in text


def test_edit_apply_replaces_only_that_text_and_keeps_image(app, dialogs, tmp_path):
    _edit_pdf(tmp_path / "e.pdf")
    t = tool(app, "EditTextTool")
    _open(t, dialogs, tmp_path / "e.pdf")
    bbox = _select_hello(t)
    _set_box(t, "Hi")
    t._apply_edit()
    page = t._doc[0]
    text = page.get_text()
    assert "Hi" in text and "Hello" not in text and "Other block" in text
    # right end of the old span: "Hi" does not reach it, so the background must show
    px = _pixel(page, bbox.x1 - 3, (bbox.y0 + bbox.y1) / 2)
    assert max(abs(a - b) for a, b in zip(px, BG_RGB, strict=True)) < 10, px


def test_edit_undo_restores_text_and_keeps_image(app, dialogs, tmp_path):
    _edit_pdf(tmp_path / "e.pdf")
    t = tool(app, "EditTextTool")
    _open(t, dialogs, tmp_path / "e.pdf")
    _select_hello(t)
    _set_box(t, "Changed text")
    t._apply_edit()
    t._undo()
    page = t._doc[0]
    assert "Hello world" in page.get_text()
    px = _pixel(page, 300, 600)
    assert max(abs(a - b) for a, b in zip(px, BG_RGB, strict=True)) < 10, px


# ── Find & Replace ───────────────────────────────────────────────────────────

def _fr(app, dialogs, tmp_path, text, find, repl, **kw):
    src = tmp_path / "fr.pdf"
    doc = fitz.open()
    doc.new_page().insert_text((72, 300), text, fontsize=14, **kw)
    doc.save(str(src))
    doc.close()
    t = tool(app, "FindReplaceTool")
    _open(t, dialogs, src)
    t._find_var.set(find)
    t._repl_var.set(repl)
    t._replace_all()
    assert not dialogs.errors(), dialogs.errors()
    return t


def _span_with(page, needle):
    for b in page.get_text("dict")["blocks"]:
        for ln in b.get("lines", []):
            for s in ln["spans"]:
                if needle in s["text"]:
                    return s
    raise AssertionError(f"{needle!r} not on page: {page.get_text()!r}")


def test_replace_keeps_baseline_size_and_colour(app, dialogs, tmp_path):
    t = _fr(app, dialogs, tmp_path, "The quick fox jumps", "fox", "dog", color=(1, 0, 0))
    s = _span_with(t._doc[0], "dog")
    assert abs(s["origin"][1] - 300) < 1, s["origin"]
    assert abs(s["size"] - 14) < 0.1, s["size"]
    assert s["color"] == 0xFF0000, hex(s["color"])


def test_replace_keeps_non_latin_text(app, dialogs, tmp_path):
    t = _fr(app, dialogs, tmp_path, "The quick fox jumps", "fox", "Ωμέγα Жж €")
    assert "Ωμέγα Жж €" in t._doc[0].get_text()


def test_replace_is_case_sensitive(app, dialogs, tmp_path):
    t = _fr(app, dialogs, tmp_path, "Cat cat CAT", "cat", "dog")
    text = t._doc[0].get_text()
    assert "Cat" in text and "CAT" in text and text.count("dog") == 1, text


def test_replace_wrapped_match_once(app, dialogs, tmp_path):
    t = _fr(app, dialogs, tmp_path, "foo bar\nbaz qux", "bar baz", "ZZZ")
    text = t._doc[0].get_text()
    assert text.count("ZZZ") == 1, text
    assert "qux" in text and "foo" in text


def test_replace_can_be_undone(app, dialogs, tmp_path):
    t = _fr(app, dialogs, tmp_path, "The quick fox jumps", "fox", "dog")
    assert app._cur_undo_fn is not None
    app._cur_undo_fn()
    text = t._doc[0].get_text()
    assert "fox" in text and "dog" not in text


# ── Annotate ─────────────────────────────────────────────────────────────────

def _annot_pdf(path, note=False, rotate=0):
    doc = fitz.open()
    p = doc.new_page()
    p.insert_text((72, 100), "TOPSECRET", fontsize=14)
    if note:
        p.add_text_annot((400, 400), "ORIGINAL author comment")
    if rotate:
        p.set_rotation(rotate)
    doc.save(str(path))
    doc.close()


def test_annotate_rect_fill_is_rgb(app, dialogs, tmp_path):
    _annot_pdf(tmp_path / "a.pdf")
    t = tool(app, "AnnotateTool")
    _open(t, dialogs, tmp_path / "a.pdf")
    t._set_tool("rect")
    t._color = (1.0, 1.0, 0.0)
    _drag(t, 100, 300, 250, 400)
    page = t._doc[0]
    fill = list(page.annots())[-1].colors["fill"]
    assert len(fill) == 3 and all(abs(a - b) < 0.01 for a, b in zip(fill, (1, 1, 0), strict=True)), fill


def test_annotate_failed_add_then_undo_keeps_existing(app, dialogs, tmp_path):
    _annot_pdf(tmp_path / "a.pdf", note=True)
    t = tool(app, "AnnotateTool")
    _open(t, dialogs, tmp_path / "a.pdf")
    t._set_tool("highlight")
    _drag(t, 100, 300, 250, 300)     # zero height: add_highlight_annot fails
    t._undo()
    contents = [a.info["content"] for a in t._doc[0].annots()]
    assert "ORIGINAL author comment" in contents, contents


def test_annotate_click_selects_and_remove_deletes(app, dialogs, tmp_path):
    _annot_pdf(tmp_path / "a.pdf", note=True)
    t = tool(app, "AnnotateTool")
    _open(t, dialogs, tmp_path / "a.pdf")
    page = t._doc[0]
    r = _screen_rect(page, next(page.annots()).rect, t._zoom)
    cx, cy = (r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2
    t._press(_ev(cx, cy))
    t._release(_ev(cx, cy))
    t._remove_selected()
    assert list(t._doc[0].annots()) == []


def test_annotate_on_rotated_page_lands_under_drag(app, dialogs, tmp_path):
    _annot_pdf(tmp_path / "a.pdf", rotate=90)
    t = tool(app, "AnnotateTool")
    _open(t, dialogs, tmp_path / "a.pdf")
    page = t._doc[0]
    word = page.search_for("TOPSECRET")[0]
    x0, y0, x1, y1 = _screen_rect(page, word, t._zoom)
    t._set_tool("rect")
    _drag(t, x0, y0, x1, y1)
    page = t._doc[0]
    rect = list(page.annots())[-1].rect
    assert rect.intersects(word), (rect, word)
