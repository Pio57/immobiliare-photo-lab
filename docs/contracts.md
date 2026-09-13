# Contratto dati

Pochi oggetti attraversano tutto il sistema (cv-service ↔ n8n ↔ sito). Fonti di verità:
`cv-service/app/schemas.py` (Pydantic) e `frontend/src/types.ts` (TypeScript); questo
file spiega cosa significano.

## `EnhanceParams` — lo spazio delle correzioni consentite

È la editorial policy scritta come tipo: un'operazione che non ha un parametro qui non
può essere chiesta da nessuno, nemmeno dal modello. Valori fuori range vengono
clampati, mai rifiutati.

| campo | range | modulo | cosa fa |
|---|---|---|---|
| `white_balance` | 0–1 | Colore | forza della correzione gray-world |
| `gamma` | 0.5–2 | Luce | esposizione (<1 schiarisce); preceduta da livelli automatici (nero al p0,5) |
| `clahe_clip` | 0–4 | Luce | contrasto locale; 0 su input compresso |
| `denoise` | 0–15 | Pulizia | non-local means, scalato sulla risoluzione |
| `rotate_deg` | −15–15 | Raddrizza | rotazione + ritaglio al rettangolo pieno; `crop_pct` riportato (36% a 15°) |
| `sharpen` | 0–1 | Nitidezza | maschera di contrasto; amplifica bordi esistenti |
| `recommendation` | apply · mild · keep_original | — | `mild` dimezza tutto, `keep_original` non tocca nulla |

Il modello parla in `exposure` (stop, +1 = più chiara); il Piano converte in `gamma = 2^(−exposure/2)`.
Non esistono parametri per cielo, oggetti, arredi, geometria delle stanze.

## `FidelityReport` — il gate

| campo | significato |
|---|---|
| `structure` | p10 della NCC per blocco (32 px) su luminanza sfocata: la struttura è la stessa? |
| `structure_local_min` | il blocco peggiore: un oggetto rimosso, una zona ridisegnata |
| `hue_corr` | correlazione dell'istogramma di tonalità dopo normalizzazione gray-world |
| `score` | 0,7·structure + 0,3·hue_corr |
| `threshold`, `local_floor` | 0,90 e 0,65 (`docs/gate-calibration.md`) |
| `passed` | `score ≥ threshold` **e** `local_min ≥ local_floor`; se falso il modulo viene saltato (o la versione generativa scartata) |

Il confronto per i moduli è contro l'originale **allineato** (ruotato con la stessa
omografia); per il generativo è diretto. Limiti dichiarati: strutture sottili (< 3 px),
lisciatura uniforme ≈ denoise, super-risoluzione (invisibile al gate: protegge l'etichetta).

## `Step` — cosa ha fatto un modulo

`{ module, needed, applied, passed, retried, fidelity, params }`. Un modulo "non
necessario" non gira. Bocciato dal gate: un tentativo con i valori conservativi, poi
saltato. Per il generativo le sei righe sono **misurate dopo** sui pixel
(`measured_changes`: luminanza, cast, rumore, nitidezza, tilt, scala), non decise prima.

## `VariantResult` — una famiglia su una foto (`experiments/runs/<id>.json`)

```json
{
  "image_id": "img_013", "variant": "D2", "label": "Haiku + verifica", "source": "model",
  "defects": ["underexposed", "tilt"], "advice": ["clutter"], "reason": "…", "recommendation": "apply",
  "plan": { "gamma": 0.7, "rotate_deg": -6, "…": 0 }, "plan_fixes": ["rotate_deg: measured value used"],
  "steps": [ { "module": "Luce", "needed": true, "applied": true, "passed": true, "fidelity": {…}, "params": {…} }, … ],
  "params": { …accettati }, "fidelity": {…}, "crop_pct": 12.4, "ai_reconstructed": false,
  "cost_usd": 0.0041, "latency_ms": 21000, "iterations": 1, "review_verdict": "ok",
  "status": "accepted" | "rejected_fidelity" | "unchanged" | "error" | "timeout", "error": null
}
```

Il record di un'esecuzione: `{ image_id, source: live|batch, order: [...], variants: [...],
input_warnings, heuristic_defects, latency_ms, judge: [...] }`. `order` fissa l'ordine cieco
delle schede; `judge` è vuoto nel prodotto (lo riempie solo il batch con giudice acceso).

## Giudizi e tabellone

- `POST /choices` (webhook `photo-lab-choice`) `{ image_id, task, variant, answer, shown, order, tester }` →
  `experiments/judgments.csv`, una riga per risposta. `task` = `realism` (variant = la versione
  mostrata accanto all'originale, answer `yes` = alterata | `no`), `quality` (answer `1`..`5`),
  `best` (variant = la scelta, `""` = tiene l'originale; shown = le versioni sullo schermo).
  La vista Prova non registra giudizi.
- `GET /summary` → per famiglia le quattro misure della fase 1: `alteration_rate` (+ IC di Wilson),
  `mos` (media dei voti 1-5), `choice_share` (+ IC), `effective_rate` (tasso di pubblicabilità: voto ≥ 4
  e nessuna alterazione dallo stesso valutatore sulla stessa versione); poi `cost_mean_usd`, `latency_p50/p95_ms`, `error_rate`, `fixes_rate`, `gate_rejected_rate`,
  `unchanged_rate`, `fidelity_min`, `diagnosis {precision, recall, f1}` sulle foto etichettate;
  più `verdict` con la regola di decisione applicata.
- `GET /runs/{id}/cards` → le schede cieche di un'esecuzione (immagini incluse).
- `GET /study` → id dello studio, quali sono pronti, tester finora.
