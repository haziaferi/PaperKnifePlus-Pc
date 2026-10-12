"""paperknife.core.recovery: what an app that did not close leaves to recover."""
import subprocess
import sys
import textwrap
import time

from conftest import SRC
from paperknife.core import recovery


def _child(root, body: str) -> subprocess.Popen:
    code = textwrap.dedent(f"""
        import sys, time, os
        sys.path.insert(0, {str(SRC)!r})
        from paperknife.core import recovery
        s = recovery.Session({str(root)!r})
        s.write("FindReplaceTool", {{"path": "C:/x/report.pdf", "name": "report.pdf"}}, b"%PDF-1.7 edited")
        print("ready", flush=True)
    """) + textwrap.dedent(body)
    return subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, text=True)


def test_a_crashed_app_leaves_its_edits_to_recover(tmp_path):
    p = _child(tmp_path, "os._exit(1)")          # no close(): as a crash
    assert p.stdout.readline().strip() == "ready"
    p.wait(30)
    left = recovery.orphaned(tmp_path)
    assert [(e.key, e.meta["name"]) for e in left] == [("FindReplaceTool", "report.pdf")]
    assert left[0].pdf == b"%PDF-1.7 edited" and left[0].meta["saved_at"] > 0
    recovery.discard(left)
    assert recovery.orphaned(tmp_path) == [] and list(tmp_path.iterdir()) == []


def test_a_running_app_s_edits_are_not_offered(tmp_path):
    p = _child(tmp_path, "time.sleep(60)")
    try:
        assert p.stdout.readline().strip() == "ready"
        assert recovery.orphaned(tmp_path) == []        # its lock is held
    finally:
        p.kill()
        p.wait(30)
    # Windows frees a killed process's lock once its handles are closed,
    # a moment after it ends.
    deadline = time.monotonic() + 5
    while not recovery.orphaned(tmp_path) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert [e.key for e in recovery.orphaned(tmp_path)] == ["FindReplaceTool"]


def test_session_write_remove_close(tmp_path):
    s = recovery.Session(tmp_path)
    s.write("RotateTool", {"state": {"order": [1, 0]}}, None)
    s.write("AnnotateTool", {"name": "a.pdf"}, b"pdf")
    assert s.keys() == ["AnnotateTool", "RotateTool"]
    assert recovery.orphaned(tmp_path) == []            # this process holds it
    s.write("AnnotateTool", {"name": "a.pdf"}, None)   # edits no longer in a PDF
    assert not (s.folder / "AnnotateTool.pdf").exists()
    s.remove("RotateTool")
    assert s.keys() == ["AnnotateTool"]
    s.close()                                           # a normal exit
    assert list(tmp_path.iterdir()) == []


def test_released_session_is_left_behind_and_empty_folders_go(tmp_path):
    s = recovery.Session(tmp_path)
    s.write("MetadataTool", {"state": {"title": "T"}}, None)
    s.release()
    empty = recovery.Session(tmp_path)
    empty.release()
    left = recovery.orphaned(tmp_path)
    assert [e.key for e in left] == ["MetadataTool"] and left[0].pdf is None
    assert not empty.folder.exists()


def test_unreadable_entry_is_skipped(tmp_path):
    s = recovery.Session(tmp_path)
    (s.folder / "Broken.json").write_text("{not json", encoding="utf-8")
    s.write("TocTool", {"state": []}, None)
    s.release()
    assert [e.key for e in recovery.orphaned(tmp_path)] == ["TocTool"]
