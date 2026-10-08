"""paperknife.core.metadata without any user interface."""
import pymupdf as fitz
import pytest

from conftest import make_pdf
from paperknife.core import metadata as core


@pytest.mark.parametrize("text,expect", [
    ("", ""),
    ("D:20200101000000", "D:20200101000000"),
    ("2024-01-31", "D:20240131000000"),
    (" 2024-01-31 08:15 ", "D:20240131081500"),
    ("2024-01-31 08:15:42", "D:20240131081542"),
])
def test_pdf_date_reads_the_accepted_forms(text, expect):
    assert core.pdf_date(text) == expect


def test_pdf_date_refuses_other_text():
    with pytest.raises(ValueError):
        core.pdf_date("31/01/2024")


def test_check_dates_converts_in_place_or_names_the_field():
    meta = {k: "" for k, _ in core.FIELDS}
    meta["modDate"] = "2024-02-01"
    assert core.check_dates(meta) is None
    assert meta["modDate"] == "D:20240201000000"
    meta["creationDate"] = "yesterday"
    msg = core.check_dates(meta)
    assert msg.startswith("Creation date: use YYYY-MM-DD")


def test_read_and_apply_metadata_round_trip_and_drop_xmp(tmp_path):
    src = make_pdf(tmp_path / "in.pdf", pages=1)
    with fitz.open(src) as doc:
        doc.set_xml_metadata("<x:xmpmeta xmlns:x='adobe:ns:meta/'>OLD</x:xmpmeta>")
        loaded = core.read_metadata(doc)
        assert set(loaded) == {k for k, _ in core.FIELDS}
        assert all(isinstance(v, str) for v in loaded.values())
        meta = dict(loaded, title="New title", author="Me")
        core.apply_metadata(doc, meta, changed=True)
        assert doc.get_xml_metadata() == ""
        doc.save(tmp_path / "out.pdf", garbage=1, deflate=True)
    with fitz.open(tmp_path / "out.pdf") as d:
        assert d.metadata["title"] == "New title" and d.metadata["author"] == "Me"


def test_apply_metadata_unchanged_keeps_the_xmp(tmp_path):
    src = make_pdf(tmp_path / "in.pdf", pages=1)
    with fitz.open(src) as doc:
        doc.set_xml_metadata("<x:xmpmeta xmlns:x='adobe:ns:meta/'>KEEP</x:xmpmeta>")
        core.apply_metadata(doc, core.read_metadata(doc), changed=False)
        assert "KEEP" in doc.get_xml_metadata()
