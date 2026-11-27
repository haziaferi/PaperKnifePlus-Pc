"""Program-generated test pages for OCR page layout (SPEC R40, 2026-11-26).

Every page is drawn with PyMuPDF from text written here, in fonts shipped with Windows,
so its own text layer is the ground truth. Nothing is read from anyone's own files.

Types: ruled / plain / zebra tables, a dotted price list, a till receipt (on its own narrow
page and on an A4 flatbed scan), plain text and text with a table (controls), plus a
handwriting stand-in (handwriting-style fonts, NOT real handwriting) and faint print, for
the R40 warning cut-off. The measurement is in docs/ocr-layout-2026-11-26.md.

  python tools/ocr_corpus.py [out folder]   -> build/ocr-corpus/*.pdf + manifest.json
"""
import json
import random
import sys
from pathlib import Path

import pymupdf as fitz

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "build" / "ocr-corpus"
OUT.mkdir(parents=True, exist_ok=True)
FONTS = Path(r"C:\Windows\Fonts")
F = {k: str(FONTS / v) for k, v in {
    "arial": "arial.ttf", "arialbd": "arialbd.ttf", "times": "times.ttf", "consolas": "consola.ttf",
    "courier": "cour.ttf", "segoe": "segoeui.ttf", "inkfree": "Inkfree.ttf",
    "segoeprint": "segoepr.ttf", "segoescript": "segoesc.ttf"}.items()}

ITEMS = {
    "ita": ["Pane integrale", "Latte intero", "Caffè macinato", "Mozzarella di bufala", "Pomodori pelati",
            "Olio extravergine", "Pasta di semola", "Acqua naturale", "Biscotti al burro",
            "Parmigiano grattugiato", "Prosciutto cotto", "Mele golden", "Detersivo piatti",
            "Carta igienica", "Yogurt bianco", "Riso carnaroli", "Uova fresche", "Zucchero di canna",
            "Farina tipo 00", "Tonno sott'olio", "Passata di pomodoro", "Banane", "Insalata mista",
            "Succo d'arancia", "Lenticchie secche", "Ceci in scatola", "Burro", "Sale fino"],
    "eng": ["Wholemeal bread", "Whole milk", "Ground coffee", "Buffalo mozzarella", "Peeled tomatoes",
            "Extra virgin olive oil", "Durum wheat pasta", "Still water", "Butter biscuits",
            "Grated parmesan", "Cooked ham", "Golden apples", "Washing-up liquid", "Toilet paper",
            "Plain yogurt", "Arborio rice", "Free range eggs", "Cane sugar", "Plain flour",
            "Tuna in oil", "Tomato passata", "Bananas", "Mixed salad", "Orange juice",
            "Dried lentils", "Tinned chickpeas", "Butter", "Table salt"],
}
HEAD = {"ita": ["Codice", "Descrizione", "Quantità", "Prezzo unit.", "Importo"],
        "eng": ["Code", "Description", "Qty", "Unit price", "Amount"]}
TITLE = {"ita": ["Fattura n. 2026/0417", "Riepilogo ordini di ottobre", "Listino prezzi in vigore",
                 "Inventario del magazzino"],
         "eng": ["Invoice no. 2026/0417", "October order summary", "Current price list",
                 "Warehouse inventory"]}
SENT = {
    "ita": ["La riunione del consiglio si terrà martedì prossimo presso la sede centrale.",
            "Si prega di inviare la documentazione richiesta entro la fine del mese.",
            "Il servizio clienti risponde dal lunedì al venerdì, dalle nove alle diciotto.",
            "Le spese di spedizione sono gratuite per gli ordini superiori a cinquanta euro.",
            "In caso di ritardo nella consegna, il cliente sarà avvisato per posta elettronica.",
            "Il presente documento sostituisce la versione precedente del regolamento interno.",
            "Gli importi indicati si intendono comprensivi di imposta sul valore aggiunto.",
            "Per qualsiasi chiarimento è possibile rivolgersi all'ufficio amministrativo.",
            "La garanzia copre i difetti di fabbricazione per un periodo di ventiquattro mesi.",
            "Il pagamento può essere effettuato tramite bonifico bancario o carta di credito.",
            "Le richieste di reso devono essere presentate entro quattordici giorni dall'acquisto.",
            "Il magazzino resterà chiuso per inventario nella prima settimana di gennaio."],
    "eng": ["The board meeting will be held next Tuesday at the head office.",
            "Please send the requested documents by the end of the month.",
            "Customer service is open from Monday to Friday, nine to six.",
            "Shipping is free on orders over fifty euros.",
            "If delivery is late, the customer will be told by email.",
            "This document replaces the previous version of the internal rules.",
            "The amounts shown include value added tax.",
            "For any question, please contact the accounts office.",
            "The warranty covers manufacturing defects for twenty-four months.",
            "Payment can be made by bank transfer or by credit card.",
            "Returns must be requested within fourteen days of purchase.",
            "The warehouse will be closed for stocktaking in the first week of January."],
}


REAL = [(r"C:\Program Files\PDF24\qpdf\share\doc\qpdf\qpdf-manual.pdf", range(10, 16)),
        (r"C:\Program Files\gs\gs10.06.0\doc\GS9_Color_Management.pdf", range(1, 7)),
        (r"C:\Program Files (x86)\Blackmagic Design\Blackmagic RAW\Blackmagic RAW Speed Test"
         r"\Blackmagic RAW Speed Test.pdf", range(1, 7))]


def money(v, lang):
    s = f"{v:,.2f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".") if lang == "ita" else s


def text(page, x, y, s, font="arial", size=10, color=(0, 0, 0), right=False, center=False):
    f = fitz.Font(fontfile=F[font])
    w = f.text_length(s, size)
    if right:
        x -= w
    elif center:
        x -= w / 2
    page.insert_text((x, y), s, fontsize=size, fontname=font, fontfile=F[font], color=color)
    return w


def rows_of(rng, lang, n):
    out = []
    for _ in range(n):
        item = rng.choice(ITEMS[lang])
        q = rng.randint(1, 24)
        p = rng.choice([0.49, 0.89, 1.25, 2.40, 3.99, 7.50, 12.80, 24.90, 129.00, 1249.00])
        out.append([f"{rng.randint(10000, 99999)}", item, str(q), money(p, lang), money(p * q, lang)])
    return out


def table(page, rng, lang, top, n, style, font="arial", size=9.5):
    cols = [50, 115, 330, 400, 480, 545]  # left edges; numbers right-aligned at the next edge - 6
    rh = size * 1.9
    data = [HEAD[lang]] + rows_of(rng, lang, n)
    for r, row in enumerate(data):
        y0 = top + r * rh
        if style == "zebra" and (r == 0 or r % 2 == 0):
            page.draw_rect(fitz.Rect(cols[0], y0, cols[-1], y0 + rh), color=None,
                           fill=(0.78, 0.78, 0.78) if r == 0 else (0.92, 0.92, 0.92))
        for c, cell in enumerate(row):
            fnt = "arialbd" if r == 0 and font == "arial" else font
            yb = y0 + rh * 0.68
            if c >= 2:
                text(page, cols[c + 1] - 6, yb, cell, fnt, size, right=True)
            else:
                text(page, cols[c] + 5, yb, cell, fnt, size)
    if style == "ruled":
        for r in range(len(data) + 1):
            page.draw_line((cols[0], top + r * rh), (cols[-1], top + r * rh), width=0.6)
        for x in cols:
            page.draw_line((x, top), (x, top + len(data) * rh), width=0.6)
    return top + len(data) * rh


def paragraphs(page, rng, lang, top, bottom, font="times", size=11, color=(0, 0, 0)):
    f = fitz.Font(fontfile=F[font])
    y, line = top, ""
    words = " ".join(rng.sample(SENT[lang], len(SENT[lang]))).split()
    for w in words + [""]:
        trial = (line + " " + w).strip()
        if w and f.text_length(trial, size) < 495:
            line = trial
            continue
        if y > bottom:
            break
        text(page, 50, y, line, font, size, color)
        y += size * 1.45
        line = w
    return y


def receipt(page, rng, lang, x0, y0, width, font, size):
    lh = size * 1.35
    cx = x0 + width / 2
    shop = "SUPERMERCATO DA ROSA" if lang == "ita" else "ROSA'S GROCERY"
    lines = [("c", shop), ("c", "Via Roma 12 - 40121 Bologna" if lang == "ita" else "12 High Street, Leeds"),
             ("c", "P.IVA 01234567890" if lang == "ita" else "VAT 123 4567 89"), ("", "")]
    total = 0.0
    for _ in range(rng.randint(9, 14)):
        item = rng.choice(ITEMS[lang]).upper()[:20]
        p = rng.choice([0.49, 0.89, 1.25, 1.99, 2.40, 3.99, 4.50, 7.50])
        q = rng.choice([1, 1, 1, 2, 3])
        if q > 1:
            lines.append(("lr", f"{q} x {money(p, lang)}", ""))
        lines.append(("lr", item, money(p * q, lang)))
        total += p * q
    lines += [("", ""), ("lr", "TOTALE EURO" if lang == "ita" else "TOTAL EUR", money(total, lang)),
              ("lr", "CONTANTE" if lang == "ita" else "CASH", money(total + 5, lang)),
              ("lr", "RESTO" if lang == "ita" else "CHANGE", money(5, lang)), ("", ""),
              ("c", "26-11-2026  18:42  CASSA 3" if lang == "ita" else "26/11/2026  18:42  TILL 3"),
              ("c", "GRAZIE E ARRIVEDERCI" if lang == "ita" else "THANK YOU, PLEASE COME AGAIN")]
    y = y0
    for ln in lines:
        y += lh
        if ln[0] == "c" and ln[1]:
            text(page, cx, y, ln[1], font, size, center=True)
        elif ln[0] == "lr":
            text(page, x0 + 6, y, ln[1], font, size)
            if ln[2]:
                text(page, x0 + width - 6, y, ln[2], font, size, right=True)
    return y + lh


def make(kind, lang, seed):
    rng = random.Random(f"{kind}-{lang}-{seed}")
    doc = fitz.open()
    if kind == "receipt":
        page = doc.new_page(width=227, height=520)
        receipt(page, rng, lang, 0, 10, 227, rng.choice(["consolas", "courier"]), 8.5)
    elif kind == "receipt-a4":
        page = doc.new_page(width=595, height=842)
        page.draw_rect(page.rect, color=None, fill=(0.72, 0.72, 0.72))
        x0 = rng.randint(150, 250)
        page.draw_rect(fitz.Rect(x0, 60, x0 + 200, 560), color=None, fill=(1, 1, 1))
        receipt(page, rng, lang, x0, 70, 200, rng.choice(["consolas", "courier"]), 7.5)
    else:
        page = doc.new_page(width=595, height=842)
        title = rng.choice(TITLE[lang])
        if kind in ("table-ruled", "table-plain", "table-zebra"):
            text(page, 50, 70, title, "arialbd", 15)
            style = kind.split("-")[1]
            table(page, rng, lang, 95, rng.randint(16, 24), style,
                  "times" if style == "plain" else "arial", 10 if style == "plain" else 9.5)
        elif kind == "pricelist":
            text(page, 50, 70, title, "arialbd", 15)
            f = fitz.Font(fontfile=F["segoe"])
            y = 100
            for item in rng.sample(ITEMS[lang], 22):
                price = money(rng.choice([0.89, 1.49, 2.30, 3.75, 5.90, 9.99, 14.50]), lang)
                wl = text(page, 50, y, item, "segoe", 11)
                wr = f.text_length(price, 11)
                dots = "." * int((545 - 50 - wl - wr - 12) / f.text_length(".", 11))
                text(page, 50 + wl + 6, y, dots, "segoe", 11)
                text(page, 545, y, price, "segoe", 11, right=True)
                y += 26
        elif kind == "text":
            text(page, 50, 70, title, "arialbd", 15)
            paragraphs(page, rng, lang, 100, 760)
        elif kind == "columns":
            text(page, 50, 70, title, "arialbd", 15)
            f = fitz.Font(fontfile=F["times"])
            for x0 in (50, 310):
                y, line = 100, ""
                words = " ".join(rng.sample(SENT[lang], len(SENT[lang])) * 2).split()
                for w in words + [""]:
                    trial = (line + " " + w).strip()
                    if w and f.text_length(trial, 10) < 235:
                        line = trial
                        continue
                    if y > 760:
                        break
                    text(page, x0, y, line, "times", 10)
                    y += 14.5
                    line = w
        elif kind == "mixed":
            text(page, 50, 70, title, "arialbd", 15)
            y = paragraphs(page, rng, lang, 100, 230)
            y = table(page, rng, lang, y + 10, 10, "ruled")
            paragraphs(page, rng, lang, y + 25, 760)
        elif kind.startswith("hand-"):
            font = kind.split("-")[1]
            y = 90
            for s in rng.sample(SENT[lang], 9):
                f = fitz.Font(fontfile=F[font])
                line = ""
                for w in s.split() + [""]:
                    if w and f.text_length((line + " " + w).strip(), 17) < 480:
                        line = (line + " " + w).strip()
                        continue
                    text(page, 60, y, line, font, 17, color=(0.05, 0.1, 0.45))
                    y += 34
                    line = w
        elif kind == "faint":
            text(page, 50, 70, title, "arial", 15, color=(0.8, 0.8, 0.8))
            paragraphs(page, rng, lang, 100, 760, color=(0.82, 0.82, 0.82))
    name = f"{kind}-{lang}-{seed}.pdf"
    doc.save(OUT / name)
    return name


def main():
    manifest = []
    layout = ["table-ruled", "table-plain", "table-zebra", "pricelist", "receipt", "receipt-a4",
              "text", "mixed", "columns"]
    for kind in layout:
        for lang in ("ita", "eng"):
            for seed in (1, 2):
                manifest.append({"file": make(kind, lang, seed), "kind": kind, "lang": lang, "set": "layout"})
    # Real-world control: pages of PDFs shipped with installed programs (as phase12 used),
    # each copied to a one-page PDF; odd pages train (seed 1), even pages holdout (seed 2).
    for path, pages in REAL:
        if not Path(path).exists():
            print("skipped (program not installed):", path)
            continue
        with fitz.open(path) as src:
            for pg in pages:
                stem = Path(path).stem.replace(" ", "_")[:20]
                name = f"real-{stem}-p{pg}-{1 + pg % 2}.pdf"
                with fitz.open() as d:
                    d.insert_pdf(src, from_page=pg, to_page=pg)
                    d.save(OUT / name)
                manifest.append({"file": name, "kind": "real", "lang": "eng", "set": "layout"})
    for kind in ("hand-inkfree", "hand-segoeprint", "hand-segoescript", "faint"):
        for lang in ("ita", "eng"):
            manifest.append({"file": make(kind, lang, 1), "kind": kind, "lang": lang, "set": "warning"})
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(len(manifest), "pages ->", OUT)


if __name__ == "__main__":
    main()
