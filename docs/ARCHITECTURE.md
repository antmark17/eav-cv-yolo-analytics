# Architettura locale 0.8.0

```text
snapshot / RTSP / MP4 / webcam / YouTube live
                       |
                       v
       latest-frame source + reconnect/resolution
                       |
                       v
                YOLO + ByteTrack
                       |
                       v
             stateful analytics engine
      +----------------+------------------+
      |                |                  |
 train state      associations      temporal rules
 + yellow line    bag/animal        litter/danger/fall/
                                     vandalism
      +----------------+------------------+
                       |
                       v
          local canonical event stream
           |             |               |
           v             v               v
   API + frontend   renderer/MP4   strict Team B adapter
```

## Invarianti di sicurezza

- Ogni riconnessione azzera tracking, associazioni e stato del treno.
- Lo stato iniziale del treno è `UNKNOWN`.
- Un crossing protetto produce `line_crossing` soltanto con
  `train_state == ABSENT`.
- `PRESENT` e `UNKNOWN` producono un evento locale
  `yellow_line_crossing_suppressed` e non raggiungono il Team B.
- Il normalizzatore verifica nuovamente `train_state == ABSENT`.
- Gli eventi non previsti dal contratto Team B non vengono rinominati con tipi
  compatibili ma semanticamente falsi.

## Moduli

- `source.py`: acquisizione, ultimo frame, timeout, riconnessione e risoluzione
  YouTube tramite `yt-dlp`.
- `detector.py`: detection multi-classe e tracking ByteTrack.
- `analytics.py`: geometrie, stato treno, associazioni e regole temporali.
- `health.py`: diagnostica indipendente dal modello.
- `renderer.py`: overlay, track e stato treno.
- `pipeline.py`: orchestrazione e output.
- `dashboard.py`: lettura incrementale del JSONL canonico, usata da `video_event_server.py` per il frontend.
- `team_b.py`: validazione e normalizzazione strict.
- `team_b_exporter.py`: JSONL locale e sequenza SQLite.
- `config.py`: parsing e validazione YAML, incluse dipendenze classi/modello.

## Confine dei modelli

La pipeline accetta qualsiasi peso Ultralytics compatibile e classi
configurabili. COCO offre una baseline per persona, treno, animali, bagagli,
mazza, coltello e forbici. Spazzatura/degrado, vandalismo, armi complete e una
caduta robusta richiedono pesi o modelli temporali dedicati. La presenza della
macchina a stati non equivale a validazione del modello.

## Fuori dalla release

- adapter MQTT Meraki;
- sincronizzazione delle boundary tramite Dashboard API;
- invio di rete Team B;
- outbox, retry, ACK e idempotenza end-to-end;
- storage e URL HTTPS degli snapshot;
- pesi custom e dataset ferroviario.


## Presentazione video a ruoli

`run_video.py` usa `video_pipeline.py` per elaborare tutti i frame in ordine. Pubblica snapshot e JPEG sostituibili tramite `atomic_io.py`; gli eventi rimangono append-only. Lo stato operatore usa lo stesso writer con sincronizzazione persistente.

`video_event_server.py` legge gli output e applica i contratti di `presentation.py`. Gli SSE pubblicano solo cambiamenti del contenuto, con keep-alive; MJPEG pubblica i nuovi frame. Il browser non avvia l'analisi. `frontend/app/eav.ts` raccoglie tipi e funzioni comuni alle viste.

Le versioni degli schemi 0.6.0/0.6.1/0.6.2 nei payload restano invariate per compatibilità. La versione del pacchetto è 0.8.0.
