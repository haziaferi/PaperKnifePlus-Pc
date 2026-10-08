from __future__ import annotations
from tkinter import messagebox
import customtkinter as ctk
from ..page_canvas import PageCanvasTool
from ..tool_base import register
from ..theme import ACCENT, ACCENT_H, CARD, MUTED, SUCCESS, WARN, _tk_color
from ..core import text as core_text
from ..core.text import block_font as _block_font  # noqa: F401  (old name)


@register
class EditTextTool(PageCanvasTool):
    section = "CONTENT"
    label   = "✏️   Edit Text"
    save_name  = "edited.pdf"
    saved_what = "Edited PDF"

    _sel_bi:   int | None = None
    _edit_box: ctk.CTkTextbox | None = None

    def show(self):
        app  = self.app
        body = self._card("✏️  Edit Text",
                          "Click any text block to select it · edit the span · Ctrl+S to save")
        self._viewer_file_row(body)

        zoom_row = ctk.CTkFrame(body, fg_color="transparent")
        zoom_row.pack(fill="x", padx=24, pady=(0, 4))
        ctk.CTkLabel(zoom_row, text="Zoom:", text_color=MUTED,
                     font=ctk.CTkFont(size=12)).pack(side="left")
        self._viewer_zoom(zoom_row).pack(side="left", fill="x", expand=True, padx=8)

        self._viewer_canvas(body, frame_color=CARD).bind("<Button-1>", self._on_click)

        # ── edit row ──────────────────────────────────────────────────────────
        er = ctk.CTkFrame(body, fg_color="transparent")
        er.pack(fill="x", padx=24, pady=4)
        # Multi-line: a block keeps its line breaks while it is edited.
        self._edit_box = ctk.CTkTextbox(er, height=90, wrap="word",
                                         font=ctk.CTkFont(size=14))
        self._edit_box.configure(state="disabled")
        self._edit_box.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self._apply_btn = ctk.CTkButton(
            er, text="Apply Edit", width=120, height=40,
            state="disabled", command=self._apply_edit)
        self._apply_btn.pack(side="left")

        ctk.CTkButton(body, text="  Save PDF  →", height=46,
                      command=self._save,
                      fg_color=ACCENT, hover_color=ACCENT_H,
                      font=ctk.CTkFont(size=15, weight="bold")
                      ).pack(fill="x", padx=24, pady=8)

        app._cur_open_fn = self._open
        app._cur_save_fn = self._save
        app._cur_undo_fn = self._undo
        # Undo restores the whole document as it was before each edit (ToolBase).
        self._viewer_reset()

    # A selection belongs to one page of one document: drop it when either changes,
    # or Apply Edit would write it into another file's block.
    def _on_open(self):
        self._blocks = []
        self._clear_selection()

    def _on_page(self):
        self._clear_selection()

    def _clear_selection(self):
        self._sel_bi = None
        if self._edit_box is not None and self._edit_box.winfo_exists():
            self._edit_box.configure(state="normal")
            self._edit_box.delete("1.0", "end")
            self._edit_box.configure(state="disabled")
            self._apply_btn.configure(state="disabled")

    # ── render ────────────────────────────────────────────────────────────────
    def _draw_overlay(self, page):
        self._blocks = []
        for bi, block in core_text.text_blocks(page):
            bx0, by0, bx1, by1 = self._page_to_screen(block["bbox"], page)
            rid = self._canvas.create_rectangle(
                bx0, by0, bx1, by1,
                outline=_tk_color(ACCENT) if bi == self._sel_bi else "",
                fill="", width=2)
            self._blocks.append({
                "bi": bi, "block": block, "rid": rid,
                "bbox": (bx0, by0, bx1, by1),
            })

    def _on_click(self, event):
        cx, cy = self._event_point(event)
        for item in self._blocks:
            x0, y0, x1, y1 = item["bbox"]
            if x0 <= cx <= x1 and y0 <= cy <= y1:
                self._select_block(item["bi"])
                return

    def _select_block(self, bi):
        self._sel_bi = bi
        for item in self._blocks:
            self._canvas.itemconfigure(
                item["rid"],
                outline=_tk_color(ACCENT) if item["bi"] == bi else "")
        # Keep the block's line breaks so multi-line content can be edited as such.
        block = next((it["block"] for it in self._blocks if it["bi"] == bi), None)
        if not block:
            return
        self._edit_box.configure(state="normal")
        self._edit_box.delete("1.0", "end")
        self._edit_box.insert("1.0", core_text.block_text(block))
        self._apply_btn.configure(state="normal")
        self._edit_box.focus_set()

    # ── style / layout helpers ────────────────────────────────────────────────

    def _apply_edit(self):
        if self._sel_bi is None or not self._doc:
            return
        block = next((it["block"] for it in self._blocks if it["bi"] == self._sel_bi), None)
        if not block:
            return
        new_tx = self._edit_box.get("1.0", "end-1c")

        self._push_undo()
        try:
            own_font = core_text.write_block(self._doc[self._pg], block, new_tx)
        except Exception as e:
            # The original text may already be redacted away; put it back.
            self._pop_undo()
            self._render()
            return messagebox.showerror("Edit Text", f"The edit could not be applied:\n{e}")

        self._clear_selection()
        if own_font:
            self.app._set_status("Edit applied — use Save to write to disk", SUCCESS)
        else:
            self.app._set_status(
                f"Edit applied in Helvetica: the block's font "
                f"'{core_text.block_style(block)[0]}' is not built in — use Save to write to disk",
                WARN)
        self._render()

    def _undo(self):
        if not self._undo_stack or not self._doc:
            return
        self._pop_undo()
        self._clear_selection()
        self._render()
        self.app._set_status("Undo applied", SUCCESS)
