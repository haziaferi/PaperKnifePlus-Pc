"""Run the line-art cutter over real PDFs with random boxes and measure it.

Reads PDFs, never writes them: every page is copied into a new document in memory.
For each sampled page with line art, three boxes are placed (two on drawn paths,
one anywhere) and the page is redacted two ways:

- old: MuPDF alone (what RedactTool did before L3-18);
- new: redact_page() (cut_line_art, then MuPDF for text and images).

Measured per page: ink left under the boxes with no fill (leak), path outlines
inside the boxes, ink changed outside the boxes with the black fill (collateral,
also for old, so new - old is what the cutter adds), errors and time.

    python realworld_check.py <folder> <out.json> [--pages 400] [--seed 7]
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
import traceback
from pathlib import Path

import pymupdf as fitz

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from paperknife.tools.redact import redact_page  # noqa: E402

DPI = 96
S = DPI / 72


def old_redact(doc, pno, rects, fill):
    page = doc[pno]
    for r in rects:
        page.add_redact_annot(r, fill=fill if fill is not None else False)
    page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_PIXELS)


def gray(page):
    pix = page.get_pixmap(dpi=DPI, colorspace=fitz.csGRAY, alpha=False, annots=False)
    return pix.width, pix.height, pix.samples


def box_pixels(page, boxes, w, h, grow):
    out = set()
    for b in boxes:
        r = fitz.Rect(b) * page.rotation_matrix
        r = fitz.Rect(r.x0 * S - grow, r.y0 * S - grow, r.x1 * S + grow, r.y1 * S + grow)
        for y in range(max(0, math.floor(r.y0)), min(h, math.ceil(r.y1))):
            out.update(range(y * w + max(0, math.floor(r.x0)), y * w + min(w, math.ceil(r.x1))))
    return out


def outlines_inside(page, boxes, eps=0.05):
    """Shape left in the boxes, as tests/test_redact_lineart.py counts it: path
    vertices inside a box, and stroked outlines running through one."""
    inner = [fitz.Rect(b.x0 + eps, b.y0 + eps, b.x1 - eps, b.y1 - eps) for b in boxes]
    n = 0
    for d in page.get_drawings(extended=True):
        if d["type"] == "group":
            continue
        for it in d["items"]:
            ends = (list(fitz.Rect(it[1]).quad) if it[0] == "re" else list(it[1]) if it[0] == "qu"
                    else [it[1], it[4]] if it[0] == "c" else [it[1], it[2]])
            n += sum(1 for p in ends if any(p in r for r in inner))
        if "s" not in d["type"]:
            continue
        for it in d["items"]:
            if it[0] == "l":
                pts = [it[1], it[2]]
            elif it[0] == "c":
                p0, p1, p2, p3 = it[1:5]
                pts = [p0 * (1 - t) ** 3 + p1 * 3 * (1 - t) ** 2 * t + p2 * 3 * (1 - t) * t * t
                       + p3 * t ** 3 for t in (i / 24 for i in range(25))]
            elif it[0] == "re":
                r = it[1]
                pts = [r.tl, r.tr, r.br, r.bl, r.tl]
            else:
                q = it[1]
                pts = [q.ul, q.ur, q.lr, q.ll, q.ul]
            for a, b in zip(pts, pts[1:], strict=False):
                if any((a + (b - a) * (k / 8)) in r for k in range(9) for r in inner):
                    n += 1
                    break
    return n


def boxes_for(page, rnd):
    items = [it for d in page.get_drawings() for it in d["items"]]
    if not items:
        return None
    boxes = []
    for _ in range(2):
        it = rnd.choice(items)
        p = it[1] if isinstance(it[1], fitz.Point) else fitz.Rect(it[1]).tl
        w, h = rnd.uniform(20, 140), rnd.uniform(12, 90)
        boxes.append(fitz.Rect(p.x - w / 2, p.y - h / 2, p.x + w / 2, p.y + h / 2))
    x, y = rnd.uniform(0, max(1, page.cropbox.width - 100)), rnd.uniform(0, max(1, page.cropbox.height - 60))
    boxes.append(fitz.Rect(x, y, x + rnd.uniform(30, 100), y + rnd.uniform(15, 60)))
    return [b for b in boxes if b.width > 1 and b.height > 1]


def measure(src_bytes, boxes):
    res = {}
    with fitz.open("pdf", src_bytes) as d:
        w, h, before = gray(d[0])
        inside = box_pixels(d[0], boxes, w, h, grow=-3)
        near = box_pixels(d[0], boxes, w, h, grow=3)
    outside_ink = [i for i in range(w * h) if i not in near and before[i] < 250]
    for name, fn in (("old", old_redact), ("new", redact_page)):
        t0 = time.perf_counter()
        with fitz.open("pdf", src_bytes) as bare:
            mode = fn(bare, 0, boxes, None)
            if mode in ("whole", "image"):
                res["fallback"] = mode
            bw, bh, after = gray(bare[0])
            if (bw, bh) != (w, h):
                raise RuntimeError("page size changed")
            res[f"{name}_leak_px"] = sum(1 for i in inside if after[i] < 250)
            res[f"{name}_outlines_in"] = outlines_inside(bare[0], boxes)
        with fitz.open("pdf", src_bytes) as real:
            fn(real, 0, boxes, (0, 0, 0))
            real = fitz.open("pdf", real.tobytes(garbage=4, deflate=True, clean=True))
            _, _, after = gray(real[0])
            res[f"{name}_collateral_px"] = sum(1 for i in outside_ink if abs(before[i] - after[i]) > 48)
            real.close()
        res[f"{name}_s"] = round(time.perf_counter() - t0, 3)
    res["ink_inside_px"] = sum(1 for i in inside if before[i] < 250)
    res["outside_ink_px"] = len(outside_ink)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("out")
    ap.add_argument("--pages", type=int, default=400)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--per-file", type=int, default=2)
    a = ap.parse_args()
    rnd = random.Random(a.seed)
    files = sorted(p for p in Path(a.folder).rglob("*.pdf") if 20_000 < p.stat().st_size < 40_000_000)
    rnd.shuffle(files)
    rows = []
    log = open(Path(a.out).with_suffix(".jsonl"), "w", encoding="utf-8")  # survives a stop
    for f in files:
        if len(rows) >= a.pages:
            break
        try:
            doc = fitz.open(f)
        except Exception:
            continue
        if doc.needs_pass or not doc.is_pdf:
            doc.close()
            continue
        pnos = rnd.sample(range(len(doc)), min(a.per_file, len(doc)))
        for pno in pnos:
            row = {"file": f.name, "page": pno}
            print("  start", f.name[:60], pno, flush=True)
            try:
                one = fitz.open()
                one.insert_pdf(doc, from_page=pno, to_page=pno)
                boxes = boxes_for(one[0], rnd)
                if not boxes:
                    one.close()
                    continue
                src = one.tobytes()
                one.close()
                row["boxes"] = [tuple(round(v, 1) for v in b) for b in boxes]
                row.update(measure(src, boxes))
            except Exception as e:
                row["error"] = f"{type(e).__name__}: {e}"
                row["trace"] = traceback.format_exc(limit=4)[-800:]
            rows.append(row)
            log.write(json.dumps(row) + "\n")
            log.flush()
            print(len(rows), f.name[:40], pno, {k: v for k, v in row.items()
                                               if k.endswith(("leak_px", "_in", "collateral_px", "_s", "error"))},
                  flush=True)
        doc.close()
    Path(a.out).write_text(json.dumps(rows, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
