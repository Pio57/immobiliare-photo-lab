# Calibrazione del fidelity gate

Come sono state scelte le metriche e le soglie, e cosa è stato scartato. Script:
`experiments/scripts/calibrate_gate.py`, output grezzo in `experiments/gate-calibration.txt`.
Ricalibrato il 13/09 sulle 25 foto vere di `dataset/raw/`.

## Il banco di prova

Per ogni foto del dataset:

- **Consentito** (deve passare): l'output delle regole (D1, `auto_params`, fedele per costruzione)
  e una combinazione forte ma lecita (`gamma 0.6, clahe 3, white_balance 1.0, denoise 8`).
- **Vietato** (deve fallire), applicato alla stessa foto: oggetto rimosso (inpainting su ~10%
  dell'area), finestra sostituita (regione più luminosa → gradiente "cielo"), crepa riparata
  (l'originale ha una crepa disegnata di 3 px, il candidato no), smear generativo
  (`cv2.stylization`).

## Cosa è stato scartato, e perché

| metrica (prima versione, progettata su casi sintetici) | cosa è successo sulle foto vere |
|---|---|
| SSIM su grigio **equalizzato** | `equalizeHist` amplifica il rumore delle zone piatte in "struttura": un denoise lecito sembrava un'alterazione |
| **IoU tra edge map Canny** | Schiarire rivela bordi di texture nelle ombre: le soglie fisse contano bordi diversi, non geometria diversa. Con soglie relative consentito ≥ 0,74 ma "oggetto rimosso" ≥ 0,78: non discrimina |
| Correlazione hue **globale** | Correggere una dominante tungsteno sposta tutti gli hue insieme: hue_corr 0,14 su un white balance lecito |
| Rapporto di deviazione standard per blocco | Il denoise (lecito) toglie grana fine; il clipping delle finestre (esposizione lecita) idem. Sovrapposizione totale |

Con quella versione le correzioni lecite venivano bocciate in 28 casi su 33.

## Cosa è rimasto

**Struttura = NCC per blocco (32 px) sulla luminanza sfocata a σ = 1,5.** La correlazione
normalizzata è invariante a trasformazioni affini locali dell'intensità, e gamma, CLAHE e white
balance sono localmente ≈ affini. Regolarizzatore `c3 = 150` al denominatore: due blocchi piatti
(nulla da confrontare) valgono 1 invece di essere indefiniti.

| `structure_local_min` (peggior blocco) | min | p10 | max |
|---|---|---|---|
| consentito (regole + combinazione forte) | 0,82 | 0,88 | 0,99 |
| vietato — oggetto rimosso | −0,52 | −0,36 | **0,44** |
| vietato — finestra sostituita | −0,48 | −0,18 | **0,46** |
| vietato — smear generativo | −0,62 | −0,55 | **0,05** |
| vietato — crepa riparata | −0,32 | 0,18 | 0,96 |

Floor: **0,65** (0,17 sotto il consentito peggiore, 0,19 sopra il vietato peggiore, crepe escluse).

**Hue dopo normalizzazione gray-world di entrambe le immagini**: consentito ≥ 0,91; serve solo per
sostituzioni di colore estese (cielo, finestra). Peso 0,3 nello score globale.

**Score = 0,7·structure(p10) + 0,3·hue_corr ≥ 0,90.** Consentito ≥ 0,96 sul dataset.

Banco completo sulle 25 foto: **consentiti 50/50 passano; vietati 7/100 passano**, e i 7 sono
tutti crepe sottili (oggetti rimossi, finestre sostituite, smear generativo: 0/75).

## Limiti dichiarati

1. **Strutture sottili (< ~3 px)**: una crepa disegnata viene catturata 18 volte su 25. Il test
   `test_moved_thin_walls_are_caught` è marcato `xfail` apposta.
2. **Lisciatura uniforme di texture fine** (muffa, macchie lisciate con risultato uniforme): non
   distinguibile statisticamente da un denoise lecito. Il gate cattura cambiamenti di struttura con
   bordi (oggetti, finestre, arredi, ri-sintesi), non la cancellazione di grana. Mitigazione: i
   moduli non hanno un parametro che possa farlo (denoise ≤ 15); per il generativo è un rischio
   dichiarato.
3. **Super-risoluzione**: inventa texture sotto la scala del blocco, il gate non la vede (score
   ≥ 0,99 sempre). Per questo il modulo Risoluzione parte solo sotto 1000 px ed etichetta l'output
   (`ai_reconstructed`): protegge l'etichetta, non il numero.
4. **Rotazione con verso sbagliato**: il gate confronta con l'originale ruotato uguale, quindi
   non può accorgersene. Il Piano usa il tilt misurato quando esiste; il modello decide solo dove
   il rilevatore non trova linee.
5. Soglie calibrate su 25 foto: da ricalibrare su un campione più ampio prima di qualsiasi uso reale.

## Note di pipeline

- **Ordine**: white balance → livelli → gamma → CLAHE → denoise → rotazione → nitidezza. Il denoise
  va **dopo** la curva tonale: nel buio il rumore è compresso in pochi livelli, denoisare prima
  toglie quasi nulla e la gamma poi lo amplifica. Il rumore previsto si valuta alla pendenza della
  gamma nelle ombre (12% del range), non alla media.
- **Livelli prima della gamma**: un JPEG da telefono non ha un nero vero (~10–25); la gamma lo
  porta a grigio e la foto sembra velata. Nero al percentile 0,5: blocco peggiore 0,81 → 0,90 su
  uno screenshot 540 px.
- **Input compresso** (WhatsApp, Facebook): CLAHE spento (amplifica le chiazze di quantizzazione
  sui muri piatti: mottling 1,93 con clip 1, 1,28 con 0), denoise ≥ 4, nitidezza ≤ 0,2.
- **Rumore cromatico** attaccato 3× più forte di quello di luminanza (`hColor = 3h`): il colore non
  porta dettaglio; la grana di luminanza non si toglie senza lisciare la texture (limite 2).
- **Denoise scalato sulla risoluzione**: la stessa `h` su 960 px mangia la trama (patch che
  coprono più scena); su input piccoli vale il 60%.
