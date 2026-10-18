"""The Qt Header / Footer page: a single-file transform."""
from datetime import date

import pymupdf as fitz
import pytest

from qt_harness import make_pdf, pump, spy_open, wait_job


def _page(window):
    assert window.open_tool("HeaderFooterTool")
    pump(0.05)
    return window.current_page()


def _stamp(window, dialogs, page, src, out, rng=""):
    page.file.set_path(src)
    page.page_range.setText(rng)
    dialogs.save(out)
    page.run()
    wait_job(window)


def _spans(pg, needle):
    return [s for b in pg.get_text("dict")["blocks"] for ln in b.get("lines", [])
            for s in ln["spans"] if needle in s["text"]]


def test_the_page_builds_with_the_ctk_defaults(window):
    page = _page(window)
    assert page.title_label.text() == "Header / Footer"
    assert page.pos == "bottom-center"
    assert page.content.text() == "Page {page} of {total}"
    assert page.font.currentText() == "Helvetica" and page.font_name == "helv"
    assert (page.size.text(), page.margin.text(), page.page_range.text()) == ("10", "20", "")


def test_without_a_file_or_content_it_warns(window, dialogs, tmp_path):
    page = _page(window)
    page.run()
    assert dialogs.msgs[-1] == ("warning", "Header/Footer", "Select a PDF first.")
    page.file.set_path(make_pdf(tmp_path / "in.pdf"))
    page.content.setText("  ")
    page.run()
    assert dialogs.msgs[-1] == ("warning", "Header/Footer", "Enter content text.")
    assert not window._current_job


def test_end_to_end_stamps_every_page_and_reports(window, dialogs, tmp_path):
    page = _page(window)
    out = tmp_path / "out.pdf"
    _stamp(window, dialogs, page, make_pdf(tmp_path / "in.pdf", pages=3), out)
    assert not dialogs.errors(), dialogs.errors()
    with fitz.open(out) as doc:
        assert [f"Page {i} of 3" in p.get_text() for i, p in enumerate(doc, 1)] == [True] * 3
        r = doc[0].search_for("Page 1 of 3")[-1]
        w, h = doc[0].rect.width, doc[0].rect.height
        assert r.y1 > h - 40 and abs((r.x0 + r.x1) / 2 - w / 2) < 2      # bottom centre
    assert dialogs.msgs[-1] == ("info", "Done", f"PDF with header/footer saved:\n{out}")
    assert window.status_text() == "✓  Stamped 3 page(s) → out.pdf"


def test_headerfooter_accepts_capitalised_end(window, dialogs, tmp_path):
    page = _page(window)
    out = tmp_path / "out.pdf"
    _stamp(window, dialogs, page, make_pdf(tmp_path / "in.pdf", pages=4), out, "2-End")
    assert not dialogs.errors(), dialogs.errors()
    with fitz.open(out) as doc:
        assert ["of 4" in p.get_text() for p in doc] == [False, True, True, True]


def test_headerfooter_overlapping_ranges_stamp_once(window, dialogs, tmp_path):
    page = _page(window)
    out = tmp_path / "out.pdf"
    _stamp(window, dialogs, page, make_pdf(tmp_path / "in.pdf", pages=4), out, "1-3, 2")
    with fitz.open(out) as doc:
        assert doc[1].get_text().count("Page 2 of 4") == 1


def test_a_bad_range_is_an_error_and_closes_the_document(window, dialogs, tmp_path, monkeypatch):
    page = _page(window)
    opened = spy_open(window, monkeypatch)
    out = tmp_path / "out.pdf"
    _stamp(window, dialogs, page, make_pdf(tmp_path / "in.pdf", pages=2), out, "7-9")
    assert dialogs.errors() and dialogs.errors()[-1][1] == "Header/Footer"
    assert opened and opened[-1].is_closed and not out.exists()  # the job's copy (the page holds its own)


@pytest.mark.parametrize("field", ["size", "margin"])
def test_bad_size_or_margin_warns_instead_of_defaulting(window, dialogs, tmp_path, field):
    page = _page(window)
    getattr(page, field).setText("abc")
    out = tmp_path / "out.pdf"
    _stamp(window, dialogs, page, make_pdf(tmp_path / "in.pdf"), out)
    assert dialogs.msgs[-1] == ("warning", "Header/Footer",
                                "Enter numeric values for size and margin.")
    assert not out.exists()


@pytest.mark.parametrize("pos", ["top-left", "top-center", "top-right",
                                 "bottom-left", "bottom-center", "bottom-right"])
def test_each_position_puts_the_text_in_that_margin(window, dialogs, tmp_path, pos):
    page = _page(window)
    page.positions[pos].setChecked(True)
    assert page.pos == pos
    page.content.setText("MARK")
    out = tmp_path / "out.pdf"
    _stamp(window, dialogs, page, make_pdf(tmp_path / "in.pdf", pages=1), out)
    with fitz.open(out) as doc:
        pg = doc[0]
        r = pg.search_for("MARK")[0]
        w, h = pg.rect.width, pg.rect.height
    assert (r.y0 < 40) if pos.startswith("top") else (r.y1 > h - 40)
    if pos.endswith("left"):
        assert r.x0 == pytest.approx(20, abs=1)
    elif pos.endswith("right"):
        assert r.x1 == pytest.approx(w - 20, abs=2)
    else:
        assert abs((r.x0 + r.x1) / 2 - w / 2) < 2


def test_tokens_are_replaced(window, dialogs, tmp_path):
    page = _page(window)
    page.content.setText("P {page}/{total} {date}")
    out = tmp_path / "out.pdf"
    _stamp(window, dialogs, page, make_pdf(tmp_path / "in.pdf", pages=2), out)
    today = date.today().strftime("%Y-%m-%d")
    with fitz.open(out) as doc:
        assert f"P 2/2 {today}" in doc[1].get_text()


@pytest.mark.parametrize("label,font", [("Helvetica", "Helvetica"),
                                        ("Times Roman", "Times"), ("Courier", "Courier")])
def test_font_size_and_margin_shape_the_stamp(window, dialogs, tmp_path, label, font):
    page = _page(window)
    page.font.setCurrentText(label)
    page.size.setText("16")
    page.margin.setText("50")
    page.positions["top-left"].setChecked(True)
    page.content.setText("STYLE")
    out = tmp_path / "out.pdf"
    _stamp(window, dialogs, page, make_pdf(tmp_path / "in.pdf", pages=1), out)
    with fitz.open(out) as doc:
        span = _spans(doc[0], "STYLE")[0]
    assert font in span["font"] and round(span["size"]) == 16
    assert span["bbox"][0] == pytest.approx(50, abs=1)


def test_a_dropped_pdf_is_taken_and_others_are_refused(window, tmp_path):
    page = _page(window)
    src = make_pdf(tmp_path / "in.pdf")
    other = tmp_path / "x.txt"
    other.write_text("x", encoding="utf-8")
    assert page.accept_drop(str(other)) is False and page.file.path() == ""
    assert page.accept_drop(src) is True and page.file.path() == src


def test_cancelling_the_save_dialog_closes_the_document(window, dialogs, tmp_path, monkeypatch):
    page = _page(window)
    page.file.set_path(make_pdf(tmp_path / "in.pdf"))
    opened = spy_open(window, monkeypatch)
    page.run()
    assert opened and opened[0].is_closed
    assert not window._current_job


def test_leaving_the_tool_leaves_no_document_open(window, dialogs, tmp_path, monkeypatch):
    page = _page(window)
    opened = spy_open(window, monkeypatch)
    _stamp(window, dialogs, page, make_pdf(tmp_path / "in.pdf"), tmp_path / "o.pdf")
    assert window.show_page("home")
    assert opened and all(d.is_closed for d in opened)
