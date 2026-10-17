"""Merge, split, reorder and the bookmark (outline) work of the ORGANISE tools."""
from __future__ import annotations
import os
import re

import pymupdf as fitz

from ..job_queue import atomic_output


def _kids(doc, xref: int) -> list[int]:
    kind, value = doc.xref_get_key(xref, "Kids")
    return [int(x) for x in re.findall(r"(\d+) 0 R", value)] if kind == "array" else []


def _prune_fields(doc) -> None:
    """Drop from the form's field list (/AcroForm /Fields) and calculation
    order (/CO) the fields none of whose widgets is on a page any more: listed,
    they would keep the pages left out in the file (a widget names its page)."""
    cat = doc.pdf_catalog()
    on_pages = {w.xref for p in doc for w in p.widgets()}

    def live(x, depth=0):
        return x in on_pages or (depth < 32 and any(live(k, depth + 1) for k in _kids(doc, x)))
    for key in ("AcroForm/Fields", "AcroForm/CO"):      # the form inline or not
        kind, value = doc.xref_get_key(cat, key)
        if kind != "array":
            continue
        tops = [int(x) for x in re.findall(r"(\d+) 0 R", value)]
        kept = [x for x in tops if live(x)]
        if len(kept) != len(tops):
            doc.xref_set_key(cat, key, "[" + " ".join(f"{x} 0 R" for x in kept) + "]")


def _label_rules(doc, pages) -> list[dict]:
    """Page-label rules giving each page of *pages* (indices of *doc*, in their
    new order) the label it had in *doc*.  Labels belong to positions, so
    pages that move or lose neighbours need rules of their own."""
    rules = sorted(doc.get_page_labels(), key=lambda r: r["startpage"])
    if not rules:
        return []
    out, prev = [], None
    for new, old in enumerate(pages):
        rid = next((i for i in range(len(rules) - 1, -1, -1) if rules[i]["startpage"] <= old), None)
        # Before the first rule a page has no label of its own: its number.
        r = rules[rid] if rid is not None else {"startpage": 0, "style": "D", "firstpagenum": 1}
        number = r.get("firstpagenum", 1) + old - r["startpage"]
        if prev is None or prev != (rid, old - 1):
            out.append({"startpage": new, "prefix": r.get("prefix", ""),
                        "style": r.get("style", ""), "firstpagenum": number})
        prev = (rid, old)
    return out


_TO_PAGE = (fitz.LINK_GOTO, fitz.LINK_NAMED)     # bookmark kinds with a page target


def _moved_toc(toc, new_index: dict[int, int]):
    """*toc* (get_toc(simple=False)) for the pages kept, at their new places
    (*new_index*: old page index -> new): a bookmark to a page left out goes
    (its children move up a level); one to a web address, another file or
    nowhere stays.  Targets are written as direct page targets."""
    toc = [list(e) for e in toc]
    i = 0
    while i < len(toc):
        e = toc[i]
        if e[3].get("kind") in _TO_PAGE and e[2] - 1 not in new_index:
            delete_entry(toc, i)
            continue
        if e[3].get("kind") in _TO_PAGE:
            d = e[3]
            e[2] = new_index[e[2] - 1] + 1
            e[3] = {k: d[k] for k in ("color", "bold", "italic", "collapse") if k in d}
            e[3].update(kind=fitz.LINK_GOTO, page=e[2] - 1,
                        to=d.get("to", fitz.Point(0, 0)), zoom=d.get("zoom", 0))
        i += 1
    return toc


# Catalog entries select() rewrites itself (the page tree, bookmarks, named
# destinations) or that copy_pages sets (labels); the rest it may drop are put back.
_REBUILT = {"Type", "Pages", "Outlines", "Dests", "Names", "PageLabels"}
# ... and those that reach every page: kept only while no page is left out,
# or the left-out pages would stay in the file through them.
_WHOLE_DOC = {"StructTreeRoot", "MarkInfo", "OpenAction"}
# The name trees besides the destinations (attachments, scripts, ...).
_NAME_TREES = ("EmbeddedFiles", "JavaScript", "AP", "Pages", "Templates", "IDS",
               "URLS", "AlternatePresentations", "Renditions")


def copy_pages(data: bytes, pages: list[int]) -> fitz.Document:
    """A new document holding the pages *pages* (indices, in that order, each
    once) of the PDF *data*, with what belongs to the document kept: form
    fields, bookmarks and named destinations to the pages kept, links, layers,
    page labels, attachments, the document properties and XMP.

    (insert_pdf into an empty document, as before, kept only the pages, their
    annotations and their page links; a page copied on its own lost its form
    fields.)  MuPDF's select() rearranges the pages and cleans what pointed to
    the ones left out, but drops some catalog entries: they are put back.
    Save it with garbage collection, or the pages left out stay in the file."""
    out = fitz.open("pdf", data)
    try:
        rearrange(out, pages)
    except Exception:
        out.close()
        raise
    return out


def rearrange(out, pages: list[int]) -> None:
    """Keep only the pages *pages* of *out*, in that order, in place, with
    what belongs to the document kept (copy_pages)."""
    n = len(out)
    if len(set(pages)) != len(pages) or not all(0 <= p < n for p in pages):
        raise ValueError(f"pages must be distinct indices below {n}")
    rules = _label_rules(out, pages)
    cat = out.pdf_catalog()
    whole = len(pages) == n
    before = {k: out.xref_get_key(cat, k) for k in out.xref_get_keys(cat)}
    names = {t: out.xref_get_key(cat, f"Names/{t}") for t in _NAME_TREES}
    toc = out.get_toc(simple=False)
    if "Dests" in before:
        # select() drops the catalog's destination dictionary (the older
        # form of named destinations) and the links that go through it.
        _named_links_to_goto(out)
    out.select(pages)
    # select() drops a bookmark that goes through a named destination: the
    # outline is written again when it lost one.
    want = _moved_toc(toc, {old: new for new, old in enumerate(pages)})
    if [e[:3] for e in out.get_toc(simple=False)] != [e[:3] for e in want]:
        out.set_toc(want)
    cat = out.pdf_catalog()
    have = set(out.xref_get_keys(cat))
    for k, (kind, value) in before.items():
        if k in have or k in _REBUILT or (k in _WHOLE_DOC and not whole) or kind == "null":
            continue
        out.xref_set_key(cat, k, value)
    for t, (kind, value) in names.items():
        if kind != "null" and out.xref_get_key(cat, f"Names/{t}")[0] == "null":
            if out.xref_get_key(cat, "Names")[0] == "null":
                out.xref_set_key(cat, "Names", "<<>>")
            out.xref_set_key(cat, f"Names/{t}", value)
    if not whole:
        _prune_fields(out)
    if rules:
        out.set_page_labels(rules)


CUT_LEAF = 4    # parts written straight from the copy that holds them


def _cut_parts(data: bytes, offset: int, parts, stop, written) -> bool:
    """Write each (first, last, before, target) of *parts* (pages of the
    whole document; *data* holds its pages from *offset* on): before(target)
    runs, then the pages go to *target*.  Each part is cut from a copy of the
    whole, so cutting every part from the whole costs parts x pages; above
    CUT_LEAF parts the pages each half needs are cut out first and the half is
    cut from them (parts x log parts).  False when *stop* was set."""
    if len(parts) <= CUT_LEAF:
        for fr, to, before, target in parts:
            if stop.is_set():
                return False
            before(target)
            with atomic_output(target) as tmp, \
                    copy_pages(data, list(range(fr - offset, to - offset + 1))) as nd:
                nd.save(tmp, garbage=1, deflate=True)
            written()
        return True
    half = len(parts) // 2
    for chunk in (parts[:half], parts[half:]):
        if stop.is_set():
            return False
        lo, hi = min(p[0] for p in chunk), max(p[1] for p in chunk)
        with copy_pages(data, list(range(lo - offset, hi - offset + 1))) as sub:
            sub_data = sub.tobytes(garbage=1)
        if not _cut_parts(sub_data, lo, chunk, stop, written):
            return False
    return True


def split_ranges(doc, groups, out_dir: str, base: str, stop, progress) -> int | None:
    """Write each (first, last) page group of *doc* to its own file in *out_dir*,
    named <base>_partNN_pA-B.pdf.  Returns the number written, None if cancelled.
    The caller owns *doc*."""
    total = len(groups)
    done = [0]

    def written():
        done[0] += 1
        progress(done[0] / total)
    parts = [(fr, to, lambda _t: None,
              os.path.join(out_dir, f"{base}_part{i + 1:02d}_p{fr + 1}-{to + 1}.pdf"))
             for i, (fr, to) in enumerate(groups)]
    return total if _cut_parts(doc.tobytes(), 0, parts, stop, written) else None


def split_parts(doc, parts, out_dir: str, base: str, stop, progress) -> int | None:
    """split_ranges for Split's parts (lists of 0-based pages, owner 2026-10-17):
    a part in a row is <base>_partNN_pA-B.pdf as before, one of scattered pages
    <base>_partNN_p2+5+7.pdf.  Returns the number written, None if cancelled."""
    runs = [(p[0], p[-1]) for p in parts if p == list(range(p[0], p[-1] + 1))]
    if len(runs) == len(parts):
        return split_ranges(doc, runs, out_dir, base, stop, progress)
    from ..pages import parts_text
    data, total = doc.tobytes(), len(parts)
    for i, pages in enumerate(parts):
        if stop.is_set():
            return None
        target = os.path.join(out_dir, f"{base}_part{i + 1:02d}_p{parts_text([pages])}.pdf")
        with atomic_output(target) as tmp, copy_pages(data, list(pages)) as nd:
            nd.save(tmp, garbage=1, deflate=True)
        progress((i + 1) / total)
    return total


_MARK = "PKsrc"     # a key put on each input's layers to find their copies


def _refs(text: str) -> list[int]:
    return [int(x) for x in re.findall(r"(\d+) 0 R", text)]


def _named_links_to_goto(doc) -> None:
    """Links to a named destination as direct page links: insert_pdf drops
    the former (the names do not come along) and keeps the latter."""
    for page in doc:
        for lk in page.get_links():
            if lk["kind"] == fitz.LINK_NAMED and lk.get("page", -1) >= 0:
                page.delete_link(lk)
                page.insert_link({"kind": fitz.LINK_GOTO, "from": lk["from"], "page": lk["page"],
                                  "to": lk.get("to", fitz.Point(0, 0)), "zoom": lk.get("zoom", 0)})


def _layers_of(doc, tag: int) -> dict:
    """Mark *doc*'s layers (optional content groups) with (tag-xref) so their
    copies can be found after insert_pdf, which copies the groups a page uses
    but not the catalog's list of them or which are off.  Their settings."""
    cat = doc.pdf_catalog()
    ocgs = _refs(doc.xref_get_key(cat, "OCProperties/OCGs")[1])
    for x in ocgs:
        doc.xref_set_key(x, _MARK, f"({tag}-{x})")
    off = set(_refs(doc.xref_get_key(cat, "OCProperties/D/OFF")[1]))
    if doc.xref_get_key(cat, "OCProperties/D/BaseState")[1] == "/OFF":
        off = set(ocgs) - set(_refs(doc.xref_get_key(cat, "OCProperties/D/ON")[1]))
    kind, order = doc.xref_get_key(cat, "OCProperties/D/Order")
    return {"ocgs": ocgs, "off": off, "order": order if kind == "array" else ""}


def _write_layers(merged, layers: list[dict]) -> None:
    """The merged file's layer list (/OCProperties): every input's layers
    found in it, off where they were off, in each input's order."""
    if not any(L["ocgs"] for L in layers):
        return
    found = {}
    for x in range(1, merged.xref_length()):
        kind, value = merged.xref_get_key(x, _MARK)
        if kind == "string":
            found[value] = x
            merged.xref_set_key(x, _MARK, "null")
    all_, off, order = [], [], []
    for tag, L in enumerate(layers):
        new = {x: found[f"{tag}-{x}"] for x in L["ocgs"] if f"{tag}-{x}" in found}
        all_ += new.values()
        off += [new[x] for x in L["off"] if x in new]
        if L["order"]:
            order.append(re.sub(r"(\d+) 0 R", lambda m, new=new: f"{new[int(m[1])]} 0 R"
                                if int(m[1]) in new else "", L["order"])[1:-1])
        else:
            order += [f"{x} 0 R" for x in new.values()]
    if not all_:
        return
    refs = lambda xs: " ".join(f"{x} 0 R" for x in xs)    # noqa: E731
    merged.xref_set_key(merged.pdf_catalog(), "OCProperties",
                        f"<</OCGs[{refs(all_)}]/D<</OFF[{refs(off)}]/Order[{' '.join(order)}]>>>>")


def _title(doc, i: int) -> str:
    """The bookmark naming input *i*: its file name."""
    name = doc.name or ""
    return os.path.basename(name) if os.path.isfile(name) else f"Document {i + 1}"


def merge(jobs, out: str, stop, progress) -> int | None:
    """Append the page groups of each (doc, groups) in *jobs* into one PDF at *out*.
    Each input is closed as soon as it has been copied, since the output may be one
    of the inputs and must not be open when it is replaced.  Returns the page count,
    None if cancelled (nothing written).

    The merged file (owner's choices, 2026-10-12): a top-level bookmark per
    input, named after its file, with the input's own bookmarks under it; the
    first input's properties and XMP; plain page numbers.  Each input's form
    fields, links (named ones as page links), layers and attachments come
    along; a page range drops the bookmarks to the pages it leaves out."""
    n = len(jobs)
    pages = 0
    toc, layers, first = [], [], None
    with atomic_output(out) as tmp, fitz.open() as merged:
        for i, (src, groups) in enumerate(jobs):
            if stop.is_set():
                return None
            if first is None:
                first = (dict(src.metadata or {}), src.get_xml_metadata())
            title, data = _title(src, i), src.tobytes()
            embedded = [(src.embfile_info(k), src.embfile_get(k)) for k in range(src.embfile_count())]
            src.close()
            flat = [p for fr, to in groups for p in range(fr, to + 1)]
            # One copy of the pages in order when no page is taken twice:
            # insert_pdf keeps form fields only when it copies a whole document.
            chunks = [flat] if len(set(flat)) == len(flat) else [
                list(range(fr, to + 1)) for fr, to in groups]
            toc.append([1, title, pages + 1])
            for chunk in chunks:
                with copy_pages(data, chunk) as part:
                    _named_links_to_goto(part)
                    layers.append(_layers_of(part, len(layers)))
                    own = _moved_toc(part.get_toc(simple=False),
                                     {k: k + pages for k in range(len(part))})
                    toc += [[e[0] + 1, *e[1:]] for e in own]
                    merged.insert_pdf(part)
                    pages += len(part)
            for info, content in embedded:
                name, k = info["name"], 1
                while name in merged.embfile_names():
                    k += 1
                    name = f"{info['name']} ({k})"
                merged.embfile_add(name, content, filename=info.get("filename") or name,
                                   desc=info.get("description", ""))
            progress((i + 1) / n)
        _write_layers(merged, layers)
        merged.set_toc(toc)
        meta, xmp = first if first else ({}, "")
        merged.set_metadata({k: meta.get(k, "") for k in ("title", "author", "subject", "keywords")})
        if xmp:
            merged.set_xml_metadata(xmp)
        merged.save(tmp, deflate=True)
    return pages


def reorder(doc, order, extra, out: str) -> None:
    """Write *doc*'s pages in *order* to *out*, each turned by its *extra* degrees;
    the rest of the document (form, bookmarks, labels, layers, properties) is kept."""
    with atomic_output(out) as tmp, copy_pages(doc.tobytes(), list(order)) as nd:
        for ni, pi in enumerate(order):
            ex = extra[pi]
            if ex:
                p = nd[ni]
                p.set_rotation((p.rotation + ex) % 360)
        nd.save(tmp, deflate=True)


def turn_in_place(doc, order, extra) -> None:
    """reorder() on *doc* itself: its pages in *order*, each turned by its
    *extra* degrees, so the edits can be appended to its file."""
    order = list(order)
    if order != list(range(len(doc))):
        rearrange(doc, order)
    for ni, pi in enumerate(order):
        ex = extra[pi]
        if ex:
            p = doc[ni]
            p.set_rotation((p.rotation + ex) % 360)


def bookmark_chapters(toc, total: int, all_levels: bool):
    """The chapters to cut from an outline: [(title, first page index)] in page
    order, ending with ("_END_", total), and how many bookmarks had no page.
    get_toc reports -1 for a bookmark with no page target; levels can also point
    backwards, so chapters are cut in page order.  Empty when nothing points to a page."""
    chosen = [(title, page) for level, title, page, *_ in toc if all_levels or level == 1]
    entries = sorted(((t, p - 1) for t, p in chosen if 1 <= p <= total), key=lambda e: e[1])
    skipped = len(chosen) - len(entries)
    if entries:
        entries.append(("_END_", total))
    return entries, skipped


def split_chapters(doc, entries, out_dir: str, stop, progress, release=lambda path: None) -> int:
    """Write each chapter of *entries* (from bookmark_chapters) to NN_<title>.pdf
    in *out_dir*.  *release(path)* is called before a file is replaced, so a tool
    holding that file open can let it go.  Returns the number written."""
    parts = len(entries) - 1
    targets = [os.path.join(out_dir, f"{i + 1:02d}_"
                            + re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', title)[:50].strip() + ".pdf")
               for i, (title, _) in enumerate(entries[:-1])]
    # Read once: a chapter may replace the source itself, and release() lets
    # the caller close it; the parts are cut from the content as it is now.
    data = doc.tobytes()
    chosen = [(start, entries[i + 1][1] - 1, release, targets[i])
              for i, (_, start) in enumerate(entries[:-1]) if start <= entries[i + 1][1] - 1]
    count = [0]

    def written():
        count[0] += 1
        progress(count[0] / parts)
    _cut_parts(data, 0, chosen, stop, written)
    return count[0]


def toc_level_error(toc) -> str | None:
    """Why *toc* cannot be saved, or None: a bookmark may be at most one level
    deeper than the one above it."""
    prev = 0
    for n, (level, title, *_) in enumerate(toc, 1):
        if level > prev + 1:
            return (f"Bookmark {n} ('{title}') is level {level} but "
                    f"follows level {prev}; a bookmark can be at most "
                    "one level deeper than the one above it.")
        prev = level
    return None


def delete_entry(toc, i: int) -> None:
    """Remove bookmark *i* in place, promoting its children so levels stay contiguous."""
    level = toc.pop(i)[0]
    for e in toc[i:]:
        if e[0] <= level:
            break
        e[0] -= 1
