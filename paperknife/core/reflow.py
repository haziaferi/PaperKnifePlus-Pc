"""Reflow: change text on a PDF page the way a word processor would.

A change re-wraps its unit (a line, a paragraph or a page's column), from the
line it starts on until the wrap meets an unchanged line break again; when the
unit needs more or fewer lines, the text below it in the column moves, and
what no longer fits goes on to the following pages, pushing their text down
(owner, 2026-10-11).  Each piece of text keeps its own font where the page
surely holds its letters; a change that would move text past a picture, line
art, a link, two columns or the end of the document is not made and is
reported as a Skip instead.

Everything is planned first and written only when the whole plan fits, so a
skipped change leaves its pages as they were.
"""
from __future__ import annotations

import difflib
import re
import statistics
from dataclasses import dataclass, field

import pymupdf as fitz

from ..pages import textwriter_point
from .text import erase_box, span_rgb, unicode_font

LINE, PARAGRAPH, PAGE = "line", "paragraph", "page"
UNITS = (LINE, PARAGRAPH, PAGE)
HEAD, FOOT = 0.07, 0.93          # page-height shares: header and footer zones never move
TIGHT_GAP = 1.35                 # a baseline step this many leads wide starts a paragraph


@dataclass
class Skip:
    page: int                    # 0-based
    text: str                    # the words around the change
    reason: str


@dataclass
class Result:
    done: int = 0
    skips: list[Skip] = field(default_factory=list)
    fallback_fonts: set[str] = field(default_factory=set)   # fonts some letters could not be drawn in


# ── fonts ────────────────────────────────────────────────────────────────────
def _norm_font(name: str) -> str:
    return "".join(c for c in name.split("+")[-1] if c.isalnum()).lower()


def _font_xref(page, name: str) -> int:
    """The xref of the embedded font a text span names.  The text layer gives
    the font's own name ("CharisSIL") where the PDF may say "Charis SIL
    Regular", so names are compared without spaces or punctuation: equal
    first, else the closest one that starts with the other."""
    want = _norm_font(name)
    best, gap = 0, None
    for xref, ext, _t, base, *_rest in page.get_fonts(full=True):
        if ext in ("n/a", ""):
            continue
        have = _norm_font(base)
        if have == want:
            return xref
        if have.startswith(want) or want.startswith(have):
            d = abs(len(have) - len(want))
            if gap is None or d < gap:
                best, gap = xref, d
    return best


class FontBook:
    """The document's own fonts, and which letters each page draws with them:
    a subset font is only sure to hold the glyphs it was used for."""

    def __init__(self, doc):
        self.doc = doc
        self._fonts: dict[tuple, tuple] = {}
        self._used: dict[int, dict] = {}
        self._shared: dict[int, set] = {}
        self.helv = fitz.Font("helv")

    def used(self, page) -> dict[str, set]:
        if page.number not in self._used:
            out: dict[str, set] = {}
            raw = page.get_text("rawdict", flags=fitz.TEXT_PRESERVE_WHITESPACE)
            for blk in raw["blocks"]:
                for ln in blk.get("lines", []):
                    for sp in ln["spans"]:
                        out.setdefault(sp["font"], set()).update(c["c"] for c in sp["chars"])
            self._used[page.number] = out
        return self._used[page.number]

    def own(self, page, name: str):
        """(fitz.Font or None, True when it holds every glyph it claims)."""
        key = (page.number, name)
        if key not in self._fonts:
            got = (None, False)
            xref = _font_xref(page, name)
            if xref:
                try:
                    buf = self.doc.extract_font(xref)[3]
                    if buf:
                        got = (fitz.Font(fontbuffer=buf), False)
                except Exception:                # noqa: BLE001 - a font we cannot read is no font
                    pass
            if got[0] is None:
                try:
                    got = (fitz.Font(name), True)
                except Exception:                # noqa: BLE001 - not a built-in name
                    pass
            self._fonts[key] = got
        return self._fonts[key]

    def shared(self, font) -> set:
        """Characters whose glyph also stands for another character: drawn with
        it, the text layer gives back the other one (space as no-break space)."""
        key = id(font)
        if key not in self._shared:
            by_glyph: dict[int, list] = {}
            for cp in font.valid_codepoints():
                by_glyph.setdefault(font.has_glyph(cp), []).append(cp)
            self._shared[key] = {chr(cp) for cps in by_glyph.values() if len(cps) > 1
                                 for cp in cps}
        return self._shared[key]

    def pick(self, page, src_page, span: dict, s: str):
        """The font to draw *s* in: the span's own when *src_page* surely holds
        those letters in it, else a built-in one."""
        own, complete = self.own(src_page, span["font"])
        letters = [c for c in s if not c.isspace()]
        if own is not None and all(own.has_glyph(ord(c)) for c in letters) and (
                complete or all(c in self.used(src_page).get(span["font"], ()) for c in letters)):
            return own
        return unicode_font(s) or self.helv

    def width(self, page, span, s: str) -> float:
        return self.pick(page, page, span, s).text_length(s, fontsize=span["size"])


# ── the page as lines of styled characters ───────────────────────────────────
@dataclass
class Ch:
    c: str
    x: float                     # origin x
    span: dict                   # font, size, color of the run it came from
    src: int = -1                # page it was drawn on (its font's letters live there)
    x1: float = 0.0              # right edge of its box


@dataclass
class Line:
    block: int
    chars: list
    bbox: fitz.Rect
    base: float                  # baseline y
    size: float
    spans: list                  # the rawdict spans, for erasing
    hidden: bool = False         # an invisible text layer (OCR over a scan)

    @property
    def text(self):
        return "".join(ch.c for ch in self.chars)


MARKUP = (fitz.PDF_ANNOT_HIGHLIGHT, fitz.PDF_ANNOT_UNDERLINE, fitz.PDF_ANNOT_STRIKE_OUT,
          fitz.PDF_ANNOT_SQUIGGLY)


def page_lines(page) -> tuple[list[Line], int]:
    """(left-to-right lines of page text, count of other text lines).

    The text of a comment box or form field is in the text layer too, but it
    is not page content: those lines are counted as other."""
    boxes = [a.rect for a in page.annots() or [] if a.type[0] not in MARKUP]
    hidden = set()
    for tr in page.get_texttrace():
        if tr.get("type") == 3 or tr.get("opacity", 1) == 0:
            hidden.add(tuple(round(v) for v in tr["bbox"]))
    raw = page.get_text("rawdict", flags=fitz.TEXT_PRESERVE_WHITESPACE | fitz.TEXT_MEDIABOX_CLIP)
    out, other = [], 0
    for bi, blk in enumerate(raw["blocks"]):
        for ln in blk.get("lines", []):
            chars = [Ch(c["c"], c["origin"][0], sp, page.number, c["bbox"][2])
                     for sp in ln["spans"] for c in sp["chars"]]
            if not "".join(c.c for c in chars).strip():
                continue
            r = fitz.Rect(ln["bbox"])
            if tuple(ln["dir"]) != (1.0, 0.0) or any(
                    (r & b).get_area() > 0.5 * r.get_area() for b in boxes):
                other += 1
                continue
            sp0 = ln["spans"][0]
            hid = any(tuple(round(v) for v in sp["bbox"]) in hidden for sp in ln["spans"])
            out.append(Line(bi, chars, fitz.Rect(ln["bbox"]), sp0["origin"][1],
                            max(sp["size"] for sp in ln["spans"]), ln["spans"], hid))
    out.sort(key=lambda ln: (ln.base, ln.bbox.x0))
    return out, other


def body(page, ln: Line) -> bool:
    h = page.rect.height
    return ln.bbox.y0 >= h * HEAD and ln.bbox.y1 <= h * FOOT


# ── units ────────────────────────────────────────────────────────────────────
def _lead(lines):
    steps = [b.base - a.base for a, b in zip(lines, lines[1:], strict=False)]
    return statistics.median(steps) if steps else lines[0].size * 1.2


def _columns(lines):
    """Lines grouped by column: x ranges that overlap, in reading order."""
    cols: list[list[Line]] = []
    for ln in sorted(lines, key=lambda ln: ln.bbox.x0):
        for col in cols:
            x0 = min(c.bbox.x0 for c in col)
            x1 = max(c.bbox.x1 for c in col)
            if ln.bbox.x0 < x1 - 2 and ln.bbox.x1 > x0 + 2:
                col.append(ln)
                break
        else:
            cols.append([ln])
    for col in cols:
        col.sort(key=lambda ln: ln.base)
    return cols


def units(lines: list[Line], unit: str) -> list[list[Line]]:
    """The page's lines split into units: one per line, per paragraph, or per
    column stretch between wide gaps."""
    if unit == LINE:
        return [[ln] for ln in lines]
    out = []
    for col in _columns(lines):
        cur: list[Line] = []
        for ln in col:
            if cur and _breaks(cur, ln, unit):
                out.append(cur)
                cur = []
            cur.append(ln)
        if cur:
            out.append(cur)
    return out


def _breaks(cur: list[Line], ln: Line, unit: str) -> bool:
    prev = cur[-1]
    step = ln.base - prev.base
    lead = _lead(cur) if len(cur) > 1 else prev.size * 1.25
    if step <= 0 or step > TIGHT_GAP * lead or abs(ln.size - prev.size) >= 0.2 * prev.size:
        return True
    if unit == PAGE:
        return False
    left = min(c.bbox.x0 for c in cur)
    right = max(c.bbox.x1 for c in cur)
    centred = _align(cur + [ln]) == "centre"
    indent = ln.bbox.x0 - left > 0.8 * ln.size and prev.bbox.x0 - left < 0.8 * ln.size
    short = prev.bbox.x1 < right - max(0.12 * (right - left), 2 * prev.size)
    if len(cur) == 1:
        short = False            # one line gives no measure of the full width yet
    return indent or (short and not centred)


def _align(lines: list[Line]) -> str:
    if len(lines) < 2:
        return "left"
    left = min(ln.bbox.x0 for ln in lines)
    right = max(ln.bbox.x1 for ln in lines)
    mid = (left + right) / 2
    body_lines = lines[:-1]
    if all(abs((ln.bbox.x0 + ln.bbox.x1) / 2 - mid) < 2 for ln in lines) and any(
            ln.bbox.x0 - left > 2 for ln in lines):
        return "centre"
    if all(abs(ln.bbox.x1 - right) < 1.5 for ln in lines) and any(
            ln.bbox.x0 - left > 2 for ln in lines):
        return "right"
    if len(body_lines) >= 2 and all(abs(ln.bbox.x1 - right) < 1.5 for ln in body_lines):
        return "justify"
    return "left"


# ── one unit's text as styled characters ─────────────────────────────────────
WORDS = re.compile(r"[^\W\d_]+(?:-[^\W\d_]+)*")


def vocabulary(doc) -> set[str]:
    """The document's own words, lower case, hyphenated ones whole."""
    out: set[str] = set()
    for page in doc:
        out.update(w.lower() for w in WORDS.findall(page.get_text()))
    return out


def _tail_letters(seq) -> str:
    out = ""
    for ch in reversed(seq):
        if not ch.c.isalpha():
            break
        out = ch.c + out
    return out


def unit_chars(lines: list[Line], vocab: set | None = None):
    """(styled characters of the unit, index where each line starts).

    Lines are joined by a space.  After a line-end hyphen with a lower-case
    letter following, they are joined without a space; the hyphen goes only
    when the document spells the joined word without it elsewhere (and never
    with it), so "exam-" + "ple" is "example" and "non-" + "recoverable"
    stays "non-recoverable"."""
    seq: list[Ch] = []
    starts = []
    for i, ln in enumerate(lines):
        chars = list(ln.chars)
        while chars and chars[-1].c.isspace():
            chars.pop()
        if i:
            head = ln.text.lstrip()
            nxt = head[:1]
            if seq and seq[-1].c == "-" and nxt.islower():
                a = _tail_letters(seq[:-1]).lower()
                b = re.match(r"[^\W\d_]*", head).group(0).lower()
                if vocab and a + b in vocab and f"{a}-{b}" not in vocab:
                    seq.pop()
            elif seq:
                seq.append(Ch(" ", seq[-1].x, seq[-1].span, seq[-1].src, seq[-1].x1))
        while chars and chars[0].c.isspace():
            chars.pop(0)
        starts.append(len(seq))
        seq.extend(chars)
    return seq, starts


def unit_text(lines: list[Line], vocab: set | None = None) -> str:
    return "".join(c.c for c in unit_chars(lines, vocab)[0])


def _gaps(lines: list[Line]) -> list[tuple[float, float]]:
    """(gap between two words, size) for each word gap of the lines."""
    out = []
    for ln in lines:
        prev_end, seen_space = None, False
        for ch in ln.chars:
            if ch.c.isspace():
                seen_space = True
                continue
            if prev_end is not None and (seen_space or ch.x - prev_end > 0.25 * ln.size):
                out.append((ch.x - prev_end, ln.size))
            prev_end, seen_space = ch.x1, False
    return out


def tab_laid(lines: list[Line], unit_lines: list[Line]) -> bool:
    """A line laid out with tab stops or form fields: a gap between two
    words much wider than the unit's usual one."""
    allg = [g for g, _s in _gaps(unit_lines)]
    if not allg:
        return False
    usual = statistics.median(allg)
    return any(g > max(2.0 * s, 3 * usual) for g, s in _gaps(lines))


# ── wrapping ─────────────────────────────────────────────────────────────────
def _words(seq, a, b):
    """[(start, end)] of the words in seq[a:b]; a hard break "\\n" is a word."""
    out, i = [], a
    while i < b:
        if seq[i].c == "\n":
            out.append((i, i + 1))
            i += 1
            continue
        if seq[i].c.isspace():
            i += 1
            continue
        j = i
        while j < b and not seq[j].c.isspace():
            j += 1
        out.append((i, j))
        i = j
    return out


def _runs(seq, a, b):
    """Consecutive characters of one span, as (text, span, source page)."""
    out = []
    for ch in seq[a:b]:
        if out and out[-1][1] is ch.span and out[-1][2] == ch.src:
            out[-1][0] += ch.c
        else:
            out.append([ch.c, ch.span, ch.src])
    return out


class Wrapper:
    def __init__(self, page, book: FontBook, doc):
        self.page, self.book, self.doc = page, book, doc

    def width(self, seq, a, b) -> float:
        return sum(self.book.pick(self.page, self.doc[src], span, t).text_length(t, fontsize=span["size"])
                   for t, span, src in _runs(seq, a, b))

    def space(self, ch: Ch) -> float:
        return self.book.pick(self.page, self.doc[ch.src], ch.span, " ").text_length(
            " ", fontsize=ch.span["size"])

    def wrap(self, seq, start, widths, stop_at=None):
        """Greedy lines from seq[start:]: [(first word start, end)], each within
        widths(i); stops after a line that ends where *stop_at* says a line
        started before the change (resync).  Returns (lines, resync index or None)."""
        words = _words(seq, start, len(seq))
        lines, i = [], 0
        while i < len(words):
            avail = widths(len(lines))
            a, b = words[i]
            if seq[a].c == "\n":
                lines.append((a, a))
                i += 1
                continue
            x = self.width(seq, a, b)
            j = i + 1
            while j < len(words) and seq[words[j][0]].c != "\n":
                w = self.width(seq, *words[j]) + self.space(seq[words[j - 1][1] - 1])
                if x + w > avail + 0.6:
                    break
                x += w
                j += 1
            lines.append((a, words[j - 1][1]))
            i = j
            if i < len(words) and seq[words[i][0]].c == "\n":
                i += 1                       # the break is consumed by its line
            if stop_at is not None and i < len(words) and words[i][0] in stop_at:
                return lines, words[i][0]
        return lines, None


# ── what a change becomes ────────────────────────────────────────────────────
@dataclass
class Draw:
    """One line to draw: words at x positions on a baseline."""
    base: float
    words: list                  # [(x, [(text, span, src page)])]
    lead: float
    size: float


def _keep(ln: Line, dy: float) -> Draw:
    """An unchanged line moved down by dy, each word at its own x."""
    words, cur = [], []
    for ch in ln.chars:
        if ch.c.isspace():
            if cur:
                words.append(cur)
                cur = []
        else:
            cur.append(ch)
    if cur:
        words.append(cur)
    out = []
    for w in words:
        out.append((w[0].x, _runs(w, 0, len(w))))
    return Draw(ln.base + dy, out, ln.size * 1.2, ln.size)


@dataclass
class Plan:
    erase: dict = field(default_factory=dict)      # page -> [Line]
    draw: dict = field(default_factory=dict)       # page -> [Draw]

    def add(self, pno, erase=(), draw=()):
        self.erase.setdefault(pno, []).extend(erase)
        self.draw.setdefault(pno, []).extend(draw)


def _set_line(wr: Wrapper, seq, a, b, left, width, align, last, base, lead, size):
    words = _words(seq, a, b)
    ws = [wr.width(seq, *w) for w in words]
    gaps = [wr.space(seq[w[1] - 1]) for w in words[:-1]]
    natural = sum(ws) + sum(gaps)
    x = left
    if align == "centre":
        x = left + (width - natural) / 2
    elif align == "right":
        x = left + width - natural
    extra = (width - natural) / len(gaps) if align == "justify" and not last and gaps else 0.0
    out = []
    for k, (w, wd) in enumerate(zip(words, ws, strict=True)):
        out.append((x, _runs(seq, *w)))
        x += wd + (gaps[k] + extra if k < len(gaps) else 0)
    return Draw(base, out, lead, size)


def _region_risky(page, rect) -> str | None:
    """Why moving text through *rect* is unsafe, or None."""
    area = page.rect.width * page.rect.height
    for info in page.get_image_info():
        r = fitz.Rect(info["bbox"])
        if r.width * r.height < 0.6 * area and r.intersects(rect):   # not a page background
            return "a picture is in the way"
    for dr in page.get_drawings():
        r = fitz.Rect(dr["rect"])
        if r.width * r.height < 0.6 * area and (r.width > 2 or r.height > 2) and r.intersects(rect):
            return "lines or shapes are in the way"
    for link in page.get_links():
        if fitz.Rect(link["from"]).intersects(rect):
            return "a link is in the way"
    for annot in page.annots() or []:
        if annot.rect.intersects(rect):
            return "a comment or form field is in the way"
    return None


def _two_columns(lines: list[Line], page) -> bool:
    cols = [c for c in _columns([ln for ln in lines if body(page, ln)]) if len(c) >= 4]
    return len(cols) > 1


def _in_rows(moving: list[Line], all_lines: list[Line]) -> bool:
    """Text beside the moving text on the same baseline: a table or form row,
    which moving one side would break apart."""
    ids = {id(ln) for ln in moving}
    for ln in moving:
        for other in all_lines:
            if id(other) in ids:
                continue
            if abs(other.base - ln.base) < 0.5 * ln.size and (
                    other.bbox.x0 >= ln.bbox.x1 or other.bbox.x1 <= ln.bbox.x0):
                return True
    return False


def text_area(doc, pno, cache) -> tuple[float, float]:
    """(first, last) body-text baseline on pages near *pno*: where a page's
    text may start and end.  The foot is the lowest text on those pages, or
    the top margin mirrored at the bottom when that is lower (a document of
    part-filled pages never shows its foot), and stays above the footer zone."""
    if pno not in cache:
        tops, top_edges, bottoms = [], [], []
        for p in range(max(0, pno - 3), min(len(doc), pno + 4)):
            page = doc[p]
            ls = [ln for ln in page_lines(page)[0] if body(page, ln)]
            if ls:
                tops.append(min(ln.base for ln in ls))
                top_edges.append(min(ln.bbox.y0 for ln in ls))
                bottoms.append(max(ln.base for ln in ls))
        h = doc[pno].rect.height
        mirror = min(h - min(top_edges), h * FOOT) - 4 if top_edges else h * 0.88
        cache[pno] = (min(tops) if tops else h * 0.1, max(max(bottoms, default=0), mirror))
    return cache[pno]


class Engine:
    def __init__(self, doc, unit=PARAGRAPH):
        if unit not in UNITS:
            raise ValueError(f"unit must be one of {UNITS}")
        self.doc, self.unit = doc, unit
        self.book = FontBook(doc)
        self._area: dict = {}
        self._vocab: set | None = None
        self.fallback_fonts: set[str] = set()

    @property
    def vocab(self) -> set:
        if self._vocab is None:
            self._vocab = vocabulary(self.doc)
        return self._vocab

    def text_of(self, ulines) -> str:
        return unit_text(ulines, self.vocab)

    def _finish(self, plan):
        """The plan, or why not: an erase removes a comment box or form field
        it touches, and a highlight or link would stay where the text was."""
        for pno, lns in plan.erase.items():
            page = self.doc[pno]
            marks = [(a.rect, "a comment, highlight or form field is on this text")
                     for a in page.annots() or []]
            marks += [(fitz.Rect(lk["from"]), "a link is on this text") for lk in page.get_links()]
            for ln in lns:
                for sp in ln.spans:
                    box = erase_box(sp["bbox"], sp["origin"], sp["size"])
                    for r, why in marks:
                        if r.intersects(box):
                            return why if pno == self._pno else f"on page {pno + 1}, {why}"
        return plan

    # -- planning -------------------------------------------------------------
    def plan_change(self, pno, ulines, all_lines, changes):
        """A Plan for replacing, in the unit *ulines*, each (start, end, text)
        of *changes* (indexes into unit_chars); or a reason string."""
        page = self.doc[pno]
        self._pno = pno
        seq0, _s0 = unit_chars(ulines, self.vocab)
        if all("".join(c.c for c in seq0[a:b]) == t for a, b, t in changes):
            return Plan()                       # nothing changes: touch nothing
        if any(ln.hidden for ln in ulines):
            return "it is a hidden text layer (a scanned page)"
        seq, starts = unit_chars(ulines, self.vocab)
        # inserted text takes the style of the character it starts at (the
        # last one when it is added at the end)
        at = min(min(a for a, _b, _t in changes), len(seq) - 1)
        ins_span = seq[at].span if seq else ulines[0].spans[0]
        ins_src = seq[at].src if seq else pno
        new, mapping, pos = [], {}, 0
        for a, b, txt in sorted(changes):
            for i in range(pos, a):
                mapping[i] = len(new)
                new.append(seq[i])
            span = seq[a].span if a < len(seq) else ins_span
            src = seq[a].src if a < len(seq) else ins_src
            new.extend(Ch(c, 0.0, span, src) for c in txt)
            pos = b
        for i in range(pos, len(seq)):
            mapping[i] = len(new)
            new.append(seq[i])
        first = min(a for a, _b, _t in changes)
        last_end = max(b for _a, b, _t in changes)
        k = max(i for i, s in enumerate(starts) if s <= first)
        # where the wrap may stop: an old line start after the last change
        resync = {mapping[s]: j for j, s in enumerate(starts) if s >= last_end and s in mapping and j > k}
        left = min(ln.bbox.x0 for ln in ulines)
        right = max(ln.bbox.x1 for ln in ulines)
        width = right - left
        lead = _lead(ulines)
        size = statistics.median(ln.size for ln in ulines)
        align = _align(ulines) if self.unit != LINE else "left"
        indent = ulines[0].bbox.x0 - left if align in ("left", "justify") else 0.0
        if self.unit == LINE or len(ulines) == 1:
            # one line shows no right margin: its column's, else the left
            # margin mirrored (as text_area mirrors the top for the foot)
            col_right = max((ln.bbox.x1 for ln in all_lines
                             if ln.bbox.x0 < right and ln.bbox.x1 > left), default=right)
            if align == "left" and col_right <= right + 0.5:
                col_right = max(col_right, page.rect.width - left)
            width = col_right - left
        wr = Wrapper(page, self.book, self.doc)
        start = mapping.get(starts[k], 0) if k else 0

        def widths(i):
            return width - (indent if k + i == 0 else 0)

        made, sync = wr.wrap(new, start, widths, stop_at=resync)
        if self.unit == LINE and len(made) > 1:
            return "the line has no room for it"
        old_n = (resync[sync] if sync is not None else len(ulines)) - k
        if tab_laid(ulines[k:k + old_n], ulines):
            return "the text is laid out with tab stops or form fields"
        if _in_rows(ulines[k:k + old_n], all_lines):
            return "the text is laid out in rows (a table or a form)"
        delta = (len(made) - old_n) * lead
        draws = []
        for i, (a, b) in enumerate(made):
            base = ulines[k + i].base if k + i < len(ulines) and i < old_n else (
                ulines[k].base + i * lead)
            x0 = left + (indent if k + i == 0 else 0)
            last = sync is None and i == len(made) - 1
            if a == b:
                continue                      # an empty line from a hard break
            draws.append(_set_line(wr, new, a, b, x0, widths(i), align, last, base, lead, size))
        erase = ulines[k:k + old_n]
        tail = ulines[k + old_n:]
        plan = Plan()
        if not delta:
            plan.add(pno, erase, draws)
            return self._finish(plan)
        if not all(body(page, ln) for ln in ulines):
            return "it would move a header or footer"
        # text below in the column moves by delta; what passes the foot carries on
        below = [ln for ln in all_lines if ln not in ulines and body(page, ln)
                 and ln.bbox.y0 >= ulines[-1].bbox.y1 - 0.5 and ln.bbox.x0 < right and ln.bbox.x1 > left]
        if _two_columns(all_lines, page):
            return "the page has two columns"
        if _in_rows(ulines[k:] + below, all_lines):
            return "the text is laid out in rows (a table or a form)"
        top, foot = text_area(self.doc, pno, self._area)
        region = fitz.Rect(left, ulines[-1].bbox.y1 - 0.5, right, foot + size + abs(delta))
        why = _region_risky(page, region)
        if why:
            return why
        moving = [(_keep(ln, delta), ln) for ln in tail + below]
        plan.add(pno, erase + tail + below)
        stay, carry = [], []
        for d in draws + [m for m, _ln in moving]:
            (carry if d.base > foot + 0.5 else stay).append(d)
        plan.add(pno, draw=stay)
        p = pno
        while carry:
            p += 1
            if p >= len(self.doc):
                return "there is no room left at the end of the document"
            nxt = self.doc[p]
            nlines, _o = page_lines(nxt)
            ntop, nfoot = text_area(self.doc, p, self._area)
            nbody = [ln for ln in nlines if body(nxt, ln)]
            if _two_columns(nlines, nxt):
                return f"page {p + 1} has two columns"
            first_base = min((ln.base for ln in nbody), default=ntop)
            shift = first_base - carry[0].base
            span_h = carry[-1].base - carry[0].base + lead
            why = _region_risky(nxt, fitz.Rect(left, ntop - size, right, nfoot + size + span_h))
            if why:
                return f"on page {p + 1}, {why}"
            moved_carry = [Draw(d.base + shift, d.words, d.lead, d.size) for d in carry]
            pushed = [_keep(ln, span_h) for ln in nbody]
            plan.add(p, erase=nbody)
            carry = []
            for d in moved_carry + pushed:
                (carry if d.base > nfoot + 0.5 else plan.draw.setdefault(p, [])).append(d)
        return self._finish(plan)

    # -- writing --------------------------------------------------------------
    def commit(self, plan: Plan):
        # Fonts and their letters first: erasing a page's last line of a font
        # drops that font from the page, and it could no longer be found.
        for draws in plan.draw.values():
            for d in draws:
                for _x, runs in d.words:
                    for _t, span, src in runs:
                        self.book.own(self.doc[src], span["font"])
                        self.book.used(self.doc[src])
        for pno in sorted(set(plan.erase) | set(plan.draw)):
            page = self.doc[pno]
            for ln in plan.erase.get(pno, []):
                for sp in ln.spans:
                    if "".join(c["c"] for c in sp["chars"]).strip():
                        page.add_redact_annot(erase_box(sp["bbox"], sp["origin"], sp["size"]))
            if plan.erase.get(pno):
                page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE,
                                      graphics=fitz.PDF_REDACT_LINE_ART_NONE,
                                      text=fitz.PDF_REDACT_TEXT_REMOVE)
            for d in sorted(plan.draw.get(pno, []), key=lambda d: d.base):
                self._draw(page, d)

    def _draw(self, page, d: Draw):
        tw, color = None, None
        for x, runs in d.words:
            for text, span, src in runs:
                rgb = span_rgb(span["color"])
                if tw is not None and rgb != color:
                    tw.write_text(page)
                    tw = None
                if tw is None:
                    tw, color = fitz.TextWriter(page.rect, color=rgb), rgb
                x = self._put(tw, page, x, d.base, text, span, self.doc[src])
        if tw is not None:
            tw.write_text(page)

    def _put(self, tw, page, x, y, text, span, src_page):
        font = self.book.pick(page, src_page, span, text)
        if text.strip() and font is not self.book.own(src_page, span["font"])[0]:
            self.fallback_fonts.add(span["font"])
        size = span["size"]
        shared = self.book.shared(font) if font is not self.book.helv else set()
        run = ""

        def flush(x, run):
            if run:
                tw.append(textwriter_point(page, (x, y)), run, font=font, fontsize=size)
                x += font.text_length(run, fontsize=size)
            return x

        for c in text:
            if c in shared:
                x = flush(x, run)
                run = ""
                if not c.isspace():          # a space is left as a gap: the text layer reads it back
                    alt = unicode_font(c) or self.book.helv
                    tw.append(textwriter_point(page, (x, y)), c, font=alt, fontsize=size)
                x += font.text_length(c, fontsize=size)
            else:
                run += c
        return flush(x, run)


def _context(seq_text: str, a: int, b: int) -> str:
    lo, hi = max(0, a - 24), min(len(seq_text), b + 24)
    return ("…" if lo else "") + seq_text[lo:hi].strip() + ("…" if hi < len(seq_text) else "")


def replace_all(doc, needle: str, repl: str, unit: str = PARAGRAPH, stop=None,
                progress=lambda v: None) -> Result | None:
    """Replace every *needle* (case-sensitive) with *repl*, reflowing each
    change in its *unit*.  None when *stop* was set (the caller undoes)."""
    eng = Engine(doc, unit)
    res = Result()
    total = len(doc)
    for n, pno in enumerate(range(total - 1, -1, -1)):   # last page first: carries land on done pages
        if stop is not None and stop.is_set():
            return None
        page = doc[pno]
        found_page = page.get_text().count(needle)
        lines, _other = page_lines(page)
        us = units(lines, unit)
        todo = []
        for u in us:
            t = eng.text_of(u)
            hits, i = [], t.find(needle)
            while i >= 0 and needle:
                hits.append((i, i + len(needle), repl))
                i = t.find(needle, i + len(needle))
            if hits:
                todo.append((u[0].bbox.y0, u[0].bbox.x0, len(hits)))
        done_here = 0
        # bottom of the page first: a push from above moves text already changed
        for y0, x0, _n in sorted(todo, reverse=True):
            lines, _other = page_lines(page)
            us = units(lines, unit)
            u = min(us, key=lambda u: abs(u[0].bbox.y0 - y0) + abs(u[0].bbox.x0 - x0))
            t = eng.text_of(u)
            hits, i = [], t.find(needle)
            while i >= 0 and needle:
                hits.append((i, i + len(needle), repl))
                i = t.find(needle, i + len(needle))
            if not hits:
                continue
            plan = eng.plan_change(pno, u, lines, hits)
            if isinstance(plan, str):
                for a, b, _r in hits:
                    res.skips.append(Skip(pno, _context(t, a, b), plan))
                continue
            eng.commit(plan)
            eng._area.clear()
            eng.book._used.pop(pno, None)
            res.done += len(hits)
            done_here += len(hits)
            res.fallback_fonts |= eng.fallback_fonts
        missed = found_page - done_here - sum(1 for s in res.skips if s.page == pno)
        if missed > 0:
            res.skips.append(Skip(pno, needle, f"{missed} match(es) run across two paragraphs"
                                  " or in text that does not run left to right"))
        progress((n + 1) / total)
    return res


def rewrite_unit(doc, pno: int, ulines: list[Line], new_text: str, unit: str = PARAGRAPH):
    """Edit Text: make the unit read *new_text* ("\\n" a hard line break),
    keeping the styles of the characters that stay.  Returns a Result: done 1,
    or done 0 and the reason in its one Skip."""
    eng = Engine(doc, unit)
    old = eng.text_of(ulines)
    changes = [(a1, a2, new_text[b1:b2])
               for tag, a1, a2, b1, b2 in difflib.SequenceMatcher(None, old, new_text, autojunk=False)
               .get_opcodes() if tag != "equal"]
    if not changes:
        return Result(done=1)
    lines, _o = page_lines(doc[pno])
    plan = eng.plan_change(pno, ulines, lines, changes)
    if isinstance(plan, str):
        return Result(skips=[Skip(pno, _context(old, changes[0][0], changes[-1][1]), plan)])
    eng.commit(plan)
    return Result(done=1, fallback_fonts=set(eng.fallback_fonts))
