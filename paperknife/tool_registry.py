"""
paperknife.tool_registry
The tools the app offers, toolkit-free: class name, navigation section and
label, in navigation order (sections in first-seen order).

The Qt shell builds its navigation from TOOL_REGISTRY and keys its pages
(paperknife.qt.pages.QT_PAGES) by ToolEntry.name.  The CustomTkinter app keeps
its own registry (tool_base.TOOLS, filled by importing paperknife.tools, which
loads tkinter); tests/test_tool_registry.py pins this list to that one until
phase 8 deletes the CTk app.

Labels are written as the CTk sidebar shows them (emoji included); the Qt
shell strips the emoji with pages.plain_label.
"""
from __future__ import annotations

from typing import NamedTuple


class ToolEntry(NamedTuple):
    """One tool: what a Qt page receives as its *tool* argument."""
    name: str       # the CTk tool class name; the QT_PAGES key
    section: str    # READ / ORGANISE / ENHANCE / CONVERT / CONTENT / SETTINGS
    label: str      # navigation label (emoji prefix kept, see above)


TOOL_REGISTRY: tuple[ToolEntry, ...] = (
    ToolEntry('ReaderTool', 'READ', '📖  Read / Preview'),
    ToolEntry('MergeTool', 'ORGANISE', '📎  Merge'),
    ToolEntry('SplitTool', 'ORGANISE', '✂   Split'),
    ToolEntry('RotateTool', 'ORGANISE', '🔄  Rotate & Reorder'),
    ToolEntry('BookmarksTool', 'ORGANISE', '🔖  Split by Bookmarks'),
    ToolEntry('TocTool', 'ORGANISE', '📑  Bookmarks / TOC'),
    ToolEntry('BatchTool', 'ORGANISE', '⚙   Batch'),
    ToolEntry('PasswordTool', 'ENHANCE', '🔒  Password'),
    ToolEntry('CompressTool', 'ENHANCE', '🗜   Compress'),
    ToolEntry('WatermarkTool', 'ENHANCE', '💧  Watermark'),
    ToolEntry('NormaliseTool', 'ENHANCE', '📐  Normalise Pages'),
    ToolEntry('HeaderFooterTool', 'ENHANCE', '📋  Header / Footer'),
    ToolEntry('CropTool', 'ENHANCE', '✂   Crop / Trim'),
    ToolEntry('PdfToolsTool', 'ENHANCE', '🔧  PDF Tools'),
    ToolEntry('Img2PdfTool', 'CONVERT', '🖼   Image → PDF'),
    ToolEntry('Pdf2ImgTool', 'CONVERT', '📸  PDF → Images'),
    ToolEntry('ExtractTool', 'CONVERT', '🖼   Extract Images'),
    ToolEntry('Pdf2DocTool', 'CONVERT', '📄  PDF → Doc / Text'),
    ToolEntry('Doc2PdfTool', 'CONVERT', '📤  Doc / Text → PDF'),
    ToolEntry('EditTextTool', 'CONTENT', '✏️   Edit Text'),
    ToolEntry('FindReplaceTool', 'CONTENT', '🔍  Find & Replace'),
    ToolEntry('AnnotateTool', 'CONTENT', '📝  Annotate'),
    ToolEntry('RedactTool', 'CONTENT', '⬛  Redact'),
    ToolEntry('OCRTool', 'CONTENT', '🤖  OCR'),
    ToolEntry('MetadataTool', 'CONTENT', '🏷   Metadata'),
    ToolEntry('SettingsTool', 'SETTINGS', '⚙   Preferences'),
)
