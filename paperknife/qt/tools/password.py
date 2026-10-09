"""Password — a single-file transform (group C): add, change or remove encryption."""
from __future__ import annotations

from pathlib import Path

from qfluentwidgets import PasswordLineEdit, SwitchButton

from ...core import password as core
from .. import dialogs
from ..pages import ToolPage, card, file_card, group_title, register_page, setting_row


def _password_field(placeholder: str) -> PasswordLineEdit:
    e = PasswordLineEdit()
    e.setPlaceholderText(placeholder)
    e.setMinimumWidth(260)
    return e


def _switch(on: bool) -> SwitchButton:
    s = SwitchButton()
    s.setOnText("")
    s.setOffText("")
    s.setChecked(on)
    return s


@register_page("PasswordTool")
class PasswordPage(ToolPage):
    def __init__(self, tool=None, window=None):
        super().__init__("Password", "Add AES-256 encryption or remove an existing password",
                         tool=tool, window=window)
        self.file = file_card()
        self.body.addWidget(self.file)
        self.body.addSpacing(16)

        self.body.addWidget(group_title("Add / Change Password"))
        add = card(padding=0)
        self.body.addWidget(add)
        self.pw1 = _password_field("Open (user) password")
        setting_row(add, "Open (user) password").layout().addWidget(self.pw1)
        self.pw2 = _password_field("Owner password (blank = random)")
        setting_row(add, "Owner password", "blank = random").layout().addWidget(self.pw2)
        self.allow_print = _switch(True)
        setting_row(add, "Allow printing").layout().addWidget(self.allow_print)
        self.allow_copy = _switch(True)
        setting_row(add, "Allow copying text").layout().addWidget(self.allow_copy)

        self.body.addWidget(group_title("Remove Password"))
        rm = card(padding=0)
        self.body.addWidget(rm)
        self.cur_pw = _password_field("Current password")
        setting_row(rm, "Current password").layout().addWidget(self.cur_pw)
        self.body.addStretch(1)

        self.secondary("Remove Password", self.unprotect)
        self.primary("Protect PDF", self.protect)

    def _forget_passwords(self):
        # The job's closures hold what the worker needs; the fields (whose
        # eye button shows them) keep nothing once it ended or the page is left.
        for e in (self.pw1, self.pw2, self.cur_pw):
            e.clear()

    def deactivate(self):
        self._forget_passwords()

    def _open_unlocked(self, src, password, title, wrong_message, any_encryption=False):
        """The document at src, authenticated with password when it needs one
        to open (or, with any_encryption, whenever it is encrypted at all), or
        None after telling the user why not."""
        try:
            doc = core.open_unlocked(src, password, any_encryption)
        except Exception as e:
            dialogs.error("Error", str(e))
            return None
        if doc is None:
            dialogs.error(title, wrong_message)
        return doc

    def protect(self):
        src = self.chosen_file("Protect", "Select a PDF.")
        if not src:
            return
        pw = self.pw1.text()
        if not pw:
            return dialogs.warning("Protect", "Enter a password.")
        owner = core.owner_password(self.pw2.text())
        perm = core.permissions(self.allow_print.isChecked(), self.allow_copy.isChecked())
        cur = self.cur_pw.text()
        self.run_on_file(
            "Protect", lambda doc, out, stop, _p: core.protect_pdf(doc, out, pw, owner, perm),
            "Encrypting…",
            lambda _v, out: ("success", f"✓  Protected → {Path(out).name}",
                             "Done", f"Protected PDF saved:\n{out}"),
            src=src, save=("protected.pdf", ".pdf", [("PDF", "*.pdf")]),
            open_doc=lambda s: self._open_unlocked(
                s, cur, "Protect", "This PDF is already encrypted. Enter its password "
                                   "in “Current password” below to change it."),
            ended=lambda _kind: self._forget_passwords(), cancellable=False, ask_first=True)

    def unprotect(self):
        src = self.chosen_file("Unprotect", "Select a PDF.")
        if not src:
            return
        pw = self.cur_pw.text()
        self.run_on_file(
            "Unprotect", lambda doc, out, stop, _p: core.unprotect_pdf(doc, out),
            "Removing the password…",
            lambda _v, out: ("success", f"✓  Unlocked → {Path(out).name}",
                             "Done", f"Unlocked PDF saved:\n{out}"),
            src=src, save=("unlocked.pdf", ".pdf", [("PDF", "*.pdf")]),
            open_doc=lambda s: self._open_unlocked(s, pw, "Error", "Incorrect password.",
                                                   any_encryption=True),
            ended=lambda _kind: self._forget_passwords(), cancellable=False, ask_first=True)
