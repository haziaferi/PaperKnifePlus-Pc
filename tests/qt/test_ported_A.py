"""Phase 8, map A: CTk UI tests whose behaviour no Qt test checked yet, ported to
the Qt pages before the CTk app (and its tests) is deleted.  Each test names the
CTk test it replaces; the map is _qt-2026-10-09/phase8/map-A.md."""
import html as _html
import math
from pathlib import Path

import pymupdf as fitz
import pytest
from qt_harness import pump, wait_job

CANVAS_TOOLS = ["AnnotateTool", "EditTextTool", "FindReplaceTool", "RedactTool"]


def _open(window, name, path):
    assert window.open_tool(name, str(path))
    pump(0.1)
    page = window.current_page()
    assert page._doc is not None
    return page


def _scene(page, x, y):
    r = page.view.page_to_scene(fitz.Rect(x, y, x, y))
    return r.x(), r.y()


def _drag_scene(page, p0, p1):
    page._press(p0)
    page._drag(p1)
    page._mouse_up(p1)


def _drag(page, p0, p1):
    _drag_scene(page, _scene(page, *p0), _scene(page, *p1))


def _drawn(page, rect):
    """Where *rect* (page space) is drawn on the shown pixmap: rotate as the page
    is shown, then zoom, worked out apart from the view's own mapping (the CTk
    tests' _screen_rect), so a mouse drag over what the user sees is simulated."""
    pg = page._doc[page._pg]
    return fitz.Rect(rect) * pg.rotation_matrix * fitz.Matrix(page.view.zoom, page.view.zoom)


# ── Annotate (tests/test_content.py) ─────────────────────────────────────────
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
    return str(path)


def test_annotate_rect_fill_is_rgb(window, tmp_path):
    # test_content.py::test_annotate_rect_fill_is_rgb
    page = _open(window, "AnnotateTool", _annot_pdf(tmp_path / "a.pdf"))
    page.set_kind("rect")
    page.color = (1.0, 1.0, 0.0)
    _drag(page, (100, 300), (250, 400))
    pg = page._doc[0]
    fill = list(pg.annots())[-1].colors["fill"]
    assert len(fill) == 3 and all(abs(a - b) < 0.01
                                  for a, b in zip(fill, (1, 1, 0), strict=True)), fill


def test_annotate_failed_add_then_undo_keeps_existing(window, tmp_path):
    # test_content.py::test_annotate_failed_add_then_undo_keeps_existing
    page = _open(window, "AnnotateTool", _annot_pdf(tmp_path / "a.pdf", note=True))
    page.set_kind("highlight")
    _drag(page, (100, 300), (250, 300))     # zero height: add_highlight_annot fails
    assert window.status_role == "danger"
    page.undo()
    pg = page._doc[0]
    contents = [a.info["content"] for a in pg.annots()]
    assert "ORIGINAL author comment" in contents, contents


def test_annotate_click_selects_an_existing_note_and_remove_deletes_it(window, tmp_path):
    # test_content.py::test_annotate_click_selects_and_remove_deletes
    page = _open(window, "AnnotateTool", _annot_pdf(tmp_path / "a.pdf", note=True))
    pg = page._doc[0]
    r = next(pg.annots()).rect
    xy = _scene(page, (r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2)
    page._press(xy)
    page._mouse_up(xy)
    assert page.sel_xref is not None
    page.delete()
    pg = page._doc[0]
    assert list(pg.annots()) == []


@pytest.mark.parametrize("rotate", [0, 90])
def test_annotate_on_rotated_page_lands_under_drag(window, tmp_path, rotate):
    # test_content.py::test_annotate_on_rotated_page_lands_under_drag
    page = _open(window, "AnnotateTool", _annot_pdf(tmp_path / "a.pdf", rotate=rotate))
    pg = page._doc[0]
    word = pg.search_for("TOPSECRET")[0]
    x0, y0, x1, y1 = _drawn(page, word)
    page.set_kind("rect")
    _drag_scene(page, (x0, y0), (x1, y1))
    pg = page._doc[0]
    rect = list(pg.annots())[-1].rect
    assert rect.intersects(word), (rect, word)


# ── Redact on a rotated page (tests/test_content.py) ─────────────────────────
@pytest.mark.parametrize("rotate", [0, 90])
def test_redact_box_drawn_over_the_word_on_a_rotated_page_removes_it(window, dialogs, tmp_path,
                                                                      rotate):
    # test_content.py::test_redact_box_on_rotated_page_covers_drawn_content
    src = tmp_path / "rot.pdf"
    doc = fitz.open()
    p = doc.new_page()
    p.insert_text((72, 100), "TOPSECRET", fontsize=14)
    p.set_rotation(rotate)
    doc.save(str(src))
    doc.close()
    page = _open(window, "RedactTool", src)
    word = page._doc[0].search_for("TOPSECRET")[0]
    x0, y0, x1, y1 = _drawn(page, word)
    _drag_scene(page, (x0 - 2, y0 - 2), (x1 + 2, y1 + 2))
    assert len(page._pending) == 1
    page.set_fill("Black")
    dialogs.asks.append(True)
    dialogs.save(tmp_path / "out.pdf")
    page.save()
    wait_job(window)
    assert not dialogs.errors(), dialogs.errors()
    assert "TOPSECRET" not in page._doc[0].get_text()


# ── Find & Replace progress (tests/test_content.py) ──────────────────────────
def test_replace_moves_the_bar_through_its_second_half(window, dialogs, tmp_path, monkeypatch):
    # test_content.py::test_replace_moves_the_bar_through_its_second_half (review R2b-13)
    seen = []
    monkeypatch.setattr(window, "set_progress", seen.append)
    src = tmp_path / "fr.pdf"
    doc = fitz.open()
    doc.new_page().insert_text((72, 300), "The quick fox jumps", fontsize=14)
    doc.save(str(src))
    doc.close()
    page = _open(window, "FindReplaceTool", src)
    page.find_edit.setText("fox")
    page.repl_edit.setText("dog")
    dialogs.asks.append(True)
    page.replace_all()
    wait_job(window)
    pump(0.05)
    assert not dialogs.errors(), dialogs.errors()
    assert "dog" in page._doc[0].get_text()
    assert seen and abs(max(seen) - 1.0) < 1e-9, seen


# ── OCR with Tesseract off PATH (tests/test_convert.py) ──────────────────────
_WORDS = [("Smith", 95, 100, 300, 50, 16), ("don't", 92, 170, 300, 40, 16)]


@pytest.fixture
def tess_off_path(monkeypatch, tmp_path):
    """Tesseract in its default install folder but not on PATH, as the
    UB-Mannheim installer leaves it; the stubs answer only when pointed there."""
    import pytesseract
    exe = tmp_path / "pf" / "Tesseract-OCR" / "tesseract.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"")
    monkeypatch.setenv("ProgramFiles", str(tmp_path / "pf"))
    monkeypatch.setenv("ProgramFiles(x86)", str(tmp_path / "none"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "none"))
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    monkeypatch.setattr(pytesseract.pytesseract, "tesseract_cmd", "tesseract")

    def only_at_exe(fn):
        def wrapped(*a, **k):
            if pytesseract.pytesseract.tesseract_cmd != str(exe):
                raise pytesseract.TesseractNotFoundError()
            return fn(*a, **k)
        return wrapped

    def image_to_data(img, lang=None, output_type=None, **k):
        s = img.size[0] / 595.0
        d = {"text": [], "conf": [], "left": [], "top": [], "width": [], "height": []}
        for text, conf, x, y, w, h in _WORDS:
            for key, v in zip(("text", "conf", "left", "top", "width", "height"),
                              (text, conf, x * s, y * s, w * s, h * s), strict=True):
                d[key].append(round(v) if key not in ("text", "conf") else v)
        return d

    def image_to_pdf_or_hocr(img, lang=None, extension=None, **k):
        s = img.size[0] / 595.0
        spans = "".join(
            f"<span class='ocrx_word' title='bbox {round(x*s)} {round(y*s)} "
            f"{round((x+w)*s)} {round((y+h)*s)}; x_wconf {c}'>{_html.escape(t)}</span>"
            for t, c, x, y, w, h in _WORDS)
        return f"<html><body>{spans}</body></html>".encode()

    monkeypatch.setattr(pytesseract, "get_tesseract_version", only_at_exe(lambda: "5.0"))
    monkeypatch.setattr(pytesseract, "image_to_data", only_at_exe(image_to_data))
    monkeypatch.setattr(pytesseract, "image_to_pdf_or_hocr", only_at_exe(image_to_pdf_or_hocr))
    monkeypatch.setattr(pytesseract, "image_to_string",
                        only_at_exe(lambda img, lang=None, **k: "text"))
    return exe


def _source_pdf(path):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 120), "Original vector heading", fontsize=18)
    doc.save(str(path))
    doc.close()
    return str(path)


def test_ocr_finds_tesseract_in_its_default_folder_off_path(window, dialogs, tmp_path,
                                                            tess_off_path):
    # test_convert.py::test_ocr_finds_tesseract_in_its_default_folder_off_path
    assert window.open_tool("OCRTool")
    pump(0.05)
    page = window.current_page()
    out = tmp_path / "off_path.pdf"
    page.file.set_path(_source_pdf(tmp_path / "s.pdf"))
    dialogs.save(out)
    page.run()
    wait_job(window)
    assert not dialogs.errors(), dialogs.errors()
    with fitz.open(out) as doc:
        assert "Smith" in doc[0].get_text()


def test_batch_ocr_finds_tesseract_in_its_default_folder_off_path(window, dialogs, tmp_path,
                                                                  tess_off_path):
    # test_convert.py::test_batch_ocr_finds_tesseract_in_its_default_folder_off_path
    in_dir, out_dir = tmp_path / "in", tmp_path / "out"
    in_dir.mkdir()
    out_dir.mkdir()
    _source_pdf(in_dir / "a.pdf")
    assert window.open_tool("BatchTool")
    pump(0.05)
    page = window.current_page()
    page._set_in_dir(str(in_dir))
    page._set_out_dir(str(out_dir))
    page.op.setCurrentText("OCR")
    pump(0.02)
    page.controls["dpi"].setValue(150)
    page.run()
    wait_job(window)
    # A finished batch empties its list (owner, 2026-10-10): its status says how it went.
    assert window.status_text() == "✓  Batch done — 1 OK, 0 errors", window.status_text()
    with fitz.open(out_dir / "a_ocr.pdf") as doc:
        assert "Smith" in doc[0].get_text()


# ── every tool, both modes (tests/test_open_tools.py) ────────────────────────
def _registry_names():
    from paperknife.tool_registry import TOOL_REGISTRY
    return [t.name for t in TOOL_REGISTRY]


@pytest.mark.parametrize("name", _registry_names())
def test_tool_view_builds(window, dialogs, name):
    # test_open_tools.py::test_tool_view_builds
    from paperknife.qt.pages import QT_PAGES
    assert window.open_tool(name), name
    pump(0.02)
    page = window.current_page()
    assert type(page) is QT_PAGES[name] and page.isVisible()
    assert not dialogs.errors() and not dialogs.warnings(), dialogs.msgs


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_home_and_tools_both_modes(window, dialogs, mode):
    # test_open_tools.py::test_home_and_tools_both_modes
    from paperknife.qt import theme
    theme.apply_appearance(mode)
    try:
        for name in _registry_names():
            assert window.open_tool(name), name
            pump(0.01)
        assert window.show_page("home")
        pump(0.02)
        assert window.current_page().isVisible()
        assert not dialogs.errors(), dialogs.errors()
    finally:
        theme.apply_appearance("light")


# ── window icon (tests/test_packaging.py) ────────────────────────────────────
def test_window_uses_the_app_icon(window):
    # test_packaging.py::test_window_uses_the_app_icon_not_customtkinters
    from PySide6.QtGui import QIcon

    import paperknife
    ico = Path(paperknife.__file__).resolve().parents[1] / "assets" / "icon.ico"
    assert ico.is_file()
    given = window.windowIcon()
    assert not given.isNull(), "no icon was set"
    want = QIcon(str(ico))
    assert given.pixmap(32, 32).toImage() == want.pixmap(32, 32).toImage()


# ── the shared page view (tests/test_page_canvas.py) ─────────────────────────
def _rotated_cropped_pdf(path, rotate=90):
    doc = fitz.open()
    p = doc.new_page()
    p.insert_text((150, 300), "Marker", fontsize=20)
    p.set_cropbox(fitz.Rect(40, 120, 500, 700))
    p.set_rotation(rotate)
    doc.save(str(path))
    doc.close()
    return str(path)


def _two_page_pdf(path, words=("Alpha", "Beta")):
    doc = fitz.open()
    for w in words:
        p = doc.new_page()
        p.insert_text((72, 100), f"{w} first block", fontsize=14)
        p.insert_text((72, 300), f"{w} second block", fontsize=14)
    doc.save(str(path))
    doc.close()
    return str(path)


def _dark(img, x0, y0, x1, y1):
    x0, y0 = max(0, int(x0)), max(0, int(y0))
    x1, y1 = min(img.width(), math.ceil(x1)), min(img.height(), math.ceil(y1))
    return sum(1 for x in range(x0, x1) for y in range(y0, y1)
               if img.pixelColor(x, y).lightness() < 128)


@pytest.mark.parametrize("rotate", [0, 90])
@pytest.mark.parametrize("name", CANVAS_TOOLS)
def test_every_canvas_tool_maps_page_and_screen_the_same_way(window, tmp_path, name, rotate):
    # test_page_canvas.py::test_every_canvas_tool_maps_page_and_screen_the_same_way
    page = _open(window, name, _rotated_cropped_pdf(tmp_path / f"{name}.pdf", rotate))
    pg = page._doc[0]
    word = pg.search_for("Marker")[0]
    img = page.view._pix_item.pixmap().toImage()
    total = _dark(img, 0, 0, img.width(), img.height())
    drawn = _dark(img, *(_drawn(page, word) + (-1, -1, 1, 1)))
    assert total > 20 and drawn >= 0.95 * total, (drawn, total)    # the harness is right
    # page -> screen: the view puts the word where it is drawn.
    sr = page.view.page_to_scene(word)
    assert (sr.x(), sr.y(), sr.right(), sr.bottom()) == pytest.approx(tuple(_drawn(page, word)),
                                                                      abs=0.01)
    # screen -> page, back again: a corner of the drawn word is a corner of the word.
    d = _drawn(page, word)
    back = page.view.scene_to_page(d.x0, d.y0)
    corners = {(round(p.x, 3), round(p.y, 3)) for p in (word.tl, word.tr, word.bl, word.br)}
    assert (round(back.x, 3), round(back.y, 3)) in corners


@pytest.mark.parametrize("name", CANVAS_TOOLS)
def test_every_canvas_tool_shows_the_page_and_stays_on_it(window, tmp_path, name):
    # test_page_canvas.py::test_every_canvas_tool_shows_the_page_and_stays_on_it
    from PySide6.QtWidgets import QGraphicsPixmapItem
    page = _open(window, name, _two_page_pdf(tmp_path / f"{name}.pdf"))
    assert page._pg == 0
    page.go(-1)
    assert page._pg == 0
    page.go(1)
    assert page._pg == 1
    page.go(1)
    assert page._pg == 1
    images = [i for i in page.view.scene().items() if isinstance(i, QGraphicsPixmapItem)]
    assert len(images) == 1
    sr = page.view.scene().sceneRect()
    z = page.view.zoom
    assert (sr.width(), sr.height()) == (math.ceil(page._doc[1].rect.width * z),
                                         math.ceil(page._doc[1].rect.height * z))
