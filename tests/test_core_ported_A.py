"""Phase 8, map A: toolkit-free checks ported from CTk tests (map-A.md)."""
from paperknife.tool_registry import TOOL_REGISTRY

# tests/test_tool_registry.py::test_tool_registry_matches_the_ctk_registry compared
# this registry with the CTk one (tool_base.TOOLS).  With the CTk app gone, the
# list it matched on b247a3f is pinned here: no tool may go missing, move
# section or change place without this test being changed on purpose.
CTK_REGISTRY_AT_PHASE_8 = [
    ("ReaderTool", "READ", "📖  Read / Preview"),
    ("MergeTool", "ORGANISE", "📎  Merge"),
    ("SplitTool", "ORGANISE", "✂   Split"),
    ("RotateTool", "ORGANISE", "🔄  Rotate & Reorder"),
    ("TocTool", "ORGANISE", "📑  Bookmarks / TOC"),
    ("BatchTool", "ORGANISE", "⚙   Batch"),
    ("PasswordTool", "ENHANCE", "🔒  Password"),
    ("CompressTool", "ENHANCE", "🗜   Compress"),
    ("WatermarkTool", "ENHANCE", "💧  Watermark"),
    ("NormaliseTool", "ENHANCE", "📐  Normalise Pages"),
    ("HeaderFooterTool", "ENHANCE", "📋  Header / Footer"),
    ("CropTool", "ENHANCE", "✂   Crop / Trim"),
    ("PdfToolsTool", "ENHANCE", "🔧  PDF Tools"),
    ("Img2PdfTool", "CONVERT", "🖼   Image → PDF"),
    ("Pdf2ImgTool", "CONVERT", "📸  PDF → Images"),
    ("ExtractTool", "CONVERT", "🖼   Extract Images"),
    ("Pdf2DocTool", "CONVERT", "📄  PDF → Doc / Text"),
    ("Doc2PdfTool", "CONVERT", "📤  Doc / Text → PDF"),
    ("EditTextTool", "CONTENT", "✏️   Edit Text"),
    ("FindReplaceTool", "CONTENT", "🔍  Find & Replace"),
    ("AnnotateTool", "CONTENT", "📝  Annotate"),
    ("RedactTool", "CONTENT", "⬛  Redact"),
    ("OCRTool", "CONTENT", "🤖  OCR"),
    ("MetadataTool", "CONTENT", "🏷   Metadata"),
    ("SettingsTool", "SETTINGS", "⚙   Preferences"),
]


def test_tool_registry_keeps_every_tool_the_ctk_app_had():
    assert [tuple(e) for e in TOOL_REGISTRY] == CTK_REGISTRY_AT_PHASE_8
    # Split by Bookmarks became Split's "Cut at" choice (owner, 2026-10-17).
    assert len(TOOL_REGISTRY) == 25
