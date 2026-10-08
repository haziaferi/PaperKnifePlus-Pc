"""The Qt PDF Tools page: repair a damaged file."""
import pymupdf as fitz

from qt_harness import make_pdf, pump, wait_job


def _page(window):
    assert window.open_tool("PdfToolsTool")
    pump(0.05)
    return window.current_page()


def _spy_open(window):
    opened = []
    real = window.open_pdf_safe

    def spy(path):
        doc = real(path)
        opened.append(doc)
        return doc
    window.open_pdf_safe = spy
    return opened


def _truncated(tmp_path):
    good = make_pdf(tmp_path / "good.pdf", pages=2)
    data = open(good, "rb").read()
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(data[: data.rfind(b"xref")])
    return str(bad)


def test_the_page_builds_and_offers_only_repair(window):
    from PySide6.QtWidgets import QLabel
    from qfluentwidgets import RadioButton
    page = _page(window)
    assert type(page).__name__ == "PdfToolsPage"
    assert page.title_label.text() == "PDF Tools"
    assert page.findChildren(RadioButton) == [], "a single operation needs no radio button"
    texts = [lbl.text() for lbl in page.findChildren(QLabel)]
    assert any(t.startswith("Repair") for t in texts), texts
    assert not any("Linear" in t or "PDF/A" in t for t in texts), texts


def test_without_a_file_it_asks_for_one(window, dialogs):
    page = _page(window)
    page.run()
    assert dialogs.msgs[-1] == ("warning", "PDF Tools", "Select a PDF first.")


def test_pdftools_default_run_saves_a_clean_copy(window, dialogs, tmp_path):
    page = _page(window)
    page.file.set_path(make_pdf(tmp_path / "in.pdf"))
    out = tmp_path / "out.pdf"
    dialogs.save(out)
    page.run()
    wait_job(window)
    assert [m for m in dialogs.msgs if m[0] != "info"] == [], dialogs.msgs
    assert dialogs.msgs[-1] == ("info", "Done", f"No damage found; cleaned copy saved:\n{out}")
    assert window.status_text() == "✓  No damage found; cleaned copy saved → out.pdf"
    with fitz.open(out) as doc:
        assert doc.page_count == 3 and doc[2].get_text().strip() == "Page 3"


def test_pdftools_repair_recovers_a_truncated_file(window, dialogs, tmp_path):
    page = _page(window)
    page.file.set_path(_truncated(tmp_path))
    out = tmp_path / "out.pdf"
    dialogs.save(out)
    page.run()
    wait_job(window)
    assert not dialogs.errors(), dialogs.errors()
    assert dialogs.msgs[-1] == ("info", "Done", f"Repaired PDF saved:\n{out}")
    assert window.status_text() == "✓  Repaired PDF saved → out.pdf"
    with fitz.open(out) as doc:
        assert not doc.is_repaired and doc.page_count == 2
        assert doc[1].get_text().strip() == "Page 2"


def test_a_dropped_pdf_fills_the_file_card_and_others_are_refused(window, tmp_path):
    page = _page(window)
    src = make_pdf(tmp_path / "in.pdf")
    other = tmp_path / "x.txt"
    other.write_text("x", encoding="utf-8")
    assert page.accept_drop(str(other)) is False
    assert page.accept_drop(src) is True and page.file.path() == src


def test_cancelling_the_save_dialog_closes_the_document(window, dialogs, tmp_path):
    page = _page(window)
    page.file.set_path(make_pdf(tmp_path / "in.pdf"))
    opened = _spy_open(window)
    page.run()                     # no save path queued: the dialog returns ""
    assert opened and opened[0].is_closed
    assert window._current_job is None


def test_leaving_the_tool_leaves_no_document_open(window, dialogs, tmp_path):
    page = _page(window)
    page.file.set_path(make_pdf(tmp_path / "in.pdf"))
    opened = _spy_open(window)
    out = tmp_path / "out.pdf"
    dialogs.save(out)
    page.run()
    window.show_page("CompressTool")
    wait_job(window)
    assert opened and opened[0].is_closed
    with fitz.open(out) as doc:
        assert doc.page_count == 3
