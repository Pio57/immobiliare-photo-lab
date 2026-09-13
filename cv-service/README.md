# cv-service

Il pezzo che n8n non può fare: pipeline OpenCV deterministica e metriche di fedeltà.

| endpoint        | chi lo usa | cosa fa                                                            |
|-----------------|------------|--------------------------------------------------------------------|
| `POST /analyze` | flow B     | statistiche misurate (luminanza, cast, rumore, tilt) come hint     |
| `POST /enhance` | flow A     | parametri euristici → pipeline → fidelity gate                     |
| `POST /apply`   | flow B     | parametri dal modello vision → stessa pipeline → stesso gate       |
| `POST /fidelity`| flow C     | gate standalone su un output prodotto altrove                      |

Immagini in base64 dentro JSON. Docs interattive su `/docs` una volta avviato.

```powershell
py -3.12 -m venv .venv; .venv\Scripts\activate
pip install -r requirements.txt
pytest
uvicorn app.main:app --reload --port 8000
```

Le soglie del gate (`fidelity_threshold`, `fidelity_local_floor`) sono in
`app/config.py` e vanno ricalibrate sul dataset reale: il flusso A è fedele per
costruzione, la sua distribuzione fissa il livello sotto cui non si scende.
