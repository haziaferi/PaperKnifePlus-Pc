# PaperKnife+ PC — v3.2.2

Toolkit PDF locale al 100% per **Windows 10 e 11**. Nessun cloud, nessun account, nessun dato che lascia il tuo computer.

Il manuale completo, in inglese, è **[MANUAL.md](MANUAL.md)**: strumenti, scorciatoie, preferenze, risoluzione dei problemi, compilazione e changelog. Questo file è solo un riassunto in italiano.

## Cosa fa

26 strumenti in sei sezioni (MANUAL.md, sezione 5):

- **Leggi:** anteprima.
- **Organizza:** unisci, dividi, ruota e riordina, dividi per segnalibri, segnalibri / indice, batch.
- **Migliora:** password, comprimi, filigrana, normalizza pagine, intestazione / piè di pagina, ritaglia, strumenti PDF.
- **Converti:** immagini → PDF, PDF → immagini, estrai immagini, PDF → documento / testo, documento / testo → PDF.
- **Contenuto:** modifica testo, trova e sostituisci, annota, oscura (redazione), OCR, metadati.
- **Preferenze.**

## Avvio rapido (dal sorgente)

Serve Python 3.10 o superiore.

1. Decomprimi il pacchetto e apri la cartella `PaperKnifePlusPC`.
2. Fai doppio clic su **`setup.bat`**: crea `.venv` e installa le dipendenze di `requirements.txt`.
3. Fai doppio clic su **`run.bat`** per avviare l'app.

Installazione manuale e installer NSIS: MANUAL.md, sezioni 3 e 9.

## OCR

L'OCR richiede il programma Tesseract, da installare a parte: <https://github.com/UB-Mannheim/tesseract/wiki>. Nella cartella predefinita (`C:\Program Files\Tesseract-OCR`) l'app lo trova da sola; se lo installi altrove, aggiungi quella cartella al `PATH`. Per l'italiano serve il pacchetto lingua `ita`; il codice lingua si imposta nelle Preferenze (MANUAL.md, sezione 4.3).

## Dati e privacy

Preferenze e file recenti stanno in `C:\Users\<utente>\.paperknifepluspc\`. L'app non usa la rete (MANUAL.md, sezione 10).

## Licenza

GNU Affero General Public License v3.0 — vedi [LICENSE](LICENSE) e MANUAL.md, sezione 12.
