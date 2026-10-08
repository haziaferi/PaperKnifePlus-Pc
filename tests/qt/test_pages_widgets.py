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
