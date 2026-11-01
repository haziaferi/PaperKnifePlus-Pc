"""OCR: find Tesseract, read the words of rendered pages, and add them to the
PDF as an invisible text layer (or typeset them as a text-only PDF)."""
from __future__ import annotations
import functools
import html
import importlib.util as _ilu
import math
import os
import shutil
from typing import NamedTuple

import pymupdf as fitz
from PIL import Image

from ..job_queue import atomic_output
from ..pages import render

HAS_OCR  = _ilu.find_spec("pytesseract") is not None
# Measured by ScanKnife+ (docs/ocr-bench/questions.md, 2026-10; Tesseract's fast
# models, as the Windows installer ships them):
# - the text layer keeps every word: it is invisible, so a junk word costs nothing
#   and a dropped one cannot be found (question 4);
# - the text-only copy leaves out words below 40, which removed 306 junk words for
#   82 real ones out of about 31,000 (question 4);
# - orientation detection's turn is taken from a confidence of 3: no wrong turn in
#   200 pages above 1.5 (question 5).
TEXT_MIN_CONF = 40
MIN_TURN_CONF = 3
# PIL's transposition that turns an image clockwise by the key
_TURN_CW = {90: Image.Transpose.ROTATE_270, 180: Image.Transpose.ROTATE_180,
            270: Image.Transpose.ROTATE_90}
# Where the UB-Mannheim installer puts Tesseract; it does not add itself to PATH.
TESS_DIRS = (("ProgramFiles", "Tesseract-OCR"), ("ProgramFiles(x86)", "Tesseract-OCR"),
             ("LOCALAPPDATA", r"Programs\Tesseract-OCR"))


def tesseract():
    """pytesseract, pointed at the Tesseract binary: PATH first, then its install folders."""
    import pytesseract
    pt = pytesseract.pytesseract
    if pt.tesseract_cmd == "tesseract" and not shutil.which("tesseract"):
        for var, sub in TESS_DIRS:
            base = os.environ.get(var)
            if base and os.path.isfile(exe := os.path.join(base, sub, "tesseract.exe")):
                pt.tesseract_cmd = exe
                break
    return pytesseract


# ── Languages (owner, 2026-10-22: pick from the installed ones; Windows' display
# language the first time, the last one used after that) ─────────────────────────
NOT_TEXT = {"osd", "equ"}          # page orientation and maths, not text languages
LANG_NAMES = {
    "eng": "English", "ita": "Italian", "deu": "German", "fra": "French", "spa": "Spanish",
    "por": "Portuguese", "nld": "Dutch", "ell": "Greek", "grc": "Ancient Greek",
    "lat": "Latin", "pol": "Polish", "ces": "Czech", "slk": "Slovak", "slv": "Slovenian",
    "hrv": "Croatian", "srp": "Serbian", "ron": "Romanian", "hun": "Hungarian",
    "fin": "Finnish", "swe": "Swedish", "nor": "Norwegian", "dan": "Danish",
    "tur": "Turkish", "rus": "Russian", "ukr": "Ukrainian", "bul": "Bulgarian",
    "ara": "Arabic", "heb": "Hebrew", "hin": "Hindi", "jpn": "Japanese",
    "chi_sim": "Chinese (simplified)", "chi_tra": "Chinese (traditional)", "kor": "Korean",
    "cat": "Catalan", "eus": "Basque", "glg": "Galician",
    "ita_old": "Italian (old)", "spa_old": "Spanish (old)", "enm": "Middle English",
    "frm": "Middle French", "frk": "German (Fraktur)",
}
# ISO 639-1 (what Windows' locale names start with) -> Tesseract's code
_ISO_TO_TESS = {"en": "eng", "it": "ita", "de": "deu", "fr": "fra", "es": "spa", "pt": "por",
                "nl": "nld", "el": "ell", "pl": "pol", "cs": "ces", "sk": "slk", "sl": "slv",
                "hr": "hrv", "sr": "srp", "ro": "ron", "hu": "hun", "fi": "fin", "sv": "swe",
                "nb": "nor", "no": "nor", "da": "dan", "tr": "tur", "ru": "rus", "uk": "ukr",
                "bg": "bul", "ar": "ara", "he": "heb", "hi": "hin", "ja": "jpn", "ko": "kor",
                "ca": "cat", "eu": "eus", "gl": "glg"}


def lang_name(code: str) -> str:
    return LANG_NAMES.get(code, code)


@functools.lru_cache(maxsize=1)
def _languages() -> tuple[str, ...]:
    try:
        langs = tesseract().get_languages(config="")
    except Exception:
        return ()
    return tuple(c for c in langs if c not in NOT_TEXT)


def installed_languages() -> list[str]:
    """Tesseract's installed text languages (codes), [] when it cannot be asked.  Asked
    once per run (it starts a Tesseract process)."""
    return list(_languages())


def windows_language() -> str:
    """Windows' display language as a Tesseract code ("ita"), or "" when unknown."""
    try:
        import ctypes
        import locale
        lcid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
        name = locale.windows_locale.get(lcid, "")
    except Exception:
        return ""
    return _ISO_TO_TESS.get(name.split("_")[0].lower(), "")


def default_lang(installed: list[str] | None = None) -> str:
    """The language a picker starts with: the one last used (saved in the preferences),
    else Windows' display language when installed, else English."""
    from ..prefs import PREFS
    saved = str(PREFS.get("ocr_lang", "") or "").strip()
    if saved:
        return saved
    installed = installed_languages() if installed is None else installed
    win = windows_language()
    return win if win and win in installed else "eng"


def remember_lang(lang: str) -> None:
    """A run used *lang*: it becomes the next default."""
    from ..prefs import PREFS
    lang = (lang or "").strip()
    if lang and PREFS.get("ocr_lang", "") != lang:
        PREFS.ocr_lang = lang
        PREFS.save()


class OcrWord(NamedTuple):
    """A word Tesseract read: its box in page.rect space, its text, Tesseract's
    confidence (0-100) and (block, paragraph, line), which tell where the text breaks."""
    rect: fitz.Rect
    text: str
    conf: float
    line: tuple[int, int, int]


def upright_turn(img) -> int:
    """The clockwise turn (0, 90, 180 or 270) that makes the page in *img* upright:
    Tesseract's orientation detection, taken from a confidence of MIN_TURN_CONF.
    0 when it cannot tell (Tesseract refuses a page with too little text) or
    cannot run; the reading that follows reports a missing Tesseract."""
    pytesseract = tesseract()
    try:
        osd = pytesseract.image_to_osd(img, output_type=pytesseract.Output.DICT)
    except (RuntimeError, ValueError, OSError):
        return 0
    turn = int(osd.get("rotate", 0)) % 360
    if turn in _TURN_CW and float(osd.get("orientation_conf", 0)) >= MIN_TURN_CONF:
        return turn
    return 0


def _unturned(box, width: int, height: int, turn: int):
    """*box* (pixels of a *width* x *height* image that is the page turned
    clockwise by *turn*) as pixels of the page image before the turn."""
    u0, v0, u1, v1 = box
    if turn == 90:
        return v0, width - u1, v1, width - u0
    if turn == 180:
        return width - u1, height - v1, width - u0, height - v0
    if turn == 270:
        return height - v1, u0, height - v0, u1
    return box


def ocr_words(img, lang: str, scale: float, turn: int = 0) -> list[OcrWord]:
    """Every word Tesseract reads in *img* (a page rendered at *scale*), read
    turned clockwise by *turn* and boxed in page.rect space, whatever its
    confidence: the text layer is invisible, so a junk word costs nothing and a
    dropped one cannot be found (ScanKnife+, question 4)."""
    pytesseract = tesseract()
    upright = img.transpose(_TURN_CW[turn]) if turn else img
    data = pytesseract.image_to_data(upright, lang=lang, output_type=pytesseract.Output.DICT)
    n = len(data["text"])
    blocks, pars, lines = (data.get(k) or [0] * n for k in ("block_num", "par_num", "line_num"))
    width, height = upright.size
    words = []
    for text, conf, x, y, w, h, b, p, ln in zip(
            data["text"], data["conf"], data["left"], data["top"], data["width"],
            data["height"], blocks, pars, lines, strict=True):
        text = text.strip()
        if text:
            box = _unturned((x, y, x + w, y + h), width, height, turn)
            words.append(OcrWord(fitz.Rect(box) * (1 / scale), text, float(conf),
                                 (int(b), int(p), int(ln))))
    return words


def words_text(words, min_conf: float = TEXT_MIN_CONF) -> str:
    """*words* as plain text without those below *min_conf*: words on a line joined
    by spaces, lines by a line break, blocks by an empty line."""
    out, last = [], None
    for w in words:
        if w.conf < min_conf:
            continue
        if last is not None:
            out.append("\n\n" if w.line[0] != last[0] else "\n" if w.line != last else " ")
        out.append(w.text)
        last = w.line
    return "".join(out)


def add_text_layer(page: fitz.Page, words, turn: int = 0) -> None:
    """Add *words* ((rect, text, ...) in page.rect space) to *page* as invisible,
    searchable text, each word filling its box: its height from the font's ascent
    to its descent, its length stretched to the box's, so a selection covers the
    printed word.  On a page read turned clockwise by *turn* the words run as the
    printed text does: turned back anticlockwise."""
    if not words:
        return
    if page.rotation:
        # Text placed on a rotated page lands in unrotated space, and
        # remove_rotation() shifts the content of a cropped page; derotating
        # the uncropped page and re-applying the crop keeps both right.
        crop = page.cropbox
        page.set_cropbox(page.mediabox)
        mat = page.rotation_matrix
        page.remove_rotation()
        page.set_cropbox((crop * mat) & page.mediabox)
    layer = fitz.open()
    lp = layer.new_page(width=page.rect.width, height=page.rect.height)
    tw = fitz.TextWriter(lp.rect)
    probe = fitz.TextWriter(lp.rect)            # measures a word's length
    font = fitz.Font("helv")      # MuPDF falls back to its Noto fonts for other scripts
    em = font.ascender - font.descender
    lang = fitz.mupdf.fz_text_language_from_string(None)
    cos, sin = round(math.cos(math.radians(turn))), round(math.sin(math.radians(turn)))
    sideways = turn in (90, 270)
    for rect, text, *_ in words:
        # The box in the writer's space: PDF's, y up from the bottom.
        left, right = rect.x0, rect.x1
        bottom, top = lp.rect.height - rect.y1, lp.rect.height - rect.y0
        across = right - left if sideways else top - bottom
        along = top - bottom if sideways else right - left
        if across <= 0 or along <= 0:
            continue
        size = across / em
        length = probe.append((0, 0), text, font=font, fontsize=size)[1].x
        if length <= 0:
            continue
        stretch = along / length
        drop = -font.descender * size           # the baseline above the box's edge
        x, y = {90: (right - drop, bottom), 180: (right, top - drop),
                270: (left + drop, top)}.get(turn, (left, bottom + drop))
        # TextWriter.append has no stretch or turn: its call with a text matrix
        # that has both (font size and stretch along, turned anticlockwise).
        trm = fitz.mupdf.fz_make_matrix(size * stretch * cos, size * stretch * sin,
                                        -size * sin, size * cos, x, y)
        fitz.mupdf.fz_show_string(tw.this, font.this, trm, text, 0, 0, 0, lang)
    tw.write_text(lp, render_mode=3)
    layer.subset_fonts()
    # TextWriter ignores a cropbox offset on the target page; show_pdf_page honours it.
    page.show_pdf_page(page.rect, layer, 0)
    layer.close()


def ocr_pdf(doc, out: str, lang: str, dpi: int, text_only: bool, stop, progress,
            on_page=None, pages=None) -> int | None:
    """OCR every page of *doc* (closed here) rendered at *dpi* and write *out*:
    the original pages with an invisible text layer, or with *text_only* one
    A4 page of plain text per page.  *on_page(n, total)* is called before page
    n (1-based) is read.  Returns the number of pages, or None if cancelled,
    writing nothing.  Raises RuntimeError when Tesseract cannot be found.
    *pages* (0-based) limits the reading to those pages; the others are
    kept as they are (and left out of a text-only PDF)."""
    pytesseract = tesseract()

    try:
        pytesseract.get_tesseract_version()
    except pytesseract.TesseractNotFoundError:
        doc.close()
        raise RuntimeError(
            "Tesseract not found on PATH or in Program Files\\Tesseract-OCR.\n"
            "Install it from: https://github.com/UB-Mannheim/tesseract/wiki") from None

    seq = list(range(len(doc))) if pages is None else list(pages)
    total = len(seq)
    scale = dpi / 72.0
    # doc is closed before the replace, so the output may be the input file.
    with atomic_output(out) as tmp, doc, fitz.open() as nd:
        for n, pg_i in enumerate(seq):
            page = doc[pg_i]
            if stop.is_set():
                return None
            if on_page is not None:
                on_page(n + 1, total)
            progress((n + 1) / total)

            pix = render(page, scale)
            # Grey (measured 2026-11-01 on simulated scans): as many words as the
            # colour page, 0.7-1.1 s a page sooner.  Not contrast-stretched as
            # ScanKnife+ does (question 8): on a page of one line, whose ink is less
            # than the 0.5% clipped at each end, the stretch spread the paper's grain
            # from black to white and no word was read.
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples).convert("L")
            turn = upright_turn(img)
            words = ocr_words(img, lang, scale, turn)

            if text_only:
                text = words_text(words)
                A4   = fitz.paper_rect("A4")
                np   = nd.new_page(width=A4.width, height=A4.height)
                np.insert_htmlbox(A4,
                                  f"<pre>{html.escape(text)}</pre>",
                                  css="pre { font-size: 10pt; }")
            else:
                add_text_layer(page, words, turn)

        if text_only:
            nd.save(tmp, deflate=True)
        else:
            # Merges the fonts each page's text layer brings, at a cost that
            # grows linearly (garbage=3 grows with the square of the pages).
            doc.save(tmp, garbage=4, deflate=True, clean=True)
    return total
