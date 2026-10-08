"""paperknife.core.enhance without any user interface: compress, watermark and
normalise, progress, and Cancel leaving no file behind."""
import io
import random
import re
import threading

import pymupdf as fitz
import pytest
from PIL import Image

from conftest import make_pdf
from paperknife.core import enhance as core


def _image_pdf(path):
    """Text plus a 1500 px noise image shown 300 pt wide (= 360 DPI)."""
    rnd = random.Random(1)
    im = Image.frombytes("RGB", (1500, 1500), rnd.randbytes(1500 * 1500 * 3))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    with fitz.open() as doc:
        p = doc.new_page()
        p.insert_image(fitz.Rect(72, 72, 372, 372), stream=buf.getvalue())
        p.insert_text((72, 500), "Searchable text", fontsize=14)
        doc.save(str(path))
    return str(path)


@pytest.mark.parametrize("level,width", [("medium", 625), ("aggressive", 400),
                                         ("light", 1500)])
def test_compress_resamples_images_by_level_and_closes_the_document(tmp_path, level, width):
    src = _image_pdf(tmp_path / "in.pdf")
    out = tmp_path / "out.pdf"
    doc = fitz.open(src)
    core.compress_pdf(doc, str(out), level)
    assert doc.is_closed
    with fitz.open(out) as d:
        assert "Searchable text" in d[0].get_text()
        assert [img[2] for img in d[0].get_images(full=True)] == [width]


def test_compress_can_overwrite_its_input(tmp_path):
    src = _image_pdf(tmp_path / "in.pdf")
    core.compress_pdf(fitz.open(src), src, "medium")
    with fitz.open(src) as d:
        assert [img[2] for img in d[0].get_images(full=True)] == [625]


def test_watermark_stamps_every_page_with_progress(tmp_path):
    src = make_pdf(tmp_path / "in.pdf", pages=3)
    out = tmp_path / "out.pdf"
    seen = []
    res = core.watermark_pdf(fitz.open(src), str(out), "DRAFT COPY", 60, 0.4,
                             (0.5, 0.5, 0.5), threading.Event(), seen.append)
    assert res == str(out)
    assert seen == pytest.approx([1 / 3, 2 / 3, 1.0])
    with fitz.open(out) as d:
        for page in d:
            assert "DRAFT COPY" in page.get_text()
        gs = d.xref_get_key(d[0].xref, "Resources/ExtGState")[1]
        assert [float(v) for v in re.findall(r"/ca\s*([\d.]+)", gs)] == [0.4]


def test_watermark_cancelled_writes_nothing_and_closes_the_document(tmp_path):
    src = make_pdf(tmp_path / "in.pdf", pages=3)
    out = tmp_path / "out.pdf"
    stop = threading.Event()
    stop.set()
    doc = fitz.open(src)
    assert core.watermark_pdf(doc, str(out), "X", 60, 0.25, (0, 0, 0), stop) is None
    assert not out.exists()
    assert doc.is_closed


@pytest.mark.parametrize("orient,expect", [("Portrait", (595, 842)),
                                           ("Landscape", (842, 595))])
def test_normalise_resizes_every_page(tmp_path, orient, expect):
    src = make_pdf(tmp_path / "in.pdf", pages=2, width=300, height=400)
    out = tmp_path / "out.pdf"
    seen = []
    assert core.normalise_pdf(fitz.open(src), str(out), "A4", orient, False,
                              threading.Event(), seen.append) is True
    assert seen == pytest.approx([0.5, 1.0])
    with fitz.open(out) as d:
        assert len(d) == 2
        assert {(round(p.rect.width), round(p.rect.height)) for p in d} == {expect}


def test_normalise_keep_original_follows_each_page(tmp_path):
    with fitz.open() as d:
        d.new_page(width=300, height=400)
        d.new_page(width=400, height=300)
        d.save(tmp_path / "in.pdf")
    out = tmp_path / "out.pdf"
    core.normalise_pdf(fitz.open(tmp_path / "in.pdf"), str(out), "Letter", "Keep original",
                       True, threading.Event(), lambda v: None)
    with fitz.open(out) as d:
        assert [(round(p.rect.width), round(p.rect.height)) for p in d] == [(612, 792),
                                                                             (792, 612)]


def test_normalise_cancelled_writes_nothing_and_closes_the_document(tmp_path):
    src = make_pdf(tmp_path / "in.pdf", pages=2)
    out = tmp_path / "out.pdf"
    stop = threading.Event()
    stop.set()
    doc = fitz.open(src)
    assert core.normalise_pdf(doc, str(out), "A4", "Portrait", False, stop,
                              lambda v: None) is False
    assert not out.exists()
    assert doc.is_closed
