"""The Qt Image → PDF page: a collection of images into one PDF (group D)."""
import threading

import pymupdf as fitz
from PIL import Image

from qt_harness import make_pdf, pump, wait_job


def _page(window):
    assert window.open_tool("Img2PdfTool")
    pump(0.05)
    return window.current_page()


def _image(path, size, colour, mode="RGB"):
    Image.new(mode, size, colour).save(path)
    return str(path)


def _transparent_png(path):
    im = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
    for x in range(80, 120):
        for y in range(80, 120):
            im.putpixel((x, y), (255, 0, 0, 255))
    im.save(path)
    return str(path)


def test_the_page_builds_as_a_collection_without_settings(window):
    from paperknife.qt.pages import CollectionPage
    page = _page(window)
    assert isinstance(page, CollectionPage)
    assert page.settings is None and page.add_btn.text() == "Add Images"
    assert page.paths() == [] and page.empty_label.isVisibleTo(page)


def test_without_images_it_warns(window, dialogs):
    page = _page(window)
    page.run()
    assert dialogs.msgs[-1] == ("warning", "Convert", "Add images first.")


def test_images_become_one_page_each_in_list_order(window, dialogs, tmp_path):
    page = _page(window)
    a = _image(tmp_path / "a.png", (300, 200), (255, 0, 0))
    b = _image(tmp_path / "b.jpg", (120, 400), (0, 0, 255))
    c = _image(tmp_path / "c.bmp", (50, 60), (0, 255, 0))
    dialogs.open([a, b, c])
    page.open()
    assert page.paths() == [a, b, c]
    page.select(0)
    page.move(1)                        # b, a, c
    out = tmp_path / "out.pdf"
    dialogs.save(out)
    page.run()
    wait_job(window)
    assert not dialogs.errors(), dialogs.errors()
    with fitz.open(out) as doc:
        assert len(doc) == 3
        assert [(round(p.rect.width), round(p.rect.height)) for p in doc] == \
            [(120, 400), (300, 200), (50, 60)]
        assert all(p.get_images() for p in doc)
        r, g, bl = doc[1].get_pixmap(alpha=False).pixel(10, 10)
        assert r > 200 and g < 60 and bl < 60          # the red one is second
    assert dialogs.msgs[-1] == ("info", "Done", f"PDF saved:\n{out}")
    assert window.status_text() == "✓  Converted 3 image(s) → out.pdf"
    assert window.status_role == "success"


def test_transparent_png_gets_white_background(window, dialogs, tmp_path):
    page = _page(window)
    page.add_paths([_transparent_png(tmp_path / "t.png")])
    out = tmp_path / "t.pdf"
    dialogs.save(out)
    page.run()
    wait_job(window)
    assert not dialogs.errors(), dialogs.errors()
    with fitz.open(out) as doc:
        assert doc[0].get_pixmap(alpha=False).pixel(5, 5) == (255, 255, 255)


def test_a_dropped_image_is_taken_and_other_files_refused(window, tmp_path):
    page = _page(window)
    img = _image(tmp_path / "x.webp", (40, 40), (10, 20, 30))
    txt = tmp_path / "x.txt"
    txt.write_text("x", encoding="utf-8")
    pdf = make_pdf(tmp_path / "x.pdf")
    assert page.accept_drop(str(txt)) is False
    assert page.accept_drop(pdf) is False
    assert page.accept_drop(img) is True and page.paths() == [img]


def test_cancelling_the_save_dialog_writes_nothing(window, dialogs, tmp_path):
    page = _page(window)
    page.add_paths([_image(tmp_path / "a.png", (30, 30), (0, 0, 0))])
    page.run()                          # no save path queued: the dialog returns ""
    assert window._current_job is None or not window._current_job.is_running
    assert not list(tmp_path.glob("*.pdf")) and not dialogs.msgs


def test_a_stopped_conversion_leaves_no_file(tmp_path):
    from paperknife.core.convert import images_to_pdf
    stop = threading.Event()
    stop.set()
    out = tmp_path / "o.pdf"
    assert images_to_pdf([_image(tmp_path / "a.png", (30, 30), (0, 0, 0))],
                         str(out), stop) is False
    assert not out.exists() and not list(tmp_path.glob("*.part"))


def test_leaving_the_tool_holds_no_document(window, dialogs, tmp_path):
    import os
    page = _page(window)
    a = _image(tmp_path / "a.png", (30, 30), (0, 0, 0))
    b = _image(tmp_path / "b.jpg", (40, 20), (255, 0, 0))
    page.add_paths([a, b])
    out = tmp_path / "out.pdf"
    dialogs.save(out)
    page.run()
    wait_job(window)
    assert not dialogs.errors(), dialogs.errors()
    with fitz.open(out) as doc:
        assert len(doc) == 2
    window.show_page("home")
    pump(0.05)
    # Windows refuses to rename or delete a file a handle still holds open: no
    # input image and not the output may be held once the page is left.
    os.replace(a, tmp_path / "a-moved.png")
    os.replace(b, tmp_path / "b-moved.jpg")
    out.unlink()
    assert _page(window) is page and len(page.paths()) == 2
