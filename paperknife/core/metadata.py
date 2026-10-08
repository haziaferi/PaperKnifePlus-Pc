"""Metadata: read, check and write a PDF's document properties."""
from __future__ import annotations
from datetime import datetime

FIELDS = [
    ("title",    "Title"),
    ("author",   "Author"),
    ("subject",  "Subject"),
    ("keywords", "Keywords"),
    ("creator",  "Creator (application)"),
    ("producer", "Producer"),
    ("creationDate", "Creation date"),
    ("modDate",      "Modified date"),
]
DATE_KEYS = ("creationDate", "modDate")


def pdf_date(text: str) -> str:
    """Return *text* as a PDF date string (D:YYYYMMDDHHmmSS); raise ValueError if unreadable."""
    text = text.strip()
    if not text or text.startswith("D:"):
        return text
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).strftime("D:%Y%m%d%H%M%S")
        except ValueError:
            pass
    raise ValueError(text)


def read_metadata(doc) -> dict[str, str]:
    """Every FIELDS key of *doc*'s metadata, "" where it has none."""
    meta = doc.metadata or {}
    return {key: meta.get(key, "") or "" for key, _ in FIELDS}


def check_dates(meta: dict[str, str]) -> str | None:
    """Turn the date fields of *meta* into PDF dates in place.  Returns the
    message to show for the first one that cannot be read, else None."""
    for key, label in FIELDS:
        if key in DATE_KEYS:
            try:
                meta[key] = pdf_date(meta[key])
            except ValueError:
                return (f"{label}: use YYYY-MM-DD, YYYY-MM-DD HH:MM[:SS] "
                        "or a PDF date (D:YYYYMMDDHHmmSS).")
    return None


def apply_metadata(doc, meta: dict[str, str], changed: bool) -> None:
    """Write *meta* into *doc*; when it *changed*, also drop the XMP stream."""
    doc.set_metadata(meta)
    if changed:
        # Viewers read the XMP stream too; left alone it would keep the
        # old (or cleared) values.
        doc.del_xml_metadata()
