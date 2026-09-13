# immobiliare-photo-lab

Case study "Product Builder, Agentic AI Products" @ Immobiliare.it. La foto di copertina di un
annuncio, corretta con un click senza alterare l'immobile, e un modo per confrontare tre
famiglie di correzione (regole, modello vision con verifica, generativo). Il lavoro viene
giudicato su **come si misura**, non su quanto è bella la foto dopo. README = avvio;
`docs/report/nota.md` = nota completa (sorgente del PDF).

## Vincoli non negoziabili
- Editorial policy: consentito esposizione, white balance, denoise, raddrizzamento, nitidezza,
  super-risoluzione etichettata sotto 1000 px. Vietato: sostituzione cielo, rimozione/aggiunta
  oggetti, ampliamento stanze, qualsiasi intervento su crepe/muffa.
- Controllo di fedeltà deterministico e **bloccante**, per modulo: non è l'AI a valutare se stessa.
- Cecità nello Studio: mai nomi, mai il verdetto del gate. Il gate vive nella regola di decisione
  (tabellone), non nel giudizio del tester. La Prova è trasparente: tre metodi affiancati con nome
  e scheda, nessuna scelta, nessun verdetto del gate in evidenza (solo il punteggio di fedeltà).
- Le chiavi non entrano mai nel repo né nel browser (le chiamate ai modelli partono da n8n).

## Architettura
```
frontend/     Vite + React 19 + TS + Tailwind 4, palette immobiliare.it (blu #0074c1, grigi
              freddi). Prova (prodotto: tre colonne con scheda, resta montata), Studio (test cieco: per foto realismo
              sì/no, qualità 1-5, foto migliore), Esperimento (tabellone). Fallback su
              public/snapshot/ se il backend non risponde.
cv-service/   FastAPI + OpenCV. pipeline.py (WB → livelli+gamma → CLAHE → denoise → rotazione →
              sharpen), metrics.py (gate), api/routes.py (/prepare /apply /gate_remote),
              api/dataset.py (/dataset /runs /processed), api/experiment.py (/choices /summary
              /runs/{id}/cards /study).
n8n/          build_workflows.py genera: workflow-correct (Correggi, sub-workflow, 6 corsie con
              gate per modulo e retry), workflow-product (webhook, risponde subito, D1/D2/D3 →
              Correggi → record), workflow-choice (4 webhook), workflow-batch (dataset, stesse
              corsie, nessun giudice). I JSON non si editano a mano.
prompts/      diagnosis.md (System, User, Review).
dataset/raw/  24 foto vere + labels.csv (vocabolario: underexposed overexposed backlit color_cast noise tilt rotated
              compressed low_resolution; ok). processed/ ignorata da git.
experiments/  runs/<id>.json (versionati), judgments.csv, study-set.txt, gate-calibration.txt,
              scripts/calibrate_gate.py, scripts/export_snapshot.py.
docs/         contracts.md, gate-calibration.md, report/nota.md.
```

### Decisioni di design (perché)
- **Una sola implementazione delle correzioni** (Correggi) per prodotto e batch: quello che si
  confronta è chi diagnostica, non come si corregge.
- **Guardie deterministiche sul piano del modello** (tilt misurato vince; verso della gamma;
  CLAHE spento e nitidezza ≤0,2 su input compresso), registrate in `plan_fixes` e contate.
- **Il modello parla in stop** (`exposure`), il Piano converte in gamma: i modelli invertono
  gamma, nessuno inverte "più chiara".
- **Asincrono**: n8n Cloud chiude i webhook a ~100 s; il prodotto risponde subito con
  `image_id`, il sito interroga `photo-lab-result`.
- **Tilt**: verticali; orizzontali solo come fallback con consenso stretto; linee da un lato
  solo → solo tilt ≤3° (prospettiva ≠ rotazione; il gate non vede un verso sbagliato).
- **Gate calibrato sui dati** (`docs/gate-calibration.md`): 50/50 lecite passano, 7/100 vietate
  passano (crepe sottili). Non reintrodurre SSIM/Canny senza rifare il banco.
- **Studio = fase 1 della nota**: per ogni foto, per ogni versione (ordine casuale) realismo
  (S/N) e qualità (1-5), poi foto migliore (1/2/3, 0 = originale). Una riga per risposta in
  `judgments.csv` (`task` realism|quality|best). La Prova non registra giudizi.
  Il tabellone calcola tasso di alterazione, MOS, quota di vittorie (Wilson 95%), output efficace
  (etichette manuali; `compressed` è condizione dell'input, non difetto). La regola esclude
  errori >10%, gate >10%, alterazione >10% (con ≥10 risposte); decide `best` con ≥30 giudizi.
- Il webhook n8n resta `photo-lab-choice` → `POST /choices` (nome storico): niente re-import.

## Comandi (Windows / PowerShell)
```powershell
cd cv-service; py -3.12 -m venv .venv; .venv\Scripts\activate
pip install -r requirements.txt; pytest; uvicorn app.main:app --port 8000   # NIENTE --reload
cd frontend; npm install; npm run dev
ngrok http 8000            # via %LOCALAPPDATA%\Microsoft\WinGet\Packages\Ngrok.Ngrok_*\ngrok.exe
cv-service\.venv\Scripts\python.exe n8n\build_workflows.py      # dopo ogni cambio di .env/prompt
cv-service\.venv\Scripts\python.exe experiments\scripts\export_snapshot.py   # dopo ogni batch/studio
```
Ogni riavvio di ngrok cambia l'URL: `.env` → rigenera → re-importa tutti e quattro i workflow.
Re-import: aprire il workflow, Ctrl+A, Canc, Import from file, ricollegare le credenziali, Publish.

## Convenzioni
- Codice e commenti in inglese; README, docs e testi del sito in italiano, in prosa (niente
  elenchi telegrafici nei documenti consegnati).
- Python 3.12 (`py -3.12`); il `python` di default è 3.8 e non va usato.
- Commit solo su richiesta esplicita dell'utente.

## Stato attuale (aggiornare ogni sera)
- 2026-09-14: consegna pronta. Online su Vercel + VPS Hostinger (n8n self-hosted, cv-service Docker,
  repo in /opt/photo-lab, `bash deploy/update.sh`; judgments.csv vive sul server, ignorato da git).
  Nota PDF 2 pagine, docs/architettura.md + PDF 14 pagine, README con canvas e screenshot, video
  demo (allegato all'email, non nel repo). Studio = fase 1 (realismo, qualità, foto migliore),
  output efficace = tasso di pubblicabilità dal pool; sperimentazione non eseguita per scelta.
  Ultime correzioni dal test sul campo: limite rotazione 15° (oltre 17° tilt + reshoot), seconda
  opinione LSD sull'inclinazione, orientamento 90/180/270 via domanda a quattro vie (D2), retry
  NSFW/429 su Replicate, giudice AI rimosso dal Batch, img_013 fuori dallo studio.
  Regola: ogni modifica a build_workflows.py che tocca MODULES o Correggi richiede il re-import
  di Correggi (stesso id) oltre a Prodotto e Batch; docs e PDF vanno rigenerati con
  `build.py docs/architettura.md docs/immobiliare-photo-lab-architettura.pdf --wide`.
