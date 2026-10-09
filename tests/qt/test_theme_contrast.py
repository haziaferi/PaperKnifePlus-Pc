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


def test_glyph_paint_does_not_list_the_installed_fonts_each_time(qapp, monkeypatch):
    # R1-7: every Glyph paint rebuilt a set of every installed font family
    # (~7 ms with 1000+ families) on the UI thread.
    from PySide6.QtCore import QRect
    from PySide6.QtGui import QImage, QPainter
    from paperknife.qt import theme
    getattr(theme.icon_font_family, "cache_clear", lambda: None)()
    real = theme.QFontDatabase.families
    calls = []

    class CountingDB:
        @staticmethod
        def families(*a):
            calls.append(1)
            return real(*a)
    monkeypatch.setattr(theme, "QFontDatabase", CountingDB)
    img = QImage(32, 32, QImage.Format_ARGB32_Premultiplied)
    p = QPainter(img)
    g = theme.Glyph(0xE80F)
    for _ in range(5):
        g.render(p, QRect(0, 0, 32, 32))
    p.end()
    assert len(calls) <= 1
