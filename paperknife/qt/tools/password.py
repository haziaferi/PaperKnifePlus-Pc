"""Password — a single-file transform (group C): add, change or remove encryption."""
from __future__ import annotations

from qfluentwidgets import PasswordLineEdit

from ...core import password as core
from ...core.document import NO_PASSWORD, Protection
from .. import dialogs
from ..pages import (APPLY, ToolPage, card, group_title, register_page, setting_row,
                     toggle_switch)


def _password_field(placeholder: str) -> PasswordLineEdit:
    e = PasswordLineEdit()
    e.setPlaceholderText(placeholder)
    e.setMinimumWidth(260)
    return e




@register_page("PasswordTool")
class PasswordPage(ToolPage):
    def __init__(self, tool=None, window=None):
        super().__init__("Password", "Add AES-256 encryption or remove an existing password",
                         tool=tool, window=window)
        self.doc_input()
        self.body.addSpacing(16)

        self.body.addWidget(group_title("Add / Change Password"))
        add = card(padding=0)
        self.body.addWidget(add)
        self.pw1 = _password_field("Open (user) password")
        setting_row(add, "Open (user) password").layout().addWidget(self.pw1)
        self.pw2 = _password_field("Owner password (blank = random)")
        setting_row(add, "Owner password", "blank = random").layout().addWidget(self.pw2)
        self.allow_print = toggle_switch(True)
        setting_row(add, "Allow printing").layout().addWidget(self.allow_print)
        self.allow_copy = toggle_switch(True)
        setting_row(add, "Allow copying text").layout().addWidget(self.allow_copy)

        self.body.addWidget(group_title("Remove Password"))
        rm = card(padding=0)
        self.body.addWidget(rm)
        self.cur_pw = _password_field("Current password")
        setting_row(rm, "Current password").layout().addWidget(self.cur_pw)
        self.body.addStretch(1)

        self.secondary("Remove Password", self.unprotect)
        self.primary(APPLY, self.protect)

    def _forget_passwords(self):
        # The job's closures hold what the worker needs; the fields (whose
        # eye button shows them) keep nothing once it ended or the page is left.
        for e in (self.pw1, self.pw2, self.cur_pw):
            e.clear()

    def deactivate(self):
        self._forget_passwords()

    def _attempt(self, fn):
        """Run one Protect / Remove attempt; the fields (whose eye button
        shows them) are emptied after it, whatever came of it."""
        try:
            fn()
        finally:
            self._forget_passwords()

    def protect(self):
        self._attempt(self._protect)

    def unprotect(self):
        self._attempt(self._unprotect)

    def _the_document(self, title):
        """The window's document for the chosen file (opened there first,
        after the unsaved-edits question, when it is another one), or None."""
        src = self.chosen_file(title)
        if not src or not self.window_.adopt(src, ask=True):
            return None
        return self.window_.document

    @staticmethod
    def _files_protection(sd) -> bool:
        """The file is encrypted and no protection was set here since."""
        return sd.protection is None and (
            core.open_password_of(sd.doc) is not None
            or bool((sd.doc.metadata or {}).get("encryption")))

    def _current_password_opens_it(self, sd, cur, title, wrong) -> bool:
        """The password typed in Current password opens the file (its own
        encryption: one set here is the user's own); else said why."""
        if not self._files_protection(sd):
            return True
        try:
            doc = core.open_unlocked(sd.path, cur, any_encryption=True)
        except Exception as e:
            dialogs.error("Error", str(e))
            return False
        if doc is None:
            dialogs.error(title, wrong)
            return False
        doc.close()
        return True

    def _protect(self):
        sd = self._the_document("Protect")
        if sd is None:
            return
        pw = self.pw1.text()
        if not pw:
            return dialogs.warning("Protect", "Enter a password.")
        if (core.open_password_of(sd.doc) is None and self._files_protection(sd)
                and not self._current_password_opens_it(
                    sd, self.cur_pw.text(), "Protect",
                    "This PDF is already encrypted. Enter its password in "
                    "“Current password” below to change it.")):
            return
        owner = core.owner_password(self.pw2.text())
        perm = core.permissions(self.allow_print.isChecked(), self.allow_copy.isChecked())
        # The document's protection from now on: Save writes it (2026-10-23).
        sd.set_protection(Protection(pw, owner, perm), "Protect", {"page": "PasswordTool"})
        self.window_.set_status("✓  Password set · Save writes it to the file", "success")

    def _unprotect(self):
        sd = self._the_document("Unprotect")
        if sd is None:
            return
        if not (isinstance(sd.protection, Protection) or self._files_protection(sd)):
            return dialogs.info("Unprotect", "This PDF has no password.")
        if not self._current_password_opens_it(sd, self.cur_pw.text(), "Error",
                                               "Incorrect password."):
            return
        sd.set_protection(NO_PASSWORD, "Remove password", {"page": "PasswordTool"})
        self.window_.set_status("✓  Password removed · Save writes the file without it",
                                "success")
