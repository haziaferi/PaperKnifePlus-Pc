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


def _organiser(n=6):
    from PySide6.QtGui import QImage
    from paperknife.qt.pages import OrganiserPage
    page = OrganiserPage("Rotate & Reorder", "")
    page.resize(1000, 700)
    page.show()
    calls = []

    def render(k):
        calls.append(k)
        img = QImage(60, 80, QImage.Format_RGB32)
        img.fill(0xFFFFFF)
        return img
    page.set_pages(list(range(n)), render, lambda k: f"p.{k + 1}")
    return page, calls


def test_organiser_renders_thumbs_a_few_per_turn(qapp):
    page, calls = _organiser(n=10)
    assert calls == [] and page.rendering()      # nothing rendered inside set_pages
    pump(0.2)
    assert sorted(calls) == list(range(10)) and not page.rendering()
    assert not page.grid.item(0).icon().isNull()
    page.close()


def test_organiser_selection_enables_actions_and_moves_a_block(qapp):
    from qfluentwidgets import FluentIcon as FIF
    page, _ = _organiser()
    hits = []
    b = page.add_action("Rotate", FIF.ROTATE, lambda: hits.append(1))
    assert not b.isEnabled() and "Click a thumbnail" in page.hint_label.text()
    page.select(1)
    page.grid.item(2).setSelected(True)
    assert b.isEnabled() and page.selected() == [1, 2]
    assert page.hint_label.text() == "2 pages selected"
    page.move(1)
    assert page.order() == [0, 3, 1, 2, 4, 5] and page.selected() == [2, 3]
    page.move(-2)
    assert page.order() == [1, 2, 0, 3, 4, 5]
    page.move(-1)                                 # at the start: nothing moves
    assert page.order() == [1, 2, 0, 3, 4, 5]
    page.clear_pages()
    assert page.order() == [] and page.empty_label.isVisibleTo(page)
    page.close()


def test_organiser_drop_goes_to_the_file_card(qapp, tmp_path):
    from paperknife.qt.pages import OrganiserPage
    loaded = []

    class P(OrganiserPage):
        def load(self, path):
            loaded.append(path)
    page = P("Rotate", "")
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF")
    other = tmp_path / "a.txt"
    other.write_text("x")
    assert page.accept_drop(str(other)) is False
    assert page.accept_drop(str(pdf)) is True and loaded == [str(pdf)]
    page.close()


def test_master_detail_selection_drives_tools_and_detail(qapp, tmp_path):
    from qfluentwidgets import LineEdit
    from paperknife.qt.pages import MasterDetailPage
    seen = []

    class P(MasterDetailPage):
        def on_select(self, i):
            seen.append(i)
            if i is not None:
                self.detail_begin("Selected bookmark")
                self.detail_field("Title").addWidget(LineEdit())
    page = P("Bookmarks / TOC", "")
    page.resize(1000, 700)
    page.show()
    add = page.add_tool("Add below", None, lambda: None)
    rm = page.add_tool("Delete", None, lambda: None, needs_selection=True)
    assert page.empty_label.isVisibleTo(page) and add.isEnabled() and not rm.isEnabled()
    page.set_items(["Intro (p.1)", "  Part (p.3)"])
    assert page.count() == 2 and page.current() is None and not rm.isEnabled()
    page.select(1)
    assert page.current() == 1 and rm.isEnabled() and seen[-1] == 1
    assert page.detail is not None and page.findChildren(LineEdit)
    page.set_items(["A", "B", "C"], keep=2)
    assert page.current() == 2 and page.count_label.text() == "3 entries"
    page.select(None)
    assert page.current() is None and seen[-1] is None and not rm.isEnabled()
    page.close()


def test_a_fixed_width_field_sits_at_the_left(qapp):
    from qfluentwidgets import LineEdit
    from paperknife.qt.pages import MasterDetailPage
    page = MasterDetailPage("TOC", "")
    page.resize(1000, 700)
    page.show()
    page.detail_begin("Selected bookmark")
    wide, narrow = LineEdit(), LineEdit()
    narrow.setFixedWidth(90)
    page.detail_field("Title").addWidget(wide)
    page.detail_field("Page").addWidget(narrow)
    pump(0.1)
    assert narrow.x() == wide.x() and wide.width() > 200
    page.close()


def _ctrl_wheel(view, dx: int, dy: int):
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QWheelEvent
    ev = QWheelEvent(QPointF(10, 10), QPointF(10, 10), QPoint(0, 0), QPoint(dx, dy),
                     Qt.NoButton, Qt.ControlModifier, Qt.NoScrollPhase, False)
    view.wheelEvent(ev)


def _page_view(qapp, tmp_path, monkeypatch):
    import pymupdf as fitz
    from qt_harness import make_pdf
    from paperknife.qt import pageview
    renders = []
    real = pageview.render
    monkeypatch.setattr(pageview, "render", lambda *a, **k: (renders.append(1), real(*a, **k))[1])
    doc = fitz.open(make_pdf(tmp_path / "z.pdf", 1))
    view = pageview.PageView()
    view.show_page(doc[0])
    zooms = []
    view.zoomed.connect(zooms.append)
    return view, doc, renders, zooms


def test_ctrl_sideways_wheel_does_not_zoom(qapp, tmp_path, monkeypatch):
    # R1-13: a horizontal tilt / touchpad pan with Ctrl held zoomed out.
    view, doc, renders, zooms = _page_view(qapp, tmp_path, monkeypatch)
    before = view.zoom
    n = len(renders)
    _ctrl_wheel(view, 120, 0)
    assert view.zoom == before and zooms == [] and len(renders) == n
    doc.close()


def test_ctrl_wheel_at_the_zoom_limit_does_not_rerender(qapp, tmp_path, monkeypatch):
    # R1-13: at 3.0 every Ctrl+wheel up re-rendered an identical page.
    from paperknife.qt.pageview import ZOOM_MAX
    view, doc, renders, zooms = _page_view(qapp, tmp_path, monkeypatch)
    view.set_zoom(ZOOM_MAX)
    n = len(renders)
    _ctrl_wheel(view, 0, 120)
    view.set_zoom(ZOOM_MAX + 1)
    assert view.zoom == ZOOM_MAX and len(renders) == n and zooms == []
    doc.close()
