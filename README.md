# PaperKnife+ PC — v3.2.1

Toolkit PDF locale al 100%. Nessun cloud, nessun account, nessun dato che lascia il tuo computer.

---

## Requisiti di sistema

| | Minimo |
|---|---|
| **Sistema operativo** | Windows 10/11 · macOS 12+ · Linux (con Tk) |
| **Python** | 3.10 o superiore |
| **Spazio su disco** | ~150 MB (dipendenze incluse) |

---

## Installazione rapida su Windows

1. Scarica e decomprimi l'archivio `PaperKnifePlusPC_v3_2_1.zip`.
2. Apri la cartella `PaperKnifePlus`.
3. Fai doppio clic su **`setup.bat`**.
   Lo script installa automaticamente tutte le dipendenze core e opzionali.
4. Al termine, fai doppio clic su **`run.bat`** per avviare l'applicazione.

> Se Windows mostra un avviso "App sconosciuta", clicca **Ulteriori informazioni → Esegui comunque**.

---

## Installazione manuale (Windows · macOS · Linux)

### 1. Verifica Python

```bash
python --version   # deve essere 3.10+
```

Se non è installato: <https://python.org/downloads>

### 2. (Consigliato) Crea un ambiente virtuale

```bash
# Nella cartella PaperKnifePlus
python -m venv .venv

# Attiva l'ambiente:
# Windows:
.venv\Scripts\activate
# macOS / Linux:
source .venv/bin/activate
```

### 3. Installa le dipendenze

**Dipendenze core** (obbligatorie):

```bash
pip install "PyMuPDF>=1.23.0,<2.0.0" "customtkinter>=5.2.0" "Pillow>=10.0.0"
```

**Dipendenze opzionali** (abilitano funzionalità aggiuntive):

```bash
# Drag & drop di file sull'interfaccia
pip install tkinterdnd2

# Conversione DOCX / PPTX / XLSX / RTF ↔ PDF
pip install python-docx python-pptx openpyxl striprtf

# OCR (riconosce testo da PDF scansionati)
pip install pytesseract
# Richiede anche il binario Tesseract separatamente — vedi sotto.
```

In alternativa, installa tutto in un solo comando:

```bash
pip install -r requirements.txt
```

### 4. Avvia l'applicazione

```bash
python -m paperknife
```

Oppure, se hai usato `pip install -e .` nella cartella del progetto:

```bash
paperknife
```

---

## OCR — installazione di Tesseract

La funzione OCR richiede il programma Tesseract, che va installato separatamente dal pacchetto Python.

**Windows:** scarica l'installer da <https://github.com/UB-Mannheim/tesseract/wiki> e aggiungi la cartella di installazione al `PATH` di sistema (es. `C:\Program Files\Tesseract-OCR`).

**macOS:**
```bash
brew install tesseract
```

**Linux (Debian/Ubuntu):**
```bash
sudo apt install tesseract-ocr
```

Per il riconoscimento di lingue diverse dall'inglese, installa il pacchetto dati corrispondente (es. `tesseract-ocr-ita` per l'italiano) e imposta il codice lingua nelle Preferenze dell'app.

---

## Struttura dei file

```
PaperKnifePlus/
├── paperknife/          # Codice sorgente
│   ├── tools/           # Un file per ogni strumento PDF
│   ├── app.py           # Finestra principale
│   ├── prefs.py         # Preferenze utente (~/.paperknifepluspc/prefs.json)
│   └── recent.py        # File recenti (~/.paperknifepluspc/recent.json)
├── requirements.txt     # Dipendenze pip
├── setup.py             # Installazione come pacchetto
├── setup.bat            # Setup automatico (Windows)
└── run.bat              # Avvio rapido (Windows)
```

I dati utente (preferenze e file recenti) vengono salvati in:

- **Windows:** `C:\Users\<utente>\.paperknifepluspc\`
- **macOS / Linux:** `~/.paperknifepluspc/`

---

## Risoluzione dei problemi

**L'app non si avvia e mostra `ImportError: cannot import name 'PasswordTool'`**
Aggiorna all'archivio v3.2.1 — questo bug era presente nella v3.2.0 ed è stato corretto.

**La finestra appare ma i pulsanti della barra laterale non fanno nulla**
Verifica che `customtkinter` sia alla versione 5.2.0 o superiore: `pip show customtkinter`.

**L'OCR produce solo errori**
Controlla che Tesseract sia installato e raggiungibile: `tesseract --version`. Se il comando non viene trovato, il percorso di installazione non è nel `PATH`.

**Errore `ModuleNotFoundError: No module named 'docx'` durante la conversione**
Installa le dipendenze opzionali per i documenti: `pip install python-docx python-pptx openpyxl striprtf`.

**Su macOS: la finestra è vuota o molto piccola**
Assicurati di usare Python installato da python.org o Homebrew, non il Python di sistema (2.x).

---

## Changelog v3.2.1

- **Corretto:** l'app non si avviava a causa di un import errato di `PasswordTool` (`tools/__init__.py`).
- **Corretto:** gli errori interni degli strumenti venivano inghiottiti silenziosamente senza mostrare messaggi all'utente.
- **Corretto:** il pulsante Annulla in "Modifica Testo" non ripristinava effettivamente il testo precedente.
- **Corretto:** la modifica di paragrafi multiriga causava l'uscita del testo fuori dalla pagina; ora usa word-wrap preciso contro la larghezza del blocco originale.
- **Corretto:** caratteri speciali (`<`, `&`, ecc.) nei testi OCR e convertiti corrompevano silenziosamente l'output.
- **Corretto:** l'export XML di PDF multipagina produceva file non validi (prologhi XML duplicati).
- **Corretto:** tre impostazioni nelle Preferenze (cartella di output, file recenti massimi, livello di compressione) venivano salvate ma ignorate dall'app.
- **Corretto:** aprire un PDF corrotto o non valido in 8 strumenti causava un crash senza messaggio di errore.
- **Corretto:** lo strumento Unisci riapreva inutilmente tutti i file sorgente una seconda volta dopo il merge.
- **Corretto:** la conversione di PPTX, XLSX, PNG e JPEG in PDF non mostrava il dialogo di completamento.
- **Corretto:** le voci in `recent.json` con schema non valido causavano un crash all'avvio.
- **Corretto (stile):** numeri di versione allineati a 3.2.1 in `setup.py` e `setup.bat` (erano rimasti a 3.0.0).
