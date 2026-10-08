"""No Qt page may define a method under a DocHolder method's name: a page's
mouse handler called _release hid DocHolder._release(path), which frees the
open file before a save replaces it."""
import inspect


def test_no_page_hides_a_doc_holder_method(qapp):
    import paperknife.tools  # noqa: F401
    import paperknife.qt.tools  # noqa: F401
    from paperknife.core.doc_state import DocHolder
    from paperknife.qt.pages import QT_PAGES
    names = {n for n, v in vars(DocHolder).items() if inspect.isfunction(v)}
    bad = [f"{cls.__name__}.{n}" for cls in QT_PAGES.values() if issubclass(cls, DocHolder)
           for k in cls.__mro__ if k is not DocHolder and k is not object
           for n in names if n in vars(k)]
    assert not bad, bad
