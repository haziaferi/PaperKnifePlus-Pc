"""The shared modules load no user-interface toolkit: the Qt build ships without
tkinter and customtkinter, so anything they import must not pull them in."""
import subprocess
import sys

import pytest

from conftest import SRC

# Every module in paperknife/core is read from the folder, so a new one is
# covered without editing this list (core.settings and core.reader were missed
# while it was kept by hand).
CORE = sorted(f"paperknife.core.{p.stem}" for p in (SRC / "paperknife" / "core").glob("*.py")
              if p.stem != "__init__")
TOOLKIT_FREE = ["paperknife", "paperknife.core", *CORE,
                "paperknife.job_queue", "paperknife.prefs", "paperknife.recent",
                "paperknife.pages", "paperknife.lineart", "paperknife.tool_base"]


def test_every_core_module_is_probed():
    assert {"paperknife.core.settings", "paperknife.core.reader"} <= set(CORE)


@pytest.mark.parametrize("module", TOOLKIT_FREE)
def test_module_imports_without_a_toolkit(module):
    probe = (f"import sys; sys.path.insert(0, {str(SRC)!r}); import {module}; "
             "bad = [m for m in ('tkinter', 'customtkinter', 'tkinterdnd2') if m in sys.modules]; "
             "print(','.join(bad))")
    out = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True,
                         timeout=60)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "", f"{module} loads {out.stdout.strip()}"
