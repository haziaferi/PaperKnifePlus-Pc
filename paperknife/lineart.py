"""Cut vector line art at redaction-box edges, in place in the content stream (L3-18).

MuPDF keeps or removes whole subpaths, so a line that crosses a box edge survives
under the box.  This module rewrites only the paths a box touches, where they are:
drawing order and every graphics-state setting stay as they were.

- Strokes are split exactly where they cross a box edge; curves stay Béziers
  (de Casteljau).  Dashed strokes keep their phase.
- Fills and clip paths become the shape minus the boxes: each touched subpath is
  clipped to the four strips around a box (curve-aware Sutherland-Hodgman), which
  keeps the winding number of every point outside the boxes, so both fill rules hold.
- Shadings (`sh`) are painted through a clip that leaves out the boxes.
- Form XObjects are rewritten recursively into page-private copies.

Geometry is cut in page space (where the boxes are axis-aligned) and mapped back
through the inverse CTM: splitting a Bézier commutes with an affine map.
Text and image pixels are left to MuPDF's apply_redactions, which runs afterwards.
Not handled: tiling-pattern cells, Type3 glyph procedures and annotation
appearances (the Redact tool deletes annotations under a box).
"""
from __future__ import annotations

import math
import re

import pymupdf as fitz

_WS = b" \t\n\r\f\x00"
_DELIM = b"()<>[]{}/%"
_NUM = re.compile(rb"[+-]?(?:\d+\.?\d*|\.\d+)\Z")
_ARGC = {"m": 2, "l": 2, "c": 6, "v": 4, "y": 4, "h": 0, "re": 4}
_PATH_OPS = set(_ARGC)
_PAINT_OPS = {"S", "s", "f", "F", "f*", "B", "B*", "b", "b*", "n"}
_FILL_OPS = {"f", "F", "f*", "B", "B*", "b", "b*"}
_STROKE_OPS = {"S", "s", "B", "B*", "b", "b*"}
_CLOSING_OPS = {"s", "b", "b*"}
_EO_OPS = {"f*", "B*", "b*"}
# Colour and line state that PyMuPDF (and other writers) put between a path and
# its paint operator; anything else there ends the path unpainted.
_PDF_OPS = set("b B b* B* BDC BI BMC BT BX c cm CS cs d d0 d1 Do DP EI EMC ET EX f F f* G g "
               "gs h i ID j J K k l m M MP n q Q re RG rg ri s S SC sc SCN scn sh T* Tc Td TD "
               "Tf Tj TJ TL Tm Tr Ts Tw Tz v w W W* y ' \"".split())
_INLINE_STATE_OPS = {"w", "J", "j", "M", "d", "ri", "i", "gs", "CS", "cs", "SC", "SCN",
                     "sc", "scn", "G", "g", "RG", "rg", "K", "k"}
_EPS = 1e-9
_FAR = 1e5                      # stands in for "unbounded" in strips and clips
_MAX_DEPTH = 12                 # nested forms


class _Name(str):
    pass


_HEX_ESCAPE = re.compile(rb"#([0-9A-Fa-f]{2})")


def _name(raw: bytes) -> _Name:
    """A name as MuPDF reads it: #xx escapes decoded (/E#31 is /E1)."""
    return _Name(_HEX_ESCAPE.sub(lambda m: bytes([int(m.group(1), 16)]), raw).decode("latin-1"))


# ── content-stream lexer ──────────────────────────────────────────────────────
def _skip_string(data: bytes, i: int) -> int:
    depth, n = 0, len(data)
    while i < n:
        c = data[i]
        if c == 0x5C:           # backslash: the next byte is escaped
            i += 2
            continue
        if c == 0x28:
            depth += 1
        elif c == 0x29:
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return n


def _skip_dict(data: bytes, i: int) -> int:
    depth, n = 0, len(data)
    while i < n:
        if data.startswith(b"<<", i):
            depth += 1
            i += 2
        elif data.startswith(b">>", i):
            depth -= 1
            i += 2
            if depth == 0:
                return i
        elif data[i] == 0x28:
            i = _skip_string(data, i)
        elif data[i] == 0x3C:
            j = data.find(b">", i)
            i = n if j < 0 else j + 1
        else:
            i += 1
    return n


def _token_end(data: bytes, i: int) -> int:
    n = len(data)
    while i < n and data[i] not in _WS and data[i] not in _DELIM:
        i += 1
    return i


def _parse_value(data: bytes, i: int):
    """One operand starting at i: (value, end).  Strings and dicts are kept raw."""
    c = data[i]
    if c == 0x2F:
        j = _token_end(data, i + 1)
        return _name(data[i + 1:j]), j
    if c == 0x28:
        j = _skip_string(data, i)
        return data[i:j], j
    if c == 0x3C:
        if data.startswith(b"<<", i):
            j = _skip_dict(data, i)
            return data[i:j], j
        j = data.find(b">", i)
        j = len(data) if j < 0 else j + 1
        return data[i:j], j
    if c == 0x5B:
        items, j, n = [], i + 1, len(data)
        while j < n:
            while j < n and data[j] in _WS:
                j += 1
            if j >= n:
                break
            if data[j] == 0x5D:
                return items, j + 1
            v, j = _parse_value(data, j)
            items.append(v)
        return items, n
    j = _token_end(data, i)
    if j == i:                  # a stray delimiter
        return None, i + 1
    tok = data[i:j]
    if _NUM.match(tok):
        return float(tok), j
    return tok.decode("latin-1"), j


def _skip_inline_image(data: bytes, i: int) -> int:
    """i is just past BI; return the index just past the matching EI."""
    n = len(data)
    params: dict = {}
    key = None
    while i < n:
        while i < n and data[i] in _WS:
            i += 1
        if i >= n:
            return n                                # truncated: BI without ID
        if data.startswith(b"ID", i) and (i + 2 >= n or data[i + 2] in _WS):
            i += 3                                  # ID and its single whitespace byte
            break
        v, i = _parse_value(data, i)
        if key is None:
            key = v
        else:
            if isinstance(key, str):
                params[key] = v
            key = None
    length = _inline_image_length(params)
    if length is not None and data.startswith(b"EI", _skip_ws(data, i + length)):
        return _skip_ws(data, i + length) + 2
    m = re.compile(rb"[\s]EI(?=[\s/\[<(%]|\Z)").search(data, i)
    return m.end() if m else n


def _skip_ws(data: bytes, i: int) -> int:
    while i < len(data) and data[i] in _WS:
        i += 1
    return i


def _inline_image_length(p: dict):
    """Byte length of unfiltered inline-image data, or None when it cannot be known."""
    if p.get("F") or p.get("Filter"):
        return None
    try:
        w, h = int(p.get("W", p.get("Width"))), int(p.get("H", p.get("Height")))
        mask = p.get("IM", p.get("ImageMask")) == "true"
        bpc = 1 if mask else int(p.get("BPC", p.get("BitsPerComponent")))
        cs = p.get("CS", p.get("ColorSpace"))
        comps = 1 if mask else {"G": 1, "DeviceGray": 1, "RGB": 3, "DeviceRGB": 3,
                                "CMYK": 4, "DeviceCMYK": 4}.get(cs)
    except (TypeError, ValueError, OverflowError):
        return None
    if comps is None or w <= 0 or h <= 0 or bpc <= 0:
        return None
    return h * ((w * bpc * comps + 7) // 8)


# One match per token on the common path; strings, arrays and dicts go to _parse_value.
_TOKEN = re.compile(rb"[ \t\n\r\f\x00]+|%[^\r\n]*|(/[^ \t\n\r\f\x00()<>\[\]{}/%]*)"
                    rb"|([+-]?(?:\d+\.?\d*|\.\d+))(?![^ \t\n\r\f\x00()<>\[\]{}/%])"
                    rb"|([^ \t\n\r\f\x00()<>\[\]{}/%]+)")


def _operations(data: bytes):
    """(operator, operands, start, end) for each operation; start..end spans both."""
    i, n = 0, len(data)
    operands: list = []
    start = None
    match = _TOKEN.match
    while i < n:
        m = match(data, i)
        if m is None:                               # ( < [ or a stray delimiter
            if start is None:
                start = i
            v, i = _parse_value(data, i)
            if v is not None:
                operands.append(v)
            continue
        name, num, word = m.groups()
        if name is None and num is None and word is None:
            i = m.end()                             # whitespace or a comment
            continue
        if start is None:
            start = i
        j = m.end()
        if name is not None:
            operands.append(_name(name[1:]))
        elif num is not None:
            operands.append(float(num))
        else:
            kw = word.decode("latin-1")
            if kw in ("true", "false", "null"):
                operands.append(kw)
            else:
                if kw == "BI":
                    j = max(_skip_inline_image(data, j), j)    # never back up
                yield kw, operands, start, j
                operands, start = [], None
        i = j


# ── geometry (page space, plain tuples) ───────────────────────────────────────
def _tf(p, m):
    return (p[0] * m.a + p[1] * m.c + m.e, p[0] * m.b + p[1] * m.d + m.f)


def _lerp(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def _seg_at(seg, t):
    if len(seg) == 2:
        return _lerp(seg[0], seg[1], t)
    p0, p1, p2, p3 = seg
    u = 1 - t
    return (u * u * u * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t * t * t * p3[0],
            u * u * u * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t * t * t * p3[1])


def _split(seg, t):
    """de Casteljau: the parts of a segment before and after parameter t."""
    if len(seg) == 2:
        m = _lerp(seg[0], seg[1], t)
        return (seg[0], m), (m, seg[1])
    p0, p1, p2, p3 = seg
    a, b, c = _lerp(p0, p1, t), _lerp(p1, p2, t), _lerp(p2, p3, t)
    d, e = _lerp(a, b, t), _lerp(b, c, t)
    f = _lerp(d, e, t)
    return (p0, a, d, f), (f, e, c, p3)


def _pieces(seg, ts):
    """The segment cut at the sorted parameters ts (all inside (0, 1))."""
    out, prev = [], 0.0
    rest = seg
    for t in ts:
        local = (t - prev) / (1 - prev)
        a, rest = _split(rest, local)
        out.append(a)
        prev = t
    out.append(rest)
    return out


def _roots(seg, k: int, v: float) -> list[float]:
    """Parameters in (0, 1) where coordinate k of the segment equals v."""
    if len(seg) == 2:
        a, b = seg[0][k], seg[1][k]
        if (a - v) * (b - v) < 0:
            return [(v - a) / (b - a)]
        return []
    c0, c1, c2, c3 = (p[k] for p in seg)
    if min(c0, c1, c2, c3) >= v or max(c0, c1, c2, c3) <= v:
        return []
    a3 = -c0 + 3 * c1 - 3 * c2 + c3
    a2 = 3 * c0 - 6 * c1 + 3 * c2
    a1 = -3 * c0 + 3 * c1
    a0 = c0 - v

    def f(t):
        return ((a3 * t + a2) * t + a1) * t + a0

    # Split [0, 1] at the turning points so that f is monotonic on each piece.
    stops = [0.0]
    qa, qb, qc = 3 * a3, 2 * a2, a1
    if abs(qa) > _EPS:
        disc = qb * qb - 4 * qa * qc
        if disc > 0:
            r = math.sqrt(disc)
            stops += sorted(t for t in ((-qb - r) / (2 * qa), (-qb + r) / (2 * qa)) if 0 < t < 1)
    elif abs(qb) > _EPS and 0 < -qc / qb < 1:
        stops.append(-qc / qb)
    stops.append(1.0)
    out = []
    for lo, hi in zip(stops, stops[1:], strict=False):
        flo, fhi = f(lo), f(hi)
        if flo * fhi >= 0:
            continue
        for _ in range(60):
            mid = (lo + hi) / 2
            if (f(mid) < 0) == (flo < 0):
                lo = mid
            else:
                hi = mid
        t = (lo + hi) / 2
        if 1e-7 < t < 1 - 1e-7:
            out.append(t)
    return out


def _bbox(points):
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


def _overlaps(bb, box) -> bool:
    """Does bbox bb reach into the open interior of box?"""
    return bb[0] < box[2] and bb[2] > box[0] and bb[1] < box[3] and bb[3] > box[1]


def _inside(p, boxes) -> bool:
    return any(b[0] < p[0] < b[2] and b[1] < p[1] < b[3] for b in boxes)


def _same(a, b) -> bool:
    return abs(a[0] - b[0]) < 1e-7 and abs(a[1] - b[1]) < 1e-7


# ── subpaths ──────────────────────────────────────────────────────────────────
class _Sub:
    """One subpath in user space: segments are 2-tuples (line) or 4-tuples (cubic)."""
    __slots__ = ("start", "segs", "closed")

    def __init__(self, start):
        self.start = start
        self.segs: list = []
        self.closed = False

    def end(self):
        return self.segs[-1][-1] if self.segs else self.start


def _build_path(ops) -> list[_Sub]:
    subs: list[_Sub] = []
    cur = None
    for op, a in ops:
        # As MuPDF reads them (measured): missing operands are 0, extra ones are
        # ignored from the end.  The cut must follow the path MuPDF draws.
        a = (list(a) + [0.0] * _ARGC[op])[:_ARGC[op]]
        if op == "m":
            cur = _Sub((a[0], a[1]))
            subs.append(cur)
        elif op == "re":
            x, y, w, h = a
            s = _Sub((x, y))
            s.segs = [((x, y), (x + w, y)), ((x + w, y), (x + w, y + h)),
                      ((x + w, y + h), (x, y + h)), ((x, y + h), (x, y))]
            s.closed = True
            subs.append(s)
            cur = _Sub((x, y))          # a following l/c continues from the rect origin
            subs.append(cur)
        elif op == "h":
            if cur is not None:
                cur.closed = True
                cur = _Sub(cur.start)
                subs.append(cur)
        else:
            if cur is None:
                cur = _Sub((0.0, 0.0))
                subs.append(cur)
            p = cur.end()
            if op == "l":
                cur.segs.append((p, (a[0], a[1])))
            elif op == "c":
                cur.segs.append((p, (a[0], a[1]), (a[2], a[3]), (a[4], a[5])))
            elif op == "v":
                cur.segs.append((p, p, (a[0], a[1]), (a[2], a[3])))
            elif op == "y":
                cur.segs.append((p, (a[0], a[1]), (a[2], a[3]), (a[2], a[3])))
    return [s for s in subs if s.segs]


def _to_page(sub: _Sub, m) -> list:
    segs = [tuple(_tf(p, m) for p in s) for s in sub.segs]
    return segs


def _hides_shape(loop, boxes, visible) -> bool:
    """Does a box hide part of this outline that cannot be read off the rest?

    True when a vertex lies in a box, or when a segment runs through a box and no
    part of it is visible on the page outside the boxes.  A segment seen anywhere
    outside fixes the rest of it (a line by two points, a cubic by any piece);
    a control point is off the path, so it needs no hiding."""
    for seg in loop:
        if _inside(seg[0], boxes):
            return True
        if not any(_overlaps(_bbox(seg), b) for b in boxes):
            continue
        edges = [(k, v) for b in boxes + [visible]
                 for k, v in ((0, b[0]), (0, b[2]), (1, b[1]), (1, b[3]))]
        ts = sorted({t for k, v in edges for t in _roots(seg, k, v)})
        mids = [_seg_at(pc, 0.5) for pc in _pieces(seg, ts)]
        # The page edge itself is visible: test against the area grown a little.
        seen = (visible[0] - 0.01, visible[1] - 0.01, visible[2] + 0.01, visible[3] + 0.01)
        if any(_inside(m, boxes) for m in mids) and not any(
                _inside(m, [seen]) and not _inside(m, boxes) for m in mids):
            return True
    return False


def _closed_loop(segs):
    """The segments of a filled subpath with its implicit closing line."""
    if not _same(segs[-1][-1], segs[0][0]):
        segs = segs + [(segs[-1][-1], segs[0][0])]
    return segs


# ── strokes ───────────────────────────────────────────────────────────────────
def _cut_stroke(segs, closed, boxes, rejoin=True):
    """Runs (lists of continuous segments) of a subpath outside every box, and
    whether anything was cut away."""
    if closed:
        segs = _closed_loop(segs)
    runs, run = [], []
    dropped = False
    for seg in segs:
        if not any(_overlaps(_bbox(seg), b) for b in boxes):
            parts = [seg]
        else:
            ts = sorted({t for b in boxes for k, v in ((0, b[0]), (0, b[2]), (1, b[1]), (1, b[3]))
                         for t in _roots(seg, k, v)})
            parts = _pieces(seg, ts)
        for pc in parts:
            if _inside(_seg_at(pc, 0.5), boxes):
                dropped = True
                if run:
                    runs.append(run)
                    run = []
            else:
                run.append(pc)
    if run:
        runs.append(run)
    # Rejoin across the start point, unless a dash pattern restarts there.
    if rejoin and closed and len(runs) > 1 and _same(runs[-1][-1][-1], runs[0][0][0]):
        runs[0] = runs.pop() + runs[0]
    return runs, dropped


def _arc_length(seg) -> float:
    if len(seg) == 2:
        return math.dist(seg[0], seg[1])
    pts = [_seg_at(seg, i / 32) for i in range(33)]
    return sum(math.dist(a, b) for a, b in zip(pts, pts[1:], strict=False))


# ── fills and clips ───────────────────────────────────────────────────────────
def _clip_half(loop, k, v, keep_ge):
    """A closed loop clipped to the half-plane coord_k >= v (or <= v), curves kept."""
    out: list = []
    first = None
    for seg in loop:
        for pc in _pieces(seg, _roots(seg, k, v)):
            c = _seg_at(pc, 0.5)[k]
            if (c >= v - 1e-9) if keep_ge else (c <= v + 1e-9):
                if out and not _same(out[-1][-1], pc[0]):
                    out.append((out[-1][-1], pc[0]))        # along the clip line
                if first is None:
                    first = pc[0]
                out.append(pc)
    if out and not _same(out[-1][-1], first):
        out.append((out[-1][-1], first))
    return out


def _strips(b):
    """The four regions around box b, each as half-planes (axis, value, keep >=)."""
    x0, y0, x1, y1 = b
    return [[(0, x0, False)], [(0, x1, True)],
            [(0, x0, True), (0, x1, False), (1, y0, False)],
            [(0, x0, True), (0, x1, False), (1, y1, True)]]


def _minus_boxes(loop, boxes):
    """Loops that together cover loop minus the boxes, with the same winding outside."""
    loops = [loop]
    for b in boxes:
        nxt = []
        for lp in loops:
            if not _overlaps(_bbox([p for s in lp for p in s]), b):
                nxt.append(lp)
                continue
            for strip in _strips(b):
                piece = lp
                for k, v, ge in strip:
                    piece = _clip_half(piece, k, v, ge)
                    if not piece:
                        break
                if piece:
                    bb = _bbox([p for s in piece for p in s])
                    if bb[2] - bb[0] > 1e-6 and bb[3] - bb[1] > 1e-6:
                        nxt.append(piece)
        loops = nxt
    return loops


def _complement(boxes):
    """Disjoint rectangles covering a huge area minus the boxes (for shading clips)."""
    pieces = [(-_FAR, -_FAR, _FAR, _FAR)]
    for b in boxes:
        nxt = []
        for p in pieces:
            if not _overlaps(p, b):
                nxt.append(p)
                continue
            if p[1] < b[1]:
                nxt.append((p[0], p[1], p[2], b[1]))
            if b[3] < p[3]:
                nxt.append((p[0], b[3], p[2], p[3]))
            y0, y1 = max(p[1], b[1]), min(p[3], b[3])
            if p[0] < b[0]:
                nxt.append((p[0], y0, b[0], y1))
            if b[2] < p[2]:
                nxt.append((b[2], y0, p[2], y1))
        pieces = nxt
    return pieces


# ── writing ───────────────────────────────────────────────────────────────────
def _n(v: float) -> str:
    if abs(v) < 5e-5:
        return "0"
    s = f"{v:.4f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def _write_run(segs, inv, closed=False) -> str:
    out = [f"{_n(_tf(segs[0][0], inv)[0])} {_n(_tf(segs[0][0], inv)[1])} m"]
    for s in segs:
        pts = [_tf(p, inv) for p in s[1:]]
        coords = " ".join(f"{_n(x)} {_n(y)}" for x, y in pts)
        out.append(f"{coords} {'l' if len(s) == 2 else 'c'}")
    if closed:
        out.append("h")
    return "\n".join(out)


def _write_dash(arr, phase) -> str:
    return f"[{' '.join(_n(x) for x in arr)}] {_n(phase)} d"


# ── the rewriter ──────────────────────────────────────────────────────────────
class _Rewriter:
    def __init__(self, doc, boxes, visible):
        self.doc = doc
        self.boxes = [(b.x0, b.y0, b.x1, b.y1) for b in boxes]
        self.visible = visible          # the page area a reader can see (page space)
        self.changed = 0
        self.unsafe: list[str] = []     # content this module cannot cut
        self._forms: dict = {}

    def rewrite(self, data: bytes, ctm, holder: int, depth=0, dash=([], 0.0)):
        """Rewritten stream, or None when nothing in it touches a box."""
        out: list[bytes] = []
        stack = []
        path_ops: list = []
        path_start = None
        clip = None
        inline: list[bytes] = []
        changed = False
        for op, args, start, end in _operations(data):
            if op not in _PDF_OPS:
                # MuPDF reports an unknown keyword, drops its operands and goes on
                # (a path under construction continues); do the same.
                if path_start is None:
                    out.append(data[start:end])
                continue
            if op in _PATH_OPS:
                if path_start is None:
                    path_start = start
                nums = [a for a in args if isinstance(a, float)]
                path_ops.append((op, nums))
                continue
            if op in ("W", "W*") and path_start is not None:
                clip = op
                continue
            if op in _PAINT_OPS and path_start is not None:
                new = self._paint(path_ops, op, clip, ctm, dash)
                if new is None:
                    out.append(data[path_start:end])
                else:
                    # State set inside the path (PyMuPDF writes its colours there)
                    # applies to the paint: keep it, ahead of the new path.
                    out.extend(inline)
                    out.append(new.encode("latin-1"))
                    changed = True
                path_ops, path_start, clip, inline = [], None, None, []
                continue
            if path_start is not None:
                if op in _INLINE_STATE_OPS:     # tolerated inside a path, as MuPDF does
                    piece = data[start:end]
                    if op == "d" and len(args) == 2 and isinstance(args[0], list):
                        dash = ([a for a in args[0] if isinstance(a, float)],
                                args[1] if isinstance(args[1], float) else 0.0)
                    elif op == "gs" and args and isinstance(args[-1], _Name):
                        dash, renamed = self._gs(args[-1], ctm, holder, depth, dash)
                        if renamed is not None:
                            piece = f"/{renamed} gs".encode("latin-1")
                            changed = True
                    elif op in ("scn", "SCN") and args and isinstance(args[-1], _Name):
                        self._check_pattern(args[-1], holder)
                    inline.append(piece)
                    continue
                out.append(data[path_start:start])  # malformed: a path without a paint op
                path_ops, path_start, clip, inline = [], None, None, []
            if op == "q":
                stack.append((ctm, dash))
            elif op == "Q":
                if stack:
                    ctm, dash = stack.pop()
            elif op == "cm":                    # operand count read as MuPDF does
                nums = ([a for a in args if isinstance(a, float)] + [0.0] * 6)[:6]
                ctm = fitz.Matrix(*nums) * ctm
            elif op == "d" and len(args) == 2 and isinstance(args[0], list):
                dash = ([a for a in args[0] if isinstance(a, float)],
                        args[1] if isinstance(args[1], float) else 0.0)
            elif op == "sh" and self.boxes:
                if args and isinstance(args[-1], _Name):
                    self._check_shading(f"Resources/Shading/{args[-1]}", holder)
                wrapped = self._clip_out_boxes(ctm)
                if wrapped:
                    out.append(f"q\n{wrapped}\n".encode() + data[start:end] + b"\nQ")
                    changed = True
                    continue
            elif op in ("scn", "SCN") and args and isinstance(args[-1], _Name):
                self._check_pattern(args[-1], holder)
            elif op == "gs" and args and isinstance(args[-1], _Name):
                dash, name = self._gs(args[-1], ctm, holder, depth, dash)
                if name is not None:
                    out.append(f"/{name} gs".encode("latin-1"))
                    changed = True
                    continue
            elif op == "Do" and args and isinstance(args[-1], _Name):
                name = self._form_do(args[-1], ctm, holder, depth, dash)
                if name is not None:
                    out.append(f"/{name} Do".encode("latin-1"))
                    changed = True
                    continue
            out.append(data[start:end])
        if path_start is not None:
            out.append(data[path_start:])
        return b"\n".join(out) if changed else None

    # ── paths ──
    def _paint(self, path_ops, op, clip, ctm, dash):
        subs = _build_path(path_ops)
        if not subs:
            return None
        page_subs = [_to_page(s, ctm) for s in subs]
        hit = [any(_overlaps(_bbox([p for seg in segs for p in seg]), b) for b in self.boxes)
               for segs in page_subs]
        if not any(hit):
            return None
        self.changed += 1
        try:
            inv = ~ctm
        except Exception:
            inv = None
        if inv is None or abs(ctm.a * ctm.d - ctm.b * ctm.c) < 1e-12:
            return "0 0 0 0 re W n" if clip else ""     # nothing visible; drop it
        parts = []
        if op in _FILL_OPS or clip:
            loops, covers = [], False
            for segs, h in zip(page_subs, hit, strict=True):
                loop = _closed_loop(segs)
                if h and _hides_shape(loop, self.boxes, self.visible):
                    # The shape in a box is information (a bar's hidden height, a
                    # logo, an edge seen nowhere else on the page).  Destroy it.
                    loops += _minus_boxes(loop, self.boxes)
                else:
                    # Whatever runs through a box follows from what is visible
                    # outside the boxes.  Keep it whole and paint it
                    # through a clip that leaves the boxes out: MuPDF renders a
                    # cut-up rectangle or tiling pattern differently, even outside.
                    loops.append(loop)
                    covers = covers or h
            area = "\n".join(_write_run(lp, inv, closed=True) for lp in loops)
            outside = self._clip_out_boxes(ctm) if covers else None
            if op in _FILL_OPS and area:
                fill = f"{area}\n{'f*' if op in _EO_OPS else 'f'}"
                if outside:
                    fill = f"q\n{outside}\n{fill}\nQ"
                parts.append(fill)
        if op in _STROKE_OPS:
            parts.append(self._strokes(subs, page_subs, hit, op, inv, dash))
        if clip:
            rule = "W*" if clip == "W*" else "W"
            parts.append(f"{area}\n{rule} n" if area else _empty_clip(inv))
            if outside:                         # and leave the boxes out of it
                parts.append(outside)
        return "\n".join(p for p in parts if p)

    def _strokes(self, subs, page_subs, hit, op, inv, dash):
        arr, phase = dash
        dashed = bool(arr) and any(x > 0 for x in arr)
        plain, out = [], []
        for sub, segs, h in zip(subs, page_subs, hit, strict=True):
            closed = sub.closed or op in _CLOSING_OPS
            if not h:
                plain.append(_write_run(segs, inv, closed=closed))
                continue
            runs, dropped = _cut_stroke(segs, closed, self.boxes, rejoin=not dashed)
            if not dropped:                     # the box only grazed its bbox
                plain.append(_write_run(segs, inv, closed=closed))
                continue
            for run in runs:
                path = _write_run(run, inv)
                if not dashed:
                    plain.append(path)
                    continue
                # The dash restarts at each subpath: carry on from where this run
                # began along the original subpath, in user-space length.
                offset = self._offset(segs, closed, run[0][0], inv)
                out.append(f"{_write_dash(arr, phase + offset)}\n{path}\nS")
        if plain:
            out.insert(0, "\n".join(plain) + "\nS")
        if dashed and out:
            out.append(_write_dash(arr, phase))
        return "\n".join(out)

    @staticmethod
    def _offset(segs, closed, start, inv):
        """User-space length along the subpath from its start to point start."""
        if closed:
            segs = _closed_loop(segs)
        total = 0.0
        for seg in segs:
            user = tuple(_tf(p, inv) for p in seg)
            if _same(seg[0], start):
                return total
            for t in _ts_through(seg, start):
                return total + _arc_length(_split(user, t)[0])
            total += _arc_length(user)
        return 0.0

    # ── shadings ──
    def _clip_out_boxes(self, ctm):
        try:
            inv = ~ctm
        except Exception:
            return None
        if abs(ctm.a * ctm.d - ctm.b * ctm.c) < 1e-12:
            return None
        rects = []
        for x0, y0, x1, y1 in _complement(self.boxes):
            corners = [_tf(p, inv) for p in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]
            rects.append(" ".join(f"{_n(x)} {_n(y)} {'m' if i == 0 else 'l'}"
                                  for i, (x, y) in enumerate(corners)) + " h")
        return "\n".join(rects) + "\nW n"

    # ── forms and soft masks ──
    def _form_do(self, name, ctm, holder, depth, dash):
        doc = self.doc
        kind, val = doc.xref_get_key(holder, f"Resources/XObject/{name}")
        if kind != "xref":
            return None
        xref = int(val.split()[0])
        if doc.xref_get_key(xref, "Subtype")[1] != "/Form":
            return None
        copy = self._form_copy(xref, ctm, holder, depth, dash)
        if copy is None:
            return None
        new_name = f"{name}R{copy}"
        _set_resource(doc, holder, "XObject", new_name, f"{copy} 0 R")
        return new_name

    def _check_shading(self, path, holder):
        """Mesh shadings (types 4-7) carry positioned data a clip does not remove."""
        kind, val = self.doc.xref_get_key(holder, f"{path}/ShadingType")
        if kind == "int" and val.strip() in ("4", "5", "6", "7"):
            self.unsafe.append("mesh shading")

    def _check_pattern(self, name, holder):
        kind, val = self.doc.xref_get_key(holder, f"Resources/Pattern/{name}/PatternType")
        if kind == "int" and val.strip() == "2":
            self._check_shading(f"Resources/Pattern/{name}/Shading", holder)

    def _gs(self, name, ctm, holder, depth, dash):
        """(the dash in force after gs name, a renamed cut copy of the ExtGState or None)."""
        kind, val = self.doc.xref_get_key(holder, f"Resources/ExtGState/{name}/D")
        if kind == "array":
            d = _dash_value(val)
            if d is not None:
                dash = d
        return dash, self._gs_smask(name, ctm, holder, depth, dash)

    def _gs_smask(self, name, ctm, holder, depth, dash):
        """A copy of ExtGState name whose soft-mask group is cut, or None.

        A soft mask's group is drawn in the CTM in force when gs runs; MuPDF's
        redaction does not look inside it, and Figma, Inkscape and Illustrator
        put shapes there."""
        doc = self.doc
        kind, val = doc.xref_get_key(holder, f"Resources/ExtGState/{name}")
        if kind == "xref":
            gs_text = doc.xref_object(int(val.split()[0]), compressed=False)
        elif kind == "dict":
            gs_text = val
        else:
            return None
        kind, val = doc.xref_get_key(holder, f"Resources/ExtGState/{name}/SMask/G")
        if kind != "xref":
            return None
        group = self._form_copy(int(val.split()[0]), ctm, holder, depth, dash)
        if group is None:
            return None
        gs2 = doc.get_new_xref()
        doc.update_object(gs2, gs_text)
        kind, val = doc.xref_get_key(gs2, "SMask")
        if kind == "xref":                      # a shared soft-mask dict: copy it too
            sm2 = doc.get_new_xref()
            doc.update_object(sm2, doc.xref_object(int(val.split()[0]), compressed=False))
            doc.xref_set_key(sm2, "G", f"{group} 0 R")
            doc.xref_set_key(gs2, "SMask", f"{sm2} 0 R")
        else:
            doc.xref_set_key(gs2, "SMask/G", f"{group} 0 R")
        new_name = f"{name}R{gs2}"
        _set_resource(doc, holder, "ExtGState", new_name, f"{gs2} 0 R")
        return new_name

    def _form_copy(self, xref, ctm, holder, depth, dash):
        """xref of a page-private, cut copy of Form xref drawn in ctm, or None.

        None also when it cannot be read here (nesting too deep, an indirect
        /Matrix element): residual() then sees what is left and the page falls back."""
        doc = self.doc
        if depth >= _MAX_DEPTH:
            return None
        kind, val = doc.xref_get_key(xref, "Matrix")
        fm = fitz.Matrix(1, 0, 0, 1, 0, 0)
        if kind == "array":
            try:
                nums = [float(v) for v in val.strip("[]").split()]
            except ValueError:
                return None
            if len(nums) == 6:
                fm = fitz.Matrix(*nums)
        form_ctm = fm * ctm
        key = (xref, tuple(round(v, 6) for v in form_ctm), holder, str(dash))
        if key in self._forms:
            return self._forms[key]
        form_holder = xref if doc.xref_get_key(xref, "Resources")[0] != "null" else holder
        body = doc.xref_stream(xref) or b""
        new = self.rewrite(body, form_ctm, form_holder, depth + 1, dash)
        # The BBox clips the form.  A corner of it in a box shows where something
        # sat there, so it is cut like any clip path with a vertex in a box.
        bbox = _rect_value(doc, xref, "BBox")
        bbox_cut = None
        if bbox is not None:
            corners = [_tf(p, form_ctm) for p in ((bbox[0], bbox[1]), (bbox[2], bbox[1]),
                                                  (bbox[2], bbox[3]), (bbox[0], bbox[3]))]
            if any(_inside(c, self.boxes) for c in corners):
                bbox_cut = self._bbox_clip(corners, form_ctm, bbox)
        if new is None and bbox_cut is None:
            self._forms[key] = None
            return None
        content = new if new is not None else body
        # A page-private copy: the same form may be shown elsewhere unredacted.
        copy = doc.get_new_xref()
        doc.update_object(copy, doc.xref_object(xref, compressed=False))
        for k in ("Filter", "DecodeParms", "Length"):
            doc.xref_set_key(copy, k, "null")
        if bbox_cut is not None:
            clip, big = bbox_cut
            content = f"q\n{clip}\n".encode("latin-1") + content + b"\nQ"
            doc.xref_set_key(copy, "BBox", "[" + " ".join(_n(v) for v in big) + "]")
        doc.update_stream(copy, content)
        self._forms[key] = copy
        return copy

    def _bbox_clip(self, corners, form_ctm, bbox):
        """(explicit clip: the BBox minus the boxes, a BBox that holds them all)."""
        try:
            inv = ~form_ctm
        except Exception:
            inv = None
        if inv is None or abs(form_ctm.a * form_ctm.d - form_ctm.b * form_ctm.c) < 1e-12:
            return "0 0 0 0 re W n", bbox
        loop = [(corners[i], corners[(i + 1) % 4]) for i in range(4)]
        pieces = _minus_boxes(loop, self.boxes)
        clip = ("\n".join(_write_run(lp, inv, closed=True) for lp in pieces) + "\nW n"
                if pieces else _empty_clip(inv))
        # Its corners must lie outside every box: hold the boxes with a margin.
        pts = [(bbox[0], bbox[1]), (bbox[2], bbox[3])]
        for x0, y0, x1, y1 in self.boxes:
            pts += [_tf(p, inv) for p in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]
        bx0, by0, bx1, by1 = _bbox(pts)
        m = max(bx1 - bx0, by1 - by0) * 0.01 + 1
        return clip, (bx0 - m, by0 - m, bx1 + m, by1 + m)


def _dash_value(text: str):
    """An ExtGState /D value '[[6 3] 0]' as (array, phase), or None."""
    m = re.fullmatch(r"\s*\[\s*\[([^\]]*)\]\s*([-+.\d]+)\s*\]\s*", text)
    if not m:
        return None
    try:
        return [float(v) for v in m.group(1).split()], float(m.group(2))
    except ValueError:
        return None


def _empty_clip(inv) -> str:
    """A clip to nothing, placed far off the page: a zero-size rectangle at the user
    origin could land inside a box and read as a vertex there."""
    x, y = _tf((-_FAR, -_FAR), inv)
    return f"{_n(x)} {_n(y)} 0 0 re W n"


def _rect_value(doc, xref: int, key: str):
    kind, val = doc.xref_get_key(xref, key)
    if kind != "array":
        return None
    try:
        nums = [float(v) for v in val.strip("[]").split()]
    except ValueError:
        return None
    if len(nums) != 4:
        return None
    return min(nums[0], nums[2]), min(nums[1], nums[3]), max(nums[0], nums[2]), max(nums[1], nums[3])


def _set_resource(doc, holder: int, kind: str, name: str, ref: str) -> None:
    """Add name -> ref to holder's /Resources/<kind>, following indirect objects
    (xref_set_key refuses a key path that runs through one)."""
    obj, prefix = holder, ""
    for key in ("Resources", kind):
        kind, val = doc.xref_get_key(obj, prefix + key)
        if kind == "xref":
            obj, prefix = int(val.split()[0]), ""
            continue
        if kind == "null":
            doc.xref_set_key(obj, prefix + key, "<<>>")
        prefix += key + "/"
    doc.xref_set_key(obj, prefix + name, ref)


def _ts_through(seg, p):
    """Parameter t at which segment seg passes through point p (cut points only)."""
    for k in (0, 1):
        for t in _roots(seg, k, p[k]):
            if _same(_seg_at(seg, t), p):
                return [t]
    return []


def page_matrix(page: fitz.Page) -> fitz.Matrix:
    """PDF default user space -> PyMuPDF's unrotated page space.

    page.transformation_matrix is wrong on pages that are both rotated and cropped
    (PyMuPDF 1.28.2); this uses the effective CropBox, with inheritance, via MuPDF.
    """
    mu = fitz.mupdf
    r, m = mu.FzRect(), mu.FzMatrix()
    mu.pdf_page_transform(page._pdf_page(), r, m)
    return fitz.Matrix(m.a, m.b, m.c, m.d, m.e, m.f) * page.derotation_matrix


def _resource_holder(doc, xref: int) -> int:
    """The page or ancestor whose /Resources the page uses."""
    seen = set()
    while xref and xref not in seen:
        seen.add(xref)
        if doc.xref_get_key(xref, "Resources")[0] != "null":
            return xref
        kind, val = doc.xref_get_key(xref, "Parent")
        xref = int(val.split()[0]) if kind == "xref" else 0
    return 0


def _drawing_segments(d):
    """Page-space segments of a get_drawings() path, as subpaths with their
    implicit closing lines (a fill closes every subpath)."""
    subs, cur = [], []
    for it in d["items"]:
        if it[0] == "re":
            r = it[1]
            c = [(r.x0, r.y0), (r.x1, r.y0), (r.x1, r.y1), (r.x0, r.y1)]
            subs.append([(c[i], c[(i + 1) % 4]) for i in range(4)])
            continue
        if it[0] == "qu":
            q = it[1]
            c = [tuple(q.ul), tuple(q.ur), tuple(q.lr), tuple(q.ll)]
            subs.append([(c[i], c[(i + 1) % 4]) for i in range(4)])
            continue
        seg = tuple(tuple(p) for p in it[1:5 if it[0] == "c" else 3])
        if cur and not _same(cur[-1][-1], seg[0]):
            subs.append(cur)
            cur = []
        cur.append(seg)
    if cur:
        subs.append(cur)
    return subs


def _winding(subs, p) -> int:
    w = 0
    for sub in subs:
        for seg in _closed_loop(sub):
            pts = [_seg_at(seg, i / 16) for i in range(17)] if len(seg) == 4 else list(seg)
            for a, b in zip(pts, pts[1:], strict=False):
                if a[1] <= p[1] < b[1] or b[1] <= p[1] < a[1]:
                    x = a[0] + (p[1] - a[1]) * (b[0] - a[0]) / (b[1] - a[1])
                    if x > p[0]:
                        w += 1 if b[1] > a[1] else -1
    return w


def _covers(subs, even_odd, p) -> bool:
    w = _winding(subs, p)
    return bool(w % 2) if even_odd else w != 0


def residual(page: fitz.Page, boxes, eps=0.05) -> bool:
    """Does MuPDF still see line art inside a box: a vertex of any path in it, a stroke running through it, or a fill covering a point of it after
    the clips around that fill?  The check reads the page through MuPDF itself, so
    it holds even where this module parses a stream differently."""
    inner = [(b.x0 + eps, b.y0 + eps, b.x1 - eps, b.y1 - eps) for b in map(fitz.Rect, boxes)]
    inner = [b for b in inner if b[2] > b[0] and b[3] > b[1]]
    visible = visible_area(page)
    stack: list = []                    # (level, clip subpaths and rule, or None)
    for d in page.get_drawings(extended=True):
        level = d.get("level", 0)
        while stack and stack[-1][0] >= level:
            stack.pop()
        if d["type"] == "group":
            stack.append((level, None))
            continue
        subs = _drawing_segments(d)
        # Shape information in a box, in any path: a vertex there, or an edge
        # through it seen nowhere else on the page (see _hides_shape).
        closes = d["type"] != "s"
        if any(_inside(p, inner) for sub in subs for seg in sub for p in (seg[0], seg[-1])) \
                or any(_hides_shape(_closed_loop(sub) if closes else sub, inner, visible)
                       for sub in subs):
            return True
        if d["type"] == "clip":
            stack.append((level, (subs, d.get("even_odd"))))
            continue
        clips = [c for _, c in stack if c]
        r = d["rect"]
        if not any(_overlaps((r.x0 - 1, r.y0 - 1, r.x1 + 1, r.y1 + 1), b) for b in inner):
            continue
        if "s" in d["type"]:            # a stroke running through a box shows there
            for sub in subs:
                for seg in sub:
                    for b in inner:
                        if not _overlaps(_bbox(seg), b):
                            continue
                        ts = sorted({t for k, v in ((0, b[0]), (0, b[2]), (1, b[1]), (1, b[3]))
                                     for t in _roots(seg, k, v)})
                        if any(_inside(_seg_at(pc, 0.5), [b]) for pc in _pieces(seg, ts)):
                            return True
        if d.get("fill") is not None:
            for b in inner:
                cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
                for p in ((cx, cy), (b[0], b[1]), (b[2], b[1]), (b[0], b[3]), (b[2], b[3])):
                    p = ((p[0] + cx) / 2, (p[1] + cy) / 2) if p != (cx, cy) else p
                    if _covers(subs, d.get("even_odd"), p) and all(
                            _covers(csubs, ceo, p) for csubs, ceo in clips):
                        return True
    return False


class CutReport(int):
    """Number of paths changed; .unsafe names content this module cannot cut
    (mesh shadings), which the caller must deal with some other way."""
    unsafe: list


def visible_area(page: fitz.Page):
    """What a reader sees of the page, in unrotated page space (the CropBox)."""
    cb = page.cropbox
    return (0.0, 0.0, cb.width, cb.height)


def cut_line_art(page: fitz.Page, boxes) -> CutReport:
    """Remove the parts of every path on page that lie inside boxes (page space).

    Run before apply_redactions(graphics=PDF_REDACT_LINE_ART_NONE), which then
    removes text and image pixels and draws the fill.
    """
    boxes = [fitz.Rect(b) for b in boxes]
    boxes = [b for b in boxes if b.width > 0 and b.height > 0]
    report = CutReport(0)
    report.unsafe = []
    if not boxes:
        return report
    doc = page.parent
    data = b"\n".join(doc.xref_stream(x) or b"" for x in page.get_contents())
    holder = _resource_holder(doc, page.xref)
    if not holder:
        doc.xref_set_key(page.xref, "Resources", "<<>>")
        holder = page.xref
    rw = _Rewriter(doc, boxes, visible_area(page))
    new = rw.rewrite(data, page_matrix(page), holder)
    report = CutReport(rw.changed if new is not None else 0)
    report.unsafe = sorted(set(rw.unsafe))
    if new is not None:
        xref = doc.get_new_xref()
        doc.update_object(xref, "<<>>")
        doc.update_stream(xref, new)
        doc.xref_set_key(page.xref, "Contents", f"{xref} 0 R")
    return report
