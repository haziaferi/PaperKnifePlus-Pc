from __future__ import annotations
import tkinter as tk
from tkinter import messagebox
from pathlib import Path
import customtkinter as ctk
from ..tool_base import ToolBase, register
from ..core import password as core
from ..core.password import ALL_PERMS as _ALL_PERMS  # noqa: F401
from ..theme import ACCENT, ACCENT_H, CARD, TEXT, DANGER, DANGER_H, SUCCESS


@register
class PasswordTool(ToolBase):
    section = "ENHANCE"
    label   = "🔒  Password"

    def show(self):
        body = self._card("🔒  Password Protect",
                          "Add AES-256 encryption or remove an existing password")
        self._path = tk.StringVar()
        self._file_row(body, self._path)

        add = ctk.CTkFrame(body, fg_color=CARD, corner_radius=8)
        add.pack(fill="x", padx=24, pady=8)
        ctk.CTkLabel(add, text="Add / Change Password",
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=TEXT, anchor="w").pack(padx=16, pady=(14, 6), fill="x")
        self._pw1 = ctk.CTkEntry(add, height=42, show="•",
                                  placeholder_text="Open (user) password")
        self._pw1.pack(fill="x", padx=16, pady=4)
        self._pw2 = ctk.CTkEntry(add, height=42, show="•",
                                  placeholder_text="Owner password (blank = random)")
        self._pw2.pack(fill="x", padx=16, pady=4)
        pf = ctk.CTkFrame(add, fg_color="transparent")
        pf.pack(fill="x", padx=16, pady=4)
        self._allow_print = ctk.CTkCheckBox(pf, text="Allow printing", text_color=TEXT)
        self._allow_print.select()
        self._allow_print.pack(side="left", padx=(0, 16))
        self._allow_copy = ctk.CTkCheckBox(pf, text="Allow copying text", text_color=TEXT)
        self._allow_copy.select()
        self._allow_copy.pack(side="left")
        ctk.CTkButton(add, text="  Protect PDF  →", command=self._protect,
                      height=44, fg_color=ACCENT, hover_color=ACCENT_H,
                      font=ctk.CTkFont(size=14, weight="bold")
                      ).pack(fill="x", padx=16, pady=12)

        rm = ctk.CTkFrame(body, fg_color=CARD, corner_radius=8)
        rm.pack(fill="x", padx=24, pady=8)
        ctk.CTkLabel(rm, text="Remove Password",
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=TEXT, anchor="w").pack(padx=16, pady=(14, 6), fill="x")
        self._cur_pw = ctk.CTkEntry(rm, height=42, show="•",
                                     placeholder_text="Current password")
        self._cur_pw.pack(fill="x", padx=16, pady=4)
        ctk.CTkButton(rm, text="  Remove Password  →", command=self._unprotect,
                      height=44, fg_color=DANGER, hover_color=DANGER_H,
                      font=ctk.CTkFont(size=14, weight="bold")
                      ).pack(fill="x", padx=16, pady=12)

    def _protect(self):
        src = self._path.get()
        if not src:
            return messagebox.showwarning("Protect", "Select a PDF.")
        pw = self._pw1.get()
        if not pw:
            return messagebox.showwarning("Protect", "Enter a password.")
        owner = core.owner_password(self._pw2.get())
        out   = self.app._save_as("protected.pdf")
        if not out:
            return
        perm = core.permissions(self._allow_print.get(), self._allow_copy.get())
        doc = self._open_unlocked(src, self._cur_pw.get(), "Protect",
                                  "This PDF is already encrypted. Enter its password "
                                  "in “Current password” below to change it.")
        if doc is None:
            return

        def work(stop):
            core.protect_pdf(doc, out, pw, owner, perm)

        def done(_):
            self.app._set_status(f"✓  Protected → {Path(out).name}", SUCCESS)
            messagebox.showinfo("Done", f"Protected PDF saved:\n{out}")

        if not self._run_job(work, "Encrypting…", done):
            doc.close()

    @staticmethod
    def _open_unlocked(src, password, title, wrong_message, any_encryption=False):
        """The document at src, authenticated with password when it needs one
        to open (or, with any_encryption, whenever it is encrypted at all), or
        None after telling the user why not."""
        try:
            doc = core.open_unlocked(src, password, any_encryption)
        except Exception as e:
            messagebox.showerror("Error", str(e))
            return None
        if doc is None:
            messagebox.showerror(title, wrong_message)
        return doc

    def _unprotect(self):
        src = self._path.get()
        if not src:
            return messagebox.showwarning("Unprotect", "Select a PDF.")
        pw  = self._cur_pw.get()
        out = self.app._save_as("unlocked.pdf")
        if not out:
            return
        doc = self._open_unlocked(src, pw, "Error", "Incorrect password.", any_encryption=True)
        if doc is None:
            return

        def work(stop):
            core.unprotect_pdf(doc, out)

        def done(_):
            self.app._set_status(f"✓  Unlocked → {Path(out).name}", SUCCESS)
            messagebox.showinfo("Done", f"Unlocked PDF saved:\n{out}")

        if not self._run_job(work, "Removing the password…", done):
            doc.close()
