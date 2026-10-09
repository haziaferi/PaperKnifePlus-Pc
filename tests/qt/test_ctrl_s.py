"""Ctrl+S means save: it answers only on screens whose main action saves the
document or settings being edited (owner rule, 2026-10-09). Split, Password,
PDF Tools, Crop and Split by Bookmarks used to run their main action on it."""

SAVES = {"AnnotateTool", "EditTextTool", "FindReplaceTool", "RedactTool", "TocTool",
         "RotateTool", "MetadataTool", "SettingsTool"}


def test_only_the_saving_screens_answer_ctrl_s(window):
    from paperknife.qt.pages import QT_PAGES
    answering = set()
    for cls in QT_PAGES:
        assert window.open_tool(cls)
        if callable(getattr(window.current_page(), "save", None)):
            answering.add(cls)
    assert answering == SAVES
