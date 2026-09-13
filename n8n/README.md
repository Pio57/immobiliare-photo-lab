# n8n

Quattro workflow, generati da `build_workflows.py` (i prompt vengono da `prompts/*.md`,
gli URL da `.env`): non modificare i JSON a mano, rigenerare.

```powershell
cv-service\.venv\Scripts\python.exe n8n\build_workflows.py
```

| file | cosa fa | trigger |
|---|---|---|
| `workflow-correct.json` | **Correggi**: il router. Sei corsie in sequenza (Risoluzione, Colore, Luce, Pulizia, Raddrizza, Nitidezza); ognuna gira solo se il piano la chiede, applica il suo parametro sopra quelli già accettati ripartendo dall'originale, passa dal gate; bocciata → un tentativo conservativo → saltata. `Finale` applica gli accettati. | sub-workflow |
| `workflow-product.json` | **Prodotto**: upload → `/prepare` → *risponde subito* con l'`image_id` → tre famiglie (D1 regole, D2 Haiku + verifica, D3 generativo) → record con ordine cieco → `/runs`. | webhook `photo-lab-product` |
| `workflow-choice.json` | **Scelte**: registra una risposta dello Studio (`photo-lab-choice`), serve il tabellone (`photo-lab-summary`), il risultato di un'esecuzione (`photo-lab-result`) e la lista dello studio (`photo-lab-study`). | 4 webhook |
| `workflow-batch.json` | **Batch sul dataset**: le stesse corsie, una foto alla volta (`Config.ids` = lo studio). Prepara le versioni che lo Studio mostra. | manuale |

## Import

1. Importa `workflow-correct.json`, salva, copia l'id dall'URL in `.env` come
   `N8N_CORRECT_WORKFLOW_ID`, rigenera, **pubblica**.
2. Importa gli altri tre. Credenziali da selezionare a mano dopo l'import:
   - Anthropic (`anthropicApi`): `D2: modello`, `D2: verifica modello`.
   - Replicate (Header Auth, `Authorization: Bearer <token>`): `D3: Replicate`, `D3: stato`,
     e in Correggi `Risoluzione: Real-ESRGAN`.
3. Pubblica prodotto e scelte. URL del webhook prodotto in `.env` come `VITE_N8N_WEBHOOK_URL`
   (gli altri tre webhook sono derivati dallo stesso prefisso).

Ogni riavvio di ngrok cambia `CV_SERVICE_PUBLIC_URL`: aggiornare `.env`, rigenerare,
re-importare i workflow che chiamano cv-service (tutti e quattro).

## Perché così

- **Asincrono**: n8n Cloud chiude un webhook dopo ~100 s; il generativo a freddo ne vuole 120.
  Il prodotto risponde subito e il sito interroga `photo-lab-result` ogni 5 s.
- **Un solo Correggi** per prodotto e batch: quello che si misura è la diagnosi, non la
  correzione.
- **Polling di Replicate** sul canvas (`in corso? → attendi → stato → conta`): il cold start è
  un costo reale della famiglia generativa, e si vede.
- **Guardie deterministiche nel Piano** (tilt misurato, verso della gamma, CLAHE su input
  compresso): registrate in `plan_fixes`, contate nel tabellone.
