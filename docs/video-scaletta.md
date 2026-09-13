# Scaletta del video demo (2 min 30 s circa)

Registrazione dello schermo con voce, browser a tutto schermo su https://immobiliare-photo-lab.vercel.app, 1080p.
Win+G (Xbox Game Bar) o OBS. Niente musica. Parlato in prima persona, tono da chi racconta una cosa fatta.

## Prima di registrare

1. Fai un giro completo di Prova con la foto che userai nel video: scalda il modello generativo su
   Replicate, così durante la registrazione risponde in 30–40 secondi e non in due minuti.
2. Tieni pronta una seconda scheda con `?result=<image_id>` di quella prova (l'id compare nella barra
   dei tempi in fondo alla pagina, o in `experiments/runs/` sul server): se in registrazione l'attesa
   è lunga, tagli e riprendi dalla scheda già pronta.
3. Una scheda su n8n con il canvas di Prodotto aperto e uno zoom che mostri tutte e tre le corsie.
4. Studio: apri `?view=studio`, inserisci iniziali nuove (es. `DEMO`), così parti dalla foto 1.

## Sequenza

**0:00 – 0:20 · Il problema** (schermata: home di Prova, ferma)

> Un agente immobiliare fotografa una casa col telefono, in fretta, con la luce che c'è, e quelle
> foto vanno nell'annuncio così come sono. Ho costruito un prototipo che riconosce i difetti tipici
> dello scatto veloce e corregge solo quelli, senza toccare la realtà dell'immobile. E, soprattutto,
> un modo per confrontare tre metodi diversi e decidere quale usare.

**0:20 – 0:55 · Prova, il prodotto** (trascina la foto, attesa, poi le tre colonne)

> Carico una foto. Tre flussi la correggono in parallelo: uno a regole, senza modelli; uno con un
> modello di visione che diagnostica, corregge e poi verifica il risultato; uno generativo, che
> ridisegna la stanza. Tutti passano dallo stesso controllo di fedeltà, che blocca ogni correzione
> troppo diversa dall'originale.

(mentre arrivano le versioni, muovi la maniglia prima/dopo su una colonna, poi scendi sulla scheda)

> Per ogni versione vedo cosa il metodo ha visto, quali moduli ha eseguito e con quali valori, e
> il tempo. Il generativo non dichiara scelte: le sue differenze sono misurate dopo, sui pixel.

**0:55 – 1:25 · Come è fatto** (scheda n8n, canvas di Prodotto; poi 5 secondi su Correggi)

> Dietro c'è n8n: il webhook risponde subito con un identificativo, poi le tre corsie lavorano in
> parallelo. Le prime due costruiscono un piano e lo passano a un sotto-workflow, Correggi, che
> applica un modulo per difetto (colore, luce, pulizia, raddrizzamento, nitidezza) e dopo ciascuno
> esegue il controllo di fedeltà. Se un modulo viene fermato, un tentativo più prudente, poi si
> salta. Le correzioni e il controllo sono in un servizio Python con OpenCV; le chiamate ai modelli
> partono da n8n, nessuna chiave nel browser.

**1:25 – 2:00 · Studio, il test cieco** (rispondi a una foto intera: 7 domande, veloce)

> Per decidere quale metodo è migliore non mi fido del mio occhio. Nello Studio un valutatore
> risponde a tre domande per ogni foto, senza sapere quale metodo ha prodotto cosa: vedi elementi
> finti o diversi dall'originale? Che voto dai a luce, nitidezza e colori? Quale useresti
> nell'annuncio? Tastiera, dieci minuti per ventiquattro foto.

**2:00 – 2:25 · Esperimento, la decisione** (tabellone)

> Le risposte finiscono qui: tasso di alterazione, voto medio, quota di vittorie con intervallo di
> confidenza, tasso di pubblicabilità. La regola è fissata prima di guardare i dati: fuori chi
> altera l'immobile o supera il dieci per cento di correzioni fermate; tra gli ammessi vince la
> foto migliore, con almeno trenta giudizi; a parità decide il costo. Il tabellone è vuoto perché
> la sperimentazione con il panel è il passo successivo: il prototipo è pronto a raccoglierla.

**2:25 – 2:35 · Chiusura** (README su GitHub)

> Codice, workflow, nota e documento tecnico sono nel repository. Grazie.

## Note

- Se il generativo tarda in registrazione, taglia: passa alla scheda con `?result=` e riprendi il
  parlato da "Per ogni versione vedo…".
- Nello Studio non commentare le foto: il punto è la meccanica delle tre domande, non il giudizio.
- Nel tabellone non dire quale metodo vincerebbe.
- Link al video nel README (`Prototipo online`, `Nota`, `Architettura`, `Video demo`).
