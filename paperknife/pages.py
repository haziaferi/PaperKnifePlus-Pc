from __future__ import annotations
import re

_PART = re.compile(r"^(\d+|end)(?:\s*-\s*(\d+|end))?$")


class PageRangeError(ValueError):
    pass


def parse_ranges(text: str, total: int) -> list[tuple[int, int]]:
    """Parse '1-3, 5, 8-end' (1-based) into 0-based inclusive (first, last) pairs.

    Raises PageRangeError for anything that does not name pages that exist,
    so a typo never silently selects other pages or none at all."""
    groups: list[tuple[int, int]] = []
    for raw in text.split(","):
        part = raw.strip().lower()
        if not part:
            continue
        m = _PART.match(part)
        if not m:
            raise PageRangeError(f"'{raw.strip()}' is not a page or page range "
                                 "(use e.g. 1-3, 5, 8-end).")
        a, b = (total if g == "end" else int(g) for g in (m[1], m[2] or m[1]))
        for n in (a, b):
            if n < 1:
                raise PageRangeError(f"'{raw.strip()}': pages start at 1.")
            if n > total:
                raise PageRangeError(f"'{raw.strip()}': page {n} does not exist "
                                     f"(the document has {total} page(s)).")
        if a > b:
            raise PageRangeError(f"'{raw.strip()}': the range runs backwards; "
                                 f"write {b}-{a}.")
        groups.append((a - 1, b - 1))
    if not groups:
        raise PageRangeError("No pages given.")
    return groups
