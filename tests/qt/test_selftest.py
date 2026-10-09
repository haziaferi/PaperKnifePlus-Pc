"""The build's self-check (PaperKnifePlusPC.exe --selftest report.txt)."""
from paperknife.qt import selftest
from paperknife.qt.pages import QT_PAGES


def test_the_selftest_checks_every_page_and_library(window, tmp_path):
    report = tmp_path / "report.txt"
    code = selftest.run(window, str(report))
    lines = report.read_text(encoding="utf-8").splitlines()
    pages = [ln for ln in lines if ln.split()[1] == "page"]
    assert len(pages) == len(QT_PAGES) and all(ln.startswith("ok") for ln in pages)
    assert {ln.split()[2] for ln in lines if ln.split()[1] == "import"} == set(selftest.OPTIONAL)
    # the test platform is offscreen: exactly that check fails, and so does the run
    fails = [ln for ln in lines[:-1] if ln.startswith("FAIL")]
    assert [f.split(":")[0] for f in fails] == ["FAIL Qt platform"], fails
    assert code == 1 and lines[-1] == f"FAIL {len(lines) - 2}/{len(lines) - 1}"
