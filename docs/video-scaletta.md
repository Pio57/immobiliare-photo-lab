# Scaletta del video demo (senza audio, 90 secondi circa)

Registrazione dello schermo, browser a tutto schermo su https://immobiliare-photo-lab.vercel.app,
1080p, nessun audio. Solo le tre viste del sito: Prova, Studio, Esperimento. Senza voce contano i
movimenti: lenti, uno alla volta, con una pausa di un paio di secondi su ogni cosa che si vuole far
leggere.

## Prima di registrare

1. Un giro completo di Prova con la foto che userai: scalda il modello generativo, così in
   registrazione le tre versioni arrivano in 30–40 secondi.
2. Una seconda scheda già aperta su `?result=<image_id>` di quella prova: se l'attesa è lunga, tagli
   il video lì e riprendi da questa scheda.
3. Studio con iniziali nuove (es. `DEMO`), per partire dalla foto 1.

## Sequenza

**0:00 – 0:08 · Prova, pagina iniziale.** Fermo due secondi sul titolo e sul testo di presentazione,
poi trascini la foto nella zona di caricamento.

**0:08 – 0:35 · Attesa.** Lascia il messaggio "Tre correzioni in corso" con il contatore dei
secondi per 5–8 secondi, poi taglia (in montaggio) fino all'arrivo delle tre versioni.

**0:35 – 1:00 · Le tre versioni.** Muovi lentamente la maniglia prima/dopo sulla prima colonna
(Regole), poi sulla terza (Generativo). Scorri giù piano: fermati due secondi sulla scheda della
seconda colonna (Modello con verifica), dove si leggono i difetti trovati, la spiegazione del
modello e i moduli con i valori. Torna su, clic su "Ingrandisci il confronto" di una versione,
maniglia avanti e indietro, chiudi.

**1:00 – 1:25 · Studio.** Clic su "Studio". Fermo due secondi sull'introduzione, inserisci le
iniziali, "Inizia". Rispondi a una foto intera, con calma: realismo (clic sul bottone, non tasto,
così si vede), qualità (voto), realismo e qualità per le altre due versioni, poi "foto migliore"
con l'originale sopra e le tre versioni sotto. La barra di avanzamento in alto si muove.

**1:25 – 1:40 · Esperimento.** Clic su "Esperimento". Fermo tre secondi sulla card in alto (giudizi
raccolti, regola di decisione), scorri alla tabella delle quattro misure, fermo tre secondi. Fine.

## Note

- Niente Studio oltre una foto: il punto è la meccanica delle tre domande.
- Le risposte date durante la registrazione finiscono nel tabellone: dopo il video, sul server,
  `rm /opt/photo-lab/experiments/judgments.csv` per ripartire da zero.
- Formato: MP4, 1080p, 25–30 fps. Se supera i 100 MB, comprimi o carica su YouTube come "non in
  elenco" e metti il link nel README.
