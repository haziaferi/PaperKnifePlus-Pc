"""Owner (2026-10-10): the after-job bar is the same length on every screen,
half the page area (the window less the navigation pane), with its buttons
right after the text; a group with one tool (Read: Read / Preview) has no
title and never folds."""
import pytest

from qt_harness import make_pdf, pump, wait_job


def _merge(window, dialogs, tmp_path):
    a, b = make_pdf(tmp_path / "a.pdf"), make_pdf(tmp_path / "b.pdf")
    assert window.open_tool("MergeTool")
    pump(0.05)
    page = window.current_page()
    page.add_paths([a, b])
    dialogs.save(str(tmp_path / "merged1.pdf"))
    page.run()
    wait_job(window)
    return page


def _extract(window, dialogs, tmp_path):
    # a job that writes one new PDF on an organiser screen (Compress changes
    # the document since 2026-10-23)
    assert window.open_tool("RotateTool", make_pdf(tmp_path / "in.pdf"))
    pump(0.05)
    page = window.current_page()
    page.select(0)
    dialogs.save(str(tmp_path / "extracted1.pdf"))
    page.extract()
    wait_job(window)
    return page


@pytest.mark.parametrize("run", [_extract, _merge], ids=["extract", "merge"])
@pytest.mark.parametrize("width", [1280, 1700, 2400])   # 2400: room to spare offscreen
def test_the_bar_is_half_the_page_with_its_buttons_after_the_text(window, dialogs, tmp_path,
                                                                 run, width):
    window.resize(width, 820)
    pump(0.1)
    page = run(window, dialogs, tmp_path)
    pump(0.1)
    bar = page.offer_bar()
    assert bar is not None and bar.isVisibleTo(page)
    # half the page, unless the text and buttons need more (a long file name is
    # never cut; offscreen test fonts are wider than Windows', so they often do)
    want = max(bar.minimumSizeHint().width(), page.width() // 2)
    assert abs(bar.width() - want) <= 2, (bar.width(), want, page.width())
    title_right = bar.titleLabel.geometry().right()
    gap = bar.continue_button.geometry().left() - title_right
    assert 0 <= gap <= 40, f"buttons {gap} px after the text"


def test_the_bar_is_the_same_length_on_both_screens(window, dialogs, tmp_path):
    window.resize(2400, 820)          # wide enough that half the page fits both texts
    pump(0.1)
    widths = [run(window, dialogs, tmp_path).offer_bar().width() for run in (_extract, _merge)]
    assert abs(widths[0] - widths[1]) <= 2, widths


def test_a_group_with_one_tool_has_no_title(window):
    sections = {s: (h, keys) for s, h, keys in window._sections}
    header, keys = sections["READ"]
    assert keys == ["ReaderTool"] and header is None
    window.toggle_group("READ")                      # nothing to fold: still shown
    pump(0.05)
    assert window._items["ReaderTool"].isVisible()
    for s, (h, ks) in sections.items():
        if len(ks) > 1 and s not in ("SETTINGS",):
            assert h is not None, s
