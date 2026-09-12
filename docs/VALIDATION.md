# Verifiche

Dalla radice, con le dipendenze installate:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
npm --prefix frontend run typecheck
npm --prefix frontend run lint
npm --prefix frontend run build
```

I test Python coprono configurazione, geometrie, analisi, API, stati degli eventi e sessioni. Usano `tests/fixtures/video.yaml`, indipendente dalla configurazione locale.

## Verifica browser

Installare Playwright senza aggiungerlo alle dipendenze del progetto:

```powershell
npm install --no-save --package-lock=false playwright
npx playwright install chromium
npm --prefix frontend run dev -- --port 3108
```

In un altro terminale, dalla radice:

```powershell
node tests/browser_v080.mjs
```

La variabile `EAV_TEST_URL` permette di scegliere un altro indirizzo. Il test simula API e immagini, quindi non richiede l’avvio dell’analisi. Verifica il carosello, gli aggiornamenti degli eventi, la sessione, il ritorno dalla Console AI, la creazione delle aree, gli errori di salvataggio e il recupero della bozza. Report e immagini vengono generati in `outputs/browser-tests/`, esclusa da Git.

Queste verifiche non sostituiscono una prova completa del modello sui video e sull’hardware di destinazione.
