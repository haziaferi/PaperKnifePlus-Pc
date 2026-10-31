"""Step 5 (owner, 2026-10-23): Save v (its arrow: Save as…) and Print in the
document bar beside Open (option A); the card's action reads "Apply" on the tools
that change the open document from their settings (option E); Font size and
Opacity are typed in number boxes, not sliders."""
import pymupdf as fitz
import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from qt_harness import make_pdf, pump, wait_job


def _page(window, tool):
    assert window.open_tool(tool)
    pump(0.05)
    return window.current_page()


def test_save_and_print_show_only_with_a_document(window, tmp_path):
    page = _page(window, "WatermarkTool")
    bar = page.doc_bar
    assert not bar.save_control.isVisibleTo(page) and not bar.print_button.isVisibleTo(page)
    page.file.set_path(make_pdf(tmp_path / "in.pdf"))
    pump(0.05)
    assert bar.save_control.isVisibleTo(page) and bar.print_button.isVisibleTo(page)
    assert bar.save_control.text() == "Save" and bar.print_button.text() == "Print"
    assert [a.text() for a in bar.save_control.flyout.actions()] == ["Save as…"]
    # same row and height as Open
    assert bar.save_control.height() == bar.open_control.height()


def test_the_bar_s_save_writes_the_applied_watermark_over_the_file(window, dialogs, tmp_path):
    page = _page(window, "WatermarkTool")
    src = make_pdf(tmp_path / "in.pdf")
    page.file.set_path(src)
    page.text.setText("DRAFT")
    page.run()
    wait_job(window)
    assert window.document.dirty
    page.doc_bar.save_control.button.click()        # the split button's main part
    wait_job(window)
    assert not window.document.dirty
    with fitz.open(src) as doc:
        assert all("DRAFT" in p.get_text() for p in doc)


def test_the_arrow_s_save_as_writes_a_new_file(window, dialogs, tmp_path):
    page = _page(window, "WatermarkTool")
    src = make_pdf(tmp_path / "in.pdf")
    out = tmp_path / "out.pdf"
    page.file.set_path(src)
    page.text.setText("DRAFT")
    page.run()
    wait_job(window)
    dialogs.save(str(out))
    page.doc_bar.save_control.save_as_action.trigger()
    wait_job(window)
    with fitz.open(out) as doc:
        assert "DRAFT" in doc[0].get_text()
    with fitz.open(src) as doc:
        assert "DRAFT" not in doc[0].get_text()


def test_the_bar_s_print_opens_the_window_s_print(window, monkeypatch, tmp_path):
    page = _page(window, "WatermarkTool")
    page.file.set_path(make_pdf(tmp_path / "in.pdf"))
    calls = []
    monkeypatch.setattr(window, "print_document", lambda: calls.append(1) or True)
    page.doc_bar.print_button.click()
    assert calls == [1]


@pytest.mark.parametrize("tool", ["WatermarkTool", "HeaderFooterTool", "CompressTool",
                                  "CropTool", "NormaliseTool", "MetadataTool", "TocTool",
                                  "PdfToolsTool", "PasswordTool", "OCRTool"])
def test_a_tool_that_changes_the_document_from_its_settings_reads_apply(window, tool):
    page = _page(window, tool)
    assert [b.text() for b in page._buttons if b.pk_primary] == ["Apply"]


def test_metadata_apply_changes_the_document_and_not_the_file(window, dialogs, tmp_path):
    page = _page(window, "MetadataTool")
    src = make_pdf(tmp_path / "in.pdf")
    page.file.set_path(src)
    page.fields["author"].setText("Ada")
    primary = next(b for b in page._buttons if b.pk_primary)
    primary.click()
    assert window.document.dirty and window.document.doc.metadata["author"] == "Ada"
    assert window.status_text() == "✓  Metadata applied · Save writes it to the file"
    with fitz.open(src) as doc:
        assert doc.metadata["author"] != "Ada"
    primary.click()                                 # nothing more to apply
    assert window.status_text() == "No changes to apply"


def test_font_size_and_opacity_take_a_typed_number(window, dialogs, tmp_path):
    page = _page(window, "WatermarkTool")
    for box, typed, want in ((page.size, "73", 73), (page.opacity, "37", 37)):
        box.lineEdit().selectAll()
        QTest.keyClicks(box.lineEdit(), typed)
        QTest.keyClick(box.lineEdit(), Qt.Key_Tab)
        assert box.value() == want
    box = page.size                                 # out of range: kept within it
    box.lineEdit().selectAll()
    QTest.keyClicks(box.lineEdit(), "999")
    QTest.keyClick(box.lineEdit(), Qt.Key_Tab)
    assert 18 <= box.value() <= 120


def test_number_boxes_are_one_width(window):
    from paperknife.qt.pages import NUMBER_BOX_W
    page = _page(window, "WatermarkTool")
    pump(0.1)
    assert page.size.width() == page.opacity.width() == NUMBER_BOX_W


@pytest.mark.parametrize("tool", ["AnnotateTool", "EditTextTool", "FindReplaceTool",
                                  "RotateTool"])
def test_an_editor_that_applies_at_once_has_no_card_save(window, tool):
    # Owner, 2026-10-23: the document bar's Save is the one place to save.
    page = _page(window, tool)
    assert not [b.text() for b in page._buttons if b.pk_primary]


def test_ocr_reads_apply_for_the_overlay_and_names_the_new_file_for_text_only(window):
    page = _page(window, "OCRTool")
    assert page.run_button.text() == "Apply"
    page.modes["text"].click()
    assert page.run_button.text() == "Text-only PDF from OCR"
    page.modes["overlay"].click()
    assert page.run_button.text() == "Apply"


def test_dpi_and_quality_are_number_boxes(window):
    from paperknife.qt.pages import NUMBER_BOX_W
    ocr = _page(window, "OCRTool")
    assert type(ocr.dpi).__name__ != "TallSlider" and ocr.dpi.text().endswith(" DPI")
    p2d = _page(window, "Pdf2DocTool")
    assert p2d.quality_box.text() == "92%" and p2d.dpi_box.text().endswith(" DPI")
    assert p2d.dpi_box.maximumWidth() == p2d.quality_box.maximumWidth() == NUMBER_BOX_W
