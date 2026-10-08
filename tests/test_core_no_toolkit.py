"""The shared modules load no user-interface toolkit: the Qt build ships without
tkinter and customtkinter, so anything they import must not pull them in."""
import subprocess
import sys

import pytest

from conftest import SRC

TOOLKIT_FREE = ["paperknife", "paperknife.core", "paperknife.core.convert",
                "paperknife.core.enhance",
                "paperknife.job_queue", "paperknife.prefs", "paperknife.recent",
                "paperknife.pages", "paperknife.lineart", "paperknife.tool_base"]


@pytest.mark.parametrize("module", TOOLKIT_FREE)
def test_module_imports_without_a_toolkit(module):
    probe = (f"import sys; sys.path.insert(0, {str(SRC)!r}); import {module}; "
             "bad = [m for m in ('tkinter', 'customtkinter', 'tkinterdnd2') if m in sys.modules]; "
             "print(','.join(bad))")
    out = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True,
                         timeout=60)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "", f"{module} loads {out.stdout.strip()}"
