# v0.8.0

- Sessione operatore temporanea di 15 minuti, condivisa con Console AI.
- Correzione indicatori del carosello eventi.
- Cambio stato senza navigazione alla sezione di destinazione.
- Demo Console rinominata Console AI; uscita verso la vista operatore.
- Gerarchia azioni, conferma cancellazione e salvataggio visibile.
- Campi aree, bagagli e animali con descrizioni e validazione.
- Consegna pulita, verifica Python e browser.
- Dipendenze runtime aggiornate e rese esplicite per PyTorch 2.14/Torchvision 0.29; documentata l'installazione CUDA.
- Configurazione della precisione allineata a Ultralytics (`quantize`) con compatibilità per il vecchio campo `half` e controllo anticipato della disponibilità CUDA.
- `.gitignore` esteso per artefatti Vinext/Cloudflare, variabili locali, output Ultralytics e log dei package manager.

# 0.7.1

- Dashboard operatore suddivisa in tre sezioni: **Nuovi eventi**, **In gestione** (presi in carico/in verifica) e **Archivio** (risolti/falsi positivi), con contatori dedicati.
- Gli stati terminali `Risolto` e `Falso positivo` sono definitivi: il backend rifiuta la riapertura e il frontend rimuove le azioni di avanzamento sugli eventi archiviati.
- Ogni nuovo evento salva due snapshot: frame annotato con bounding box/overlay e frame pulito senza annotazioni.
- Il dettaglio evento mostra i frame in una gallery orizzontale swippabile con controlli e indicatori; gli eventi storici con un solo frame restano compatibili.
- Consentita la rimozione delle geometrie esistenti, inclusa la cancellazione completa dalla Demo Console; una geometria treno vuota resta uno stato valido con rilevamento `UNKNOWN`.
- Resa robusta la gestione degli stati operatore e rimossi artefatti di checkpoint/verifica non necessari dalla consegna.

# 0.7.0

Accesso passeggeri pubblico; dashboard con trend e confronto zone; operatore event-first; Demo Console protetta con editor ROI/linee/crowd/train, tuning validato e salvataggio YAML atomico. Sorgente locale allineata al video incluso; 115 test backend e frontend verificato.

# Changelog

## 0.6.3 — factorized

- Base: ZIP della 0.6.2, mantenendo ruoli, analytics, configurazioni, modello e video di prova.
- Scrittura atomica condivisa tra stato live, JPEG e stati evento; sincronizzazione su disco riservata agli stati persistenti.
- Proiezioni utente/operatore separate dal trasporto HTTP; congestione calcolata sulle sole zone pubbliche di affollamento.
- Snapshot eventi inviato nello stesso stream degli aggiornamenti, eliminando la finestra di perdita tra lettura iniziale e connessione; ripristino completo alla riconnessione.
- SSE: nessun invio per il solo cambio di timestamp; memoria degli eventi inviati limitata alla finestra corrente; intestazioni condivise.
- Richieste con stato non testuale o lunghezza corpo negativa/eccessiva restituite come errore 400; token oscurati nei log HTTP.
- Parametri FPS non finiti/non positivi rifiutati; risorse rilasciate anche se l'inizializzazione del tracker fallisce.
- Frontend: tipi e funzioni comuni estratti, stato del dettaglio sincronizzato, errore di rete sul cambio stato gestito.
- Corretti tipi Worker e comando di verifica; rimossi pacchetti inutilizzati Drizzle, skeleton e Tailwind con aggiornamento lockfile.
- Consolidati README e changelog; esclusi ambienti, cache, output precedenti, note di patch e validazioni superate.

## Base 0.6.0–0.6.2

Analisi video sequenziale con tempo del media, quattro eventi operativi e relativi frame; avvio da Python; snapshot live; separazione ruoli con token, CV MJPEG e presa in carico persistente.

## Base precedente

Sorgenti live e YouTube, tracking, regole temporali, stato treno e protezione del crossing, diagnostica, editor di calibrazione e adapter Team B locale. Queste funzionalità sono conservate.
