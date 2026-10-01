from __future__ import annotations
import tkinter as tk
from tkinter import messagebox
from pathlib import Path
import fitz
import customtkinter as ctk
from ..tool_base import ToolBase, register
from ..theme import ACCENT, ACCENT_H, CARD, TEXT, MUTED, DANGER, DANGER_H, SUCCESS


@register
class PasswordTool(ToolBase):
    section = "ENHANCE"
    label   = "🔒  Password"

    def show(self):
        app  = self.app
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
                                  placeholder_text="Owner password (defaults to same)")
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
        owner = self._pw2.get() or pw
        out   = self.app._save_as("protected.pdf")
        if not out:
            return
        try:
            perm = 0
            if self._allow_print.get(): perm |= fitz.PDF_PERM_PRINT
            if self._allow_copy.get():  perm |= fitz.PDF_PERM_COPY
            doc = fitz.open(src)
            doc.save(out, encryption=fitz.PDF_ENCRYPT_AES_256,
                     user_pw=pw, owner_pw=owner, permissions=perm)
            doc.close()
            self.app._set_status(f"✓  Protected → {Path(out).name}", SUCCESS)
            messagebox.showinfo("Done", f"Protected PDF saved:\n{out}")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _unprotect(self):
        src = self._path.get()
        if not src:
            return messagebox.showwarning("Unprotect", "Select a PDF.")
        pw  = self._cur_pw.get()
        out = self.app._save_as("unlocked.pdf")
        if not out:
            return
        try:
            doc = fitz.open(src)
            if doc.is_encrypted and not doc.authenticate(pw):
                messagebox.showerror("Error", "Incorrect password.")
                doc.close()
                return
            doc.save(out, encryption=fitz.PDF_ENCRYPT_NONE)
            doc.close()
            self.app._set_status(f"✓  Unlocked → {Path(out).name}", SUCCESS)
            messagebox.showinfo("Done", f"Unlocked PDF saved:\n{out}")
        except Exception as e:
            messagebox.showerror("Error", str(e))
