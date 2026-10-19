"""Batch: one operation applied to many PDFs, each file on its own."""
from __future__ import annotations
import os
from pathlib import Path

import pymupdf as fitz

from ..job_queue import atomic_output
from ..prefs import DPI_RANGE
from .convert import NoText, pdf_to_doc
from .enhance import compress_pdf, watermark_pdf
from .ocr import ocr_pdf

# Each worker takes (src_path, out_dir, opts, stop) → out_path, None if
# cancelled, or raises.

def open_input(src):
    # A batch cannot stop for a password prompt per file; name the cause
    # instead of letting save() fail with "document closed or encrypted".
    doc = fitz.open(src)
    if doc.needs_pass:
        doc.close()
        raise ValueError("password-protected (open it in the single-file tool)")
    return doc

def _do_compress(src, out_dir, opts, stop):
    if stop.is_set(): return None
    out = os.path.join(out_dir, Path(src).stem + "_compressed.pdf")
    if not compress_pdf(open_input(src), out, opts.get("level", "medium"), stop):
        return None
    return out

def _do_watermark(src, out_dir, opts, stop):
    out = os.path.join(out_dir, Path(src).stem + "_watermarked.pdf")
    return watermark_pdf(open_input(src), out, opts.get("text", "DRAFT"),
                         opts.get("size", 60), opts.get("opacity", 0.25),
                         tuple(opts.get("color", (0.5, 0.5, 0.5))), stop)

def _do_ocr(src, out_dir, opts, stop):
    if stop.is_set(): return None
    out = os.path.join(out_dir, Path(src).stem + "_ocr.pdf")
    n = ocr_pdf(open_input(src), out, opts.get("lang", "eng"), opts.get("dpi", 150),
                bool(opts.get("text_only", False)), stop, lambda v: None)
    return out if n is not None else None

def _do_pdf2txt(src, out_dir, opts, stop):
    out = os.path.join(out_dir, Path(src).stem + ".txt")
    with open_input(src) as doc:
        parts = []
        for i, page in enumerate(doc):
            if stop.is_set(): return None
            parts.append(page.get_text())
            if i < len(doc) - 1:
                parts.append("\n\n── Page Break ──\n\n")
    if not any(p.strip() for p in parts[::2]):
        raise NoText
    with atomic_output(out) as tmp:
        Path(tmp).write_text("".join(parts), encoding="utf-8")
    return out

# What PDF → Other writes, by format: (extension, suffix of the file name).
OTHER_OUT = {"TXT": (".txt", ""), "HTML": (".html", ""), "XML": (".xml", ""),
             "RTF": (".rtf", ""), "DOCX": (".docx", ""), "PPTX": (".pptx", ""),
             "XLSX": (".xlsx", ""), "PNG": (".zip", "_png"), "JPEG": (".zip", "_jpeg")}


def _do_pdf2other(src, out_dir, opts, stop):
    fmt = opts.get("fmt", "TXT")
    ext, suffix = OTHER_OUT[fmt]
    out = os.path.join(out_dir, Path(src).stem + suffix + ext)
    if not pdf_to_doc(open_input(src), fmt, out, stop, lambda v: None,
                      dpi=opts.get("dpi", 150), quality=opts.get("quality", 92)):
        return None
    return out


# The tools' own full settings, by tool (prototypes B and C): what the
# single-file screens offer, applied to a folder.
TOOL_OPS = {
    "compress":  _do_compress,
    "watermark": _do_watermark,
    "ocr":       _do_ocr,
    "other":     _do_pdf2other,
}

OPS = {
    "Compress":      _do_compress,
    "Watermark":     _do_watermark,
    "OCR":           _do_ocr,
    "PDF → TXT":     _do_pdf2txt,
}


def validate_options(opts: dict) -> dict:
    """*opts* (text typed in the options pane) with size, DPI and opacity as
    numbers, in place.  Raises ValueError with the message to show when one
    of them is out of range or not a number, or the watermark text is empty
    (the single-file Watermark tool refuses it the same way)."""
    if "text" in opts and not str(opts["text"]).strip():
        raise ValueError("Enter watermark text.")
    lo, hi = DPI_RANGE
    try:
        if "size" in opts:
            opts["size"] = int(opts["size"])
            if opts["size"] <= 0:
                raise ValueError
        if "dpi" in opts:
            opts["dpi"] = int(opts["dpi"])
            if not lo <= opts["dpi"] <= hi:
                raise ValueError
        if "opacity" in opts:
            opts["opacity"] = float(opts["opacity"])
            if not 0 < opts["opacity"] <= 1:
                raise ValueError
    except ValueError:
        raise ValueError(
            f"Size must be a positive whole number, DPI a whole number "
            f"from {lo} to {hi}, opacity a number above 0 and up to 1.") from None
    return opts
