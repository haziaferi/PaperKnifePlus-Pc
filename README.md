# PaperKnife+ PC — v4.0.0

Basato su PaperKnife di potatameister (github/potatameister), autore del progetto originale.

Toolkit PDF locale al 100% per **Windows 10 e 11**. Nessun cloud, nessun account, nessun dato che lascia il tuo computer. Dalla 4.0.0 l'interfaccia usa PySide6 (Qt 6) e QFluentWidgets, nello stile Fluent di Windows 11.

Il manuale completo, in inglese, è **[MANUAL.md](MANUAL.md)**: strumenti, scorciatoie, preferenze, risoluzione dei problemi, compilazione e changelog. Questo file è solo un riassunto in italiano.

## Cosa fa

22 strumenti in cinque gruppi, più le Preferenze (MANUAL.md, sezione 5):

- **Leggi:** anteprima.
- **Organizza:** unisci, dividi (per intervalli di pagine o per segnalibri), ruota e riordina, segnalibri / indice, batch.
- **Migliora:** password, comprimi, filigrana, normalizza pagine, intestazione / piè di pagina, ritaglia, strumenti PDF (ripara, pulisci, appiattisci, togli le pagine bianche).
- **Converti:** altro → PDF (immagini e documenti), estrai immagini, PDF → altro (testo, documenti, immagini).
- **Contenuto:** modifica testo, trova e sostituisci, annota, oscura (redazione), OCR, metadati.
- **Preferenze.**

## Avvio rapido (dal sorgente)

Serve Python 3.10 o superiore.

1. Decomprimi il pacchetto e apri la cartella `PaperKnifePlusPC`.
2. Fai doppio clic su **`setup.bat`**: crea `.venv` e installa le dipendenze di `requirements.txt`, poi quelle di `requirements-fluent.txt` con `--no-deps`.
3. Fai doppio clic su **`run.bat`** per avviare l'app (oppure: `python -m paperknife.qt`).

Installazione manuale e installer NSIS: MANUAL.md, sezioni 3 e 9.

## Test

Dopo `setup.bat`: `.venv\Scripts\python.exe -m pip install -r requirements-dev.txt`, poi (core e Qt in due esecuzioni separate):

```
.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests --ignore=tests/qt
.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/qt
.venv\Scripts\python.exe -m ruff check paperknife tests --select F,E9,B
```

## OCR

L'OCR richiede il programma Tesseract, da installare a parte: <https://github.com/UB-Mannheim/tesseract/wiki>. Nella cartella predefinita (`C:\Program Files\Tesseract-OCR`) l'app lo trova da sola; se lo installi altrove, aggiungi quella cartella al `PATH`. Per l'italiano serve il pacchetto lingua `ita`; il codice lingua si imposta nelle Preferenze (MANUAL.md, sezione 4.3).

## Dati e privacy

Preferenze e file recenti stanno in `C:\Users\<utente>\.paperknifepluspc\`. L'app non usa la rete (MANUAL.md, sezione 10).

## Come arrivano le modifiche (how changes land)

Pull request verso `main` su GitHub; il proprietario le rivede e le unisce. Nessun push diretto su `main`, nessun tag di versione per ora. Ogni push passa prima `publish_check.py` (nessun dato personale).

## Licenza

GNU Affero General Public License v3.0 — vedi [LICENSE](LICENSE) e MANUAL.md, sezione 12.
