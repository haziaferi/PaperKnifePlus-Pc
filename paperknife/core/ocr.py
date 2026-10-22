"""OCR: find Tesseract, read the words of rendered pages, and add them to the
PDF as an invisible text layer (or typeset them as a text-only PDF)."""
from __future__ import annotations
import functools
import html
import importlib.util as _ilu
import os
import shutil

import pymupdf as fitz
from PIL import Image

from ..job_queue import atomic_output
from ..pages import render

HAS_OCR  = _ilu.find_spec("pytesseract") is not None
MIN_CONF = 30
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


def ocr_words(img, lang: str, scale: float) -> list[tuple[fitz.Rect, str]]:
    """Tesseract words in *img* (a page rendered at *scale*) as (rect, text) in page.rect space."""
    pytesseract = tesseract()
    data = pytesseract.image_to_data(img, lang=lang, output_type=pytesseract.Output.DICT)
    to_page = fitz.Matrix(1 / scale, 1 / scale)
    words = []
    for text, conf, x, y, w, h in zip(data["text"], data["conf"], data["left"],
                                      data["top"], data["width"], data["height"],
                                      strict=True):
        text = text.strip()
        if text and float(conf) >= MIN_CONF:
            words.append((fitz.Rect(x, y, x + w, y + h) * to_page, text))
    return words


def add_text_layer(page: fitz.Page, words) -> None:
    """Add *words* ((rect, text) in page.rect space) to *page* as invisible, searchable text."""
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
    font = fitz.Font("helv")      # TextWriter falls back to MuPDF's Noto fonts for other scripts
    for rect, text in words:
        tw.append(fitz.Point(rect.x0, rect.y1), text, font=font,
                  fontsize=max(1, rect.height * 0.85))
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
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

            if text_only:
                text = pytesseract.image_to_string(img, lang=lang)
                A4   = fitz.paper_rect("A4")
                np   = nd.new_page(width=A4.width, height=A4.height)
                np.insert_htmlbox(A4,
                                  f"<pre>{html.escape(text)}</pre>",
                                  css="pre { font-size: 10pt; }")
            else:
                add_text_layer(page, ocr_words(img, lang, scale))

        if text_only:
            nd.save(tmp, deflate=True)
        else:
            # Merges the fonts each page's text layer brings, at a cost that
            # grows linearly (garbage=3 grows with the square of the pages).
            doc.save(tmp, garbage=4, deflate=True, clean=True)
    return total
