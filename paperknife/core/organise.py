"""Merge, split, reorder and the bookmark (outline) work of the ORGANISE tools."""
from __future__ import annotations
import os
import re

import pymupdf as fitz

from ..job_queue import atomic_output


def split_ranges(doc, groups, out_dir: str, base: str, stop, progress) -> int | None:
    """Write each (first, last) page group of *doc* to its own file in *out_dir*,
    named <base>_partNN_pA-B.pdf.  Returns the number written, None if cancelled.
    The caller owns *doc*."""
    parts = len(groups)
    for i, (fr, to) in enumerate(groups):
        if stop.is_set():
            return None
        target = os.path.join(out_dir, f"{base}_part{i + 1:02d}_p{fr + 1}-{to + 1}.pdf")
        with atomic_output(target) as tmp, fitz.open() as nd:
            nd.insert_pdf(doc, from_page=fr, to_page=to)
            nd.save(tmp, deflate=True)
        progress((i + 1) / parts)
    return parts


def merge(jobs, out: str, stop, progress) -> int | None:
    """Append the page groups of each (doc, groups) in *jobs* into one PDF at *out*.
    Each input is closed as soon as it has been copied, since the output may be one
    of the inputs and must not be open when it is replaced.  Returns the page count,
    None if cancelled (nothing written)."""
    n = len(jobs)
    pages = 0
    with atomic_output(out) as tmp, fitz.open() as merged:
        for i, (src, groups) in enumerate(jobs):
            if stop.is_set():
                return None
            for fr, to in groups:
                merged.insert_pdf(src, from_page=fr, to_page=to)
                pages += to - fr + 1
            src.close()
            progress((i + 1) / n)
        merged.save(tmp, deflate=True)
    return pages


def reorder(doc, order, extra, out: str) -> None:
    """Write *doc*'s pages in *order* to *out*, each turned by its *extra* degrees."""
    with atomic_output(out) as tmp, fitz.open() as nd:
        for pi in order:
            nd.insert_pdf(doc, from_page=pi, to_page=pi)
        for ni, pi in enumerate(order):
            ex = extra[pi]
            if ex:
                p = nd[ni]
                p.set_rotation((p.rotation + ex) % 360)
        nd.save(tmp, deflate=True)


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
    if doc.name and any(os.path.exists(t) and os.path.samefile(t, doc.name) for t in targets):
        # A chapter replaces the source itself, and release() lets the caller
        # close it: go on from the content as it is now.
        doc = fitz.open("pdf", doc.tobytes())
    count = 0
    for i, (_, start) in enumerate(entries[:-1]):
        if stop.is_set():
            break
        end = entries[i + 1][1] - 1
        if start > end:
            continue
        target = targets[i]
        release(target)
        with atomic_output(target) as tmp, fitz.open() as nd:
            nd.insert_pdf(doc, from_page=start, to_page=end)
            nd.save(tmp, deflate=True)
        count += 1
        progress((i + 1) / parts)
    return count


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
