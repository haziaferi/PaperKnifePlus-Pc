"""Text on the app's own button colours meets WCAG AA (4.5:1) in both themes."""
import pytest


def _lum(hexstr):
    h = hexstr.lstrip("#")[-6:]
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def _ratio(a, b):
    hi, lo = sorted((_lum(a), _lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


@pytest.mark.parametrize("dark", [False, True])
@pytest.mark.parametrize("bg,fg", [("danger", "on_danger"), ("danger_hover", "on_danger")])
def test_button_text_contrast(dark, bg, fg):
    from paperknife.qt import theme
    r = _ratio(theme.hex_color(bg, dark), theme.hex_color(fg, dark))
    assert r >= 4.5, f"{fg} on {bg} ({'dark' if dark else 'light'}): {r:.2f}"
