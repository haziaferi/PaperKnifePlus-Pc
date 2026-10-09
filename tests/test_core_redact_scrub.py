"""After Redact, the phrase is nowhere in the saved file: not in marked-content
/ActualText, the structure tree, custom document-info keys, or attachments
(plain, zipped as a .docx is, or a PDF) — review R2a-19/20/21."""
import io
import threading
import zipfile

import pymupdf as fitz
import pytest

from paperknife.core import redact

SECRET = "ZEBRA4471"


def _encodings(s):
    yield s.encode("latin-1").lower()
    yield s.encode("latin-1").hex().encode().lower()
    yield s.encode("utf-16-be").hex().encode().lower()
    yield s.encode("utf-16-be").lower()


def leaks(path):
    """Every place in the saved file that still holds the phrase."""
    hits = []
    with fitz.open(path) as r:
        for x in range(1, r.xref_length()):
            try:
                obj = (r.xref_object(x, compressed=False) or "").encode("latin-1", "ignore").lower()
            except Exception:
                obj = b""
            blobs = [("obj", obj)]
            if r.xref_is_stream(x):
                blobs.append(("stream", (r.xref_stream(x) or b"").lower()))
            for what, data in blobs:
                compact = data.replace(b" ", b"").replace(b"\n", b"")
                if any(e in data or e in compact for e in _encodings(SECRET)):
                    hits.append(f"{what} {x}")
    return hits


def _redact_and_save(doc, tmp_path, box=None):
    stop = threading.Event()
    pending = redact.find_phrase(doc, SECRET, stop)
    if box is not None:
        pending.append((0, box, None))
    found = {}
    redact.apply_boxes(doc, pending, (0, 0, 0), stop, None, {}, found)
    secrets = {}
    redact.merge_secrets(secrets, found)
    if not secrets:
        secrets = {SECRET: False}
    removed = redact.scrub_secrets(doc, secrets)
    out = tmp_path / "out.pdf"
    doc.save(out, deflate=True, garbage=4, clean=True)
    doc.close()
    return out, removed


def _page_with_text(doc):
    p = doc.new_page()
    p.insert_text((72, 100), f"Name {SECRET} here", fontsize=12)
    return p


def test_marked_content_actual_text(tmp_path):
    doc = fitz.open()
    p = doc.new_page()
    p.insert_text((72, 300), "xxxxxxxxx", fontsize=12)
    xs = p.get_contents()[0]
    doc.update_stream(xs, b"/Span <</ActualText (" + SECRET.encode() + b")>> BDC "
                      + doc.xref_stream(xs) + b" EMC")
    doc[0].insert_text((72, 100), f"see {SECRET}", fontsize=12)   # so the phrase is a secret
    out, _ = _redact_and_save(doc, tmp_path, box=fitz.Rect(60, 280, 250, 310))
    assert leaks(out) == []


def test_actual_text_written_as_utf16_hex(tmp_path):
    doc = fitz.open()
    p = _page_with_text(doc)
    xs = p.get_contents()[0]
    hexed = ("feff" + SECRET.encode("utf-16-be").hex()).encode()
    doc.update_stream(xs, b"/Span <</ActualText <" + hexed + b">>> BDC "
                      + doc.xref_stream(xs) + b" EMC")
    out, _ = _redact_and_save(doc, tmp_path)
    assert leaks(out) == []


def test_structure_tree_alt_text(tmp_path):
    doc = fitz.open()
    _page_with_text(doc)
    elem = doc.get_new_xref()
    doc.update_object(elem, f"<</Type/StructElem/S/Figure/Alt({SECRET} photo)/ActualText({SECRET})>>")
    root = doc.get_new_xref()
    doc.update_object(root, f"<</Type/StructTreeRoot/K {elem} 0 R>>")
    doc.xref_set_key(doc.pdf_catalog(), "StructTreeRoot", f"{root} 0 R")
    out, _ = _redact_and_save(doc, tmp_path)
    assert leaks(out) == []


def test_custom_document_info_key(tmp_path):
    doc = fitz.open()
    _page_with_text(doc)
    doc.set_metadata({"author": "someone"})
    info = int(doc.xref_get_key(-1, "Info")[1].split()[0])
    doc.xref_set_key(info, "Company", f"({SECRET} Ltd)")
    out, removed = _redact_and_save(doc, tmp_path)
    assert leaks(out) == []
    assert removed


def test_file_attachment_annotation(tmp_path):
    doc = fitz.open()
    p = _page_with_text(doc)
    p.add_file_annot(fitz.Point(300, 400), f"note {SECRET}".encode(), "a.txt")
    out, removed = _redact_and_save(doc, tmp_path)
    assert leaks(out) == []
    assert any("attachment" in r for r in removed)


@pytest.mark.parametrize("kind", ["docx", "pdf"])
def test_compressed_or_pdf_attachment(tmp_path, kind):
    if kind == "docx":
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("word/document.xml", f"<w:t>{SECRET}</w:t>")
        body, name = buf.getvalue(), "report.docx"
    else:
        inner = fitz.open()
        inner.new_page().insert_text((72, 100), SECRET, fontsize=12)
        body, name = inner.tobytes(deflate=True), "inner.pdf"
        inner.close()
    doc = fitz.open()
    _page_with_text(doc)
    doc.embfile_add(name, body, filename=name)
    out, removed = _redact_and_save(doc, tmp_path)
    with fitz.open(out) as r:
        assert name not in r.embfile_names()
    assert any(name in r for r in removed)


def test_unrelated_attachment_and_info_are_kept(tmp_path):
    doc = fitz.open()
    _page_with_text(doc)
    doc.embfile_add("other.txt", b"nothing secret", filename="other.txt")
    info_doc = {"author": "Alice"}
    doc.set_metadata(info_doc)
    out, _ = _redact_and_save(doc, tmp_path)
    with fitz.open(out) as r:
        assert r.embfile_names() == ["other.txt"]
        assert r.metadata["author"] == "Alice"
