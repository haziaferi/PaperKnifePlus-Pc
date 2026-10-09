"""A job whose worker never checks stop offers no Cancel: pressing Cancel used
to let the save finish and then report "Cancelled" (review R1-16 / R3-10)."""
import ast
import threading
from pathlib import Path

from qt_harness import pump, wait_job

TOOLS = Path(__file__).resolve().parents[2] / "paperknife" / "qt" / "tools"


def _uses_first_arg(fn) -> bool:
    if not fn.args.args:
        return False
    name = fn.args.args[0].arg
    body = fn.body if isinstance(fn.body, list) else [fn.body]
    return any(isinstance(n, ast.Name) and n.id == name for s in body for n in ast.walk(s))


def test_every_worker_that_ignores_stop_is_marked_not_cancellable():
    bad = []
    for f in sorted(TOOLS.glob("*.py")):
        tree = ast.parse(f.read_text(encoding="utf-8"))
        funcs = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
        for c in ast.walk(tree):
            if not (isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)
                    and c.func.attr == "run_job" and c.args):
                continue
            w = c.args[0]
            fn = w if isinstance(w, ast.Lambda) else funcs.get(getattr(w, "id", ""))
            if fn is None:
                continue
            marked = any(k.arg == "cancellable" and isinstance(k.value, ast.Constant)
                         and k.value.value is False for k in c.keywords)
            if not _uses_first_arg(fn) and not marked:
                bad.append(f"{f.name}:{c.lineno}")
    assert not bad, f"run_job workers that ignore stop but offer Cancel: {bad}"


def test_cancel_is_hidden_and_ignored_for_a_job_that_cannot_stop(window, tmp_path):
    out = tmp_path / "out.txt"
    gate = threading.Event()
    kinds = []

    def work(stop):
        gate.wait(5)
        out.write_text("saved", encoding="utf-8")
        return None

    window.run_job(work, "Saving…", then=lambda k, v: kinds.append(k), cancellable=False)
    pump(0.05)
    assert window.cancel_button.isHidden()
    window._cancel_job()                       # Esc / a stray click: must not mark it cancelled
    gate.set()
    wait_job(window)
    assert out.read_text(encoding="utf-8") == "saved" and kinds == ["done"]


def test_cancel_still_works_for_a_job_that_checks_stop(window):
    kinds = []

    def work(stop):
        while not stop.is_set():
            stop.wait(0.01)

    window.run_job(work, "Working…", then=lambda k, v: kinds.append(k))
    pump(0.05)
    assert not window.cancel_button.isHidden()
    window._cancel_job()
    wait_job(window)
    assert kinds == ["cancel"]
