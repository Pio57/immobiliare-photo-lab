# immobiliare-photo-lab

Prototipo per il case study *Product Builder, Agentic AI Products* di Immobiliare.it. Il
progetto serve a testare e confrontare diversi workflow di miglioramento automatico delle foto
degli annunci immobiliari, misurando per ciascuno la qualità percepita, il costo, il tempo,
l'affidabilità e il rischio di alterare l'immobile.

Il caso d'uso è la foto di copertina caricata dal telefono da un agente immobiliare. Il
prodotto diagnostica i difetti della foto (buia, controluce, colori falsati, rumore,
inclinazione, compressione, bassa risoluzione), corregge solo quelli con moduli separati e
sottopone ogni correzione a un controllo di fedeltà che impedisce di alterare la realtà
dell'immobile. Tre workflow diversi decidono cosa correggere: uno a regole, uno basato su un
modello vision con verifica del risultato, uno generativo. Il sito permette di provarli su una
foto, di confrontarli in un test cieco e di leggere il tabellone dei risultati.

La nota di accompagnamento completa, con la definizione del problema, i workflow nel dettaglio,
i parametri di confronto e il metodo di misura, è nel PDF allegato alla consegna (sorgente in
`docs/report/`).

## Struttura del progetto

```
cv-service/   servizio Python (FastAPI + OpenCV): pipeline di correzione, controllo di
              fedeltà, dataset, record delle esecuzioni, giudizi, tabellone
n8n/          i quattro workflow n8n (correct, product, choice, batch) e lo script che li genera
frontend/     sito React: Prova (prodotto), Studio (test cieco), Esperimento (tabellone)
prompts/      prompt del modello vision (diagnosi e verifica) e del giudice automatico
dataset/      le foto di prova con le etichette manuali dei difetti
experiments/  record delle esecuzioni, giudizi raccolti, calibrazione del controllo di fedeltà
docs/         contratto dati, calibrazione del controllo di fedeltà, sorgente del PDF
```

## Tecnologie

- **n8n** (self-hosted in Docker) per l'orchestrazione: quattro workflow generati da codice
  (`n8n/build_workflows.py`), con i prompt letti da `prompts/` e gli indirizzi da `.env`.
- **Python 3.12, FastAPI, OpenCV** per il servizio `cv-service`, che esegue tutto ciò che è
  deterministico e gira come container accanto a n8n. Trentacinque test con `pytest`.
- **Docker** sul server (Hostinger VPS), **Vercel** per il sito.
- **React 19, Vite, TypeScript, Tailwind 4** per il sito, che parla soltanto con i webhook n8n.
- **Claude Haiku 4.5** (diagnosi e verifica), **Claude Sonnet 5** (giudice automatico del batch),
  **SDXL + ControlNet** e **Real-ESRGAN** su Replicate (parte generativa).
- Sviluppo con **Claude Code**.

## Dove gira

Il prototipo è pubblicato e funziona senza nulla di acceso sul computer di chi lo ha costruito:

- il sito è su Vercel: https://immobiliare-photo-lab.vercel.app;
- n8n è self-hosted su un VPS Hostinger (Docker), raggiungibile in https;
- cv-service gira sullo stesso VPS come container Docker, sulla rete interna di n8n
  (`deploy/docker-compose.yml`), con `dataset/` ed `experiments/` montati dal repository clonato
  sul server.

Ogni push su `main` ricostruisce il sito da solo. Per aggiornare cv-service sul server basta
`bash /opt/photo-lab/deploy/update.sh` (pull, rebuild, riavvio, controllo di salute). I workflow
n8n si aggiornano rigenerando i JSON e reimportandoli.

## Di cosa c'è bisogno per farlo girare da zero

- Python 3.12, Node 20 o superiore.
- Un'istanza n8n (self-hosted con Docker, come sul VPS, oppure n8n Cloud) e, se cv-service gira in
  locale, ngrok per esporlo.
- Una chiave API Anthropic e un token Replicate. Le chiavi vanno in `.env`, che è ignorato da
  git; `.env.example` elenca i nomi delle variabili e a cosa servono.

## Come si avvia

### Sul server (come è pubblicato)

Sul VPS con il template n8n di Hostinger, da root:

```bash
git clone https://github.com/Pio57/immobiliare-photo-lab.git /opt/photo-lab
cd /opt/photo-lab
docker compose -f deploy/docker-compose.yml up -d --build
docker exec <container n8n> wget -qO- http://cv-service:8000/health   # {"status":"ok"}
```

In `.env` locale si mette `CV_SERVICE_PUBLIC_URL=http://cv-service:8000`, si rigenerano i workflow
e si importano nel n8n del server seguendo `n8n/README.md` (Correggi per primo, il suo
identificativo in `.env` come `N8N_CORRECT_WORKFLOW_ID`, poi prodotto e scelte, credenziali sui
nodi, Publish). Su Vercel si imposta `VITE_N8N_WEBHOOK_URL` con l'URL del webhook del prodotto.

### In locale (sviluppo)

1. Copiare `.env.example` in `.env` e inserire le chiavi.
2. Avviare il servizio:
   ```powershell
   cd cv-service
   py -3.12 -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   pytest
   uvicorn app.main:app --port 8000
   ```
3. Esporlo con `ngrok http 8000` e copiare l'indirizzo pubblico in `.env` come
   `CV_SERVICE_PUBLIC_URL`.
4. Generare i workflow con `cv-service\.venv\Scripts\python.exe n8n\build_workflows.py` e
   importarli in n8n come sopra.
5. Copiare l'indirizzo del webhook del prodotto in `.env` come `VITE_N8N_WEBHOOK_URL`.
6. Avviare il sito: `cd frontend`, `npm install`, `npm run dev`, e aprire `http://localhost:5173`.

A ogni riavvio di ngrok l'indirizzo cambia: aggiornare `.env`, rigenerare i workflow e
reimportarli. Il sito, anche senza backend, mostra Studio ed Esperimento dalla copia statica in
`frontend/public/snapshot/` (rigenerabile con `experiments/scripts/export_snapshot.py`).

## Come si usa

- **Prova**: si carica una foto; dopo circa un minuto arrivano tre versioni in ordine casuale e
  senza nome, si sceglie quella che si userebbe come copertina (o si tiene l'originale) e poi si
  scopre quale workflow ha prodotto cosa, con difetti trovati, moduli eseguiti, costo e tempo.
- **Studio**: test cieco a coppie sulle foto del dataset, per raccogliere giudizi in modo
  sistematico da più valutatori.
- **Esperimento**: il tabellone, ricalcolato a ogni apertura dai record e dai giudizi, con la
  regola di decisione applicata.

Il workflow batch rigenera le tre versioni per tutte le foto del dataset (con giudice
automatico opzionale) ed è quello con cui sono state preparate le foto dello Studio.
