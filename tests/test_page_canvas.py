"""The page viewer shared by Annotate, Edit Text, Find & Replace and Redact (RS-07)."""
import pymupdf as fitz
import pytest

from conftest import tool

CANVAS_TOOLS = ["AnnotateTool", "EditTextTool", "FindReplaceTool", "RedactTool"]


def _two_page_pdf(path, words=("Alpha", "Beta")):
    doc = fitz.open()
    for w in words:
        p = doc.new_page()
        p.insert_text((72, 100), f"{w} first block", fontsize=14)
        p.insert_text((72, 300), f"{w} second block", fontsize=14)
    doc.save(str(path))
    doc.close()
    return path


def _rotated_cropped_pdf(path):
    doc = fitz.open()
    p = doc.new_page()
    p.insert_text((150, 300), "Marker", fontsize=20)
    p.set_cropbox(fitz.Rect(40, 120, 500, 700))
    p.set_rotation(90)
    doc.save(str(path))
    doc.close()
    return path


def _open(t, dialogs, path):
    dialogs.open(str(path))
    t._open()
    assert t._doc is not None


def test_edit_text_forgets_the_selected_block_when_another_file_is_opened(
        app, dialogs, tmp_path):
    t = tool(app, "EditTextTool")
    _open(t, dialogs, _two_page_pdf(tmp_path / "a.pdf", ("Alpha",)))
    t._select_block(t._blocks[0]["bi"])
    _open(t, dialogs, _two_page_pdf(tmp_path / "b.pdf", ("Beta",)))
    t._apply_edit()
    text = t._doc[0].get_text()
    assert "Alpha" not in text, "file A's text was written into file B"
    assert "Beta first block" in text
    assert t._edit_box.get("1.0", "end-1c") == ""


@pytest.mark.parametrize("name", CANVAS_TOOLS)
def test_every_canvas_tool_maps_page_and_screen_the_same_way(app, dialogs, tmp_path, name):
    t = tool(app, name)
    _open(t, dialogs, _rotated_cropped_pdf(tmp_path / f"{name}.pdf"))
    page = t._doc[0]
    word = page.search_for("Marker")[0]
    expected = word * page.rotation_matrix * fitz.Matrix(t._zoom, t._zoom)
    # page -> screen
    assert fitz.Rect(t._page_to_screen(word)) == expected
    # screen -> page, back again
    back = t._screen_to_page(fitz.Point(expected.x0, expected.y0))
    assert abs(back.x - word.tl.x) < 1e-6 or abs(back.x - word.bl.x) < 1e-6
    corners = {(round(p.x, 4), round(p.y, 4)) for p in (word.tl, word.tr, word.bl, word.br)}
    assert (round(back.x, 4), round(back.y, 4)) in corners


@pytest.mark.parametrize("name", CANVAS_TOOLS)
def test_every_canvas_tool_shows_the_page_and_stays_on_it(app, dialogs, tmp_path, name):
    t = tool(app, name)
    _open(t, dialogs, _two_page_pdf(tmp_path / f"{name}.pdf"))
    assert t._pg == 0
    t._nav(-1)
    assert t._pg == 0
    t._nav(1)
    assert t._pg == 1
    t._nav(1)
    assert t._pg == 1
    images = [i for i in t._canvas.find_all() if t._canvas.type(i) == "image"]
    assert len(images) == 1
    x0, y0, x1, y1 = (float(v) for v in str(t._canvas.cget("scrollregion")).split())
    import math   # the pixmap rounds a fractional size up
    assert (x1, y1) == (math.ceil(t._doc[1].rect.width * t._zoom),
                        math.ceil(t._doc[1].rect.height * t._zoom))
