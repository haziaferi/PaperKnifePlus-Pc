"""The Qt Edit Text page: click a paragraph, edit it in the panel, save.

Ports the checks of the CTk tool's tests (tests/test_content.py Edit Text,
tests/test_page_canvas.py, tests/test_review.py RC-01/RC-07/RC-02)."""
import io

import pymupdf as fitz
import pytest
from PIL import Image

from qt_harness import make_pdf, pump, wait_job

BG_RGB = (230, 230, 120)


def _bg_image_png():
    buf = io.BytesIO()
    Image.new("RGB", (60, 80), BG_RGB).save(buf, "PNG")
    return buf.getvalue()


def _edit_pdf(path):
    doc = fitz.open()
    p = doc.new_page()
    p.insert_image(p.rect, stream=_bg_image_png())
    p.insert_text((72, 100), "Hello world", fontsize=14)
    p.insert_text((72, 300), "Other block", fontsize=14)
    doc.save(str(path))
    doc.close()
    return str(path)


def _hello_pdf(path, rot=0, crop=None):
    doc = fitz.open()
    page = doc.new_page(width=400, height=600)
    page.insert_text((120, 200), "Hello there", fontsize=14)
    if crop:
        page.set_cropbox(fitz.Rect(crop))
    if rot:
        page.set_rotation(rot)
    doc.save(str(path))
    doc.close()
    return str(path)


def _two_page_pdf(path, words):
    doc = fitz.open()
    for w in words:
        p = doc.new_page()
        p.insert_text((72, 100), f"{w} first block", fontsize=14)
    doc.new_page().insert_text((72, 100), "Second page", fontsize=14)
    doc.save(str(path))
    doc.close()
    return str(path)


def _words(page, text):
    return [fitz.Rect(w[:4]) for w in page.get_text("words") if w[4] == text]


def _pixel(page, x, y):
    pix = page.get_pixmap(clip=fitz.Rect(x, y, x + 1, y + 1), alpha=False)
    return tuple(pix.pixel(0, 0))


def _open(window, src):
    assert window.open_tool("EditTextTool", str(src))
    pump(0.1)
    page = window.current_page()
    assert page._doc is not None
    return page


def _select_hello(page):
    item = next(it for it in page._blocks if it["block"]["bbox"][1] < 150)
    page.select_block(item["bi"])
    return fitz.Rect(item["block"]["bbox"])


def _edit(page, new_text):
    page.select_block(page._blocks[0]["bi"])
    page.edit_box.setPlainText(new_text)
    page.apply_edit()


def _click(page, x, y):
    """A mouse click at the page point (x, y), as the view reports it."""
    r = page.view.page_to_scene(fitz.Rect(x, y, x, y))
    page._mouse_down((r.x(), r.y()))
    page._mouse_up((r.x(), r.y()))


def test_page_builds_with_the_hint_and_no_editor(window):
    assert window.open_tool("EditTextTool")
    page = window.current_page()
    assert page.title_label.text() == "Edit Text"
    assert page.edit_box is None and page.apply_btn is None


def test_save_without_a_document_warns(window, dialogs):
    assert window.open_tool("EditTextTool")
    window.current_page().save()
    assert ("warning", "Save", "Open a PDF first.") in dialogs.msgs


def test_click_selects_the_block_and_shows_its_text(window, tmp_path):
    page = _open(window, _edit_pdf(tmp_path / "e.pdf"))
    _click(page, 100, 95)
    assert page.edit_box is not None
    assert page.edit_box.toPlainText() == "Hello world"
    pump(0.05)
    assert page.apply_btn.isVisibleTo(page)


def test_click_outside_any_block_selects_nothing(window, tmp_path):
    page = _open(window, _edit_pdf(tmp_path / "e.pdf"))
    _click(page, 500, 700)
    assert page._sel_bi is None and page.edit_box is None


def test_apply_unchanged_keeps_text(window, tmp_path):
    page = _open(window, _edit_pdf(tmp_path / "e.pdf"))
    _select_hello(page)
    page.apply_edit()
    text = page._doc[0].get_text()
    assert "Hello world" in text and "Other block" in text


def test_apply_replaces_only_that_text_and_keeps_image(window, tmp_path):
    page = _open(window, _edit_pdf(tmp_path / "e.pdf"))
    bbox = _select_hello(page)
    page.edit_box.setPlainText("Hi")
    page.apply_edit()
    pg = page._doc[0]
    text = pg.get_text()
    assert "Hi" in text and "Hello" not in text and "Other block" in text
    # right end of the old span: "Hi" does not reach it, so the background must show
    px = _pixel(pg, bbox.x1 - 3, (bbox.y0 + bbox.y1) / 2)
    assert max(abs(a - b) for a, b in zip(px, BG_RGB, strict=True)) < 10, px
    assert window.status_label.text() == "✓  Edit applied — use Save to write to disk"
    assert page._sel_bi is None and page.edit_box is None


def test_multi_line_edit_keeps_its_line_breaks(window, tmp_path):
    page = _open(window, _edit_pdf(tmp_path / "e.pdf"))
    _select_hello(page)
    page.edit_box.setPlainText("First line\nSecond line")
    page.apply_edit()
    first = _words(page._doc[0], "First")[0]
    second = _words(page._doc[0], "Second")[0]
    assert second.y0 > first.y0 + 10 and second.x0 == pytest.approx(first.x0, abs=1)


def test_undo_restores_text_and_keeps_image(window, tmp_path):
    page = _open(window, _edit_pdf(tmp_path / "e.pdf"))
    _select_hello(page)
    page.edit_box.setPlainText("Changed text")
    page.apply_edit()
    window.page_hook("undo")
    pg = page._doc[0]
    assert "Hello world" in pg.get_text() and "Changed" not in pg.get_text()
    px = _pixel(pg, 300, 600)
    assert max(abs(a - b) for a, b in zip(px, BG_RGB, strict=True)) < 10, px
    assert window.status_label.text() == "✓  Undone: Edit Text"
    assert not page.is_dirty()                      # back at the file as opened


def test_selection_is_forgotten_when_another_file_is_opened(window, tmp_path):
    page = _open(window, _two_page_pdf(tmp_path / "a.pdf", ("Alpha",)))
    page.select_block(page._blocks[0]["bi"])
    assert page.accept_drop(_two_page_pdf(tmp_path / "b.pdf", ("Beta",)))
    page.apply_edit()
    text = page._doc[0].get_text()
    assert "Alpha" not in text, "file A's text was written into file B"
    assert "Beta first block" in text
    assert page.edit_box is None


def test_selection_is_forgotten_on_another_page(window, tmp_path):
    page = _open(window, _two_page_pdf(tmp_path / "a.pdf", ("Alpha",)))
    page.select_block(page._blocks[0]["bi"])
    page.go(1)
    assert page._sel_bi is None and page.edit_box is None
    page.apply_edit()
    assert page._doc[1].get_text().strip() == "Second page"


def test_click_maps_to_the_block_on_a_rotated_page(window, tmp_path):
    page = _open(window, _hello_pdf(tmp_path / "in.pdf", rot=90))
    word = page._doc[0].search_for("Hello")[0]
    _click(page, (word.x0 + word.x1) / 2, (word.y0 + word.y1) / 2)
    assert page.edit_box is not None and page.edit_box.toPlainText() == "Hello there"


def test_edit_on_rotated_page_applies_and_undoes(window, dialogs, tmp_path):
    page = _open(window, _hello_pdf(tmp_path / "in.pdf", rot=90))
    assert page._blocks, "no text blocks shown on the rotated page"
    _edit(page, "Howdy there")
    assert "Howdy" in page._doc[0].get_text()
    page.undo()
    text = page._doc[0].get_text()
    assert "Hello there" in text and "Howdy" not in text
    assert not dialogs.errors(), dialogs.errors()


def test_failed_edit_puts_the_original_text_back(window, dialogs, tmp_path, monkeypatch):
    page = _open(window, _hello_pdf(tmp_path / "in.pdf"))

    def boom(*a, **k):
        raise RuntimeError("writer failed")
    monkeypatch.setattr(fitz.TextWriter, "write_text", boom)
    _edit(page, "Howdy there")
    assert "Hello there" in page._doc[0].get_text()
    assert any(m[1] == "Edit Text" and "The edit could not be applied:\nwriter failed" in m[2]
               for m in dialogs.errors()), dialogs.msgs


def test_edit_on_cropped_page_keeps_the_baseline(window, tmp_path):
    src = _hello_pdf(tmp_path / "in.pdf", crop=(50, 50, 380, 560))
    with fitz.open(src) as d:
        before = _words(d[0], "Hello")[0]
    page = _open(window, src)
    _edit(page, "Howdy there")
    after = _words(page._doc[0], "Howdy")
    assert after and abs(after[0].y1 - before.y1) < 2, (before, after)


def test_letters_the_font_cannot_draw_fall_back_with_a_warning(window, tmp_path, monkeypatch):
    from paperknife.core import reflow
    page = _open(window, _edit_pdf(tmp_path / "e.pdf"))
    monkeypatch.setattr(reflow.FontBook, "own", lambda self, page, name: (None, False))
    _select_hello(page)
    page.edit_box.setPlainText("Hi")
    page.apply_edit()
    assert "Hi" in page._doc[0].get_text()
    assert window.status_role == "warning"
    assert window.status_label.text().startswith(
        "⚠  Edit applied — some letters are not in the font '")


def test_save_writes_the_edited_text(window, dialogs, tmp_path):
    page = _open(window, _edit_pdf(tmp_path / "e.pdf"))
    _select_hello(page)
    page.edit_box.setPlainText("Saved edit")
    page.apply_edit()
    out = tmp_path / "out.pdf"
    dialogs.save(out)
    window.save_as()
    wait_job(window)
    with fitz.open(out) as d:
        text = d[0].get_text()
    assert "Saved edit" in text and "Hello" not in text and "Other block" in text
    assert window.status_label.text() == "✓  Saved → out.pdf"
    assert not [m for m in dialogs.msgs if m[0] == "info"]


def test_save_over_the_open_input_keeps_the_document(window, dialogs, tmp_path):
    src = make_pdf(tmp_path / "in.pdf", pages=2)
    page = _open(window, src)
    _edit(page, "Changed")
    dialogs.save(src)
    page.save()
    wait_job(window)
    assert not dialogs.errors(), dialogs.errors()
    assert page._doc is not None and not page._doc.is_closed and len(page._doc) == 2, \
        "the page lost its document after saving"
    with fitz.open(src) as d:
        assert len(d) == 2 and "Changed" in d[0].get_text()


def test_cancelled_save_writes_nothing_and_keeps_the_document(window, dialogs, tmp_path):
    page = _open(window, _edit_pdf(tmp_path / "e.pdf"))
    doc = page._doc
    window.save_as()                          # no path queued: the dialog is cancelled
    pump(0.1)
    assert window._current_job is None or not window._current_job.is_running
    assert page._doc is doc and not doc.is_closed
    assert sorted(p.name for p in tmp_path.iterdir()) == ["e.pdf"]


def test_drop_takes_pdfs_only(window, tmp_path):
    page = _open(window, _edit_pdf(tmp_path / "e.pdf"))
    other = tmp_path / "x.txt"
    other.write_text("x", encoding="utf-8")
    assert page.accept_drop(str(other)) is False
    second = make_pdf(tmp_path / "second.pdf", pages=4)
    assert page.accept_drop(second) is True
    assert len(page._doc) == 4 and page.subtitle_label.text() == "second.pdf"


@pytest.mark.parametrize("target", ["home", "AnnotateTool"])
def test_leaving_the_tool_keeps_the_document(window, tmp_path, target):
    page = _open(window, _edit_pdf(tmp_path / "e.pdf"))
    doc = page._doc
    if target == "home":
        window.show_page("home")
    else:
        assert window.open_tool(target)
    assert not doc.is_closed and window.document.doc is doc


# ── reflow (owner, 2026-10-11) ───────────────────────────────────────────────
def _panel_title(page):
    from PySide6.QtWidgets import QLabel
    return page._panel_box.findChild(QLabel, "panelTitle").text()


def _para_pdf(path, picture=False):
    doc = fitz.open()
    page = doc.new_page()
    words = ("alpha beta gamma delta epsilon zeta theta iota kappa lambda " * 5).split()
    page.insert_textbox(fitz.Rect(72, 72, 380, 300), " ".join(words), fontsize=11, fontname="tiro")
    page.insert_textbox(fitz.Rect(72, 310, 380, 420), "The next paragraph stays below.",
                        fontsize=11, fontname="tiro")
    if picture:
        pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 20, 20), False)
        pix.clear_with(100)
        page.insert_image(fitz.Rect(72, 430, 200, 480), pixmap=pix)
    doc.save(str(path))
    doc.close()
    return str(path)


def test_a_click_selects_the_whole_paragraph_as_one_text(window, tmp_path):
    page = _open(window, _para_pdf(tmp_path / "p.pdf"))
    assert page.unit_box.currentText() == "Paragraph"
    _click(page, 100, 80)
    assert page.edit_box is not None
    text = page.edit_box.toPlainText()
    assert "\n" not in text and text.startswith("alpha beta") and text.endswith("lambda")
    assert _panel_title(page) == "Selected paragraph"


def test_line_choice_selects_one_line(window, tmp_path):
    page = _open(window, _para_pdf(tmp_path / "p.pdf"))
    page.unit_box.setCurrentText("Line")
    pump(0.05)
    _click(page, 100, 80)
    assert _panel_title(page) == "Selected line"
    assert len(page.edit_box.toPlainText()) < 70


def test_a_longer_edit_moves_the_next_paragraph_down(window, tmp_path):
    page = _open(window, _para_pdf(tmp_path / "p.pdf"))
    before = _words(page._doc[0], "next")[0]
    _click(page, 100, 80)
    page.edit_box.setPlainText(page.edit_box.toPlainText() + " and many more words " * 6)
    page.apply_edit()
    after = _words(page._doc[0], "next")[0]
    assert after.y0 > before.y0 + 5
    assert window.status_label.text() == "✓  Edit applied — use Save to write to disk"


def test_an_edit_that_cannot_move_its_text_is_refused_and_says_why(window, dialogs, tmp_path):
    page = _open(window, _para_pdf(tmp_path / "p.pdf", picture=True))
    _click(page, 100, 80)
    old = page.edit_box.toPlainText()
    page.edit_box.setPlainText(old + " and many more words " * 12)
    page.apply_edit()
    assert ("warning", "Edit Text", "The edit was not applied: a picture is in the way.") in dialogs.msgs
    assert "many more" not in page._doc[0].get_text()
    assert not page._undo_stack
