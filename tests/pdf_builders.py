"""Toolkit-neutral PDF builders shared by both harnesses: the Tk/core suite
imports this module by name (tests/ is on sys.path there) and the Qt harness
re-exports it from qt_harness.py.  Nothing here imports a GUI toolkit."""
from __future__ import annotations

import io
import random


def image_pdf(path, pages: int = 1) -> str:
    """Each page: the text "Searchable text <n>" plus a 1500 px noise image
    shown 300 pt wide (= 360 DPI).  Compress resamples the image to 625 px
    (medium) and 400 px (aggressive) and keeps 1500 px (light)."""
    import pymupdf as fitz
    from PIL import Image
    rnd = random.Random(1)
    im = Image.frombytes("RGB", (1500, 1500), rnd.randbytes(1500 * 1500 * 3))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    doc = fitz.open()
    for i in range(pages):
        p = doc.new_page()
        p.insert_image(fitz.Rect(72, 72, 372, 372), stream=buf.getvalue())
        p.insert_text((72, 500), f"Searchable text {i + 1}", fontsize=14)
    doc.save(str(path))
    doc.close()
    return str(path)


def truncated_pdf(good, bad) -> str:
    """Write *good* to *bad* cut just before its xref table, so the table, the
    trailer, startxref and %%EOF are all gone (rfind(b"xref") would land in
    "startxref" and keep the whole table)."""
    data = open(good, "rb").read()
    cut = data.find(b"\nxref\n")
    assert cut > 0, "the source PDF has no classic xref table"
    open(bad, "wb").write(data[:cut])
    kept = data[:cut]
    assert b"xref" not in kept and b"trailer" not in kept and b"%%EOF" not in kept
    return str(bad)
