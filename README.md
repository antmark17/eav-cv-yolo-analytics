# EAV AI 0.8.0

Applicazione per analizzare video di stazione e gestire segnalazioni di affollamento, attraversamento delle linee, bagagli incustoditi e animali non sorvegliati.

Comprende una pipeline Python con YOLO e ByteTrack, un’API locale e un frontend con vista passeggero, vista operatore e Console AI per la calibrazione.

Il progetto nasce come **Project Work EAV svolto durante il Cisco Digital Transformation Lab (DTLab)**. Questa repository raccoglie un dimostratore locale e il relativo materiale tecnico: non va considerata, senza ulteriore hardening, una soluzione di videosorveglianza pronta per un deployment di produzione.

## Requisiti

- Python 3.10 o superiore.
- Node.js 22.13 o superiore e npm.
- Una sorgente video (file locale oppure sorgente live supportata) e pesi compatibili con Ultralytics, ad esempio `yolo12n.pt`.
- Per usare `cuda:0`, una GPU NVIDIA, driver aggiornati e una build CUDA di PyTorch.

Le dipendenze Python dichiarano esplicitamente **PyTorch 2.14.0** e **Torchvision 0.29.0**. La precisione di inferenza segue la sintassi corrente di Ultralytics: `model.quantize: 16` abilita **FP16** sull’hardware compatibile, mentre `model.quantize: null` mantiene FP32. In questo contesto `quantize: 16` indica la precisione FP16 di inferenza, non una quantizzazione INT16.

Video e pesi presenti nella copia locale sono esclusi da Git. Dopo un clone, procurare separatamente il video e il modello e indicarne i percorsi nella configurazione.

## Installazione su Windows

Aprire PowerShell nella radice del progetto:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
```

### Installazione consigliata con GPU NVIDIA

Installare prima la build CUDA di PyTorch. L’esempio seguente usa CUDA 13.0:

```powershell
.\.venv\Scripts\python.exe -m pip install torch==2.14.0 torchvision==0.29.0 --index-url https://download.pytorch.org/whl/cu130
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
npm --prefix frontend ci
```

PyTorch 2.14.0 è disponibile anche con altre build CUDA: scegliere quella compatibile con il driver NVIDIA installato. Il numero di versione in `pyproject.toml` vincola PyTorch, ma la variante CUDA viene selezionata tramite il repository usato da `pip`.

Verifica rapida della GPU:

```powershell
.\.venv\Scripts\python.exe -c "import torch; print('torch', torch.__version__); print('cuda runtime', torch.version.cuda); print('cuda available', torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU')"
```

Se `cuda available` è `False`, non usare `model.device: cuda:0`: correggere driver/installazione PyTorch oppure impostare `model.device: auto`/`cpu`.

### Installazione CPU

```powershell
.\.venv\Scripts\python.exe -m pip install torch==2.14.0 torchvision==0.29.0 --index-url https://download.pytorch.org/whl/cpu
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
npm --prefix frontend ci
```

Se `configs/video.local.yaml` non esiste, crearlo dal modello:

```powershell
Copy-Item configs/video.example.yaml configs/video.local.yaml
```

Nel file locale impostare:

- `source.uri`: percorso del video.
- `model.weights`: percorso dei pesi.
- `model.device`: `cuda:0` per la prima GPU NVIDIA, `auto` per selezione automatica, oppure `cpu`.
- `model.quantize`: `16` per FP16 oppure `null` per FP32.
- Geometrie e soglie in `analytics`: da calibrare sull’inquadratura utilizzata.

La copia locale fornita usa `videos/prova4.mp4`; il modello generico usa `videos/clip.mp4` come percorso da sostituire. Non sovrascrivere una configurazione locale già calibrata.

## Avvio

Aprire tre terminali nella radice del progetto.

**1. API**

Impostare un codice operatore personale nel terminale e avviare il servizio:

```powershell
$env:EAV_OPERATOR_TOKEN = "INSERISCI-UN-CODICE-PERSONALE"
.\.venv\Scripts\python.exe video_event_server.py --config configs/video.local.yaml
```

Il servizio ascolta su `http://127.0.0.1:8765`. Se non si imposta il codice, il valore dimostrativo è `operator-demo`.

**2. Frontend**

```powershell
npm --prefix frontend run dev
```

Aprire l’indirizzo mostrato nel terminale. Per cambiare l’indirizzo dell’API, copiare `frontend/.env.local.example` in `frontend/.env.local`, modificare `NEXT_PUBLIC_EAV_EVENT_API` e riavviare il frontend.

**3. Analisi video**

```powershell
.\.venv\Scripts\python.exe run_video.py --video videos/prova4.mp4 --config configs/video.local.yaml --station "Stazione EAV" --realtime-pacing
```

Sostituire il percorso del video se necessario: deve coincidere con `source.uri`, usato dalla Console AI per l’anteprima. Il frontend non avvia automaticamente l’analisi.

## Utilizzo

- **Passeggero:** accesso pubblico ai dati aggregati di affollamento.
- **Operatore:** gestione degli eventi e consultazione delle immagini. Il codice viene richiesto al primo accesso della scheda e dopo 15 minuti dal login. Uscire dalla vista mantiene la sessione fino alla scadenza.
- **Console AI:** calibrazione delle aree, delle linee e dei parametri di rilevamento. L’uscita riporta alla vista operatore.

Quando un evento viene preso in carico o risolto, cambia categoria senza spostare l’operatore dalla sezione selezionata.

Per configurare un’area: scegliere il tipo, aggiungere i punti sull’immagine o tramite coordinate, premere **Applica geometria**, quindi **Salva configurazione**. La cancellazione delle geometrie richiede conferma. Le modifiche salvate si applicano al successivo riavvio dell’analisi.

## Struttura

| Percorso | Contenuto |
|---|---|
| `crowd_monitor/` | Acquisizione, analisi, configurazione e gestione degli eventi |
| `frontend/` | Interfaccia web e configurazione di sviluppo/build |
| `configs/` | Modelli YAML e configurazioni locali |
| `tests/` | Test Python, fixture e verifica browser |
| `docs/` | Architettura e istruzioni di verifica |
| `outputs/` | Risultati generati durante l’esecuzione, esclusi da Git |

La calibrazione di aree e linee e l’anteprima sono disponibili nella Console AI. `run_realtime.py` resta l’avvio per sorgenti live; `validate_team_b_json.py` verifica i file di esportazione.

## Sorgenti video supportate

La stessa pipeline di detection, tracking e analytics può lavorare sia offline sia in tempo reale. Il video locale usato nella demo è quindi una sorgente di test, non un vincolo architetturale.

- `stream`: file video, webcam/indice camera e stream compatibili con OpenCV/FFmpeg, inclusi RTSP, RTMP e URL HTTP/HTTPS.
- `snapshot`: endpoint HTTP che restituisce JPEG; l'applicazione acquisisce snapshot ripetuti alla frequenza configurata.
- `youtube`: URL YouTube, inclusi live stream; `yt-dlp` risolve il media stream effettivo e il codice gestisce la riapertura della sorgente.

Per le sorgenti live usare `run_realtime.py` e uno dei file di esempio in `configs/`. La pipeline mantiene il frame più recente per evitare di accumulare una coda crescente quando l'inferenza è più lenta della sorgente.

## Verifiche e build

```powershell
.\.venv\Scripts\python.exe -m pytest -q
npm --prefix frontend run typecheck
npm --prefix frontend run lint
npm --prefix frontend run build
```

Dopo la build, `npm --prefix frontend start` avvia il frontend. API e analisi restano processi separati.

I test Python usano fixture versionate e non richiedono `configs/video.local.yaml`. Ulteriori istruzioni in [docs/VALIDATION.md](docs/VALIDATION.md). Architettura in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

Il test browser in `tests/browser_v080.mjs` richiede Playwright e Chromium; vedere `docs/VALIDATION.md`. Non viene eseguito automaticamente da `pytest`.

## Nota di sicurezza

L’API nasce per uso locale e ascolta di default solo su `127.0.0.1`. Il token `operator-demo` è un fallback dimostrativo: prima di una presentazione condivisa o di qualsiasi esposizione su rete impostare sempre `EAV_OPERATOR_TOKEN` a un valore personale. Non esporre il server su `0.0.0.0` senza ulteriori protezioni di rete e autenticazione. Il progetto non implementa autenticazione enterprise né hardening per Internet.

## Preparazione per GitHub

Il `.gitignore` esclude ambienti, dipendenze, build (`dist`, `.next`, `.vinext`), cache, output, video, pesi, credenziali, `.dev.vars` e configurazioni locali. I file di esempio, le fixture di test e `frontend/package-lock.json` devono essere versionati.

Prima del push, controllare i file aggiunti con `git status` e il contenuto con `git diff --cached`. Le regole di esclusione non rimuovono file già tracciati: se necessario, rimuoverli dall’indice con `git rm --cached <percorso>` senza cancellare la copia locale.

Non è presente un file `LICENSE`: prima di pubblicare il repository decidere con il team/EAV quale licenza applicare e verificare che asset, video, pesi e materiale del project work siano effettivamente pubblicabili. Video, pesi e configurazioni locali restano esclusi dalla consegna Git.


## File utilizzati durante il run video standard

Il run descritto sopra avvia tre processi separati:

| Processo | File utilizzati |
|---|---|
| Analisi video | `run_video.py`, moduli Python elencati sotto, `configs/video.local.yaml`, il video indicato da `--video` e i pesi indicati da `model.weights` |
| API e gestione eventi | `video_event_server.py`, moduli Python elencati sotto, configurazione locale e file generati in `outputs/` |
| Frontend | `frontend/app/`, `frontend/public/`, `frontend/package.json`, dipendenze installate, configurazione Vite e `frontend/worker/index.ts` |

Nella configurazione locale attuale gli asset sono `videos/prova4.mp4` e `yolo12n.pt`. In modalità produzione il frontend usa la build generata; i sorgenti restano necessari per modificarla e ricostruirla.

Moduli Python richiesti direttamente o indirettamente dai due comandi di avvio:

- `crowd_monitor/__init__.py`
- `crowd_monitor/access_control.py`
- `crowd_monitor/analytics.py`
- `crowd_monitor/atomic_io.py`
- `crowd_monitor/config.py`
- `crowd_monitor/cv_live.py`
- `crowd_monitor/dashboard.py`
- `crowd_monitor/demo_config.py`
- `crowd_monitor/detector.py`
- `crowd_monitor/event_frames.py`
- `crowd_monitor/frontend_events.py`
- `crowd_monitor/geometry.py`
- `crowd_monitor/live_state.py`
- `crowd_monitor/presentation.py`
- `crowd_monitor/renderer.py`
- `crowd_monitor/video_pipeline.py`

I file `outputs/video_events.jsonl`, `outputs/event_status.json`, `outputs/live_state.json`, `outputs/live_cv.jpg` e le immagini in `outputs/event_frames/` vengono creati durante l’uso. Cancellarli azzera lo storico o le immagini associate: non sono file inutilizzati.

### File che servono fuori dal run standard

- `run_realtime.py`, `crowd_monitor/pipeline.py`, `source.py`, `health.py` e i moduli `team_b*`: modalità di acquisizione in tempo reale, diagnostica ed esportazione.
- `crowd_monitor/dashboard.py`: lettore degli eventi condiviso con l’API principale, necessario anche senza la vecchia dashboard.
- `validate_team_b_json.py` e `crowd_monitor/cli_utils.py`: validazione delle esportazioni e caricamento della configurazione per l’avvio live.
- `tests/`, `docs/`, `DESIGN.md`, `UX-CONTRACT.md`, `CHANGELOG.md`: verifica e manutenzione.
- `pyproject.toml`, `.gitignore`, lockfile, configurazioni TypeScript/ESLint ed esempi YAML: installazione, sviluppo e gestione del repository.

Questi file non sono tutti caricati nel run video, ma non sono inutilizzati: eliminarli rimuoverebbe strumenti o verifiche del progetto.

Tutti e quattro i video di test sono conservati nella cartella locale e restano esclusi da Git. Sono stati rimossi la dashboard precedente, i suoi script di avvio, i vecchi editor e gli script separati di anteprima/verifica camera. Il frontend e la Console AI sono l’interfaccia mantenuta.
