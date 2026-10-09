"""The toolkit-free registry (paperknife.tool_registry, read by the Qt shell)
lists the same tools as the CTk one (tool_base.TOOLS): same class names,
sections, labels and order.  Deleted with the CTk app in phase 8."""


def test_tool_registry_matches_the_ctk_registry():
    import paperknife.tools  # noqa: F401  (fills TOOLS; loads customtkinter)
    from paperknife.tool_base import TOOLS
    from paperknife.tool_registry import TOOL_REGISTRY
    ctk = [(type(t).__name__, t.section, t.label) for t in TOOLS]
    assert [tuple(e) for e in TOOL_REGISTRY] == ctk
    assert len(TOOL_REGISTRY) == 26


def test_tool_registry_names_are_unique():
    from paperknife.tool_registry import TOOL_REGISTRY
    names = [e.name for e in TOOL_REGISTRY]
    assert len(set(names)) == len(names)
