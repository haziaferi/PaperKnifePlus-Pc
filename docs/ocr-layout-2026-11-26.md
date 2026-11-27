# OCR page layout measured (2026-11-26, SPEC R40)

Generated pages (`tools/ocr_corpus.py`) plus pages of PDFs shipped with installed programs,
simulated scans (200/300 ppi, clean/worn), read at 200 DPI grey. The scan simulation, scorer
and optimizer run stayed in the work folder beside the repo; this file is their output.
Score = mean of found, 100-junk, 100-CER, rows (weight 1) and speed vs Auto (0.5).

Exhaustive check over 1120 rules (train pages): best mode 3 at 96.53; Auto at 96.53.

Optimizer's rule: mode 3 at 96.53 (train).

## All layout pages, train (seed 1)

| rule | score | found % | junk % | CER % | rows % | s/page |
|---|---|---|---|---|---|---|
| mode 3 | **96.5** | 94.6 | 2.6 | 2.6 | 95.1 | 1.18 |
| mode 4 | **93.0** | 94.9 | 2.6 | 2.5 | 78.9 | 1.11 |
| mode 6 | **88.6** | 87.9 | 7.0 | 8.9 | 76.5 | 1.12 |
| mode 11 | **95.0** | 95.7 | 2.0 | 1.4 | 85.2 | 1.07 |
| mode 3 | **96.5** | 94.6 | 2.6 | 2.6 | 95.1 | 1.18 |

## All layout pages, holdout (seed 2)

| rule | score | found % | junk % | CER % | rows % | s/page |
|---|---|---|---|---|---|---|
| mode 3 | **96.3** | 93.8 | 3.1 | 3.0 | 95.6 | 1.16 |
| mode 4 | **93.0** | 94.5 | 2.9 | 2.7 | 79.5 | 1.10 |
| mode 6 | **88.7** | 87.1 | 6.0 | 9.6 | 77.8 | 1.11 |
| mode 11 | **94.2** | 94.9 | 4.0 | 1.7 | 85.0 | 1.06 |
| mode 3 | **96.3** | 93.8 | 3.1 | 3.0 | 95.6 | 1.16 |

## Per kind, both seeds

| kind | mode 3 | mode 4 | mode 6 | mode 11 | mode 3 |
|---|---|---|---|---|---|
| columns | 99.8 (f 99, r 100) | 77.7 (f 99, r 1) | 77.7 (f 99, r 1) | 99.7 (f 99, r 100) | 99.8 (f 99, r 100) |
| mixed | 99.5 (f 99, r 100) | 99.5 (f 99, r 100) | 88.5 (f 79, r 96) | 96.4 (f 99, r 86) | 99.5 (f 99, r 100) |
| pricelist | 77.3 (f 61, r 97) | 79.4 (f 64, r 98) | 61.1 (f 36, r 92) | 88.6 (f 95, r 56) | 77.3 (f 61, r 97) |
| real | 97.1 (f 94, r 99) | 96.9 (f 93, r 99) | 96.4 (f 94, r 98) | 96.4 (f 93, r 100) | 97.1 (f 94, r 99) |
| receipt | 88.4 (f 84, r 74) | 92.2 (f 85, r 87) | 96.3 (f 90, r 99) | 85.2 (f 83, r 61) | 88.4 (f 84, r 74) |
| receipt-a4 | 89.7 (f 75, r 98) | 89.7 (f 75, r 98) | 96.0 (f 92, r 98) | 89.3 (f 90, r 66) | 89.7 (f 75, r 98) |
| table-plain | 91.7 (f 96, r 68) | 99.5 (f 98, r 100) | 99.4 (f 98, r 100) | 82.1 (f 94, r 27) | 91.7 (f 96, r 68) |
| table-ruled | 98.1 (f 98, r 100) | 97.6 (f 97, r 100) | 28.9 (f 3, r 58) | 80.6 (f 95, r 24) | 98.1 (f 98, r 100) |
| table-zebra | 87.5 (f 93, r 53) | 99.6 (f 99, r 100) | 99.6 (f 99, r 100) | 82.3 (f 95, r 27) | 87.5 (f 93, r 53) |
| text | 99.8 (f 99, r 100) | 99.6 (f 99, r 100) | 99.6 (f 99, r 100) | 98.9 (f 99, r 100) | 99.8 (f 99, r 100) |

## Handwriting warning: mean word confidence in mode 3

| pages | n | min | median | max | found % median |
|---|---|---|---|---|---|
| faint | 8 | 95.5 | 95.9 | 96.1 | 100 |
| hand-inkfree | 8 | 89.7 | 90.4 | 91.6 | 94 |
| hand-segoeprint | 8 | 92.6 | 94.5 | 95.6 | 99 |
| hand-segoescript | 8 | 74.5 | 80.4 | 86.9 | 64 |
| print (all layout kinds) | 216 | 34.2 | 94.3 | 96.1 | 97 |

Cut-off that best separates readings with under 50% of words found: mean confidence < 0 (247/248 pages classed right; 1 failed readings).

## Warning cut-off by balanced accuracy (`cutoff.py`)

```text
pages: 248 (train 140, holdout 108)
poor<70%  cut-off conf<87  train: warned+poor 18, warned+fine 8, missed 2, quiet+fine 112, balanced 0.92
poor<70%  cut-off conf<87  holdout: warned+poor 9, warned+fine 11, missed 6, quiet+fine 82, balanced 0.74
poor<80%  cut-off conf<89  train: warned+poor 23, warned+fine 13, missed 1, quiet+fine 103, balanced 0.92
poor<80%  cut-off conf<89  holdout: warned+poor 17, warned+fine 6, missed 8, quiet+fine 77, balanced 0.80
poor<90%  cut-off conf<90  train: warned+poor 35, warned+fine 9, missed 8, quiet+fine 88, balanced 0.86
poor<90%  cut-off conf<90  holdout: warned+poor 22, warned+fine 5, missed 16, quiet+fine 65, balanced 0.75

lowest-confidence pages (conf, words right %, kind, file, ppi, var):
   34.2   61.6  pricelist        pricelist-eng-1.pdf 200 clean
   34.5   70.0  real             real-Blackmagic_RAW_Speed-p1-2.pdf 300 worn
   38.1   70.0  real             real-Blackmagic_RAW_Speed-p1-2.pdf 200 worn
   38.7   56.2  pricelist        pricelist-eng-2.pdf 300 clean
   39.0   46.6  pricelist        pricelist-eng-1.pdf 300 clean
   40.8   63.0  pricelist        pricelist-eng-2.pdf 200 clean
   46.8   53.4  pricelist        pricelist-ita-2.pdf 200 clean
   50.1   64.4  pricelist        pricelist-ita-1.pdf 300 clean
   52.7   63.0  pricelist        pricelist-ita-1.pdf 200 clean
   53.4   65.8  pricelist        pricelist-ita-2.pdf 300 clean
   58.1   63.0  pricelist        pricelist-ita-1.pdf 200 worn
   61.5   61.6  pricelist        pricelist-eng-2.pdf 200 worn
   62.9   60.3  pricelist        pricelist-eng-1.pdf 200 worn
   64.3   72.5  real             real-Blackmagic_RAW_Speed-p1-2.pdf 300 clean
   65.5   61.6  pricelist        pricelist-ita-1.pdf 300 worn
   65.9   61.6  pricelist        pricelist-eng-1.pdf 300 worn

poorest readings (words right %, conf, kind, file, ppi, var):
   46.6   39.0  pricelist        pricelist-eng-1.pdf 300 clean
   53.4   46.8  pricelist        pricelist-ita-2.pdf 200 clean
   56.2   38.7  pricelist        pricelist-eng-2.pdf 300 clean
   57.6   78.5  hand-segoescript hand-segoescript-eng-1.pdf 300 clean
   58.7   77.6  hand-segoescript hand-segoescript-eng-1.pdf 200 worn
   59.8   74.5  hand-segoescript hand-segoescript-eng-1.pdf 200 clean
   60.3   62.9  pricelist        pricelist-eng-1.pdf 200 worn
   61.6   65.5  pricelist        pricelist-ita-1.pdf 300 worn
   61.6   76.1  pricelist        pricelist-ita-2.pdf 200 worn
   61.6   34.2  pricelist        pricelist-eng-1.pdf 200 clean
   61.6   65.9  pricelist        pricelist-eng-1.pdf 300 worn
   61.6   61.5  pricelist        pricelist-eng-2.pdf 200 worn
   61.6   69.4  pricelist        pricelist-eng-2.pdf 300 worn
   63.0   52.7  pricelist        pricelist-ita-1.pdf 200 clean
   63.0   58.1  pricelist        pricelist-ita-1.pdf 200 worn
   63.0   40.8  pricelist        pricelist-eng-2.pdf 200 clean
```
