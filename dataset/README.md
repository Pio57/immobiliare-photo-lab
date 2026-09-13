# Dataset

Ventiquattro foto vere di case, prese da annunci pubblici, nel formato in cui un agente le
avrebbe in galleria o su WhatsApp (in quel caso il difetto `compressed` è reale, non simulato).
Nessuna foto è generata o alterata.

- `raw/` contiene le foto rinominate `img_NNN.jpg` e `labels.csv` con le colonne
  `image_id, filename, origin, defects, room, source_clean, params`. I difetti sono etichettati a
  mano con il vocabolario della diagnosi (`underexposed`, `backlit`, `color_cast`, `noise`,
  `tilt`, `compressed`, `low_resolution`; `ok` = nessun difetto) e servono a misurare precisione
  e richiamo delle diagnosi. `source_clean` conserva il nome originale del file.
- `processed/` contiene gli output dei workflow (`<id>_D1.jpg`, `_D2`, `_D3`, `_orig`) ed è
  ignorata da git; una copia ridotta per il sito sta in `frontend/public/snapshot/`.

Le foto dello studio cieco sono elencate in `experiments/study-set.txt`.
