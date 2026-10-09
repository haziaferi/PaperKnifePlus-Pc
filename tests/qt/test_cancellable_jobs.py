"""A job whose worker never checks stop offers no Cancel: pressing Cancel used
to let the save finish and then report "Cancelled" (review R1-16 / R3-10)."""
import ast
import threading
from pathlib import Path

from qt_harness import pump, wait_job

TOOLS = Path(__file__).resolve().parents[2] / "paperknife" / "qt" / "tools"


def _uses_arg(fn, i: int) -> bool:
    if len(fn.args.args) <= i:
        return False
    name = fn.args.args[i].arg
    body = fn.body if isinstance(fn.body, list) else [fn.body]
    return any(isinstance(n, ast.Name) and n.id == name for s in body for n in ast.walk(s))


# The call that starts a job -> (which argument is the worker, which of the
# worker's parameters is stop): run_job(work(stop)) and the single-file pages'
# run_on_file(title, work(doc, out, stop, progress)).
JOB_CALLS = {"run_job": (0, 0), "run_on_file": (1, 2)}


def test_every_worker_that_ignores_stop_is_marked_not_cancellable():
    bad, seen = [], {k: 0 for k in JOB_CALLS}
    for f in sorted(TOOLS.glob("*.py")):
        tree = ast.parse(f.read_text(encoding="utf-8"))
        funcs = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
        for c in ast.walk(tree):
            if not (isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)
                    and c.func.attr in JOB_CALLS):
                continue
            w_at, stop_at = JOB_CALLS[c.func.attr]
            if len(c.args) <= w_at:
                continue
            w = c.args[w_at]
            fn = w if isinstance(w, ast.Lambda) else funcs.get(getattr(w, "id", ""))
            if fn is None:
                continue
            seen[c.func.attr] += 1
            marked = any(k.arg == "cancellable" and isinstance(k.value, ast.Constant)
                         and k.value.value is False for k in c.keywords)
            if not _uses_arg(fn, stop_at) and not marked:
                bad.append(f"{f.name}:{c.lineno}")
    assert all(seen.values()), f"the guard saw no call of one kind: {seen}"
    assert not bad, f"job workers that ignore stop but offer Cancel: {bad}"


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
