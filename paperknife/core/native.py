"""Write text back through the page's own font (owner, 2026-10-11).

TextWriter embeds a new copy of a font and writes its own character map, and
that map cuts characters beyond U+FFFF (the math alphabet: 𝐾 U+1D43E reads
back as U+1D43).  Here the text is written as the page's own glyph codes in
the page's own font object, so the font's own map from codes to characters
(its ToUnicode, or its encoding) reads it back exactly as it was.

A NativeFont knows, for one font object of the document, which code draws a
character and how wide it is (from the font's /Widths or /W, as viewers lay
it out).  Two kinds are handled: Type0 fonts with Identity-H encoding (Word,
LibreOffice, browsers) and simple one-byte fonts (Type1, TrueType).  Type3
fonts and anything whose codes cannot be worked out are None: the caller
falls back to TextWriter.
"""
from __future__ import annotations

import re

import pymupdf as fitz

_HEX = re.compile(rb"<([0-9A-Fa-f]*)>")
_TOKEN = re.compile(rb"\[|\]|<[0-9A-Fa-f]*>|[-+]?\d*\.?\d+")

# one-byte base encodings by name; StandardEncoding is close enough to Latin-1
# for the letters it shares, and anything else needs a ToUnicode or Differences
_BASE = {"WinAnsiEncoding": "cp1252", "MacRomanEncoding": "mac_roman",
         "StandardEncoding": "latin-1", "PDFDocEncoding": "latin-1"}


def _obj(doc, value: tuple):
    """The PDF source of an xref_get_key result, following one reference."""
    kind, val = value
    if kind == "xref":
        return doc.xref_object(int(val.split()[0]), compressed=True)
    return val


def _xref(value: tuple) -> int:
    return int(value[1].split()[0]) if value[0] == "xref" else 0


def _utf16(hexstr: bytes) -> str:
    raw = bytes.fromhex(hexstr.decode())
    try:
        return raw.decode("utf-16-be")
    except UnicodeDecodeError:
        return ""


def _parse_tounicode(data: bytes) -> dict[str, int]:
    """{character(s): code} from a ToUnicode CMap stream (first code wins)."""
    out: dict[str, int] = {}

    def put(text, code):
        if text and text not in out:
            out[text] = code

    for block in re.findall(rb"beginbfchar(.*?)endbfchar", data, re.S):
        vals = _HEX.findall(block)
        for src, dst in zip(vals[0::2], vals[1::2], strict=False):
            put(_utf16(dst), int(src, 16))
    for block in re.findall(rb"beginbfrange(.*?)endbfrange", data, re.S):
        for m in re.finditer(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*(\[[^\]]*\]|<[0-9A-Fa-f]+>)", block):
            lo, hi, dst = int(m.group(1), 16), int(m.group(2), 16), m.group(3)
            if dst.startswith(b"["):
                for i, d in enumerate(_HEX.findall(dst)):
                    put(_utf16(d), lo + i)
            else:
                text = _utf16(dst[1:-1])
                if not text:
                    continue
                for i in range(min(hi - lo + 1, 65536)):
                    put(text[:-1] + chr(ord(text[-1]) + i), lo + i)
    return out


def _numbers(src: str) -> list:
    """Tokens of a PDF array source: numbers, and '[' / ']' marks."""
    out = []
    for t in _TOKEN.findall(src.encode()):
        out.append(t.decode() if t in (b"[", b"]") else float(t))
    return out


class NativeFont:
    """One font object of the document, written through by code."""

    def __init__(self, doc, xref: int):
        self.doc, self.xref = doc, xref
        self.codes: dict[str, int] = {}
        self.widths: dict[int, float] = {}
        self.default_width = 0.0
        self.two_byte = False
        self.ok = False
        try:
            self._load()
        except Exception:                        # noqa: BLE001 - a font we cannot read is no font
            self.ok = False

    def _load(self):
        doc, x = self.doc, self.xref
        subtype = doc.xref_get_key(x, "Subtype")[1]
        tu = doc.xref_get_key(x, "ToUnicode")
        if _xref(tu):
            self.codes = _parse_tounicode(doc.xref_stream(_xref(tu)) or b"")
        if subtype == "/Type0":
            enc = doc.xref_get_key(x, "Encoding")[1]
            if enc not in ("/Identity-H",) or not self.codes:
                return
            self.two_byte = True
            desc = _obj(doc, doc.xref_get_key(x, "DescendantFonts"))
            dx = int(re.search(r"(\d+)\s+0\s+R", desc).group(1)) if "R" in desc else 0
            if not dx:
                return
            self.default_width = float(doc.xref_get_key(dx, "DW")[1] or 1000) \
                if doc.xref_get_key(dx, "DW")[0] != "null" else 1000.0
            w = doc.xref_get_key(dx, "W")
            if w[0] != "null":
                self._cid_widths(_numbers(_obj(doc, w)))
            self.ok = True
            return
        if subtype not in ("/Type1", "/TrueType", "/MMType1"):
            return                               # Type3 and the rest: TextWriter
        if not self.codes:
            self.codes = self._from_encoding()
        first = doc.xref_get_key(x, "FirstChar")
        widths = doc.xref_get_key(x, "Widths")
        if first[0] == "null" or widths[0] == "null" or not self.codes:
            return
        fc = int(float(first[1]))
        for i, wv in enumerate(n for n in _numbers(_obj(doc, widths)) if not isinstance(n, str)):
            self.widths[fc + i] = wv
        self.codes = {c: k for c, k in self.codes.items() if 0 <= k <= 255}
        self.ok = bool(self.codes)

    def _cid_widths(self, toks):
        if toks[:1] == ["["] and toks[-1:] == ["]"]:
            toks = toks[1:-1]                    # the /W array's own brackets
        i = 0
        while i < len(toks):
            c = toks[i]
            if i + 1 < len(toks) and toks[i + 1] == "[":
                j, k = i + 2, int(c)
                while j < len(toks) and toks[j] != "]":
                    self.widths[k] = toks[j]
                    k += 1
                    j += 1
                i = j + 1
            elif i + 2 < len(toks):
                for k in range(int(c), int(toks[i + 1]) + 1):
                    self.widths[k] = toks[i + 2]
                i += 3
            else:
                break

    def _from_encoding(self) -> dict[str, int]:
        doc, x = self.doc, self.xref
        enc = doc.xref_get_key(x, "Encoding")
        base, diffs = None, []
        if enc[0] == "name":
            base = _BASE.get(enc[1].lstrip("/"))
        elif enc[0] in ("dict", "xref"):
            src = _obj(doc, enc)
            m = re.search(r"/BaseEncoding\s*/(\w+)", src)
            base = _BASE.get(m.group(1)) if m else "latin-1"
            d = re.search(r"/Differences\s*\[(.*?)\]", src, re.S)
            diffs = re.findall(r"(\d+)|/([^\s/\[\]]+)", d.group(1)) if d else []
        else:
            return {}                            # the font's built-in encoding: unknown here
        out: dict[str, int] = {}
        if base:
            for code in range(32, 256):
                try:
                    out.setdefault(bytes([code]).decode(base), code)
                except UnicodeDecodeError:
                    pass
        code = 0
        for num, name in diffs:
            if num:
                code = int(num)
                continue
            u = fitz.glyph_name_to_unicode(name)
            if u and u != 0xFFFD:
                ch = chr(u)
                for k in [k for k, v in out.items() if v == code]:
                    del out[k]
                out[ch] = code
            code += 1
        return out

    # -- use --------------------------------------------------------------------
    def encode(self, text: str) -> bytes | None:
        """The codes that draw *text*, or None if any character has none."""
        out = bytearray()
        for c in text:
            code = self.codes.get(c)
            if code is None:
                return None
            # no width for the code: the font object does not draw it (a
            # subset without that letter), or a viewer would lay it out at 0
            if not self.widths.get(code, self.default_width) and not c.isspace():
                return None
            out += code.to_bytes(2 if self.two_byte else 1, "big")
        return bytes(out)

    def width(self, text: str, size: float) -> float:
        total = 0.0
        for c in text:
            code = self.codes.get(c, -1)
            total += self.widths.get(code, self.default_width)
        return total / 1000 * size


def font_xrefs(page) -> dict[str, int]:
    """{normalised font name: xref} of the fonts the page uses."""
    out = {}
    for xref, _ext, _t, base, *_rest in page.get_fonts(full=True):
        out.setdefault("".join(c for c in base.split("+")[-1] if c.isalnum()).lower(), xref)
    return out


def font_dict(page) -> tuple[int, str] | None:
    """(object, key path) where the page's /Font resources can be written,
    or None when the page inherits its resources (then TextWriter is used:
    giving the page its own would hide the inherited ones)."""
    doc = page.parent
    res = doc.xref_get_key(page.xref, "Resources")
    if res[0] == "xref":
        target, prefix = _xref(res), ""
    elif res[0] == "dict":
        target, prefix = page.xref, "Resources/"
    else:
        return None
    font = doc.xref_get_key(target, prefix + "Font")
    if font[0] == "xref":
        return _xref(font), ""
    return target, prefix + "Font/"


class Emitter:
    """Collects one page's text drawn by code and appends it as one content
    stream, with the fonts it names put in the page's resources."""

    def __init__(self, page):
        self.page = page
        self.ops: list[str] = []
        self.fonts: set[int] = set()
        self._m = ~page.transformation_matrix
        self.where = font_dict(page)

    @property
    def usable(self) -> bool:
        return self.where is not None

    def show(self, font: NativeFont, x: float, y: float, codes: bytes, size: float, rgb):
        p = fitz.Point(x, y) * self._m
        name = f"PKN{font.xref}"
        self.fonts.add(font.xref)
        r, g, b = rgb
        self.ops.append(f"BT /{name} {size:g} Tf {r:.4f} {g:.4f} {b:.4f} rg "
                        f"1 0 0 1 {p.x:.3f} {p.y:.3f} Tm <{codes.hex().upper()}> Tj ET")

    def flush(self):
        if not self.ops:
            return
        page, doc = self.page, self.page.parent
        target, prefix = self.where
        for x in sorted(self.fonts):
            doc.xref_set_key(target, f"{prefix}PKN{x}", f"{x} 0 R")
        page.wrap_contents()
        stream = ("q\n" + "\n".join(self.ops) + "\nQ").encode()
        new = doc.get_new_xref()
        doc.update_object(new, "<<>>")
        doc.update_stream(new, stream)
        old = page.get_contents()
        doc.xref_set_key(page.xref, "Contents", "[" + " ".join(f"{c} 0 R" for c in old + [new]) + "]")
        self.ops, self.fonts = [], set()
