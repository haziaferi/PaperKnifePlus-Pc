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

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QHBoxLayout, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget
from qfluentwidgets import (Pivot, StrongBodyLabel, SubtitleLabel, TitleLabel,
                            TransparentPushButton)

from . import theme
from .pages import (PAGE_MARGINS, SETTINGS_W, CollectionPage, MasterDetailPage, OrganiserPage,
                    ToolPage, WorkspacePage, muted_caption, plain_label)

# The pane, measured on the reference apps (owner, 2026-10-19): PdfCraft 272,
# Affinity's studio 264, Stirling 296, Acrobat 299 px; median about 284.  Every
# re-hosted settings column takes it (same place, same size).
PANE_W = 284
FILES_LIST_W = 200       # Files' list of jobs: a narrow column (PDF X's Converter)
_ = SETTINGS_W           # (today's column width, for comparison)


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


def details() -> str:
    """Where a chosen tool's details sit: the left pane, or a column at the right."""
    return _env("PK_DETAILS", ("left", "right"), "left")


def left_mode() -> str:
    """The navigation: its column (nav), its icon strip (rail), merged into the left
    column (merged), or a row across the top (tabs)."""
    return _env("PK_LEFT", ("nav", "rail", "merged", "tabs"), "nav")


# The details column at the right (owner, 2026-10-19: 200 px), and the tool list
# beside the page when the details sit there.
DETAILS_W = 200
LIST_W = 200
STACK_CONTROL_W = 96     # the widest minimum a stacked row's control keeps (a slider)


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


def _trim_top(area):
    """A page body's leading space (it sat under the page's title) goes: in the
    pane the options start right under the group's tools, as an editor's do."""
    from PySide6.QtWidgets import QSpacerItem
    inner = area.widget() if hasattr(area, "widget") else area
    lay = inner.layout() if inner is not None else None
    while lay is not None and lay.count() and isinstance(lay.itemAt(0), QSpacerItem):
        lay.takeAt(0)


def _stack_rows(widget):
    """A form's setting rows for the 200 px details column: the name above its
    control (a narrow column takes another row, never a squeezed one).  A row
    whose control is a radio button, a switch or a check box keeps it beside the
    name: it is one mark."""
    from PySide6.QtWidgets import QCheckBox, QRadioButton
    from qfluentwidgets import SwitchButton
    for row in widget.findChildren(QWidget, "settingRow"):
        lay = row.layout()
        if not isinstance(lay, QHBoxLayout):
            continue
        ctl = row.findChild(QWidget, "settingControl")
        marks = ctl.findChildren(QWidget) if ctl is not None else []
        if marks and all(isinstance(m, (QRadioButton, QCheckBox, SwitchButton)) or
                         isinstance(m.parent(), (QRadioButton, QCheckBox, SwitchButton))
                         for m in marks):
            continue
        items = []
        while lay.count():
            items.append(lay.takeAt(0))
        m = lay.contentsMargins()
        QWidget().setLayout(lay)            # the old layout leaves with a throwaway widget
        v = QVBoxLayout(row)
        v.setContentsMargins(m)
        v.setSpacing(6)
        for it in items:
            w = it.widget()
            if w is None:
                continue
            if w.objectName() == "settingControl":
                for c in w.findChildren(QWidget):   # under the name: the column's width
                    if c.minimumWidth() > STACK_CONTROL_W:
                        c.setMinimumWidth(STACK_CONTROL_W)
                v.addWidget(w, 0, Qt.AlignLeft)
            else:
                v.addWidget(w)


def _wrap_buttons(card, buttons, width):
    """Buttons of one row, at their own size, wrapped onto as many rows as the
    width needs (the row that held them keeps the first ones)."""
    first = buttons[0].parentWidget()
    lay = first.layout()
    for b in buttons:
        lay.removeWidget(b)
    while lay.count():                              # its trailing stretch
        lay.takeAt(0)
    rows, used, cur = [], 0, None
    for b in buttons:
        bw = b.sizeHint().width()
        if cur is None or used + bw > width:
            cur = lay if not rows else QHBoxLayout()
            if rows:
                w = QWidget(card)
                m = lay.contentsMargins()
                cur.setParent(None)
                cur = QHBoxLayout(w)
                cur.setContentsMargins(m.left(), 0, m.right(), m.bottom())
                cur.setSpacing(lay.spacing())
                card.layout().insertWidget(card.layout().indexOf(first) + len(rows), w)
            rows.append(cur)
            used = 0
        cur.addWidget(b)
        used += bw + lay.spacing()
    for r in rows:
        r.addStretch(1)


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
    # A control keeps no more than PANE_CONTROL_W of its page minimum: the row's
    # name wraps first, then the control gives way, and the row fits the pane.
    for ctl in widget.findChildren(QWidget, "settingControl"):
        for c in ctl.findChildren(QWidget):
            if c.minimumWidth() > PANE_CONTROL_W:
                c.setMinimumWidth(PANE_CONTROL_W)


ROW_H = 36      # a row in the pane: a tool, a command
PANE_CONTROL_W = 120    # the widest minimum a form control keeps in the pane


def _pane_row(btn):
    """A command in the pane, read as a row of the tool list above it: full width,
    ROW_H tall, icon and text at the left; checked = the list's selected tint (the
    accent fill stays for the main action)."""
    from qfluentwidgets import setCustomStyleSheet

    def qss(dark):
        tint = theme.hex_color("tint_selected", dark)
        fg = theme.hex_color("fluent_text", dark)
        pad = 12 if btn.icon().isNull() else 12 + 16 + 10    # after the icon
        return (f"QPushButton{{text-align:left;padding-left:{pad}px;}}"
                f"QPushButton:checked,QPushButton:checked:hover,QPushButton:checked:pressed"
                f"{{background-color:{tint};border:none;color:{fg};}}")
    btn.setMinimumHeight(ROW_H)
    btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    theme.keep_styled(btn, lambda b: setCustomStyleSheet(b, qss(False), qss(True)))


def _row_button(toggle: bool):
    """A transparent (toggle) button whose icon sits at the left edge: with no
    minimum width hint qfluentwidgets draws it at x = 12."""
    from qfluentwidgets import TransparentTogglePushButton
    base = TransparentTogglePushButton if toggle else TransparentPushButton

    class Row(base):
        def minimumSizeHint(self):
            return QSize(0, super().minimumSizeHint().height())
    return Row


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
        # The details at the right (PK_DETAILS=right): the pane is only the list.
        self.right = details() == "right" and not self.ribbon
        self._views: dict[str, _View] = {}
        self._current: str | None = None
        self._title = title
        v = QVBoxLayout(self)
        v.setContentsMargins(*PAGE_MARGINS)
        v.setSpacing(0)

        # Header, slim (no reference app has a page title): the document bar at
        # the left, the tool's main action at the right, on one row.  The tool's
        # name is on the pane.
        head = QHBoxLayout()
        self.title_label = TitleLabel(title)        # kept for the name, not shown
        self.title_label.hide()
        self.subtitle_label = muted_caption("")
        self.subtitle_label.hide()
        self.doc_bar = None
        if not self.files:
            from . import docui
            self.doc_bar = docui.DocBar(window, self)
            self.doc_bar.layout().setContentsMargins(0, 0, 0, 0)
            head.addWidget(self.doc_bar, 0, Qt.AlignVCenter)
        else:
            head.addWidget(SubtitleLabel("Files"), 0, Qt.AlignVCenter)
        head.addStretch(1)
        self.action_slot = QStackedWidget()
        self.action_slot.addWidget(QWidget())
        head.addWidget(self.action_slot, 0, Qt.AlignVCenter)
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
            self.pane.setFixedWidth(LIST_W if self.right else
                                    FILES_LIST_W if self.files else PANE_W)
            self.list_page = QWidget()
            lv = QVBoxLayout(self.list_page)
            lv.setContentsMargins(0, 0, 0, 0)
            lv.setSpacing(2)
            if not self.files and not self.right:
                lv.addWidget(SubtitleLabel("All tools"))
                lv.addSpacing(8)
            self.tool_list = self._tool_list(groups)
            lv.addWidget(self.tool_list, 1)
            self.pane.addWidget(self.list_page)
            # A tool chosen: "All tools", its group's tools (the chosen one
            # highlighted, a click switches: no back step), then its options.
            self.tool_page = QWidget()
            tv = QVBoxLayout(self.tool_page)
            tv.setContentsMargins(0, 0, 0, 0)
            tv.setSpacing(4)
            self.back_btn = TransparentPushButton(theme.glyph_icon(0xE72B, 12), "All tools")
            self.back_btn.clicked.connect(self.back)
            top = QHBoxLayout()
            top.addWidget(self.back_btn)
            top.addStretch(1)
            tv.addLayout(top)
            self.pane_title = StrongBodyLabel("")       # the group's name
            tv.addWidget(self.pane_title)
            self.group_lists = QStackedWidget()
            self._group_list = {}
            for gname, gtools in groups:
                gl = self._tool_list([("", gtools)])
                gl.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
                gl.setFixedHeight(sum(gl.sizeHintForRow(i) for i in range(gl.count()))
                                  + 2 * gl.frameWidth() + 4)
                self._group_list[gname] = gl
                self.group_lists.addWidget(gl)
            tv.addWidget(self.group_lists)
            tv.addSpacing(8)
            if not self.right:
                tv.addWidget(self.options_stack, 1)
            self.pane.addWidget(self.tool_page)
            body.addWidget(self.pane)
        self.centre = QStackedWidget()
        # The centre gives way: the pane and the options keep their width.
        self.centre.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        body.addWidget(self.centre, 1)
        if self.ribbon or self.right:
            self.options_panel = QWidget()
            self.options_panel.setFixedWidth(DETAILS_W if self.right else PANE_W)
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
                it.setSizeHint(QSize(0, ROW_H))
                lst.addItem(it)
        lst.itemClicked.connect(lambda it: it.data(Qt.UserRole) and self.pick(it.data(Qt.UserRole)))
        return lst

    def tools(self) -> list[str]:
        return [t for _g, ts in self.groups for t in ts]

    def _opt_w(self) -> int:
        """The width of the options place: the right column, or the pane."""
        return DETAILS_W if self.right else PANE_W

    def _fit(self, area):
        """A re-hosted form or settings column, fitted to the options place."""
        _narrow_rows(area)
        if self.right:
            _stack_rows(area)
        _trim_top(area)

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
                options = self._editor_options(page)
        elif isinstance(page, MasterDetailPage):
            centre = page                               # an outline: the page
        elif isinstance(page, (OrganiserPage, CollectionPage)):
            centre = page                               # a page grid, a file list
            sa = getattr(page, "settings_area", None)
            if sa is not None and not self.files:     # Files keeps each tool whole
                sa.setParent(None)
                sa.setFixedWidth(self._opt_w())
                self._fit(sa)
                options = sa
            elif self.files and self.right:
                # Files keeps each tool whole; its own details column (Batch's
                # settings, Merge's file list) takes the details width.
                if sa is not None:
                    sa.setFixedWidth(DETAILS_W)
                    self._fit(sa)
                card = getattr(page, "list_card", None)
                if card is not None and hasattr(page, "strip_card"):
                    # Merge: its file list is the column at the right (the page
                    # strip is its centre).  Up / Down / Remove keep their size
                    # (owner, 2026-10-17): what does not fit takes another row.
                    card.setFixedWidth(DETAILS_W)
                    _wrap_buttons(card, [page.up_btn, page.down_btn, page.remove_btn],
                                  DETAILS_W - 16)
                page.rows_stacked = True
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
                    _pane_row(b)
                    bv.addWidget(b)
                bv.addStretch(1)
                box.setFixedWidth(self._opt_w())
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
            area.setFixedWidth(self._opt_w())
            self._fit(area)
            options = area
        if centre is not None:
            self.centre.addWidget(centre)
        if options is not None:
            self.options_stack.addWidget(options)
        actions = QWidget()
        ah = QHBoxLayout(actions)
        ah.setContentsMargins(0, 0, 0, 0)
        ah.setSpacing(8)
        ah.addStretch(1)            # the buttons keep their size, at the right
        for b in list(page._buttons):
            b.setParent(actions)
            ah.addWidget(b)
        self.action_slot.addWidget(actions)
        view = _View(page, options, centre, actions)
        self._views[key] = view
        return view

    def _editor_options(self, page):
        """An editor's one options place, in the pane (PdfCraft's Edit, measured
        2026-10-19): its rail's tools as labelled rows, then its context panel
        (moved out of its splitter; an empty, shut placeholder keeps the
        splitter's shape for the page's own code)."""
        box = QWidget()
        bv = QVBoxLayout(box)
        bv.setContentsMargins(0, 0, 0, 0)
        bv.setSpacing(2)
        rail = page.rail
        for i in range(rail.count()):
            w = rail.itemAt(i).widget()
            if w is None or not hasattr(w, "pk_key"):
                continue
            icon = theme.glyph_icon(w.pk_glyph, 16)
            text = w.toolTip().replace("&", "&&")
            if w.isCheckable():
                row = _row_button(True)(icon, text)
                row.setChecked(w.isChecked())
                w.toggled.connect(row.setChecked)
                row.clicked.connect(lambda _=False, b=w, r=row: (b.click(), r.setChecked(b.isChecked())))
            else:
                row = _row_button(False)(icon, text)
                row.clicked.connect(lambda _=False, b=w: b.click())
            _pane_row(row)
            bv.addWidget(row)
        rail.parentWidget().hide()
        page.panel_hosted = True                    # always shown: no hide / reopen
        holder = QWidget()
        holder.setMaximumWidth(0)
        panel = page.split.replaceWidget(1, holder)
        page.split.setSizes([1, 0])
        page.reopen_btn.hide()
        bv.addSpacing(8)
        bv.addWidget(panel, 1)
        panel.setMinimumWidth(0)
        panel.setMaximumWidth(self._opt_w())
        panel.layout().setContentsMargins(0, 0, 0, 0)
        # The rows and the panel scroll together when the window is short
        # (Annotate: ten tools and a panel in an 820 px window).
        from qfluentwidgets import SingleDirectionScrollArea
        area = SingleDirectionScrollArea(orient=Qt.Vertical)
        area.setWidgetResizable(True)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        area.enableTransparentBackground()
        box.setObjectName("paneEditor")
        box.setStyleSheet("QWidget#paneEditor { background: transparent; }")
        area.setWidget(box)
        area.setFixedWidth(self._opt_w())
        return area

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
        if self.pane is not None and not self.files and not self.right:
            gname = next(g for g, ts in self.groups if key in ts)
            self.pane_title.setText(gname)
            gl = self._group_list[gname]
            self.group_lists.setCurrentWidget(gl)
            self.group_lists.setFixedHeight(gl.height())   # this group's rows, not the tallest
            for i in range(gl.count()):
                if gl.item(i).data(Qt.UserRole) == key:
                    gl.setCurrentRow(i)
            self.pane.setCurrentWidget(self.tool_page)
        if self.pane is not None and (self.files or self.right):   # the list stays shown
            for i in range(self.tool_list.count()):
                if self.tool_list.item(i).data(Qt.UserRole) == key:
                    self.tool_list.setCurrentRow(i)
        if self.right:
            self.options_panel.setVisible(view.options is not None)
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
        if self.ribbon or self.right:
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


# The hosts are pages only in a structure: kept apart from pages.QT_PAGES (the
# screens of today's navigation), the shell's page_for looks here for them.
HOSTS: dict[str, type] = {}


def _host(key: str):
    def deco(cls):
        HOSTS[key] = cls
        return cls
    return deco


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


@_host("DocWorkspace")
class DocWorkspace(StructureHost):
    def __init__(self, tool=None, window=None):
        super().__init__("Document" if struct() != "pdfx" else "Editor", GROUPS,
                         tool=tool, window=window)


def _purpose(key):
    group = PURPOSE_HOSTS[key]

    @_host(key)
    class PurposeWorkspace(StructureHost):
        def __init__(self, tool=None, window=None):
            super().__init__(group, [(group, dict(GROUPS)[group])], tool=tool, window=window)
    PurposeWorkspace.__name__ = key
    return PurposeWorkspace


for _k in PURPOSE_HOSTS:
    _purpose(_k)


@_host("FilesWorkspace")
class FilesWorkspace(StructureHost):
    """The jobs on many files in one screen (PDF X's Converter): Merge, Other →
    PDF, and the folder jobs (Batch with each tool's full settings)."""
    files = True
    follows_document = False

    def __init__(self, tool=None, window=None):
        os.environ.setdefault("PK_BATCH", "C")      # the folder jobs with full settings
        super().__init__("Files", [("", FILE_TOOLS)], tool=tool, window=window)


# ── the navigation merged with the left pane (PK_LEFT; owner, 2026-10-19) ──
PLACE_KEYS = ("home", "DocWorkspace", "FilesWorkspace")
PREFS_KEY = "SettingsTool"


def _place_rows(win, keys):
    """The places as rows of the tool list's kind (icon, name; the current one
    selected); a click goes there."""
    from PySide6.QtWidgets import QAbstractItemView, QListWidgetItem
    from qfluentwidgets import ListWidget

    from .shell import DEFAULT_GLYPH, NAV_GLYPH
    lst = ListWidget()
    lst.setSelectionMode(QAbstractItemView.SingleSelection)
    lst.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    for k in keys:
        it = QListWidgetItem(theme.glyph_icon(NAV_GLYPH.get(k, DEFAULT_GLYPH), 16),
                             win._labels.get(k, k))
        it.setData(Qt.UserRole, k)
        it.setSizeHint(QSize(0, ROW_H))
        lst.addItem(it)
    lst.setFixedHeight(sum(lst.sizeHintForRow(i) for i in range(lst.count()))
                       + 2 * lst.frameWidth() + 4)
    lst.itemClicked.connect(lambda it: win.show_page(it.data(Qt.UserRole)))
    return lst


def _prefs_button(win):
    from .shell import DEFAULT_GLYPH, NAV_GLYPH
    b = _row_button(False)(theme.glyph_icon(NAV_GLYPH.get(PREFS_KEY, DEFAULT_GLYPH), 16),
                           win._labels.get(PREFS_KEY, "Preferences"))
    b.clicked.connect(lambda: win.show_page(PREFS_KEY))
    return b


def install_left(win):
    """Build the navigation's shape for PK_LEFT (nothing for nav)."""
    mode = left_mode()
    if not active() or mode == "nav":
        return
    nav = win.navigationInterface
    if mode == "rail":
        nav.setMinimumExpandWidth(10 ** 6)          # never expands: the icon strip
        nav.panel.collapse()
        win.search.setCompacted(True)               # its icon, not a clipped field
        win._rail = True                            # the shell's first show leaves it so
        return
    win.hBoxLayout.removeWidget(nav)                # merged / tabs: no navigation column
    nav.hide()
    win._nav_gone = True
    keys = [k for k in PLACE_KEYS if k in win._labels]
    if mode == "merged":
        col = QWidget()
        col.setObjectName("mergedColumn")
        col.setFixedWidth((LIST_W if details() == "right" else PANE_W) + 16)
        cv = QVBoxLayout(col)
        cv.setContentsMargins(12, 8, 4, 8)
        cv.setSpacing(4)
        win.search.setParent(col)
        win.search.setCompacted(False)              # the field, not the nav's icon
        win.search.setFixedHeight(36)
        cv.addWidget(win.search)
        places = _place_rows(win, keys)
        cv.addWidget(places)
        slot = QStackedWidget()
        slot.addWidget(QWidget())                   # Home, Preferences: nothing below
        cv.addWidget(slot, 1)
        prefs = _prefs_button(win)
        _pane_row(prefs)
        cv.addWidget(prefs)
        win.hBoxLayout.insertWidget(0, col)
        win._left = {"mode": mode, "column": col, "places": places, "slot": slot}
    else:                                           # tabs: one row across the top
        bar = QWidget()
        bar.setObjectName("placeBar")
        h = QHBoxLayout(bar)
        h.setContentsMargins(PAGE_MARGINS[0], 6, PAGE_MARGINS[2], 0)
        h.setSpacing(8)
        tabs = Pivot(bar)
        for k in keys:
            tabs.addItem(k, win._labels.get(k, k), lambda _=False, key=k: win.show_page(key))
        h.addWidget(tabs)
        h.addStretch(1)
        win.search.setParent(bar)
        win.search.setCompacted(False)
        win.search.setFixedSize(240, 36)
        h.addWidget(win.search)
        h.addWidget(_prefs_button(win))
        win.body.layout().insertWidget(0, bar)
        win._left = {"mode": mode, "bar": bar, "tabs": tabs}
    # The search filters the tools where they are listed (the pane), as it does
    # the navigation's entries.
    win.search.edit.textChanged.connect(lambda q: _filter_lists(win, q))


def _filter_lists(win, q):
    q = q.strip().lower()
    for page in win._pages.values():
        lst = getattr(page, "tool_list", None)
        if lst is None:
            continue
        head, shown = None, 0
        for i in range(lst.count()):
            it = lst.item(i)
            if not it.data(Qt.UserRole):            # a group's heading
                if head is not None:
                    head.setHidden(bool(q) and not shown)
                head, shown = it, 0
                continue
            vis = not q or q in it.text().lower()
            it.setHidden(not vis)
            shown += vis
        if head is not None:
            head.setHidden(bool(q) and not shown)


def follow_left(win, key, page):
    """The shown place selected in the places; merged: the place's tools under them."""
    left = getattr(win, "_left", None)
    if left is None:
        return
    if left["mode"] == "merged":
        places = left["places"]
        for i in range(places.count()):
            if places.item(i).data(Qt.UserRole) == key:
                places.setCurrentRow(i)
                break
        else:
            places.clearSelection()
        slot = left["slot"]
        pane = getattr(page, "pane", None) if isinstance(page, StructureHost) else None
        if pane is not None:
            if slot.indexOf(pane) < 0:
                slot.addWidget(pane)                # the host's list moves into the column
            slot.setCurrentWidget(pane)
        else:
            slot.setCurrentIndex(0)
    elif key in PLACE_KEYS:
        left["tabs"].setCurrentItem(key)


def matching_tools(q: str) -> list[str]:
    """The workspace tools whose label holds *q* (lower case); none outside a
    re-hosting structure (today's navigation lists every tool itself)."""
    if not q or not active():
        return []
    reg = _registry()
    out = []
    for t in ONE_DOC + FILE_TOOLS + ["ReaderTool"]:
        e = reg.get(t)
        if e is not None and q in plain_label(e.label).lower() and host_for(t):
            out.append(t)
    return out
