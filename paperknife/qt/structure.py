"""Whole-app structure prototypes (owner, 2026-10-18; phase11/structure-plan.md).

Today every tool is a screen of its own (an Android inheritance).  The desktop
PDF apps looked at (PDF X, PdfCraft, Acrobat, Stirling: _polish-2026-10-08/refs/
pdfx-pdfcraft-2026-10-18.md) hold every one-document tool in one document
window, and send jobs on many files to a place of their own.  These switches
build those structures from the existing tool pages, re-hosted, not rewritten:

    PK_STRUCT   today (default) · workspace · purpose · pdfx · pdf24 (the control)
    PK_PICKER   pane · ribbon           how a workspace's tools are picked
    PK_FILES    window · screens        many-file jobs: one Files screen, or their own
    PK_WINDOWS  one · separate          pdfx: the Editor and Files in windows of their own

A StructureHost re-hosts a tool page: its own header (title, document bar,
main action) is hidden; its settings (a settings column, or a form's cards)
go into the picker's options place; its centre (a page grid, an editor, a
list) becomes the host's centre; its main action moves to the host's header.
A tool without a centre of its own (Compress, Password, PDF Tools, Metadata)
shows the document in the shared viewer (Read / Preview)."""
from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget
from qfluentwidgets import (Pivot, SubtitleLabel, TitleLabel,
                            TransparentPushButton)

from . import theme
from .pages import (PAGE_MARGINS, SETTINGS_W, CollectionPage, MasterDetailPage, OrganiserPage,
                    ToolPage, WorkspacePage, icon_button, muted_caption, plain_label,
                    register_page)

PANE_W = SETTINGS_W      # the pane is as wide as every screen's settings column


def _env(name: str, allowed, default: str) -> str:
    v = os.environ.get(name, default).strip().lower()
    return v if v in allowed else default


def struct() -> str:
    return _env("PK_STRUCT", ("today", "workspace", "purpose", "pdfx", "pdf24"), "today")


def picker() -> str:
    return _env("PK_PICKER", ("pane", "ribbon"), "ribbon" if struct() == "pdfx" else "pane")


def files_mode() -> str:
    return _env("PK_FILES", ("window", "screens"), "window")


def windows_mode() -> str:
    return _env("PK_WINDOWS", ("one", "separate"), "one")


def active() -> bool:
    """A re-hosting structure (not today's, nor the control's)."""
    return struct() in ("workspace", "purpose", "pdfx")


# The one-document tools, in the groups the pane lists and the ribbon's tabs show
# (and the purpose workspaces are), and the jobs on many files.
GROUPS = [
    ("Pages", ["RotateTool", "SplitTool", "CropTool", "NormaliseTool", "TocTool"]),
    ("Content", ["EditTextTool", "FindReplaceTool", "AnnotateTool", "RedactTool", "OCRTool",
                 "WatermarkTool", "HeaderFooterTool"]),
    ("Protect & optimise", ["PasswordTool", "CompressTool", "PdfToolsTool", "MetadataTool"]),
    ("Convert", ["Pdf2DocTool", "ExtractTool"]),
]
FILE_TOOLS = ["MergeTool", "Img2PdfTool", "BatchTool"]
PURPOSE_HOSTS = {"PagesWorkspace": "Pages", "ContentWorkspace": "Content",
                 "ProtectWorkspace": "Protect & optimise", "ConvertWorkspace": "Convert"}
ONE_DOC = [t for _g, ts in GROUPS for t in ts]


def nav_tools(registry):
    """The navigation for the structure: (ToolEntry-like) items the shell lists."""
    from ..tool_registry import ToolEntry
    by = {t.name: t for t in registry}
    s = struct()
    out = []
    if s == "workspace":
        out.append(ToolEntry("DocWorkspace", "WORK", "📄  Document"))
    elif s == "purpose":
        for key, group in PURPOSE_HOSTS.items():
            out.append(ToolEntry(key, "WORK", f"📄  {group}"))
    elif s == "pdfx":
        out.append(ToolEntry("DocWorkspace", "WORK", "📄  Editor"))
    if s == "pdfx" or files_mode() == "window":
        out.append(ToolEntry("FilesWorkspace", "FILES", "🗂  Files"))
    else:
        out += [by[t] for t in FILE_TOOLS if t in by]
    out.append(by["SettingsTool"])
    return out


def host_for(tool_key: str) -> str | None:
    """The host page that shows *tool_key* in this structure, or None."""
    if not active():
        return None
    if tool_key in FILE_TOOLS:
        return "FilesWorkspace" if (struct() == "pdfx" or files_mode() == "window") else None
    if tool_key == "ReaderTool" or tool_key in ONE_DOC:
        if struct() == "purpose":
            for key, group in PURPOSE_HOSTS.items():
                if tool_key in dict(GROUPS)[group]:
                    return key
            return "PagesWorkspace" if tool_key == "ReaderTool" else None
        return "DocWorkspace"
    return None


def _registry():
    from ..tool_registry import TOOL_REGISTRY
    return {t.name: t for t in TOOL_REGISTRY}


def _narrow_rows(widget):
    """A form's setting rows, made for a page's width (a fixed name column),
    fitted to the pane as a settings column's rows are (column_setting_row):
    the name takes the room the control leaves and wraps."""
    from PySide6.QtWidgets import QLabel, QSpacerItem
    for row in widget.findChildren(QWidget, "settingRow"):
        lay = row.layout()
        texts = lay.itemAt(0).widget() if lay.count() else None
        if texts is None:
            continue
        texts.setMinimumWidth(0)
        texts.setMaximumWidth(16777215)
        lay.setStretchFactor(texts, 1)
        if lay.count() > 1 and isinstance(lay.itemAt(1), QSpacerItem):
            lay.takeAt(1)
        for lbl in texts.findChildren(QLabel):
            lbl.setWordWrap(True)


class _View:
    """A tool page re-hosted: its options, centre and actions."""

    def __init__(self, page, options, centre, actions):
        self.page, self.options, self.centre, self.actions = page, options, centre, actions


class StructureHost(QWidget):
    """A workspace that holds tools (or, files=True, the jobs on many files)."""

    files = False

    def __init__(self, title: str, groups, tool=None, window=None):
        super().__init__()
        self.tool, self.window_ = tool, window
        self.groups = groups
        self.ribbon = picker() == "ribbon" and not self.files
        self._views: dict[str, _View] = {}
        self._current: str | None = None
        self._title = title
        v = QVBoxLayout(self)
        v.setContentsMargins(*PAGE_MARGINS)
        v.setSpacing(0)

        # Header: the title (the tool chosen), the document, the action
        head = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(0)
        self.title_label = TitleLabel(title)
        self.subtitle_label = muted_caption("")
        titles.addWidget(self.title_label)
        titles.addWidget(self.subtitle_label)
        self.doc_bar = None
        if not self.files:
            from . import docui
            self.doc_bar = docui.DocBar(window, self)
            titles.addWidget(self.doc_bar)
        head.addLayout(titles)
        head.addStretch(1)
        self.action_slot = QStackedWidget()
        self.action_slot.addWidget(QWidget())
        head.addWidget(self.action_slot, 0, Qt.AlignTop)
        v.addLayout(head)
        v.addSpacing(12)

        # Ribbon: a tab per group, a row of tool buttons
        self.tab_bar = None
        self._buttons: dict[str, TransparentPushButton] = {}
        if self.ribbon:
            self.tab_bar = Pivot(self)
            self.tab_rows = QStackedWidget()
            for name, tools in groups:
                row = QWidget()
                rh = QHBoxLayout(row)
                rh.setContentsMargins(0, 4, 0, 4)
                rh.setSpacing(4)
                for t in tools:
                    rh.addWidget(self._tool_button(t))
                rh.addStretch(1)
                self.tab_rows.addWidget(row)
                self.tab_bar.addItem(name, name.replace("&", "&&"),
                                     lambda _=False, r=row: self.tab_rows.setCurrentWidget(r))
            if groups:
                self.tab_bar.setCurrentItem(groups[0][0])
            v.addWidget(self.tab_bar)
            v.addWidget(self.tab_rows)
            v.addSpacing(8)

        body = QHBoxLayout()
        body.setSpacing(16)
        # The pane (pane picker; and the Files list): the tools, then a tool's options
        self.pane = None
        self.options_stack = QStackedWidget()
        self.options_stack.addWidget(QWidget())
        if not self.ribbon:
            self.pane = QStackedWidget()
            self.pane.setFixedWidth(PANE_W)
            self.list_page = QWidget()
            lv = QVBoxLayout(self.list_page)
            lv.setContentsMargins(0, 0, 0, 0)
            lv.setSpacing(2)
            lv.addWidget(SubtitleLabel("Files" if self.files else "All tools"))
            lv.addSpacing(8)
            self.tool_list = self._tool_list(groups)
            lv.addWidget(self.tool_list, 1)
            self.pane.addWidget(self.list_page)
            self.tool_page = QWidget()
            tv = QVBoxLayout(self.tool_page)
            tv.setContentsMargins(0, 0, 0, 0)
            top = QHBoxLayout()
            self.back_btn = icon_button(theme.glyph_icon(0xE72B, 14))
            self.back_btn.setToolTip("All tools")
            self.back_btn.clicked.connect(self.back)
            top.addWidget(self.back_btn)
            self.pane_title = SubtitleLabel("")
            top.addWidget(self.pane_title, 1)
            tv.addLayout(top)
            tv.addSpacing(8)
            tv.addWidget(self.options_stack, 1)
            self.pane.addWidget(self.tool_page)
            body.addWidget(self.pane)
        self.centre = QStackedWidget()
        # The centre gives way: the pane and the options keep their width.
        self.centre.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        body.addWidget(self.centre, 1)
        if self.ribbon:
            self.options_panel = QWidget()
            self.options_panel.setFixedWidth(PANE_W)
            ov = QVBoxLayout(self.options_panel)
            ov.setContentsMargins(0, 0, 0, 0)
            ov.addWidget(self.options_stack, 1)
            body.addWidget(self.options_panel)
            self.options_panel.hide()
        v.addLayout(body, 1)

        self.viewer = None
        if not self.files:
            self.viewer = self._embed_page("ReaderTool")
            self.viewer.panel.hide()                    # the viewer only shows the pages
            self.viewer.reopen_btn.hide()
            self.centre.addWidget(self.viewer)
        else:
            self.centre.addWidget(QWidget())
        if window is not None and not self.files:
            window.current_document_changed.connect(self._doc_changed)
        if self.files and groups and groups[0][1]:
            self.pick(groups[0][1][0])

    # ── the tools ──
    def _tool_button(self, key: str):
        from .shell import DEFAULT_GLYPH, NAV_GLYPH
        t = _registry().get(key)
        label = plain_label(t.label) if t else key
        b = TransparentPushButton(theme.Glyph(NAV_GLYPH.get(key, DEFAULT_GLYPH)),
                                  label.replace("&", "&&"))     # '&' shown, not a mnemonic
        b.setMinimumHeight(36)
        b.clicked.connect(lambda _=False, k=key: self.pick(k))
        self._buttons[key] = b
        return b

    def _tool_list(self, groups):
        """The pane's list of tools (Acrobat's All tools): a heading per group,
        a row per tool with its icon; a click chooses the tool."""
        from PySide6.QtWidgets import QAbstractItemView, QListWidgetItem
        from qfluentwidgets import ListWidget

        from .shell import DEFAULT_GLYPH, NAV_GLYPH
        lst = ListWidget()
        lst.setSelectionMode(QAbstractItemView.SingleSelection)
        reg = _registry()
        for name, tools in groups:
            if name:
                head = QListWidgetItem(name)
                f = head.font()
                f.setBold(True)
                head.setFont(f)
                head.setFlags(Qt.NoItemFlags)
                lst.addItem(head)
            for t in tools:
                e = reg.get(t)
                it = QListWidgetItem(theme.glyph_icon(NAV_GLYPH.get(t, DEFAULT_GLYPH), 16),
                                     plain_label(e.label) if e else t)
                it.setData(Qt.UserRole, t)
                lst.addItem(it)
        lst.itemClicked.connect(lambda it: it.data(Qt.UserRole) and self.pick(it.data(Qt.UserRole)))
        return lst

    def tools(self) -> list[str]:
        return [t for _g, ts in self.groups for t in ts]

    def _embed_page(self, key: str):
        page = self.window_.page_for(_registry()[key])
        page.header.hide()
        page.layout().setContentsMargins(0, 0, 0, 0)
        return page

    def _make_view(self, key: str) -> _View:
        page = self._embed_page(key)
        options = centre = None
        if isinstance(page, WorkspacePage):
            centre = page                               # an editor: the page
            if self.pane is not None and not self.files:
                # Its rail (the tool's own commands) goes into the pane.
                rail = page.rail.parentWidget()
                rail.setParent(None)
                options = rail
        elif isinstance(page, MasterDetailPage):
            centre = page                               # an outline: the page
        elif isinstance(page, (OrganiserPage, CollectionPage)):
            centre = page                               # a page grid, a file list
            sa = getattr(page, "settings_area", None)
            if sa is not None and not self.files:     # Files keeps each tool whole
                sa.setParent(None)
                sa.setFixedWidth(PANE_W)
                options = sa
            elif (sa is None and not self.files and getattr(page, "_actions", None)
                    and not hasattr(page, "all_btn")):
                # A page organiser's commands (Rotate & Reorder) go into the pane
                # as full-width buttons, one per row (PdfCraft's Organize pages).
                box = QWidget()
                bv = QVBoxLayout(box)
                bv.setContentsMargins(0, 0, 0, 0)
                bv.setSpacing(4)
                for b in list(page._actions):
                    b.setParent(box)
                    bv.addWidget(b)
                bv.addStretch(1)
                box.setFixedWidth(PANE_W)
                options = box
        elif isinstance(page, ToolPage):
            # A form: its cards are the options; the document shows in the viewer.
            if page.drop_target is not None:
                page.drop_target.setParent(None)
                page.drop_target.hide()
            area = page.scroll_area or page.content
            area.setParent(None)
            if hasattr(area, "setHorizontalScrollBarPolicy"):
                area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            area.setFixedWidth(PANE_W)
            _narrow_rows(area)
            options = area
        if centre is not None:
            self.centre.addWidget(centre)
        if options is not None:
            self.options_stack.addWidget(options)
        actions = QWidget()
        ah = QHBoxLayout(actions)
        ah.setContentsMargins(0, 0, 0, 0)
        ah.setSpacing(8)
        for b in list(page._buttons):
            b.setParent(actions)
            ah.addWidget(b)
        self.action_slot.addWidget(actions)
        view = _View(page, options, centre, actions)
        self._views[key] = view
        return view

    def pick(self, key: str):
        """Choose a tool: its options, centre and action show."""
        if key not in self.tools():
            return False
        view = self._views.get(key) or self._make_view(key)
        self._current = key
        self.centre.setCurrentWidget(view.centre or self.viewer or self.centre.widget(0))
        if view.options is not None:
            self.options_stack.setCurrentWidget(view.options)
        else:
            self.options_stack.setCurrentIndex(0)
        self.action_slot.setCurrentWidget(view.actions)
        t = _registry().get(key)
        name = plain_label(t.label) if t else key
        self.title_label.setText(name)
        if self.pane is not None and not self.files:     # Files' list stays shown
            self.pane_title.setText(name)
            self.pane.setCurrentWidget(self.tool_page)
        if self.pane is not None and self.files:
            for i in range(self.tool_list.count()):
                if self.tool_list.item(i).data(Qt.UserRole) == key:
                    self.tool_list.setCurrentRow(i)
        if self.ribbon:
            self.options_panel.setVisible(view.options is not None)
            for gname, gtools in self.groups:          # the tab the tool is on
                if key in gtools:
                    self.tab_bar.setCurrentItem(gname)
                    self.tab_rows.setCurrentIndex([g for g, _t in self.groups].index(gname))
        if self.window_ is not None and getattr(view.page, "follows_document", False):
            self.window_._follow(view.page)
        self._show_doc()
        return True

    def back(self):
        """The pane lists the tools again; the document shows in the viewer."""
        self._current = None
        if self.pane is not None:
            self.pane.setCurrentWidget(self.list_page)
        self.centre.setCurrentWidget(self.viewer or self.centre.widget(0))
        self.action_slot.setCurrentIndex(0)
        self.title_label.setText(self._title)
        if self.ribbon:
            self.options_panel.hide()

    def current_tool(self):
        v = self._views.get(self._current) if self._current else None
        return v.page if v is not None else None

    # ── the document (the window's current document) ──
    follows_document = True

    def _doc_changed(self, path):
        self._show_doc()

    def _show_doc(self):
        path = self.window_.current_document if self.window_ is not None else None
        if self.doc_bar is not None:
            self.doc_bar.show_path(path or "")
        if self.files:
            self.subtitle_label.setText("Jobs on several files or a folder")
            return
        self.subtitle_label.setText(os.path.basename(path) if path else "Open a PDF to start")
        if self.viewer is not None and path and self.viewer.document_path() != path:
            self.viewer.load_document(path)

    def document_path(self) -> str:
        p = self.current_tool()
        if p is not None and hasattr(p, "document_path"):
            return p.document_path() or (self.window_.current_document or "")
        return self.window_.current_document or "" if self.window_ is not None else ""

    def document_name(self) -> str:
        return os.path.basename(self.document_path())

    def load_document(self, path: str) -> bool:
        if self.window_ is not None:
            self.window_.set_current_document(path)
        p = self.current_tool()
        if p is not None and getattr(p, "follows_document", False):
            p.load_document(path)
        self._show_doc()
        return True

    def clear_document(self):
        p = self.current_tool()
        if p is not None and hasattr(p, "clear_document"):
            p.clear_document()
        self._show_doc()

    def refresh_document(self, announce: bool = False):
        self._show_doc()

    def is_dirty(self) -> bool:
        return any(callable(getattr(v.page, "is_dirty", None)) and v.page.is_dirty()
                   for v in self._views.values())

    def is_parked(self) -> bool:
        return False

    def discard_changes(self):
        for v in self._views.values():
            if callable(getattr(v.page, "discard_changes", None)):
                v.page.discard_changes()

    def recovery_token(self):
        return None

    def set_compact(self, on: bool):
        pass

    def accept_drop(self, path: str) -> bool:
        p = self.current_tool()
        if p is not None and p.accept_drop(path):
            return True
        if path.lower().endswith(".pdf") and self.window_ is not None and not self.files:
            return self.window_.open_document(path)
        return False

    # The shell's hooks go to the tool chosen.
    def _hook(self, name):
        p = self.current_tool()
        fn = getattr(p, name, None) if p is not None else None
        return fn() if callable(fn) else None

    def open(self):
        if self._hook("open") is None and self.window_ is not None and not self.files:
            self.window_.browse_document()

    def save(self, after=None):
        p = self.current_tool()
        if p is not None and callable(getattr(p, "save", None)):
            return p.save(after) if after is not None else p.save()

    def undo(self):
        return self._hook("undo")

    def delete(self):
        return self._hook("delete")


# ── PDF X's separate windows (PK_WINDOWS=separate) ──
_windows: dict = {}


def separate(key: str) -> bool:
    return (struct() == "pdfx" and windows_mode() == "separate"
            and key in ("DocWorkspace", "FilesWorkspace"))


def show_separate(window, key: str, page):
    """The Editor or Files in a window of its own (PDF X opens them so)."""
    from PySide6.QtCore import QPoint
    w = _windows.get(key)
    if w is None:
        w = QWidget(None, Qt.Window)
        w.setWindowTitle(f"PaperKnife+ PC — {'Editor' if key == 'DocWorkspace' else 'Files'}")
        w.setObjectName("separateWindow")
        w.setStyleSheet(f"QWidget#separateWindow {{ background: {theme.hex_color('layer')}; }}")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        page.setParent(w)
        lay.addWidget(page)
        page.show()
        if window.testAttribute(Qt.WA_ShowWithoutActivating):
            w.setAttribute(Qt.WA_ShowWithoutActivating, True)
        w.resize(window.size())
        w.move(window.pos() + QPoint(40, 40))
        _windows[key] = w
    w.show()
    w.raise_()
    return w


@register_page("DocWorkspace")
class DocWorkspace(StructureHost):
    def __init__(self, tool=None, window=None):
        super().__init__("Document" if struct() != "pdfx" else "Editor", GROUPS,
                         tool=tool, window=window)


def _purpose(key):
    group = PURPOSE_HOSTS[key]

    @register_page(key)
    class PurposeWorkspace(StructureHost):
        def __init__(self, tool=None, window=None):
            super().__init__(group, [(group, dict(GROUPS)[group])], tool=tool, window=window)
    PurposeWorkspace.__name__ = key
    return PurposeWorkspace


for _k in PURPOSE_HOSTS:
    _purpose(_k)


@register_page("FilesWorkspace")
class FilesWorkspace(StructureHost):
    """The jobs on many files in one screen (PDF X's Converter): Merge, Other →
    PDF, and the folder jobs (Batch with each tool's full settings)."""
    files = True
    follows_document = False

    def __init__(self, tool=None, window=None):
        os.environ.setdefault("PK_BATCH", "C")      # the folder jobs with full settings
        super().__init__("Files", [("", FILE_TOOLS)], tool=tool, window=window)
