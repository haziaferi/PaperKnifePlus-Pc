"""The Qt Metadata page: fields only, in the single-file form."""
import os

import pymupdf as fitz
import pytest

from qt_harness import make_pdf, pump, spy_open, wait_job

TEXT_KEYS = ["title", "author", "subject", "keywords", "creator", "producer"]


def _page(window):
    assert window.open_tool("MetadataTool")
    pump(0.05)
    return window.current_page()


def _pdf_with_meta(path, **meta):
    doc = fitz.open()
    doc.new_page()
    doc.set_metadata(meta)
    doc.save(str(path))
    doc.close()
    return str(path)


def _parts(folder):
    return [f for f in os.listdir(folder) if f.endswith(".part")]


def test_the_page_has_one_field_per_property(window):
    from paperknife.core.metadata import FIELDS
    page = _page(window)
    assert type(page).__name__ == "MetadataPage"
    assert list(page.fields) == [k for k, _ in FIELDS]
    assert page.title_label.text() == "Metadata"
    assert sum(1 for b in page._buttons if b.pk_primary) == 1


def test_saving_without_a_file_warns(window, dialogs):
    page = _page(window)
    page.save()
    assert dialogs.msgs[-1] == ("warning", "Save", "Open a PDF first.")


def test_choosing_a_file_fills_the_fields_and_save_writes_them(window, dialogs, tmp_path):
    page = _page(window)
    src = _pdf_with_meta(tmp_path / "in.pdf", title="Old title", author="Ann")
    dialogs.open(src)
    page.open()
    assert page.file.path() == src
    assert page.fields["title"].text() == "Old title"
    assert page.fields["author"].text() == "Ann"
    page.fields["title"].setText("New title")
    page.save()                             # applied, then written over the file
    wait_job(window)
    assert not dialogs.errors(), dialogs.errors()
    with fitz.open(src) as d:
        assert d.metadata["title"] == "New title"
        assert d.metadata["author"] == "Ann"
        assert len(d) == 1
    assert window.status_text() == "✓  Saved → in.pdf"
    assert window.status_role == "success"
    assert not page.has_pending() and not window.has_unsaved()


@pytest.mark.parametrize("key", TEXT_KEYS)
def test_each_text_field_is_written(window, dialogs, tmp_path, key):
    page = _page(window)
    src = make_pdf(tmp_path / "in.pdf", pages=1)
    page.file.set_path(src)
    page.fields[key].setText(f"value of {key}")
    page.save()
    wait_job(window)
    with fitz.open(src) as d:
        assert d.metadata[key] == f"value of {key}"


@pytest.mark.parametrize("key", ["creationDate", "modDate"])
def test_a_date_field_is_converted_to_a_pdf_date(window, dialogs, tmp_path, key):
    page = _page(window)
    src = make_pdf(tmp_path / "d.pdf", pages=1)
    page.file.set_path(src)
    page.fields[key].setText("2024-01-31")
    page.save()
    wait_job(window)
    with fitz.open(src) as d:
        assert d.metadata[key].startswith("D:20240131")


def test_an_unreadable_date_is_refused_and_nothing_is_saved(window, dialogs, tmp_path):
    page = _page(window)
    src = make_pdf(tmp_path / "d.pdf", pages=1)
    before = open(src, "rb").read()
    page.file.set_path(src)
    page.fields["modDate"].setText("next tuesday")
    page.save()
    kind, title, text = dialogs.msgs[-1]
    assert (kind, title) == ("error", "Metadata") and text.startswith("Modified date: use YYYY-MM-DD")
    assert window._current_job is None and open(src, "rb").read() == before
    assert page.has_pending()                       # what was typed stays


def test_clear_all_fields_removes_the_author_from_every_object(window, dialogs, tmp_path):
    src = tmp_path / "m.pdf"
    doc = fitz.open()
    doc.new_page()
    doc.set_metadata({"author": "Jane PRIVATE Doe", "title": "T"})
    doc.set_xml_metadata(
        '<?xpacket begin="" id="W5M0MpCehiHzreSzNTczkc9d"?>'
        '<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF '
        'xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
        '<rdf:Description xmlns:dc="http://purl.org/dc/elements/1.1/">'
        '<dc:creator><rdf:Seq><rdf:li>Jane PRIVATE Doe</rdf:li></rdf:Seq></dc:creator>'
        '</rdf:Description></rdf:RDF></x:xmpmeta><?xpacket end="w"?>')
    doc.save(str(src))
    doc.close()
    page = _page(window)
    page.file.set_path(str(src))
    page.clear()
    assert all(not e.text() for e in page.fields.values())
    out = tmp_path / "m_clean.pdf"
    dialogs.save(out)
    window.save_as()
    wait_job(window)
    assert not dialogs.errors(), dialogs.errors()
    with fitz.open(out) as d:
        assert "PRIVATE" not in (d.get_xml_metadata() or "")
        for xref in range(1, d.xref_length()):
            body = d.xref_object(xref) + (
                (d.xref_stream(xref) or b"").decode("latin-1") if d.xref_is_stream(xref) else "")
            assert "PRIVATE" not in body, f"xref {xref} still holds the author"


def test_it_saves_over_the_open_input(window, dialogs, tmp_path):
    src = make_pdf(tmp_path / "in.pdf", pages=2)
    page = _page(window)
    page.file.set_path(src)
    page.fields["title"].setText("New title")
    page.save()
    wait_job(window)
    assert not dialogs.errors(), dialogs.errors()
    assert _parts(tmp_path) == []
    assert page._doc is not None and len(page._doc) == 2, "the page lost its document"
    window.open_tool("CropTool")
    with fitz.open(src) as d:
        assert d.metadata["title"] == "New title"


def test_a_dropped_pdf_is_taken_and_another_file_refused(window, tmp_path):
    page = _page(window)
    other = tmp_path / "x.txt"
    other.write_text("x", encoding="utf-8")
    assert page.accept_drop(str(other)) is False
    assert page._doc is None
    src = _pdf_with_meta(tmp_path / "in.pdf", subject="Dropped")
    assert page.accept_drop(src) is True
    assert page.file.path() == src and page._doc is not None
    assert page.fields["subject"].text() == "Dropped"


def test_cancelling_save_as_writes_nothing_and_opens_nothing(window, dialogs, tmp_path,
                                                             monkeypatch):
    page = _page(window)
    page.file.set_path(make_pdf(tmp_path / "in.pdf"))
    held = page._doc
    opened = spy_open(window, monkeypatch)
    page.fields["title"].setText("x")
    window.save_as()               # no save path queued: the dialog returns ""
    assert opened == []
    assert window._current_job is None
    assert page._doc is held and not held.is_closed
    assert sorted(os.listdir(tmp_path)) == ["in.pdf"]


def test_a_refused_password_leaves_the_page_empty(window, dialogs, tmp_path):
    page = _page(window)
    src = make_pdf(tmp_path / "enc.pdf", password="pw")
    page.file.set_path(src)        # no password queued: the prompt is cancelled
    assert page._doc is None and page.file.path() == ""
    dialogs.passwords.append("pw")
    page.file.set_path(src)
    assert page._doc is not None and page.file.path() == src



@pytest.mark.parametrize("how", ["cancelled password", "unreadable file"])
def test_a_file_that_does_not_open_keeps_the_open_one_and_its_fields(window, dialogs,
                                                                     tmp_path, how):
    # R45-19: the open document was closed before the new one was tried, so a
    # cancelled prompt or a broken file threw away the document and every
    # field typed; Rotate, Split by Bookmarks and TOC keep the previous one.
    page = _page(window)
    a = _pdf_with_meta(tmp_path / "a.pdf", title="A title")
    page.file.set_path(a)
    held = page._doc
    page.fields["title"].setText("Typed title")
    page.fields["author"].setText("Typed author")
    if how == "cancelled password":
        b = make_pdf(tmp_path / "b.pdf", password="pw")     # no password queued
    else:
        b = str(tmp_path / "b.pdf")
        (tmp_path / "b.pdf").write_bytes(b"not a pdf")
    page.file.set_path(b)
    assert page._doc is held and not held.is_closed
    assert page.file.path() == a
    assert page.fields["title"].text() == "Typed title"
    assert page.fields["author"].text() == "Typed author"


def test_leaving_the_tool_keeps_the_document_and_the_fields_typed(window, tmp_path):
    # One document per window (owner, 2026-10-23).
    page = _page(window)
    src = make_pdf(tmp_path / "in.pdf", pages=2)
    page.file.set_path(src)
    held = page._doc
    page.fields["title"].setText("Typed")
    assert window.open_tool("MergeTool")
    assert not held.is_closed and window.has_unsaved()
    assert window.open_tool("MetadataTool")
    assert page._doc is held and page.fields["title"].text() == "Typed"
    assert page.file.path() == src


def test_an_undo_puts_the_fields_back(window, dialogs, tmp_path):
    page = _page(window)
    src = _pdf_with_meta(tmp_path / "in.pdf", title="Old")
    page.file.set_path(src)
    page.fields["title"].setText("New")
    assert page.commit_edits() and page._doc.metadata["title"] == "New"
    assert window.undo()
    assert page._doc.metadata["title"] == "Old" and page.fields["title"].text() == "Old"
