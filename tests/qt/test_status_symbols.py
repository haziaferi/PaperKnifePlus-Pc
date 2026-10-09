"""A coloured status line names its state with a symbol, not by colour alone
(WCAG 1.4.1): ✓ success, ⚠ warning, ✗ danger; muted lines carry none."""
import pytest


@pytest.mark.parametrize("msg,role,shown", [
    ("Undo applied", "success", "✓  Undo applied"),
    ("✓  Saved → a.pdf", "success", "✓  Saved → a.pdf"),
    ("✓  Cropped 2 page(s) · 1 skipped", "warning", "⚠  Cropped 2 page(s) · 1 skipped"),
    ("Page 3 could not be shown: x", "warning", "⚠  Page 3 could not be shown: x"),
    ("⚠  No size reduction", "warning", "⚠  No size reduction"),
    ("Error: boom", "danger", "✗  Error: boom"),
    ("Working…", "muted", "Working…"),
])
def test_status_line_carries_its_role_symbol(window, msg, role, shown):
    window.set_status(msg, role)
    assert window.status_text() == shown
