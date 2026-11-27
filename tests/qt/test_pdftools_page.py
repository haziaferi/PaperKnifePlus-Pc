"""The Qt PDF Tools page: repair a damaged file."""
import pymupdf as fitz

from qt_harness import make_pdf, pump, save_as, spy_open, truncated_pdf, wait_job


def _page(window):
    assert window.open_tool("PdfToolsTool")
    pump(0.05)
    return window.current_page()


def _truncated(tmp_path):
    """A 2-page PDF cut before its xref table (no table, trailer or %%EOF)."""
    return truncated_pdf(make_pdf(tmp_path / "good.pdf", pages=2), tmp_path / "bad.pdf")


def test_the_page_offers_four_tools_and_the_action_names_the_one_chosen(window):
    from PySide6.QtWidgets import QLabel
    page = _page(window)
    assert type(page).__name__ == "PdfToolsPage"
    assert page.title_label.text() == "PDF Tools"
    assert list(page.radios) == ["repair", "sanitise", "flatten", "blank"]
    # Every choice changes the open document: the action reads Apply (owner, 2026-10-23)
    assert page.tool_choice == "repair" and page.action_btn.text() == "Apply"
    texts = [lbl.text() for lbl in page.findChildren(QLabel)]
    assert not any("Linear" in t or "PDF/A" in t for t in texts), texts
    for key, shown in (("sanitise", "sanitise"), ("flatten", "flatten"), ("blank", None),
                       ("repair", None)):
        page.radios[key].click()
        assert page.action_btn.text() == "Apply"
        for k, (heading, box) in page.option_boxes.items():
            assert box.isVisibleTo(page) == (k == shown) and heading.isVisibleTo(page) == (k == shown)
    assert [b.text() for b in page._buttons if b.pk_primary] == ["Apply"]    # one main action


def _risky(path):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 100), "Visible", fontsize=12)
    doc.xref_set_key(doc.pdf_catalog(), "OpenAction", "<</S/JavaScript/JS(app.alert(1))>>")
    doc.embfile_add("a.txt", b"x")
    doc.save(str(path))
    doc.close()
    return str(path)


def test_sanitise_end_to_end_says_what_it_removed(window, dialogs, tmp_path):
    page = _page(window)
    page.radios["sanitise"].click()
    page.switches["embedded"].setChecked(False)
    page.file.set_path(_risky(tmp_path / "in.pdf"))
    out = tmp_path / "out.pdf"
    page.run()
    wait_job(window)
    save_as(window, dialogs, out)
    assert not dialogs.errors(), dialogs.errors()
    assert ("info", "PDF Tools", "Removed: 1 script") in dialogs.msgs      # what it found
    assert window.applied_status == "✓  Cleaned up · Save writes it to the file"
    with fitz.open(out) as d:
        assert d.embfile_count() == 1 and "Visible" in d[0].get_text()


def test_flatten_end_to_end(window, dialogs, tmp_path):
    src = tmp_path / "in.pdf"
    doc = fitz.open()
    doc.new_page().add_text_annot((100, 100), "note")
    doc.save(str(src))
    doc.close()
    page = _page(window)
    page.radios["flatten"].click()
    page.file.set_path(str(src))
    out = tmp_path / "out.pdf"
    page.run()
    wait_job(window)
    save_as(window, dialogs, out)
    assert ("info", "PDF Tools", "Flattened: 1 comment") in dialogs.msgs
    assert window.applied_status == "✓  Flattened · Save writes it to the file"
    with fitz.open(out) as d:
        assert list(d[0].annots()) == []


def _with_blanks(path, kinds):
    doc = fitz.open()
    for k in kinds:
        p = doc.new_page()
        if k:
            p.insert_text((72, 100), k, fontsize=12)
    doc.save(str(path))
    doc.close()
    return str(path)


def test_remove_blank_pages_asks_naming_them_and_writes_the_rest(window, dialogs, tmp_path):
    page = _page(window)
    page.radios["blank"].click()
    page.file.set_path(_with_blanks(tmp_path / "in.pdf", ["one", "", "two", ""]))
    out = tmp_path / "out.pdf"
    dialogs.asks.append(True)
    page.run()
    wait_job(window)                        # the look for blank pages, a job of its own
    wait_job(window)                        # then their removal
    save_as(window, dialogs, out)
    assert ("ask_yes_no", "Remove blank pages",
            "Remove pages 2 and 4? They have no text or drawing.") in dialogs.msgs
    with fitz.open(out) as d:
        assert [p.get_text().strip() for p in d] == ["one", "two"]
    assert window.applied_status == "✓  Removed 2 blank page(s) · Save writes it to the file"


def test_remove_blank_pages_said_no_or_none_found_writes_nothing(window, dialogs, tmp_path):
    page = _page(window)
    page.radios["blank"].click()
    page.file.set_path(_with_blanks(tmp_path / "in.pdf", ["one", ""]))
    dialogs.asks.append(False)
    page.run()
    wait_job(window)
    assert ("ask_yes_no", "Remove blank pages",
            "Remove page 2? It has no text or drawing.") in dialogs.msgs
    assert not window._current_job.is_running          # only the look ran
    page.file.set_path(_with_blanks(tmp_path / "full.pdf", ["one", "two"]))
    before = window._current_job
    page.run()
    wait_job(window)
    assert window._current_job is not before            # the look ran again, then nothing
    assert dialogs.msgs[-1] == ("info", "Remove blank pages", "No blank page was found.")
    assert not list(tmp_path.glob("out*.pdf"))


def test_a_file_of_blank_pages_keeps_one(window, dialogs, tmp_path):
    page = _page(window)
    page.radios["blank"].click()
    page.file.set_path(_with_blanks(tmp_path / "in.pdf", ["", ""]))
    page.run()
    wait_job(window)
    assert dialogs.msgs[-1] == ("error", "PDF Tools",
                                "A PDF needs at least one page: keep one or more.")


def test_without_a_file_it_asks_for_one(window, dialogs):
    page = _page(window)
    page.run()
    assert dialogs.msgs[-1] == ("warning", "PDF Tools", "Select a PDF first.")


def test_pdftools_default_run_saves_a_clean_copy(window, dialogs, tmp_path):
    page = _page(window)
    page.file.set_path(make_pdf(tmp_path / "in.pdf"))
    out = tmp_path / "out.pdf"
    page.run()
    wait_job(window)
    save_as(window, dialogs, out)
    assert dialogs.msgs == [], dialogs.msgs
    assert window.applied_status == "✓  No damage found; cleaned · Save writes it to the file"
    with fitz.open(out) as doc:
        assert doc.page_count == 3 and doc[2].get_text().strip() == "Page 3"


def test_pdftools_repair_recovers_a_truncated_file(window, dialogs, tmp_path):
    page = _page(window)
    page.file.set_path(_truncated(tmp_path))
    out = tmp_path / "out.pdf"
    page.run()
    wait_job(window)
    save_as(window, dialogs, out)
    assert not dialogs.errors(), dialogs.errors()
    assert window.applied_status == "✓  Repaired · Save writes it to the file"
    with fitz.open(out) as doc:
        assert not doc.is_repaired and doc.page_count == 2
        assert [p.get_text().strip() for p in doc] == ["Page 1", "Page 2"]


def test_a_dropped_pdf_fills_the_file_card_and_others_are_refused(window, tmp_path):
    page = _page(window)
    src = make_pdf(tmp_path / "in.pdf")
    other = tmp_path / "x.txt"
    other.write_text("x", encoding="utf-8")
    assert page.accept_drop(str(other)) is False
    assert page.accept_drop(src) is True and page.file.path() == src


def test_applying_asks_no_file_name_and_closes_its_copy(window, dialogs, tmp_path,
                                                          monkeypatch):
    # Applied to the document (owner's sort, 2026-10-23).
    page = _page(window)
    page.file.set_path(make_pdf(tmp_path / "in.pdf"))
    opened = spy_open(window, monkeypatch)
    page.run()                     # no file name asked (the harness would hand it nothing)
    wait_job(window)
    shared = window.document.doc
    assert opened and all(d.is_closed for d in opened if d is not shared)
    assert window.document.undo_label() == "Repair"


def test_leaving_the_tool_leaves_no_document_open(window, dialogs, tmp_path, monkeypatch):
    page = _page(window)
    page.file.set_path(make_pdf(tmp_path / "in.pdf"))
    opened = spy_open(window, monkeypatch)
    page.run()
    window.show_page("CompressTool")            # refused while the job holds the view
    wait_job(window)
    assert window.show_page("CompressTool")
    shared = window.document.doc
    assert opened and all(d.is_closed for d in opened if d is not shared)
    assert shared.page_count == 3 and not shared.is_closed


def test_a_scanned_blank_page_is_found_and_the_question_says_why(window, dialogs, tmp_path):
    import io
    from PIL import Image
    src = tmp_path / "scan.pdf"
    doc = fitz.open()
    doc.new_page().insert_text((72, 100), "one", fontsize=12)
    im = Image.effect_noise((1240, 1754), 3).point(lambda v: v + 120).convert("RGB")
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=75)
    page = doc.new_page()
    page.insert_image(page.rect, stream=buf.getvalue())     # the back of a scanned sheet
    doc.save(str(src))
    doc.close()
    tool = _page(window)
    tool.radios["blank"].click()
    tool.file.set_path(str(src))
    dialogs.asks.append(False)
    tool.run()
    wait_job(window)
    assert ("ask_yes_no", "Remove blank pages",
            "Remove page 2? It has no text or drawing. "
            "Scanned pages count when they show only empty paper.") in dialogs.msgs
