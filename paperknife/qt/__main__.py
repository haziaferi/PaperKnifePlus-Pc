"""
paperknife.qt.__main__
Start the Qt interface:  python -m paperknife.qt [file.pdf]
"""
from __future__ import annotations

import os
import sys


def main(argv=None) -> int:
    argv = list(sys.argv if argv is None else argv)
    # Per-monitor DPI awareness is Qt 6's default; nothing to set here.
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(argv)
    app.setApplicationName("PaperKnife+ PC")
    app.setOrganizationName("PaperKnife+")

    # The pages first, then the appearance BEFORE any widget is built.
    import paperknife.qt.tools  # noqa: F401  (registers the Qt pages)
    from . import bridge, theme
    bridge.install()
    theme.setup_fonts(app)
    theme.apply_appearance()

    from .shell import MainWindow
    win = MainWindow()
    if "--selftest" in argv:                    # a build checking itself (selftest.py)
        from . import selftest
        report = argv[argv.index("--selftest") + 1]
        win.move(-4000, 40)
        win.show()
        app.processEvents()
        code = selftest.run(win, report)
        win._close_ok = True
        win.close()
        return code
    win.show()
    for arg in argv[1:]:
        if os.path.isfile(arg):
            win.open_tool("ReaderTool", arg)
            break
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
