"""Split's parts and the grid's range text (paperknife.pages), without a UI."""
import pytest

from paperknife.pages import (PageRangeError, cuts_of, parse_parts, parts_from_cuts,
                              parts_text, ranges_text, take_part)


def test_ranges_text_is_the_inverse_of_a_selection():
    assert ranges_text([]) == ""
    assert ranges_text([4, 0, 1, 2, 2]) == "1-3, 5"
    assert ranges_text([7]) == "8"


def test_parse_parts_reads_ranges_and_joined_pages():
    assert parse_parts("", 3) == [[0], [1], [2]]
    assert parse_parts("1-3, 2+5+7", 7) == [[0, 1, 2], [1, 4, 6]]
    assert parse_parts("1-2+5-end", 6) == [[0, 1, 4, 5]]
    with pytest.raises(PageRangeError):
        parse_parts("1+9", 5)


@pytest.mark.parametrize("parts", [[[0, 1, 2], [3]], [[1, 4], [0, 2, 3, 5]], [[5], [0]]])
def test_parts_text_reads_back_as_the_same_parts(parts):
    assert parse_parts(parts_text(parts), 6) == parts


def test_cuts_and_parts():
    assert parts_from_cuts(5, {1, 3}) == [[0, 1], [2, 3], [4]]
    assert parts_from_cuts(3, set()) == [[0, 1, 2]]
    assert cuts_of([[0, 1], [2, 3], [4]], 5) == {1, 3}
    assert cuts_of([[1, 4], [0, 2, 3]], 5) is None          # scattered
    assert cuts_of([[0, 1]], 3) is None                     # a page left out


def test_take_part_moves_pages_and_drops_empty_parts():
    assert take_part([[0, 1, 2, 3, 4, 5]], [4, 1]) == [[1, 4], [0, 2, 3, 5]]
    assert take_part([[0], [1], [2]], [1]) == [[0], [1], [2]]
    assert take_part([[0, 1], [2, 3]], [2, 3]) == [[0, 1], [2, 3]]
    assert take_part([[0]], []) == [[0]]
