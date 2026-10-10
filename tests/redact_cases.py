"""Test PDFs and measurements shared by the Qt page tests and the core tests
(toolkit-free; loaded by path from tests/qt, imported directly from tests/).

- The line-art redaction corpus (L3-18): CASES maps a name to a builder that
  returns (document, boxes); _gray / _box_pixels / _outlines_inside /
  _words_outside measure a redacted page.
- SECRET / _secret_pdf: a PDF that hides one word in every place a PDF can.
- _long_pdf: a long PDF with one word per page.
"""
import math

import pymupdf as fitz

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


SECRET = "SECRET-ALPHA-42"


def _secret_pdf(path):
    doc = fitz.open()
    p = doc.new_page()
    p.insert_text((72, 100), f"Name: {SECRET}", fontsize=12)
    p.insert_text((72, 400), "Public paragraph", fontsize=12)
    p.add_text_annot((400, 600), f"note: {SECRET}")
    w = fitz.Widget()
    w.field_type = fitz.PDF_WIDGET_TYPE_TEXT
    w.field_name = "ref"
    w.field_value = SECRET
    w.rect = fitz.Rect(72, 650, 300, 670)
    p.add_widget(w)
    doc.set_metadata({"title": f"Report {SECRET}", "author": "Alice"})
    doc.set_xml_metadata(
        '<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF '
        'xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
        '<rdf:Description xmlns:dc="http://purl.org/dc/elements/1.1/">'
        f'<dc:title>{SECRET}</dc:title></rdf:Description></rdf:RDF></x:xmpmeta>')
    doc.set_toc([[1, f"Chapter {SECRET}", 1]])
    doc.embfile_add("notes.txt", f"attached {SECRET}".encode())
    doc.save(str(path))
    doc.close()


def _long_pdf(path, pages=400, word="needle"):
    doc = fitz.open()
    for i in range(pages):
        p = doc.new_page()
        for j in range(30):
            p.insert_text((40, 40 + j * 24), f"line {j} page {i} {word} lorem ipsum dolor sit",
                          fontsize=10)
    doc.save(str(path))
    doc.close()
    return str(path)
