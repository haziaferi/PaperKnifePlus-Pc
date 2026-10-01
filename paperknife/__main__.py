"""
paperknife.__main__
Entry point — run with:
    python -m paperknife
or (after pip install -e .):
    paperknife
"""


def main():
    # Populate the tool registry before constructing the App.
    import paperknife.tools  # noqa: F401  — side-effect: fills tool_base.TOOLS

    # Restore saved appearance mode BEFORE the App window is built so that
    # customtkinter creates every widget in the right colour variant from
    # the start.  (theme.py no longer calls set_appearance_mode itself.)
    from paperknife.prefs import PREFS
    import customtkinter as ctk
    ctk.set_appearance_mode(PREFS.get("appearance", "light"))

    from paperknife.app import App
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
