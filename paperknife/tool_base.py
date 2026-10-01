"""
paperknife.tool_base
ToolBase ABC and the global tool registry.

Each tool file defines a subclass and decorates it with @register:

    from paperknife.tool_base import ToolBase, register

    @register
    class MergeTool(ToolBase):
        section = "ORGANISE"
        label   = "📎  Merge"

        def show(self) -> None:
            body = self.app._card_layout("📎  Merge PDFs", "…")
            ...

The registry is populated by tools/__init__.py importing every tool
module.  app.py then reads TOOLS to build the sidebar navigation.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
import typing

if typing.TYPE_CHECKING:
    from .app import App

# ── Registry ──────────────────────────────────────────────────────────────────
TOOLS: list["ToolBase"] = []

def register(cls: type["ToolBase"]) -> type["ToolBase"]:
    """Class decorator: instantiate the tool and add it to the registry."""
    TOOLS.append(cls())
    return cls


# ── Base class ─────────────────────────────────────────────────────────────────
class ToolBase(ABC):
    """
    Minimal contract every tool must fulfil.

    Attributes
    ----------
    section : str   Sidebar section heading (ORGANISE / ENHANCE / CONVERT / CONTENT)
    label   : str   Sidebar button label, including emoji prefix
    """
    section: str = "MISC"
    label:   str = "(unnamed)"

    # Set by activate() before show() is called — tools use self.app freely.
    app: "App"

    def activate(self, app: "App") -> None:
        """Called by App._nav_click.  Binds app context then renders the view."""
        self.app = app
        self.show()

    @abstractmethod
    def show(self) -> None:
        """Build the tool UI into self.app.main.  Called on every navigation."""
        ...

    # ── Convenience shortcuts ─────────────────────────────────────────────────
    # These let tool code remain terse; all delegate straight to the App shell.

    def _card(self, title: str, subtitle: str = ""):
        return self.app._card_layout(title, subtitle)

    def _file_row(self, parent, var, btn_text="Open PDF", exts=(".pdf",)):
        return self.app._file_row(parent, var, btn_text, exts)

    def _listbox(self, parent, height=12):
        return self.app._listbox(parent, height)

    def _big_btn(self, parent, text, cmd, **kw):
        return self.app._big_btn(parent, text, cmd, **kw)

    def _save_as(self, default="output.pdf", ext=".pdf"):
        return self.app._save_as(default, ext)

    def _open_safe(self, path: str):
        return self.app._open_pdf_safe(path)

    def _status(self, msg: str, color=None):
        from .theme import MUTED
        self.app._set_status(msg, color or MUTED)

    def run_job(self, worker_fn, label: str = "Working…"):
        self.app.run_job(worker_fn, label)
