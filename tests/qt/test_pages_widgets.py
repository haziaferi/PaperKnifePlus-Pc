"""Shared page widgets."""
from qt_harness import pump


def test_spin_box_shows_its_number(qapp):
    from PySide6.QtWidgets import QWidget, QVBoxLayout
    from paperknife.qt.pages import spin_box
    w = QWidget()
    v = QVBoxLayout(w)
    sb = spin_box(0, 100000, 50)
    v.addWidget(sb)
    w.resize(300, 80)
    w.show()
    pump(0.1)
    assert sb.value() == 50 and sb.lineEdit().text() == "50"
    # qfluentwidgets 1.11.3 on PySide6 6.12 lays the inner edit out 1 px wide.
    assert sb.lineEdit().width() > 40
    w.close()


def _collection(tmp_path, n=3, **kw):
    from paperknife.qt.pages import CollectionPage
    page = CollectionPage("Merge", "", **kw)
    paths = []
    for i in range(n):
        p = tmp_path / f"f{i}.pdf"
        p.write_bytes(b"%PDF-1.4\n")
        paths.append(str(p))
    page.resize(900, 600)
    page.show()
    return page, paths


def test_collection_adds_moves_and_removes(qapp, tmp_path):
    page, paths = _collection(tmp_path)
    assert page.empty_label.isVisibleTo(page)
    assert page.add_paths(paths) == 3 and page.paths() == paths
    assert not page.empty_label.isVisibleTo(page)
    assert [r.num.text() for r in page.rows] == ["1.", "2.", "3."]
    assert not page.remove_btn.isEnabled()
    page.select(0)
    page.move(-1)                       # already first: nothing moves
    page.move(1)
    assert page.paths() == [paths[1], paths[0], paths[2]] and page.selected_index() == 1
    assert [r.num.text() for r in page.rows] == ["1.", "2.", "3."]
    page.select(2)
    assert not page.down_btn.isEnabled()
    page.delete()
    assert page.paths() == [paths[1], paths[0]] and page.selected_index() == 1
    page.clear_rows()
    assert page.paths() == [] and page.empty_label.isVisibleTo(page)
    page.close()


def test_collection_rows_keep_their_order_on_screen(qapp, tmp_path):
    page, paths = _collection(tmp_path)
    page.add_paths(paths)
    page.select(2)
    page.move(-1)
    pump(0.05)
    ys = [r.y() for r in page.rows]
    assert ys == sorted(ys) and page.rows[1].path == paths[2]
    page.close()


def test_collection_drop_takes_only_its_types(qapp, tmp_path):
    page, paths = _collection(tmp_path, n=1, exts=(".png",), add_text="Add images")
    img = tmp_path / "a.PNG"
    img.write_bytes(b"x")
    assert page.accept_drop(paths[0]) is False
    assert page.accept_drop(str(img)) is True and page.paths() == [str(img)]
    assert "Add images" in page.empty_label.text()
    page.close()


def test_collection_open_adds_the_chosen_files(qapp, tmp_path, dialogs):
    page, paths = _collection(tmp_path)
    dialogs.open(paths[:2])
    page.open()
    assert page.paths() == paths[:2]
    page.close()


def test_collection_row_extra_and_note(qapp, tmp_path):
    from qfluentwidgets import LineEdit
    from paperknife.qt.pages import CollectionPage

    class P(CollectionPage):
        def make_extra(self, path):
            return LineEdit()
    page = P("Merge", "")
    p = tmp_path / "a.pdf"
    p.write_bytes(b"%PDF")
    page.add_paths([str(p)])
    assert isinstance(page.rows[0].extra, LineEdit)
    page.rows[0].set_note("✓", "success")
    assert page.rows[0].note.text() == "✓" and not page.rows[0].note.isHidden()
    assert page.settings is not None
    page.close()
