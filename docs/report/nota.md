# immobiliare-photo-lab — nota di accompagnamento

*Case study "Product Builder, Agentic AI Products" — Pio Santosuosso, settembre 2026 · prototipo: https://immobiliare-photo-lab.vercel.app · codice: https://github.com/Pio57/immobiliare-photo-lab*

## 1. Il problema che affronto

Il caso d'uso è l'agente immobiliare che, in giornate piene di visite, fotografa in fretta un nuovo immobile con il cellulare, con la luce che c'è. Quelle foto finiscono direttamente nell'annuncio: quasi mai un fotografo passerà a rifarle.

Il bisogno è pubblicare subito senza che le foto sembrino fatte in fretta, senza pubblicarle così come sono né tornare a rifarle. L'obiettivo del prodotto è migliorare automaticamente le foto nei difetti tipici dello scatto veloce, lasciando all'agente il controllo e senza toccare la realtà dell'immobile.

Il prodotto riceve le foto, riconosce i difetti (foto buia, in controluce, colori falsati, rumore, inclinazione, compressione, bassa risoluzione) e corregge soltanto quelli, un intervento per difetto: una foto solo storta viene solo raddrizzata. Poi mostra all'agente cosa ha fatto; se non serve nulla, lascia l'originale.

Il prodotto non aggiunge, non toglie e non ridisegna nulla: niente cielo nuovo, oggetti rimossi, stanze allargate, crepe o muffa cancellate. Mosso, prospettiva e disordine li segnala, non li corregge. Le foto irrecuperabili le consiglia di rifare.

Il rischio principale da evitare è ingannare il compratore: la funzione non ha modo di far sparire o sistemare un dettaglio della casa, perché agisce solo su luce, colore, nitidezza e inclinazione, e ogni risultato viene confrontato con l'originale e scartato se se ne allontana troppo. Gli altri rischi (una correzione che peggiora la foto, un ritaglio non dichiarato, un agente che non sa cosa è cambiato) li affronto mostrando e spiegando ogni modifica prima della pubblicazione.

## 2. Come strutturo il workflow e i flussi da testare

Ho messo a confronto tre flussi, cioè tre modi diversi di decidere cosa correggere in una foto:

- **D1 — Regole.** Lavora solo sui numeri: luminosità media, dominante di colore, rumore e linee inclinate vengono misurati e un insieme di regole scritte a mano li traduce negli interventi da applicare. Nessun modello di intelligenza artificiale.
- **D2 — Modello esperto con verifica.** Un modello di visione (Claude Haiku) riceve la foto e le stesse misure, indica i difetti e consiglia interventi e valori; dopo la correzione riguarda il risultato accanto all'originale e, se non lo convince, corregge il proprio piano.
- **D3 — Modello generativo.** Un modello generativo (SDXL con ControlNet) riceve la foto e un prompt da fotografo esperto e restituisce direttamente una nuova immagine della stessa stanza, ben esposta, pulita e nitida.

Nei primi due flussi il modello decide e le correzioni le esegue un motore deterministico; nel terzo è il modello a generare la foto.

I flussi vivono in quattro workflow n8n che si richiamano tra loro:

- **Correggi**, il motore delle correzioni: riceve una foto e un piano, applica un intervento alla volta (colore, luce, pulizia, raddrizzamento, nitidezza, risoluzione) e dopo ciascuno esegue il controllo di fedeltà, scartando l'intervento se il risultato si allontana troppo dall'originale.
- **Prodotto**, chiamato dal sito a ogni foto caricata: misura la foto, la manda in parallelo a D1, D2 e D3 (i primi due richiamano Correggi come sotto-workflow, il terzo chiama il modello generativo e applica lo stesso controllo) e salva un record con le tre versioni e tutto ciò che è successo.
- **Scelte**, che raccoglie le preferenze dei valutatori e restituisce i risultati aggregati al sito; **Batch**, che ripete il lavoro di Prodotto su un intero insieme di foto per preparare la sperimentazione.

![Il workflow Prodotto in n8n: la foto entra, passa in parallelo dalle tre corsie D1, D2 e D3, e ne esce un record con le tre versioni.](../../n8n/screenshots/product.png)

Gli output nascono quindi tutti dallo stesso punto: per ogni foto tre versioni, ciascuna con un registro dei difetti trovati, degli interventi applicati o scartati, della fedeltà, del costo e del tempo.

I risultati li raccolgo con una sperimentazione cieca: un pool di agenti immobiliari come beta tester che, nella vista Studio, vedono l'originale e due versioni affiancate senza sapere quale flusso le ha prodotte e scelgono quella che userebbero come copertina, foto dopo foto. La stessa scelta avviene nella vista Prova sulla propria foto appena caricata. Ogni giudizio viene registrato e la vista Esperimento li aggrega in un tabellone. Con quali parametri leggere quei dati per scegliere il metodo migliore lo descrivo nel punto seguente.

## 3. Quali parametri uso per valutare che un metodo è migliore dell'altro

Dei parametri suggeriti ne ho scelti tre come base della decisione: la qualità percepita, il costo per immagine e il rischio di alterare l'immobile. Tempo e affidabilità li misuro comunque, ma li considero secondari qui: la correzione si fa una volta sola per annuncio e può girare in background, pubblicando le foto quando sono pronte. Un minuto in più o un tentativo ripetuto non cambiano il valore del prodotto; una foto che non piace, che costa troppo o che altera la casa sì.

- **Qualità percepita.** Pesa di più, perché decide se l'agente usa la foto corretta. La misuro con il test cieco: per ogni flusso, la quota di confronti vinti sul totale in cui è comparso, con un intervallo di confidenza che dice quanto fidarsi del numero. Nel prototipo, con un solo valutatore su ventiquattro foto, regole e modello esperto sono stati preferiti in circa sei confronti su dieci, il generativo in uno su quattro.
- **Costo per immagine.** Ogni annuncio ha tra le dieci e le venti foto, quindi il costo di una correzione va moltiplicato subito. Le regole non fanno chiamate: costo praticamente zero. Il modello esperto fa due chiamate a Claude Haiku per foto (circa 1.500 token in ingresso con l'immagine e 250 in uscita, a 1 e 5 dollari per milione di token): circa 0,004 dollari a foto. Il generativo paga circa quattro secondi di GPU su Replicate: 0,003 dollari (250 immagini generate nel prototipo sono costate 0,81 dollari). Per un annuncio da venti foto: zero, 0,08 e 0,06 dollari; su diecimila annunci al giorno, nulla contro 800 e 600 dollari al giorno. A qualità percepita equivalente, decide questo parametro.
- **Rischio di alterare l'immobile.** Non è un punteggio ma un requisito di ammissione: conto quante correzioni vengono scartate dal controllo di fedeltà e quanto si allontana dall'originale il caso peggiore. L'ho capito sul campo: anche migliorando il prompt, il generativo altera sempre qualche dettaglio della stanza, e nel prototipo più della metà delle sue versioni non ha superato il controllo. Un flusso così non è candidabile, per quanto piacciano le sue foto.

La regola di decisione è fissata prima di guardare i dati: primo, un flusso è ammesso solo se meno del dieci per cento delle sue correzioni viene scartata dal controllo di fedeltà; secondo, tra gli ammessi conta la preferenza nel test cieco, con almeno trenta giudizi; terzo, se due flussi non sono distinguibili con quel campione, si sceglie il più economico. Il tabellone della vista Esperimento applica già questa regola; con i beta tester darà la risposta.

## 4. Come misuro gli elementi qualitativi

Distinguo due fasi: una misurazione controllata sul prototipo, per scegliere il workflow prima di investire traffico reale, e una in produzione, dove i giudizi diventano azioni degli utenti.

**Fase 1 — sul prototipo, test cieco.** Un panel di dieci-quindici persone, idealmente con qualche agente immobiliare, usa il sito senza sapere quale workflow ha prodotto cosa: con ventiquattro foto e dieci tester, duecentoquaranta giudizi per misura. Ogni elemento qualitativo diventa una domanda precisa e un numero confrontabile tra D1, D2 e D3:

- *Realismo.* Originale accanto a una versione elaborata, una alla volta: "vedi elementi finti, generati o strutturalmente diversi rispetto all'originale?" (sì/no). Il conteggio è il tasso di alterazione; vince chi sta più vicino a zero. È la misura che tutela il vincolo del brief.
- *Qualità.* La sola versione elaborata, senza originale: voto da 1 a 5 su luce, nitidezza e colori. La media dei voti (mean opinion score) dà un punteggio per workflow; sopra 3,5 la foto è percepita come buona.
- *Foto migliore.* Originale in alto e le tre versioni affiancate, anonime: "se fossi l'agente, quale useresti?". Il conteggio è la quota di vittorie per workflow: l'equilibrio tra difetto corretto e naturalezza conservata.
- *Output efficace.* Giudico io con le etichette manuali dei difetti: per ogni foto, il workflow ha risolto i difetti presenti senza introdurne di nuovi? Il conteggio è la quota di foto pubblicabili senza altro ritocco.

**Fase 2 — in produzione, test A/B.** Se il prototipo indica un workflow, lo si prova sul mercato: annunci con foto elaborate contro annunci con foto originali, a parità di zona e fascia di prezzo, con giudizi impliciti. Il realismo si misura al contrario, con le segnalazioni "l'immobile non corrisponde alle foto" e il feedback degli agenti dopo le visite: un picco è un fallimento. Qualità e foto migliore si misurano con il tasso di click dai risultati all'annuncio quando la copertina è elaborata, con il tempo in galleria e con i contatti ricevuti. L'efficacia si misura sull'agente: tempo risparmiato tra scatto e pubblicazione e quante volte scarta la versione proposta per ricaricare l'originale.

Il prototipo copre già la prima fase con il test a coppie della vista Studio e con il controllo automatico di fedeltà; la domanda sul realismo e il voto di qualità sono l'estensione naturale dello stesso sito.

## Prototipo, strumenti e limiti

Il sito (React, su Vercel) parla con quattro workflow n8n self-hosted su un server; correzioni, controllo di fedeltà e dati stanno in un servizio Python con OpenCV sullo stesso server. I modelli sono Claude Haiku per diagnosi e verifica, SDXL con ControlNet e Real-ESRGAN su Replicate per la parte generativa. Ho lavorato con Claude Code. È tutto reale: chiamate ai modelli, le ventiquattro foto (case vere, da annunci pubblici), il controllo di fedeltà e la sua calibrazione, i giudizi, i costi e i tempi. È simulato il numero dei valutatori, finora uno: la sperimentazione con gli agenti è la proposta, non il risultato. Limiti principali: il controllo di fedeltà non vede strutture sotto i tre pixel né la super-risoluzione, che per questo viene etichettata; il rilevatore di inclinazione rinuncia quando le linee stanno da un lato solo; il campione di foto è piccolo e poco difettoso. Prossimi passi: la sperimentazione cieca con un gruppo di agenti; un modulo per sfocare volti e targhe; il test sulla piattaforma, foto corrette contro originali, misurato sui contatti.
