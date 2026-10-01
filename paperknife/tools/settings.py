from __future__ import annotations
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
from ..tool_base import ToolBase, register
from ..theme import CARD, TEXT, MUTED, SUCCESS
from ..prefs import PREFS, _DEFAULTS
from ..recent import RECENT_STORE_MAX

# (label, min, max) for the integer settings.
_INT_RANGES = {
    "max_recent":  ("Max recent files shown", 1, RECENT_STORE_MAX),
    "default_dpi": ("Default DPI", 72, 600),
}


@register
class SettingsTool(ToolBase):
    section = "SETTINGS"
    label   = "⚙   Preferences"

    def show(self):
        app  = self.app
        body = self._card("⚙  Preferences",
                          "Click Save Preferences to keep changes")

        card = ctk.CTkFrame(body, fg_color=CARD, corner_radius=8)
        card.pack(fill="x", padx=24, pady=16)

        self._vars: dict[str, tk.Variable] = {}

        def row(label, key, kind, **kw):
            r = ctk.CTkFrame(card, fg_color="transparent")
            r.pack(fill="x", padx=16, pady=6)
            ctk.CTkLabel(r, text=label, width=230, text_color=TEXT,
                         anchor="w", font=ctk.CTkFont(size=13)).pack(side="left")
            if kind == "entry":
                var = tk.StringVar(value=str(PREFS.get(key, "")))
                ctk.CTkEntry(r, textvariable=var, width=260, height=36).pack(side="left")
            elif kind == "optionmenu":
                var = tk.StringVar(value=str(PREFS.get(key, kw["values"][0])))
                ctk.CTkOptionMenu(r, variable=var, values=kw["values"],
                                   width=260, height=36).pack(side="left")
            elif kind == "dir":
                var = tk.StringVar(value=str(PREFS.get(key, "")))
                ctk.CTkEntry(r, textvariable=var, state="readonly",
                             width=200, height=36).pack(side="left", padx=(0, 8))
                def _pick(v=var):
                    d = filedialog.askdirectory()
                    if d:
                        v.set(d)
                ctk.CTkButton(r, text="Browse…", width=80, height=36,
                              command=_pick).pack(side="left")
            self._vars[key] = var

        ctk.CTkLabel(card, text="General",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=MUTED, anchor="w").pack(padx=16, pady=(14, 2), fill="x")
        row("Default output folder",  "output_dir",     "dir")
        row("Max recent files shown", "max_recent",     "entry")

        ctk.CTkLabel(card, text="Appearance",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=MUTED, anchor="w").pack(padx=16, pady=(10, 2), fill="x")
        row("Colour mode", "appearance",
            "optionmenu", values=["light", "dark", "system"])

        ctk.CTkLabel(card, text="PDF operations",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=MUTED, anchor="w").pack(padx=16, pady=(10, 2), fill="x")
        row("Default DPI (OCR / export)",  "default_dpi",    "entry")
        row("Default compress level",       "compress_level",
            "optionmenu", values=["light", "medium", "aggressive"])
        row("OCR language code",            "ocr_lang",       "entry")

        ctk.CTkFrame(card, height=8, fg_color="transparent").pack()

        btn_row = ctk.CTkFrame(body, fg_color="transparent")
        btn_row.pack(fill="x", padx=24, pady=8)
        ctk.CTkButton(btn_row, text="Restore defaults", width=150, height=40,
                      fg_color=CARD, text_color=MUTED,
                      command=self._restore).pack(side="left")
        app._big_btn(btn_row, "  Save Preferences  →", self._save,
                     ).pack(side="right")

    def _save(self):
        values = {}
        for key, var in self._vars.items():
            val = var.get()
            if key in _INT_RANGES:
                name, lo, hi = _INT_RANGES[key]
                try:
                    val = int(val)
                except ValueError:
                    val = None
                if val is None or not lo <= val <= hi:
                    messagebox.showwarning(
                        "Not saved",
                        f"{name} must be a whole number from {lo} to {hi}.")
                    return
            values[key] = val
        for key, val in values.items():
            setattr(PREFS, key, val)
        ctk.set_appearance_mode(PREFS.appearance)
        self._persist("✓  Preferences saved", "Preferences saved.")

    def _restore(self):
        if not messagebox.askyesno("Restore", "Reset all preferences to defaults?"):
            return
        for key, val in _DEFAULTS.items():
            if key != "window_geometry":
                setattr(PREFS, key, val)
        ctk.set_appearance_mode(PREFS.appearance)
        self._persist("✓  Preferences restored to defaults", None)
        self.show()

    def _persist(self, status, info):
        try:
            PREFS.save()
        except OSError as exc:
            messagebox.showerror("Not saved",
                                 f"Could not write the preferences file:\n{exc}")
            return
        self.app._set_status(status, SUCCESS)
        if info:
            messagebox.showinfo("Saved", info)
