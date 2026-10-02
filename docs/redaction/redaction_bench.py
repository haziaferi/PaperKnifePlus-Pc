"""Measure how each line-art redaction strategy trades leakage against collateral damage.

Leak:       ink left inside a redaction box when the box is applied with no fill
            (what a reader recovers by deleting the black rectangle).
Collateral: ink changed outside the boxes, as a share of the ink outside the boxes.
Search:     share of the page's words outside the boxes still extractable.
Size:       output bytes / input bytes.

Run with the project venv:  python redaction_bench.py
"""
from __future__ import annotations

import io
import json
import math
from pathlib import Path

import pymupdf as fitz

DPI = 144
OUT = Path(__file__).resolve().parent / "redaction-bench.json"


# ── Corpus: each case returns (doc bytes, list of redaction rects, page index) ──
def _page(doc, rotate=0):
    p = doc.new_page(width=595, height=842)
    if rotate:
        p.set_rotation(rotate)
    return p


def case_table(rotate=0):
    doc = fitz.open()
    p = _page(doc, rotate)
    x0, y0, cw, ch, n = 80, 120, 85, 30, 5
    sh = p.new_shape()
    for i in range(n + 1):
        sh.draw_line((x0, y0 + i * ch), (x0 + n * cw, y0 + i * ch))
        sh.draw_line((x0 + i * cw, y0), (x0 + i * cw, y0 + n * ch))
    sh.finish(color=(0, 0, 0), width=1)
    sh.commit()
    for r in range(n):
        for c in range(n):
            p.insert_text((x0 + c * cw + 6, y0 + r * ch + 20), f"R{r}C{c} 4471", fontsize=9)
    p.insert_text((80, 330), "Totals are confidential until release.", fontsize=11)
    # A box drawn over one cell, overlapping its borders by 2 pt as users do.
    # Drawing and redaction both take unrotated page coordinates.
    box = fitz.Rect(x0 + 2 * cw - 2, y0 + 2 * ch - 2, x0 + 3 * cw + 2, y0 + 3 * ch + 2)
    return doc, [box]


def case_signature():
    doc = fitz.open()
    p = _page(doc)
    p.insert_text((80, 200), "Signed: J. Doe, on behalf of the applicant", fontsize=11)
    sh = p.new_shape()
    pts = [(100, 300), (140, 250), (180, 330), (220, 260), (260, 320), (300, 255),
           (340, 315), (380, 270), (420, 300)]
    for a, b, c in zip(pts[::2], pts[1::2], pts[2::2]):
        sh.draw_bezier(a, b, b, c)
    sh.finish(color=(0, 0, 0.5), width=1.6)
    sh.commit()
    return doc, [fitz.Rect(250, 240, 440, 340)]


def case_chart():
    doc = fitz.open()
    p = _page(doc)
    sh = p.new_shape()
    sh.draw_rect(fitz.Rect(80, 150, 520, 450))
    sh.finish(color=(0.4, 0.4, 0.4), width=0.8)
    vals = [400, 330, 360, 250, 280, 190, 230, 170, 210, 160]
    pts = [(100 + i * 45, v) for i, v in enumerate(vals)]
    sh.draw_polyline(pts)
    sh.finish(color=(0.8, 0, 0), width=2)
    sh.commit()
    p.insert_text((80, 480), "Quarterly revenue (redacted quarters hidden)", fontsize=10)
    return doc, [fitz.Rect(270, 140, 380, 460)]


def case_underline():
    doc = fitz.open()
    p = _page(doc)
    p.insert_text((80, 200), "Account holder: Maria Rossi, IBAN IT60X0542811101000000123456",
                  fontsize=10)
    p.draw_line((80, 203), (470, 203), color=(0, 0, 0), width=0.7)
    words = p.get_text("words")
    box = fitz.Rect()
    for w in words:
        if w[4].startswith("IT60"):
            box = fitz.Rect(w[:4]) + (-1, -1, 1, 4)
    return doc, [box]


def case_logo():
    doc = fitz.open()
    p = _page(doc)
    sh = p.new_shape()
    sh.draw_circle((300, 300), 30)
    sh.finish(color=(0, 0.3, 0.6), fill=(0.2, 0.5, 0.8), width=2)
    sh.draw_line((280, 300), (320, 300))
    sh.finish(color=(1, 1, 1), width=3)
    sh.commit()
    p.insert_text((80, 400), "Client logo above is confidential.", fontsize=11)
    return doc, [fitz.Rect(260, 260, 340, 340)]


def case_shapes():
    doc = fitz.open()
    p = _page(doc)
    p.draw_circle((150, 300), 30, color=(0, 0.3, 0.6), width=2)            # stroke only
    p.draw_rect(fitz.Rect(330, 270, 390, 330), color=None, fill=(0.8, 0.2, 0.2))  # fill only
    p.insert_text((80, 400), "Two marks above are confidential.", fontsize=11)
    return doc, [fitz.Rect(110, 260, 190, 340), fitz.Rect(320, 260, 400, 340)]


def case_band():
    doc = fitz.open()
    p = _page(doc)
    p.draw_rect(fitz.Rect(60, 120, 540, 150), color=None, fill=(0.85, 0.9, 1))
    p.insert_text((70, 140), "Name        Salary        Bonus        Grade", fontsize=11)
    p.draw_rect(fitz.Rect(60, 150, 540, 300), color=(0.3, 0.3, 0.3), width=0.8)
    p.insert_text((70, 175), "A. Bianchi   52,000   4,000   B2", fontsize=11)
    return doc, [fitz.Rect(150, 115, 260, 185)]


CASES = {
    "table": case_table,
    "table_rot90": lambda: case_table(90),
    "signature": case_signature,
    "chart": case_chart,
    "underline": case_underline,
    "logo": case_logo,
    "shapes": case_shapes,
    "band": case_band,
}


# ── Strategies ────────────────────────────────────────────────────────────────
def _apply(page, boxes, graphics, fill):
    for b in boxes:
        page.add_redact_annot(b, fill=fill)
    page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_PIXELS, graphics=graphics)


def _clip_segment(p, q, r):
    """Parts of segment p-q outside rect r (Liang-Barsky on the inside part)."""
    dx, dy = q.x - p.x, q.y - p.y
    t0, t1 = 0.0, 1.0
    for pk, qk in ((-dx, p.x - r.x0), (dx, r.x1 - p.x), (-dy, p.y - r.y0), (dy, r.y1 - p.y)):
        if pk == 0:
            if qk < 0:
                return [(p, q)]
            continue
        t = qk / pk
        if pk < 0:
            t0 = max(t0, t)
        else:
            t1 = min(t1, t)
    if t0 >= t1:
        return [(p, q)]
    at = lambda t: fitz.Point(p.x + t * dx, p.y + t * dy)  # noqa: E731
    out = []
    if t0 > 0:
        out.append((p, at(t0)))
    if t1 < 1:
        out.append((at(t1), q))
    return out


def _bezier_points(p0, p1, p2, p3, n=24):
    pts = []
    for i in range(n + 1):
        t = i / n
        u = 1 - t
        pts.append(fitz.Point(
            u**3 * p0.x + 3 * u * u * t * p1.x + 3 * u * t * t * p2.x + t**3 * p3.x,
            u**3 * p0.y + 3 * u * u * t * p1.y + 3 * u * t * t * p2.y + t**3 * p3.y))
    return pts


def _segments(item):
    kind = item[0]
    if kind == "l":
        return [(item[1], item[2])]
    if kind == "c":
        pts = _bezier_points(*item[1:5])
        return list(zip(pts, pts[1:]))
    if kind == "re":
        r = item[1]
        c = [r.tl, r.tr, r.br, r.bl, r.tl]
        return list(zip(c, c[1:]))
    if kind == "qu":
        q = item[1]
        c = [q.ul, q.ur, q.lr, q.ll, q.ul]
        return list(zip(c, c[1:]))
    return []


def _clip_redraw(page, boxes, fill):
    """Remove every path a box touches, then redraw only the parts outside the boxes.

    Strokes are cut exactly at the box edge (curves flattened to 24 segments).
    Filled rectangles are cut exactly (rect minus boxes); other filled shapes a
    box touches are dropped, since cutting them needs general polygon clipping."""
    # get_drawings() reports unrotated page coordinates; boxes are in that space too.
    # A horizontal or vertical line has an empty rect, which intersects nothing;
    # widen every rect by half its stroke before testing.
    def hit(d):
        e = (d.get("width") or 1) / 2 + 0.01
        r = d["rect"] + (-e, -e, e, e)
        return any(r.intersects(b) for b in boxes)
    touched = [d for d in page.get_drawings() if hit(d)]
    _apply(page, boxes, fitz.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED, fill)
    sh = page.new_shape()
    # Re-added fills go underneath the page content so they do not cover text
    # that was drawn over them; re-added strokes go on top.
    under = page.new_shape()
    for d in touched:
        if d.get("fill") is not None and all(it[0] == "re" for it in d["items"]):
            for it in d["items"]:
                for r in _rect_minus(it[1], boxes):
                    under.draw_rect(r)
            under.finish(color=None, fill=d["fill"], fill_opacity=d.get("fill_opacity") or 1)
        if d.get("color") is None:
            continue
        pieces = []
        for item in d["items"]:
            for seg in _segments(item):
                parts = [seg]
                for b in boxes:
                    parts = [pp for s in parts for pp in _clip_segment(s[0], s[1], b)]
                pieces.extend(parts)
        for a, b in pieces:
            sh.draw_line(a, b)
        if pieces:
            sh.finish(color=d["color"], width=d.get("width") or 1, closePath=False,
                      lineCap=max(d.get("lineCap") or (0,)) if d.get("lineCap") else 0,
                      dashes=d.get("dashes") or None,
                      stroke_opacity=d.get("stroke_opacity") or 1)
    under.commit(overlay=False)
    sh.commit()


def _rect_minus(r, boxes):
    """Axis-aligned pieces of rect r not covered by any box."""
    pieces = [fitz.Rect(r)]
    for b in boxes:
        nxt = []
        for p in pieces:
            if not p.intersects(b):
                nxt.append(p)
                continue
            if p.y0 < b.y0:
                nxt.append(fitz.Rect(p.x0, p.y0, p.x1, b.y0))
            if b.y1 < p.y1:
                nxt.append(fitz.Rect(p.x0, b.y1, p.x1, p.y1))
            y0, y1 = max(p.y0, b.y0), min(p.y1, b.y1)
            if p.x0 < b.x0:
                nxt.append(fitz.Rect(p.x0, y0, b.x0, y1))
            if b.x1 < p.x1:
                nxt.append(fitz.Rect(b.x1, y0, p.x1, y1))
        pieces = [q for q in nxt if not q.is_empty]
    return pieces


def _rasterise(page_doc, pno, boxes, fill):
    """LibreOffice-style: redact, then replace the page by a picture of itself."""
    page = page_doc[pno]
    # The opaque fill paints over whatever line art stays; the picture keeps only that.
    _apply(page, boxes, fitz.PDF_REDACT_LINE_ART_NONE, fill if fill else (0, 0, 0))
    pix = page.get_pixmap(dpi=200)
    rect, rot = page.rect, page.rotation
    page_doc.delete_page(pno)
    np = page_doc.new_page(pno, width=rect.width, height=rect.height)
    np.insert_image(np.rect, pixmap=pix)
    return rot


STRATEGIES = {
    "none (0)":        lambda doc, b, fill: _apply(doc[0], b, fitz.PDF_REDACT_LINE_ART_NONE, fill),
    "covered (1, now)": lambda doc, b, fill: _apply(doc[0], b, fitz.PDF_REDACT_LINE_ART_REMOVE_IF_COVERED, fill),
    "touched (2)":     lambda doc, b, fill: _apply(doc[0], b, fitz.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED, fill),
    "clip at edge":    lambda doc, b, fill: _clip_redraw(doc[0], b, fill),
    "rasterise page":  lambda doc, b, fill: _rasterise(doc, 0, b, fill),
}


# ── Metrics ───────────────────────────────────────────────────────────────────
def _gray(page, clip=None):
    pix = page.get_pixmap(dpi=DPI, colorspace=fitz.csGRAY, alpha=False, clip=clip)
    return pix


def _ink_mask(page):
    pix = _gray(page)
    return pix.width, pix.height, bytes(pix.samples)


def _box_pixels(page, boxes, w, h):
    """Pixel indices inside any box (boxes in unrotated space → shown space)."""
    s = DPI / 72
    m = page.rotation_matrix
    idx = set()
    for b in boxes:
        r = (fitz.Rect(b) * m)
        r = fitz.Rect(r.x0 * s, r.y0 * s, r.x1 * s, r.y1 * s)
        for y in range(max(0, int(r.y0) + 1), min(h, int(r.y1) - 1)):
            row = y * w
            idx.update(range(row + max(0, int(r.x0) + 1), row + min(w, int(r.x1) - 1)))
    return idx


def _box_pixels_margin(page, boxes, w, h, margin):
    s = DPI / 72
    m = page.rotation_matrix
    idx = set()
    for b in boxes:
        r = fitz.Rect(b) * m
        r = fitz.Rect(r.x0 * s - margin, r.y0 * s - margin, r.x1 * s + margin, r.y1 * s + margin)
        for y in range(max(0, int(r.y0)), min(h, int(math.ceil(r.y1)))):
            row = y * w
            idx.update(range(row + max(0, int(r.x0)), row + min(w, int(math.ceil(r.x1)))))
    return idx


def _words_outside(page, boxes):
    m = page.rotation_matrix
    shown = [fitz.Rect(b) * m for b in boxes]
    out = []
    for w in page.get_text("words"):
        r = fitz.Rect(w[:4]) * m if False else fitz.Rect(w[:4])
        if not any(r.intersects(b) for b in shown):
            out.append(w[4])
    return out


def measure(case_name, strat_name):
    make = CASES[case_name]
    src_doc, boxes = make()
    src_bytes = src_doc.tobytes()
    src = fitz.open("pdf", src_bytes)
    w, h, before = _ink_mask(src[0])
    inbox = _box_pixels(src[0], boxes, w, h)
    near = _box_pixels_margin(src[0], boxes, w, h, margin=3)
    words_before = _words_outside(src[0], boxes)

    # Leak: run with no fill so whatever the strategy left under the box shows.
    leak_doc = fitz.open("pdf", src_bytes)
    STRATEGIES[strat_name](leak_doc, boxes, False)
    if strat_name == "rasterise page":
        leak = 0.0  # pixels under the box were painted before the page became an image
        lw, lh = w, h
    else:
        lw, lh, after_nofill = _ink_mask(leak_doc[0])
        ink_in = sum(1 for i in inbox if after_nofill[i] < 200)
        ink_in_before = sum(1 for i in inbox if before[i] < 200) or 1
        leak = ink_in / ink_in_before

    # Collateral and the rest: run as the app does (black fill), save like the app.
    real = fitz.open("pdf", src_bytes)
    STRATEGIES[strat_name](real, boxes, (0, 0, 0))
    buf = io.BytesIO()
    real.save(buf, garbage=4, deflate=True, clean=True)
    out = fitz.open("pdf", buf.getvalue())
    ow, oh, after = _ink_mask(out[0])
    assert (ow, oh) == (w, h), (case_name, strat_name, (ow, oh), (w, h))
    outside = [i for i in range(w * h) if i not in near]
    ink_out_before = [i for i in outside if before[i] < 200]
    changed = sum(1 for i in ink_out_before if abs(before[i] - after[i]) > 64)
    collateral = changed / (len(ink_out_before) or 1)
    words_after = set(_words_outside(out[0], boxes)) if out[0].get_text().strip() else set()
    search = (sum(1 for x in words_before if x in words_after) / len(words_before)
              if words_before else 1.0)
    return {"case": case_name, "strategy": strat_name, "leak": round(leak, 4),
            "collateral": round(collateral, 4), "search": round(search, 3),
            "size_ratio": round(len(buf.getvalue()) / len(src_bytes), 2)}


def main():
    rows = [measure(c, s) for c in CASES for s in STRATEGIES]
    OUT.write_text(json.dumps(rows, indent=1), encoding="utf-8")
    cases = list(CASES)
    print(f"{'strategy':18}" + "".join(f"{c:>13}" for c in cases))
    for s in STRATEGIES:
        for metric in ("leak", "collateral", "search", "size_ratio"):
            vals = {r["case"]: r[metric] for r in rows if r["strategy"] == s}
            print(f"{s[:12] + ' ' + metric[:5]:18}" + "".join(f"{vals[c]:>13}" for c in cases))
        print()


if __name__ == "__main__":
    main()
