"""Redaction cuts line art at the box edge (L3-18).

Each page is redacted twice: through the Redact tool as a user does it (black fill,
saved to disk), and through redact_page() with no fill, so whatever was left under
a box shows when the page is rendered.  Checked for every case:
- leak: no ink inside the boxes without the fill, and no path outline in them;
- collateral: the page outside the boxes renders as before;
- text outside the boxes is still searchable.
"""
import math

import pymupdf as fitz
import pytest

from conftest import tool, wait_job

DPI = 144
S = DPI / 72


# ── pages ─────────────────────────────────────────────────────────────────────
def _raw_page(doc, content: bytes, resources: str = "<<>>", rotate=0, cropbox=None):
    p = doc.new_page(width=595, height=842)
    xr = doc.get_new_xref()
    doc.update_object(xr, "<<>>")
    doc.update_stream(xr, content)
    doc.xref_set_key(p.xref, "Contents", f"{xr} 0 R")
    doc.xref_set_key(p.xref, "Resources", resources)
    if cropbox:
        doc.xref_set_key(p.xref, "CropBox", cropbox)
    if rotate:
        p = doc[p.number]
        p.set_rotation(rotate)
    return doc[p.number]


def case_table(rotate=0):
    doc = fitz.open()
    p = doc.new_page()
    if rotate:
        p.set_rotation(rotate)
    x0, y0, cw, ch, n = 80, 120, 85, 30, 5
    sh = p.new_shape()
    for i in range(n + 1):
        sh.draw_line((x0, y0 + i * ch), (x0 + n * cw, y0 + i * ch))
        sh.draw_line((x0 + i * cw, y0), (x0 + i * cw, y0 + n * ch))
    sh.finish(color=(0, 0, 0), width=1)
    sh.commit()
    for r in range(n):
        for c in range(n):
            p.insert_text((x0 + c * cw + 6, y0 + r * ch + 20), f"R{r}C{c}", fontsize=9)
    return doc, [fitz.Rect(x0 + 2 * cw - 2, y0 + 2 * ch - 2, x0 + 3 * cw + 2, y0 + 3 * ch + 2)]


def case_signature():
    doc = fitz.open()
    p = doc.new_page()
    p.insert_text((80, 200), "Signed on behalf of the applicant", fontsize=11)
    sh = p.new_shape()
    pts = [(100, 300), (140, 250), (180, 330), (220, 260), (260, 320), (300, 255),
           (340, 315), (380, 270), (420, 300)]
    for a, b, c in zip(pts[::2], pts[1::2], pts[2::2], strict=False):
        sh.draw_bezier(a, b, b, c)
    sh.finish(color=(0, 0, 0.5), width=1.6)
    sh.commit()
    return doc, [fitz.Rect(250, 240, 440, 340)]


def case_chart():
    doc = fitz.open()
    p = doc.new_page()
    sh = p.new_shape()
    sh.draw_rect(fitz.Rect(80, 150, 520, 450))
    sh.finish(color=(0.4, 0.4, 0.4), width=0.8)
    sh.draw_polyline([(100 + i * 45, v) for i, v in
                      enumerate([400, 330, 360, 250, 280, 190, 230, 170, 210, 160])])
    sh.finish(color=(0.8, 0, 0), width=2)
    sh.commit()
    p.insert_text((80, 480), "Quarterly revenue", fontsize=10)
    return doc, [fitz.Rect(270, 140, 380, 460)]


def case_logo():
    doc = fitz.open()
    p = doc.new_page()
    sh = p.new_shape()
    sh.draw_circle((300, 300), 30)
    sh.finish(color=(0, 0.3, 0.6), fill=(0.2, 0.5, 0.8), width=2)
    sh.commit()
    p.insert_text((80, 400), "Client logo above", fontsize=11)
    # Half the filled circle sits in the box: a non-rectangular fill to cut.
    return doc, [fitz.Rect(300, 250, 360, 350)]


def case_shapes():
    doc = fitz.open()
    p = doc.new_page()
    p.draw_circle((150, 300), 30, color=(0, 0.3, 0.6), width=2)
    p.draw_rect(fitz.Rect(330, 270, 390, 330), color=None, fill=(0.8, 0.2, 0.2))
    return doc, [fitz.Rect(110, 260, 190, 340), fitz.Rect(320, 260, 400, 340)]


def case_band():
    doc = fitz.open()
    p = doc.new_page()
    p.draw_rect(fitz.Rect(60, 120, 540, 150), color=None, fill=(0.85, 0.9, 1))
    p.insert_text((70, 140), "Name        Salary        Bonus", fontsize=11)
    p.draw_rect(fitz.Rect(60, 150, 540, 300), color=(0.3, 0.3, 0.3), width=0.8)
    return doc, [fitz.Rect(150, 115, 260, 185)]


def case_order():
    """A white sheet drawn over part of a line must keep hiding it."""
    doc = fitz.open()
    p = doc.new_page()
    p.draw_line((80, 300), (500, 300), color=(1, 0, 0), width=4)
    p.draw_rect(fitz.Rect(400, 280, 520, 320), color=None, fill=(1, 1, 1))
    p.draw_rect(fitz.Rect(60, 200, 520, 220), color=None, fill=(0, 0.6, 0))
    p.draw_line((80, 210), (500, 210), color=(1, 1, 0), width=2)   # drawn over the band
    return doc, [fitz.Rect(200, 190, 260, 320)]


def case_dashed():
    doc = fitz.open()
    p = doc.new_page()
    p.draw_line((80, 300), (520, 300), color=(0, 0, 0), width=2, dashes="[9 4] 0")
    sh = p.new_shape()
    sh.draw_circle((300, 500), 80)
    sh.finish(color=(0, 0, 1), width=1.5, dashes="[6 3 1 3] 2")
    sh.commit()
    return doc, [fitz.Rect(203, 290, 251, 310), fitz.Rect(280, 400, 400, 470)]


def case_evenodd():
    """A frame (outer square, inner hole) filled even-odd, cut through the hole."""
    doc = fitz.open()
    _raw_page(doc, b"0.2 0.4 0.8 rg 100 400 300 300 re 175 475 150 150 re f* "
                   b"0.8 0.2 0 rg 400 100 m 520 100 520 260 400 260 c h f")
    return doc, [fitz.Rect(230, 140, 300, 470), fitz.Rect(440, 560, 560, 620)]


def case_shading():
    doc = fitz.open()
    res = ("<</Shading<</S1<</ShadingType 2/ColorSpace/DeviceRGB/Coords[100 0 500 0]"
           "/Function<</FunctionType 2/Domain[0 1]/C0[1 0 0]/C1[0 0 1]/N 1>>"
           "/Extend[true true]>>>>>>")
    _raw_page(doc, b"q 100 300 400 300 re W n /S1 sh Q", res)
    return doc, [fitz.Rect(250, 300, 350, 400)]


def case_clip():
    """A circle used as a clip path, then a filled square painted through it."""
    doc = fitz.open()
    # Four Béziers, centre (300, 542) in PDF space, radius 80.
    k = 0.5523
    cx, cy, r = 300, 542, 80
    pts = []
    for a in range(4):
        a0, a1 = a * math.pi / 2, (a + 1) * math.pi / 2
        p0 = (cx + r * math.cos(a0), cy + r * math.sin(a0))
        p3 = (cx + r * math.cos(a1), cy + r * math.sin(a1))
        p1 = (p0[0] - k * r * math.sin(a0), p0[1] + k * r * math.cos(a0))
        p2 = (p3[0] + k * r * math.sin(a1), p3[1] - k * r * math.cos(a1))
        pts.append((p0, p1, p2, p3))
    c = f"q {pts[0][0][0]:.3f} {pts[0][0][1]:.3f} m ".encode()
    for _, p1, p2, p3 in pts:
        c += f"{p1[0]:.3f} {p1[1]:.3f} {p2[0]:.3f} {p2[1]:.3f} {p3[0]:.3f} {p3[1]:.3f} c ".encode()
    c += b"h W n 0 0.5 0 rg 150 392 300 300 re f Q"
    _raw_page(doc, c)
    return doc, [fitz.Rect(300, 230, 420, 330)]


def case_form():
    """Line art inside a Form XObject, shown on two pages; only page 0 is redacted."""
    src = fitz.open()
    sp = src.new_page()
    sp.draw_line((50, 300), (550, 300), color=(0.5, 0, 0.5), width=3)
    sp.draw_circle((300, 300), 60, color=(0, 0, 0), width=2)
    doc = fitz.open()
    for _ in range(2):
        doc.new_page().show_pdf_page(fitz.Rect(0, 0, 595, 842), src, 0)
    return doc, [fitz.Rect(270, 250, 400, 320)]


def case_rotated_cropped():
    doc = fitz.open()
    p = doc.new_page()
    p.draw_line((80, 300), (500, 340), color=(0, 0, 0), width=2)
    p.draw_circle((300, 500), 50, color=(0, 0.4, 0), fill=(0.6, 0.9, 0.6), width=2)
    p.insert_text((90, 250), "Kept heading", fontsize=12)
    p.set_cropbox(fitz.Rect(40, 200, 560, 700))
    p.set_rotation(90)
    return doc, [fitz.Rect(250, 280, 330, 360), fitz.Rect(310, 430, 400, 560)]


def case_many_boxes():
    doc = fitz.open()
    p = doc.new_page()
    p.draw_rect(fitz.Rect(40, 40, 555, 800), color=None, fill=(0.95, 0.95, 0.8))
    boxes = []
    for i in range(60):
        x, y = 60 + (i % 6) * 80, 60 + (i // 6) * 70
        p.insert_text((x, y + 20), f"ID{i:03}", fontsize=10)
        boxes.append(fitz.Rect(x - 2, y + 8, x + 40, y + 24))
    return doc, boxes


def case_syntax():
    """Operator-like words in strings, escapes, comments, marked content, an inline
    image whose data holds the bytes 'EI', and v / y curves under a skewed CTM."""
    img = bytes([0x45, 0x49, 0x20, 0x0A] * 4)          # 'EI \n' as pixel data, 4x2 RGB...
    img = (img * 2)[:24]                                  # 4 x 2 RGB = 24 bytes
    content = (
        b"% a comment with re S f inside\n"
        b"/Span <</MCID 0 /Alt (a\\) re S \\(f) >> BDC\n"
        b"BT /F1 12 Tf 80 760 Td (Kept: re S f m l \\(x\\)) Tj ET EMC\n"
        b"q 1 0 0.3 1 0 0 cm 0 0 1 RG 3 w 60 600 m 160 650 260 560 v 300 600 360 640 y "
        b"460 600 l S Q\n"
        b"q 60 0 0 30 400 450 cm BI /W 4 /H 2 /BPC 8 /CS /RGB ID " + img + b"\nEI Q\n"
        b"q 0.7071 0.7071 -0.7071 0.7071 300 250 cm 1 0 0 rg -80 -10 160 20 re f Q\n"
        b"q 120 120 200 200 re 160 160 120 120 re W* n 0 0.6 0.3 rg 100 100 240 240 re f Q\n")
    res = "<</Font<</F1<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>>>>>"
    doc = fitz.open()
    _raw_page(doc, content, res)
    return doc, [fitz.Rect(150, 160, 230, 300), fitz.Rect(280, 560, 340, 640),
                 fitz.Rect(230, 690, 270, 740)]


def case_nested_form():
    inner = fitz.open()
    ip = inner.new_page(width=300, height=300)
    ip.draw_line((0, 150), (300, 150), color=(0, 0, 0), width=4)
    ip.draw_circle((150, 150), 60, color=(0.5, 0, 0), fill=(1, 0.8, 0.8), width=2)
    mid = fitz.open()
    mp = mid.new_page(width=400, height=400)
    mp.show_pdf_page(fitz.Rect(50, 50, 350, 350), inner, 0, rotate=30)
    doc = fitz.open()
    doc.new_page().show_pdf_page(fitz.Rect(100, 200, 500, 600), mid, 0)
    return doc, [fitz.Rect(280, 360, 340, 460)]


def case_bars():
    """A bar chart whose bar tops are the secret: their corners lie in the box."""
    doc = fitz.open()
    p = doc.new_page()
    for i, h in enumerate((120, 260, 190, 310)):
        p.draw_rect(fitz.Rect(100 + i * 70, 600 - h, 150 + i * 70, 600), color=None,
                    fill=(0.2, 0.4, 0.8))
    return doc, [fitz.Rect(90, 250, 380, 420)]


def case_soft_mask():
    """Shapes inside a soft mask's group (Figma, Inkscape, Illustrator put them there)."""
    doc = fitz.open()
    mask = doc.get_new_xref()
    doc.update_object(mask, "<</Type/XObject/Subtype/Form/BBox[0 0 595 842]"
                            "/Group<</S/Transparency/CS/DeviceGray>>>>")
    doc.update_stream(mask, b"0 g 0 0 595 842 re f 1 g 200 400 m 400 400 l 300 600 l h f")
    res = (f"<</ExtGState<</E1<</Type/ExtGState/SMask<</Type/Mask/S/Luminosity/G {mask} 0 R>>"
           f">>>>>>")
    _raw_page(doc, b"q /E1 gs 0 0 1 rg 100 300 400 400 re f Q", res)
    return doc, [fitz.Rect(270, 220, 330, 330)]


def case_cell_clip():
    """Text drawn through a rectangular cell clip, the box over part of the cell."""
    doc = fitz.open()
    content = (b"q 26 750 262 58 re W n BT /F1 11 Tf 30 752 Td (gypsy jq descenders at the edge) Tj "
               b"ET Q")
    _raw_page(doc, content, "<</Font<</F1<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>>>>>")
    return doc, [fitz.Rect(230, 30, 300, 80)]


def case_tiling_pattern():
    """A page background painted with a tiling pattern (ONLYOFFICE does this)."""
    doc = fitz.open()
    pat = doc.get_new_xref()
    doc.update_object(pat, "<</Type/Pattern/PatternType 1/PaintType 1/TilingType 1"
                           "/BBox[0 0 40 40]/XStep 40/YStep 40/Resources<<>>>>")
    doc.update_stream(pat, b"0.8 0.3 0.1 rg 0 0 20 20 re f 0.1 0.3 0.8 rg 20 20 20 20 re f")
    _raw_page(doc, b"/Pattern cs /P1 scn 0 0 595.27 841.89 re f",
              f"<</Pattern<</P1 {pat} 0 R>>>>")
    return doc, [fitz.Rect(100, 300, 180, 360), fitz.Rect(150, 330, 260, 380)]


def case_cell_clip_edge():
    """The same cell, the box across its edge with every clip corner outside: MuPDF
    draws a rectangle clip without anti-aliasing, a cut-up one with it."""
    doc, _ = case_cell_clip()
    return doc, [fitz.Rect(250, 40, 320, 70)]


def case_form_bbox():
    """Small forms whose BBox (an implicit clip) has a corner in the box, and a clip
    that lies wholly inside the box, in a form whose origin is in the box too."""
    doc = fitz.open()
    small = doc.get_new_xref()
    doc.update_object(small, "<</Type/XObject/Subtype/Form/BBox[0 0 72 72]>>")
    doc.update_stream(small, b"0.9 0.5 0.1 rg -50 -50 200 200 re f")
    inner = doc.get_new_xref()
    doc.update_object(inner, "<</Type/XObject/Subtype/Form/BBox[-100 -100 100 100]>>")
    doc.update_stream(inner, b"q 5 5 10 10 re W n 0 0 1 rg -100 -100 200 200 re f Q "
                             b"0 g 1 w -60 0 m 60 0 l S")
    res = f"<</XObject<</F1 {small} 0 R/F2 {inner} 0 R>>>>"
    _raw_page(doc, b"q 0.3 0 0 0.3 150 500 cm /F1 Do Q q 0.3 0 0 0.3 400 500 cm /F1 Do Q "
                   b"q 1 0 0 1 300 200 cm /F2 Do Q", res)
    return doc, [fitz.Rect(155, 310, 200, 350), fitz.Rect(270, 610, 330, 670)]


CASES = {
    "form_bbox": case_form_bbox, "bars": case_bars, "soft_mask": case_soft_mask, "cell_clip": case_cell_clip,
    "cell_clip_edge": case_cell_clip_edge,
    "tiling_pattern": case_tiling_pattern,
    "syntax": case_syntax, "nested_form": case_nested_form,
    "table": case_table, "table_rot90": lambda: case_table(90), "signature": case_signature,
    "chart": case_chart, "logo": case_logo, "shapes": case_shapes, "band": case_band,
    "order": case_order, "dashed": case_dashed, "evenodd": case_evenodd,
    "shading": case_shading, "clip": case_clip, "form": case_form,
    "rotated_cropped": case_rotated_cropped, "many_boxes": case_many_boxes,
}


# ── measurements ──────────────────────────────────────────────────────────────
def _gray(page):
    pix = page.get_pixmap(dpi=DPI, colorspace=fitz.csGRAY, alpha=False)
    return pix.width, pix.height, pix.samples


def _box_pixels(page, boxes, w, h, grow):
    """Pixel indices of the boxes on the rendered (rotated, cropped) page."""
    m = page.rotation_matrix
    out = set()
    for b in boxes:
        r = fitz.Rect(b) * m
        r = fitz.Rect(r.x0 * S - grow, r.y0 * S - grow, r.x1 * S + grow, r.y1 * S + grow)
        for y in range(max(0, math.floor(r.y0)), min(h, math.ceil(r.y1))):
            out.update(range(y * w + max(0, math.floor(r.x0)), y * w + min(w, math.ceil(r.x1))))
    return out


def _outlines_inside(page, boxes, eps=0.05):
    """Shape left in the boxes: any vertex of a path, and any point along a stroked
    path.  (A fill whose vertices all lie outside may run through a box: nothing
    there is hidden, and the pixel check proves it is not painted.  Control points
    are off the path.)"""
    inner = [fitz.Rect(b.x0 + eps, b.y0 + eps, b.x1 - eps, b.y1 - eps) for b in boxes]
    bad = []
    for d in page.get_drawings(extended=True):
        if d["type"] == "group":
            continue
        for it in d["items"]:
            pts = ([it[1]] if it[0] in ("re", "qu") else [it[1], it[4]] if it[0] == "c"
                   else [it[1], it[2]])
            pts = (list(fitz.Rect(pts[0]).quad) if it[0] == "re"
                   else list(pts[0]) if it[0] == "qu" else pts)
            bad += [("point", tuple(round(v, 2) for v in p)) for p in pts
                    if any(p in r for r in inner)]
        if "s" not in d["type"]:
            continue
        for it in d["items"]:
            if it[0] == "l":
                curve = [it[1], it[2]]
            elif it[0] == "c":
                p0, p1, p2, p3 = it[1:5]
                curve = [p0 * (1 - t) ** 3 + p1 * 3 * (1 - t) ** 2 * t + p2 * 3 * (1 - t) * t * t
                         + p3 * t ** 3 for t in (i / 40 for i in range(41))]
            elif it[0] == "re":
                r = it[1]
                curve = [r.tl, r.tr, r.br, r.bl, r.tl]
            else:
                q = it[1]
                curve = [q.ul, q.ur, q.lr, q.ll, q.ul]
            for a, b in zip(curve, curve[1:], strict=False):
                for k in range(11):
                    pt = a + (b - a) * (k / 10)
                    if any(pt in r for r in inner):
                        bad.append((it[0], tuple(round(v, 2) for v in pt)))
    return bad


def _words_outside(page, boxes):
    return sorted(w[4] for w in page.get_text("words")
                  if not any(fitz.Rect(w[:4]).intersects(b) for b in boxes))


def _redact_with_tool(app, dialogs, tmp_path, name, src_bytes, boxes, pno=0):
    from paperknife.tools.redact import RedactTool  # noqa: F401  (registered)
    src = tmp_path / f"{name}.pdf"
    src.write_bytes(src_bytes)
    out = tmp_path / f"{name}_redacted.pdf"
    t = tool(app, "RedactTool")
    dialogs.open(str(src))
    t._open()
    t._pending = [(pno, fitz.Rect(b), None) for b in boxes]
    dialogs.asks.append(True)
    t._apply()
    wait_job(app)
    dialogs.save(out)
    t._save()
    wait_job(app)
    assert not dialogs.errors(), dialogs.errors()
    return out


def _redact_page():
    from paperknife.tools import redact
    if hasattr(redact, "redact_page"):
        return redact.redact_page

    def baseline(doc, pno, rects, fill):     # what RedactTool._apply did before L3-18
        page = doc[pno]
        for r in rects:
            page.add_redact_annot(r, fill=fill if fill is not None else False)
        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_PIXELS)
    return baseline


@pytest.mark.parametrize("name", list(CASES))
def test_line_art_is_cut_at_the_box_edge(app, dialogs, tmp_path, name):
    redact_page = _redact_page()
    doc, boxes = CASES[name]()
    src_bytes = doc.tobytes()
    doc.close()
    with fitz.open("pdf", src_bytes) as src:
        w, h, before = _gray(src[0])
        # A butt cap cut at an angle reaches half a line width into the box (2 px
        # here); that ink belongs to the line outside, _outlines_inside checks geometry.
        inside = _box_pixels(src[0], boxes, w, h, grow=-3)
        near = _box_pixels(src[0], boxes, w, h, grow=2.5)
        words_before = _words_outside(src[0], boxes)

    # Leak: no fill, so whatever is left under the boxes shows.
    with fitz.open("pdf", src_bytes) as bare:
        cut = redact_page(bare, 0, boxes, fill=None)
        assert cut in (None, "cut"), f"fell back: {cut}"     # None: the baseline
        bw, bh, after_bare = _gray(bare[0])
        assert (bw, bh) == (w, h)
        ink = [i for i in inside if after_bare[i] < 250]
        assert not ink, f"{len(ink)} ink pixels left under the boxes"
        assert _outlines_inside(bare[0], boxes) == []

    # As a user does it: through the tool, black fill, saved.
    out = _redact_with_tool(app, dialogs, tmp_path, name, src_bytes, boxes)
    with fitz.open(out) as red:
        _, _, after = _gray(red[0])
        outside_ink = [i for i in range(w * h) if i not in near and before[i] < 250]
        changed = [i for i in outside_ink if abs(before[i] - after[i]) > 48]
        assert len(changed) <= max(2, len(outside_ink) // 1000), \
            f"{len(changed)} of {len(outside_ink)} ink pixels outside the boxes changed"
        assert set(words_before) <= set(_words_outside(red[0], boxes))


def test_curves_stay_curves(app, dialogs, tmp_path):
    doc, boxes = case_signature()
    out = _redact_with_tool(app, dialogs, tmp_path, "sigc", doc.tobytes(), boxes)
    with fitz.open(out) as red:
        kinds = [it[0] for d in red[0].get_drawings() for it in d["items"]]
    # Two curves lie outside the box, one of them cut at its edge; the closing
    # line is cut too.  No polyline: a flattened curve would be many l items.
    assert kinds.count("c") == 2 and kinds.count("l") == 1, kinds


def test_form_shared_by_another_page_keeps_its_line_art(app, dialogs, tmp_path):
    doc, boxes = case_form()
    before = len(doc[1].get_drawings())
    pts_before = sorted(str(it) for d in doc[1].get_drawings() for it in d["items"])
    out = _redact_with_tool(app, dialogs, tmp_path, "form2", doc.tobytes(), boxes)
    with fitz.open(out) as red:
        assert len(red[1].get_drawings()) == before
        assert sorted(str(it) for d in red[1].get_drawings() for it in d["items"]) == pts_before
        assert _outlines_inside(red[0], boxes) == []


@pytest.mark.parametrize("content", [
    b"0 0 1 RG 3 w 60 600 m 360 640 y 460 600 l S",          # too few: zeros fill in
    b"0 0 1 RG 3 w 60 600 m 300 700 9 9 l 200 100 500 200 600 400 7 c S",  # too many
])
def test_wrong_operand_counts_are_read_as_mupdf_reads_them(content):
    from paperknife.lineart import cut_line_art
    doc = fitz.open()
    page = _raw_page(doc, content)
    boxes = [fitz.Rect(150, 150, 260, 320), fitz.Rect(330, 500, 420, 760)]
    assert _outlines_inside(page, boxes), "the case must draw into the boxes"
    cut_line_art(page, boxes)
    assert _outlines_inside(page, boxes) == []


def test_a_stream_read_differently_falls_back_without_leaking():
    # MuPDF reads '--300' as -300; this module treats it as an unknown keyword, so
    # its cut follows a different line.  The MuPDF-side check must catch that.
    from paperknife.lineart import residual
    from paperknife.tools.redact import redact_page
    doc = fitz.open()
    _raw_page(doc, b"0 0 1 RG 4 w 100 600 m 300 --300 l S")
    page = doc[0]
    seg = page.get_drawings()[0]["items"][0]
    mid = (seg[1] + seg[2]) / 2
    box = fitz.Rect(mid.x - 20, mid.y - 20, mid.x + 20, mid.y + 20)
    assert residual(page, [box])
    assert redact_page(doc, 0, [box], fill=None) == "whole"
    assert not residual(doc[0], [box])
    pix = doc[0].get_pixmap(clip=box + (3, 3, -3, -3), alpha=False)
    assert set(pix.samples) == {255}


@pytest.mark.parametrize("content", [
    b"EI BI /W -35 /H 1 /BPC 8 /CS /G ID x\nEI",                     # used to hang
    b"BI /W 1 ",                                                     # IndexError
    b"BI [1] 2 ID x EI",                                             # TypeError
    b"BI /W " + b"9" * 400 + b" /H 1 /BPC 8 /CS /G ID x EI",        # OverflowError
])
def test_malformed_inline_images_do_not_crash(content):
    from paperknife.lineart import cut_line_art
    doc = fitz.open()
    cut_line_art(_raw_page(doc, content + b" 0 g 10 10 m 300 300 l S"),
                 [fitz.Rect(100, 500, 200, 600)])


def test_soft_mask_reached_through_an_escaped_name_or_inside_a_path_is_cut():
    from paperknife.lineart import residual
    from paperknife.tools.redact import redact_page
    for content in (b"q /E#31 gs 0 0 1 rg 100 300 400 400 re f Q",
                    b"q 0 0 1 rg 100 300 m 500 300 l 500 700 l /E1 gs 100 700 l h f Q"):
        doc, boxes = case_soft_mask()
        doc.update_stream(doc[0].get_contents()[0], content)
        assert residual(doc[0], boxes), "the case must have mask shape in the box"
        assert redact_page(doc, 0, boxes, None) == "cut", content
        assert not residual(doc[0], boxes)


def test_an_edge_seen_only_inside_a_box_is_cut_even_with_its_vertices_off_page():
    # The top edge runs from x=-100 to 695: on the page it lies wholly inside the
    # full-width box, so where it lies is hidden even though no vertex is.
    from paperknife.lineart import residual
    from paperknife.tools.redact import redact_page
    doc = fitz.open()
    _raw_page(doc, b"0 0 1 rg -100 480 m 695 500 l 695 0 l -100 0 l h f")
    box = [fitz.Rect(0, 300, 595, 400)]
    assert residual(doc[0], box)
    assert redact_page(doc, 0, box, None) == "cut"
    assert not residual(doc[0], box)
    edges = [it for d in doc[0].get_drawings() for it in d["items"] if it[0] == "l"]
    assert not any(fitz.Rect(it[1], it[2]).normalize().intersects(box[0] + (1, 1, -1, -1))
                   for it in edges)


def test_a_dash_set_outside_a_form_keeps_its_phase_inside_it():
    from paperknife.lineart import cut_line_art
    doc = fitz.open()
    fm = doc.get_new_xref()
    doc.update_object(fm, "<</Type/XObject/Subtype/Form/BBox[0 0 595 842]>>")
    doc.update_stream(fm, b"0 g 2 w 100 100 m 500 100 l S")
    _raw_page(doc, b"[6 3] 0 d /Fm1 Do", f"<</XObject<</Fm1 {fm} 0 R>>>>")
    src = doc.tobytes()
    a, b = fitz.open("pdf", src), fitz.open("pdf", src)
    cut_line_art(b[0], [fitz.Rect(250, 730, 300, 760)])
    right = fitz.Rect(310, 735, 500, 750)
    pa = a[0].get_pixmap(dpi=144, clip=right, alpha=False).samples
    pb = b[0].get_pixmap(dpi=144, clip=right, alpha=False).samples
    assert sum(1 for x, y in zip(pa, pb, strict=True) if abs(x - y) > 48) == 0


def test_a_mesh_shading_turns_the_page_into_an_image():
    from paperknife.tools.redact import redact_page
    doc = fitz.open()
    mesh = doc.get_new_xref()
    doc.update_object(mesh, "<</ShadingType 4/ColorSpace/DeviceRGB/BitsPerCoordinate 16"
                            "/BitsPerComponent 8/BitsPerFlag 8/Decode[0 595 0 842 0 1 0 1 0 1]>>")
    import struct

    def v(x, y, r, g, b):
        return struct.pack(">BHHBBB", 0, round(x / 595 * 65535), round(y / 842 * 65535),
                           r, g, b)
    doc.update_stream(mesh, v(100, 300, 255, 0, 0) + v(500, 300, 0, 255, 0)
                      + v(300, 700, 0, 0, 255))
    _raw_page(doc, b"BT /F1 12 Tf 50 800 Td (Kept words) Tj ET /S1 sh",
              f"<</Shading<</S1 {mesh} 0 R>>/Font<</F1<</Type/Font/Subtype/Type1"
              f"/BaseFont/Helvetica>>>>>>")
    box = [fitz.Rect(250, 250, 350, 350)]
    assert redact_page(doc, 0, box, (0, 0, 0)) == "image"
    out = fitz.open("pdf", doc.tobytes(garbage=4, deflate=True))
    assert len(out[0].get_images()) == 1
    assert b"sh" not in b" ".join(out.xref_stream(x) for x in out[0].get_contents())
    assert not any(b"ShadingType" in (out.xref_object(x) or "").encode()
                   for x in range(1, out.xref_length()))



def test_a_stream_nothing_can_read_turns_the_page_into_an_image(monkeypatch):
    # cut_line_art raising leaves no list of unsafe shapes, and residual() never
    # sees a mesh shading: with no fill the page stayed vector, mesh data and all.
    import struct
    from paperknife.core import redact as core_redact
    from paperknife.tools.redact import redact_page
    doc = fitz.open()
    mesh = doc.get_new_xref()
    doc.update_object(mesh, "<</ShadingType 4/ColorSpace/DeviceRGB/BitsPerCoordinate 16"
                            "/BitsPerComponent 8/BitsPerFlag 8/Decode[0 595 0 842 0 1 0 1 0 1]>>")

    def v(x, y, r, g, b):
        return struct.pack(">BHHBBB", 0, round(x / 595 * 65535), round(y / 842 * 65535),
                           r, g, b)
    doc.update_stream(mesh, v(100, 300, 255, 0, 0) + v(500, 300, 0, 255, 0)
                      + v(300, 700, 0, 0, 255))
    _raw_page(doc, b"/S1 sh", f"<</Shading<</S1 {mesh} 0 R>>>>")

    def unreadable(page, rects):
        raise ValueError("an operator sequence lineart cannot read")
    monkeypatch.setattr(core_redact, "cut_line_art", unreadable)
    box = [fitz.Rect(250, 250, 350, 350)]
    assert redact_page(doc, 0, box, None) == "image"
    out = fitz.open("pdf", doc.tobytes(garbage=4, deflate=True))
    assert not any(b"ShadingType" in (out.xref_object(x) or "").encode()
                   for x in range(1, out.xref_length()))

def test_drawing_order_is_kept(app, dialogs, tmp_path):
    doc, boxes = case_order()
    src = doc.tobytes()
    out = _redact_with_tool(app, dialogs, tmp_path, "order2", src, boxes)
    with fitz.open(out) as red:
        page = red[0]
        # Under the white sheet the red line stays hidden ...
        sheet = page.get_pixmap(dpi=DPI, clip=fitz.Rect(410, 290, 495, 310), alpha=False)
        assert set(sheet.samples) == {255}
        # ... and the yellow line stays on top of the green band.
        pix = page.get_pixmap(dpi=DPI, clip=fitz.Rect(300, 209.5, 301, 210.5), alpha=False)
        r, g, b = pix.pixel(0, 0)
        assert r > 200 and g > 200 and b < 80, (r, g, b)
