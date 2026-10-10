"""Merge / Split / Rotate / Split-by-Bookmarks / TOC."""

import pytest



# ── shared page-range parser (L2-12..15) ─────────────────────────────────────
@pytest.mark.parametrize("text, groups", [
    ("1-3, 5", [(0, 2), (4, 4)]),
    ("2-end", [(1, 4)]),
    ("END", [(4, 4)]),
    (" 1 - 2 ,, 4 ", [(0, 1), (3, 3)]),
    ("3-3", [(2, 2)]),
])
def test_parse_ranges_accepts(text, groups):
    from paperknife.pages import parse_ranges
    assert parse_ranges(text, 5) == groups


@pytest.mark.parametrize("text, words", [
    ("99", "does not exist"),
    ("7-9", "does not exist"),
    ("4-6", "does not exist"),
    ("0", "start at 1"),
    ("5-3", "backwards"),
    ("abc", "not a page"),
    ("1-", "not a page"),
    ("-2", "not a page"),
    ("1.5", "not a page"),
    (" , ", "No pages"),
])
def test_parse_ranges_rejects(text, words):
    from paperknife.pages import PageRangeError, parse_ranges
    with pytest.raises(PageRangeError, match=words):
        parse_ranges(text, 5)


