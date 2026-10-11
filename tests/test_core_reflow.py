"""Reflow (owner, 2026-10-11): a change re-wraps its paragraph, the text below
moves, what no longer fits goes on to the next page, and a change that would
cross a picture, line art, two columns or the end of the document is skipped
and listed."""
import io

import pymupdf as fitz

from paperknife.core import reflow

WORDS = ("alpha beta gamma delta epsilon zeta theta iota kappa lambda omicron sigma "
         "upsilon omega north south east west river mountain valley forest meadow").split()


def para(n, seed):
    return " ".join(WORDS[(seed * 7 + i * 5) % len(WORDS)] for i in range(n))


def make(paras, css="p {margin: 0 0 8pt 0; line-height: 1.3; text-align: left}",
         picture_after=None, rect=None):
    """A PDF laid out from <p> paragraphs (no page numbers, one column)."""
    rect = rect or fitz.Rect(72, 72, 400, 770)
    html = ""
    for i, p in enumerate(paras):
        html += f"<p>{p}</p>"
        if picture_after == i:
            html += '<p><img src="pic.png" width="120" height="40"/></p>'
    arch = fitz.Archive()
    if picture_after is not None:
        pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 60, 20), False)
        pix.clear_with(120)
        arch.add(pix.tobytes("png"), "pic.png")
    story = fitz.Story(html=html, user_css=css + " body {font-family: serif; font-size: 11pt}",
                       archive=arch)
    buf = io.BytesIO()
    writer = fitz.DocumentWriter(buf)
    more = True
    while more:
        dev = writer.begin_page(fitz.paper_rect("a4"))
        more, _ = story.place(rect)
        story.draw(dev)
        writer.end_page()
    writer.close()
    return fitz.open("pdf", buf.getvalue())


def lines(page):
    ls, _o = reflow.page_lines(page)
    return ls


def texts(page):
    return [" ".join(ln.text.split()) for ln in lines(page)]


def flat(doc):
    return " ".join(" ".join(p.get_text().split()) for p in doc)


def no_overlaps(page):
    ls = lines(page)
    for i, a in enumerate(ls):
        for b in ls[i + 1:]:
            inter = a.bbox & b.bbox
            if not inter.is_empty and inter.height > 0.3 * min(a.bbox.height, b.bbox.height) \
                    and inter.width > 1:
                return False, (a.text, b.text)
    return True, None


def test_replacing_a_word_by_itself_changes_nothing():
    doc = make([para(60, 1), para(40, 2), para(30, 3)])
    before = texts(doc[0])
    res = reflow.replace_all(doc, "gamma", "gamma")
    assert res.done > 0 and not res.skips
    assert texts(doc[0]) == before


def marked(n, seed):
    words = para(n, seed).split()
    words[5] = "Zmark"
    return " ".join(words)


def test_a_longer_word_rewraps_the_paragraph_and_moves_the_next_one_down():
    doc = make([marked(60, 1), para(40, 2)])
    first_para = [ln for ln in lines(doc[0])]
    second_top = next(ln.base for ln in first_para if ln.text.startswith(para(40, 2).split()[0]))
    words_before = flat(doc).split()
    target = "Zmark"
    res = reflow.replace_all(doc, target, "a much longer replacement phrase here")
    assert res.done == 1 and not res.skips, res.skips
    text = flat(doc)
    assert "a much longer replacement phrase here" in text
    # every other word is still there, in its order
    want = " ".join(words_before).replace(target, "a much longer replacement phrase here")
    assert text == want
    ok, pair = no_overlaps(doc[0])
    assert ok, pair
    new_top = next(ln.base for ln in lines(doc[0]) if ln.text.startswith(para(40, 2).split()[0]))
    assert new_top > second_top + 5                          # pushed down by at least a line


def test_a_shorter_word_pulls_the_text_below_up():
    doc = make([para(60, 1), para(40, 2)])
    p2_first = para(40, 2).split()[0]
    before = next(ln.base for ln in lines(doc[0]) if ln.text.startswith(p2_first))
    res = reflow.replace_all(doc, "upsilon", "u")
    assert res.done >= 1 and not res.skips
    after = next(ln.base for ln in lines(doc[0]) if ln.text.startswith(p2_first))
    assert after <= before
    assert flat(doc).count(" u ") >= 1


def test_a_change_that_keeps_the_line_count_leaves_later_lines_alone():
    doc = make([para(80, 4)])
    ls = lines(doc[0])
    last = ls[-1]
    word = ls[0].text.split()[1]
    res = reflow.replace_all(doc, word, word[:-1] + "x")     # same length
    assert res.done >= 1
    after = lines(doc[0])
    assert after[-1].text == last.text and abs(after[-1].base - last.base) < 0.01


def test_text_that_no_longer_fits_goes_on_to_the_next_page():
    doc = make([marked(70, 0)] + [para(70, i) for i in range(1, 14)])
    assert len(doc) >= 2
    before = flat(doc)
    last_line = lines(doc[0])[-1].text
    grow = "Zmark with many more words added to it now"
    res = reflow.replace_all(doc, "Zmark", grow)
    assert res.done == 1 and not res.skips, res.skips
    assert flat(doc) == before.replace("Zmark", grow)
    # the old last line of page 1 now opens page 2
    assert " ".join(last_line.split()) in texts(doc[1])[:3]
    for page in doc:
        ok, pair = no_overlaps(page)
        assert ok, (page.number, pair)


def test_a_picture_below_skips_the_change_and_lists_it():
    doc = make([marked(60, 1), para(30, 2)], picture_after=0)
    before = flat(doc)
    target = "Zmark"
    res = reflow.replace_all(doc, target, "a much longer replacement phrase here")
    assert res.done == 0 and res.skips
    assert "picture" in res.skips[0].reason and target in res.skips[0].text
    assert flat(doc) == before


def test_running_past_the_end_of_the_document_is_skipped():
    doc = make([marked(70, 0)] + [para(70, i) for i in range(1, 14)])
    doc.select([0])                                    # one full page, nothing after it
    assert lines(doc[0])[-1].base > 740
    before = flat(doc)
    res = reflow.replace_all(doc, "Zmark", "Zmark plus several more words to push it over")
    assert res.done == 0 and res.skips and "end of the document" in res.skips[0].reason
    assert flat(doc) == before


def test_line_unit_writes_within_the_line_or_skips():
    doc = make([para(30, 1) + " Zend"], css="p {margin: 0; line-height: 1.3; text-align: left}",
               rect=fitz.Rect(72, 72, 500, 770))
    ls = lines(doc[0])
    res = reflow.replace_all(doc, "Zend", "Zendish", unit=reflow.LINE)
    assert res.done == 1                                   # the last line has room
    first_word = ls[0].text.split()[1]
    res = reflow.replace_all(doc, first_word, first_word + " " + "wide " * 12, unit=reflow.LINE)
    assert res.skips and "no room" in res.skips[0].reason


def test_two_columns_skip_a_change_that_moves_text():
    doc = fitz.open()
    page = doc.new_page()
    for col, x in enumerate((50, 320)):
        tb = fitz.Rect(x, 72, x + 230, 700)
        rc = page.insert_textbox(tb, para(60, col) + "\n\n" + para(50, col + 3), fontsize=10,
                                 fontname="tiro")
        assert rc >= 0
    word = [ln for ln in lines(page) if ln.bbox.x0 < 300][1].text.split()[1]
    res = reflow.replace_all(doc, word, word + " and a great many extra words to wrap")
    # side-by-side columns are also rows of text at the same baselines
    assert res.done == 0 and res.skips
    assert all("two columns" in s.reason or "rows" in s.reason for s in res.skips)


def test_edit_text_keeps_bold_words_and_rewraps():
    doc = make(["plain start <b>bold middle</b> plain end " + para(40, 5)])
    page = doc[0]
    us = reflow.units(lines(page), reflow.PARAGRAPH)
    u = us[0]
    old = reflow.unit_text(u)
    new = old.replace("plain start", "a new and rather longer start")
    assert reflow.rewrite_unit(doc, 0, u, new).done == 1
    page = doc[0]
    spans = [s for b in page.get_text("dict")["blocks"] for ln in b.get("lines", [])
             for s in ln["spans"]]
    bold = [s for s in spans if "bold" in s["text"]]
    assert bold and all("Bold" in s["font"] or s["flags"] & 16 for s in bold)
    assert "a new and rather longer start" in flat(doc)


def test_paragraph_units_follow_the_layout():
    doc = make([para(50, 1), para(20, 2), para(35, 3)],
               css="p {margin: 0; text-indent: 18pt; line-height: 1.2; text-align: justify}")
    us = reflow.units(lines(doc[0]), reflow.PARAGRAPH)
    assert [" ".join(reflow.unit_text(u).split()) for u in us] == [para(50, 1), para(20, 2), para(35, 3)]


def test_a_comment_box_on_the_text_is_kept_and_the_change_listed():
    doc = make([marked(60, 1), para(30, 2)])
    page = doc[0]
    zline = next(ln for ln in lines(page) if "Zmark" in ln.text)
    page.add_freetext_annot(fitz.Rect(zline.bbox.x0, zline.bbox.y0, zline.bbox.x0 + 150,
                                      zline.bbox.y1 + 20), "a reviewer's note")
    res = reflow.replace_all(doc, "Zmark", "longer words in place of the mark")
    assert res.done == 0 and "comment" in res.skips[0].reason
    assert [a.type[1] for a in doc[0].annots()] == ["FreeText"]
    assert not any("reviewer" in ln.text for ln in lines(doc[0]))   # not page text


def test_a_line_end_hyphen_follows_the_document_s_own_spelling():
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 100), "the example and the non-recoverable cases", fontsize=11)
    page.insert_text((72, 200), "one more exam-", fontsize=11)
    page.insert_text((72, 213.2), "ple and a non-", fontsize=11)
    page.insert_text((72, 226.4), "recoverable state", fontsize=11)
    eng = reflow.Engine(doc)
    u = next(u for u in reflow.units(lines(page), reflow.PARAGRAPH) if "exam-" in reflow.unit_text(u))
    assert eng.text_of(u) == "one more example and a non-recoverable state"
    assert reflow.unit_text(u) == "one more exam-ple and a non-recoverable state"   # no evidence: kept


def test_a_line_laid_out_with_tab_stops_is_not_rewrapped():
    doc = fitz.open()
    page = doc.new_page()
    for i, (a, b) in enumerate([("Name", "Surname"), ("Street", "Number"), ("Town", "Postcode")]):
        page.insert_text((72, 100 + i * 14), a + " of the person", fontsize=11)
        page.insert_text((300, 100 + i * 14), b + " field", fontsize=11)
    before = flat(doc)
    res = reflow.replace_all(doc, "Street", "Street or square")
    assert res.done == 0 and ("tab stops" in res.skips[0].reason or "rows" in res.skips[0].reason)
    assert flat(doc) == before


def test_text_added_at_the_end_of_a_paragraph_takes_its_last_style():
    doc = make([para(40, 1), para(20, 2)])
    u = reflow.units(lines(doc[0]), reflow.PARAGRAPH)[0]
    eng = reflow.Engine(doc)
    old = eng.text_of(u)
    res = reflow.rewrite_unit(doc, 0, u, old + " and a closing sentence added here")
    assert res.done == 1, res.skips
    by_position = " ".join(doc[0].get_text(sort=True).split())
    assert by_position.startswith(old + " and a closing sentence added here " + para(20, 2))


def test_a_character_beyond_the_basic_plane_skips_the_change():
    # TextWriter's text layer cuts U+1D43E (math italic K) to U+1D43, whatever
    # font draws it (seen in the owner's colour paper; TextWriter cannot even
    # write one for a test page), so a plan that would redraw one is refused
    doc = make([para(20, 1)])
    eng = reflow.Engine(doc)
    eng._pno = 0
    span = lines(doc[0])[0].chars[0].span
    k = "\U0001D43E"
    plan = reflow.Plan()
    plan.add(0, draw=[reflow.Draw(100.0, [(72.0, [(f"with {k} arbitrary", span, 0)])], 13.0, 11.0)])
    assert eng._finish(plan) == f"it holds a character that cannot be drawn again ({k})"
    ok = reflow.Plan()
    ok.add(0, draw=[reflow.Draw(100.0, [(72.0, [("with K arbitrary", span, 0)])], 13.0, 11.0)])
    assert eng._finish(ok) is ok
