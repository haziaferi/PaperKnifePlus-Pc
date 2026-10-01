"""Every registered tool view must build without raising."""
import pytest

from conftest import tool


def _tool_names():
    import paperknife.tools  # noqa: F401
    from paperknife.tool_base import TOOLS
    return [type(t).__name__ for t in TOOLS]


@pytest.mark.parametrize("name", _tool_names())
def test_tool_view_builds(app, dialogs, name):
    tool(app, name)
    assert not dialogs.errors(), dialogs.errors()


@pytest.mark.parametrize("mode", ["Light", "Dark"])
def test_home_and_tools_both_modes(app, dialogs, mode):
    import customtkinter as ctk
    ctk.set_appearance_mode(mode)
    try:
        for name in _tool_names():
            tool(app, name)
        app.show_home()
    finally:
        ctk.set_appearance_mode("Light")
