"use client";
import { useEffect, useRef, useState } from "react";
import { useOperatorSession } from "../operator-session";
import {
  apiUrl,
  requestError,
  operatorUrl,
  densityText,
  type Alert,
  type OperatorLive,
} from "../eav";
import { OperatorLogin } from "../components/OperatorLogin";
import { AppHeader, Kpi } from "../components/AppHeader";
import { Modal } from "../components/Modal";
import { GeometryEditor } from "../components/demo/GeometryEditor";
import { DemoCvPanel } from "../components/demo/DemoCvPanel";
import { DemoEventStream } from "../components/demo/DemoEventStream";
import { TuningPanel } from "../components/demo/TuningPanel";
import type { DemoConfig } from "../components/demo/types";
export default function DemoPage() {
  const { token, checked } = useOperatorSession();
  if (!checked) return <main className="loginPage"><p role="status">Verifica accesso…</p></main>;
  return <>
    {!token && <OperatorLogin onSuccess={() => {}} onBack={() => location.assign("/?view=operator")} />}
    <div hidden={!token}>
      <Console token={token} logout={() => location.assign("/?view=operator")} />
    </div>
  </>;
}
function Console({ token, logout }: { token: string; logout: () => void }) {
  const [config, setConfig] = useState<DemoConfig | null>(null);
  const [baseline, setBaseline] = useState("");
  const [reload, setReload] = useState(0);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState(false);
  const [live, setLive] = useState<OperatorLive | null>(null);
  const [events, setEvents] = useState<Alert[]>([]);
  const [connected, setConnected] = useState(false);
  const [dark, setDark] = useState(false);
  const [leaving, setLeaving] = useState(false);
  const pending = useRef(false);
  const loaded = useRef(false);
  const allowLeave = useRef(false);
  const errorRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (error) errorRef.current?.focus();
  }, [error]);
  const dirty = !!config && JSON.stringify(config) !== baseline;
  useEffect(() => {
    if (!token || loaded.current) return;
    const c = new AbortController();
    fetch(apiUrl("/api/demo/config"), {
      headers: { Authorization: `Bearer ${token}` },
      signal: c.signal,
    })
      .then(async (r) => {
        if (!r.ok)
          throw new Error(
            r.status === 403
              ? "Accesso negato. Esci e accedi con il token operatore."
              : "Configurazione non disponibile. Verifica il file YAML del server.",
          );
        return r.json();
      })
      .then((data) => {
        loaded.current = true;
        setConfig(data);
        setBaseline(JSON.stringify(data));
      })
      .catch((e) => {
        if (!c.signal.aborted) setError(requestError(e));
      });
    return () => c.abort();
  }, [token, reload]);
  useEffect(() => {
    if (!token) return;
    const es = new EventSource(
      operatorUrl("/api/operator/events/stream", token),
    );
    es.onopen = () => setConnected(true);
    es.onerror = () => setConnected(false);
    es.addEventListener("events_snapshot", (raw) => {
      try {
        setEvents(
          JSON.parse((raw as MessageEvent<string>).data).events.slice(0, 200),
        );
      } catch {}
    });
    es.addEventListener("analytics_event", (raw) => {
      try {
        const e = JSON.parse((raw as MessageEvent<string>).data) as Alert;
        setEvents((old) =>
          [e, ...old.filter((x) => x.id !== e.id)].slice(0, 200),
        );
      } catch {}
    });
    const ls = new EventSource(operatorUrl("/api/operator/live/stream", token));
    ls.addEventListener("operator_live", (raw) => {
      try {
        setLive(JSON.parse((raw as MessageEvent<string>).data));
      } catch {}
    });
    return () => {
      es.close();
      ls.close();
    };
  }, [token]);
  useEffect(() => {
    if (!dirty && !draft) return;
    const warn = (e: BeforeUnloadEvent) => {
      if (allowLeave.current) return;
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty, draft]);
  async function save() {
    if (pending.current || !config) return;
    const invalid = document.querySelector<HTMLElement>(
      '[aria-invalid="true"]',
    );
    if (invalid) {
      invalid.focus();
      return;
    }
    pending.current = true;
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const response = await fetch(apiUrl("/api/demo/config"), {
        method: "PUT",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          model: config.model,
          analytics: config.analytics,
        }),
        signal: AbortSignal.timeout(15000),
      });
      const data = await response.json();
      if (!response.ok)
        throw new Error(data.error || "Salvataggio non riuscito");
      setConfig(data.config);
      setBaseline(JSON.stringify(data.config));
      setMessage(
        "Configurazione salvata. Riavviare l’analisi per applicare le modifiche.",
      );
    } catch (e) {
      setError(requestError(e));
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }
  const back = () => {
    if (dirty || draft) setLeaving(true);
    else logout();
  };
  return (
    <div className="app">
      <AppHeader
        title="Console AI EAV"
        subtitle="Calibrazione e diagnostica"
        connected={connected}
        dark={dark}
        toggleTheme={() => {
          setDark(!dark);
          document.documentElement.dataset.theme = dark ? "light" : "dark";
        }}
        logout={() => {
          if (dirty || draft) setLeaving(true);
          else logout();
        }}
      />
      <main className="page demoPage">
        <div className="sectionHead">
          <div>
            <small>CONSOLE TECNICA</small>
            <h1>Configura e osserva</h1>
          </div>
          <button onClick={back}>← Vista operatore</button>
        </div>
        <div className="kpis">
          <Kpi
            label="Analisi"
            value={live?.running ? "In esecuzione" : "Ferma"}
            note="stato della pipeline"
          />
          <Kpi
            label="Persone"
            value={String(live?.people ?? "—")}
            note="conteggio corrente"
          />
          <Kpi
            label="Treno"
            value={live?.train_state ?? "UNKNOWN"}
            note="stato rilevato"
          />
          <Kpi
            label="Densità"
            value={densityText(live?.density_people_m2)}
            note={
              live?.updated_at
                ? `Aggiornato ${new Date(live.updated_at * 1000).toLocaleTimeString("it-IT")}`
                : "In attesa"
            }
          />
        </div>
        <div className="demoLiveGrid">
          {token && <DemoCvPanel token={token} live={live} />}
          <DemoEventStream events={events} connected={connected} />
        </div>
        {error && (
          <div
            ref={errorRef}
            tabIndex={-1}
            role="alert"
            className="notice error"
          >
            {error}
            {!config && (
              <button
                onClick={() => {
                  setError("");
                  setReload((x) => x + 1);
                }}
              >
                Riprova
              </button>
            )}
          </div>
        )}
        {config ? (
          <>
            <fieldset className="configFields" disabled={busy}>
              <GeometryEditor
                config={config}
                token={token}
                onChange={(next) => {
                  setConfig(next);
                  setMessage("");
                }}
                onDraftChange={(next) => {
                  setDraft(next);
                  if (next) setMessage("");
                }}
              />
              <TuningPanel
                config={config}
                onChange={(next) => {
                  setConfig(next);
                  setMessage("");
                }}
              />
            </fieldset>
            <div className="saveBar">
              <div>
                <strong>
                  {dirty || draft
                    ? "Modifiche non salvate"
                    : "Configurazione salvata"}
                </strong>
                <p role="status">
                  {message ||
                    (config.restart_required
                      ? "Riavviare l’analisi per applicare le modifiche."
                      : "Il salvataggio non riavvia automaticamente l’analisi.")}
                </p>
                {draft && (
                  <small>Applica o scarta il disegno prima di salvare.</small>
                )}
              </div>
              <button
                className="primary"
                disabled={busy || draft || !dirty}
                onClick={save}
              >
                {busy ? "Salvataggio…" : "Salva configurazione"}
              </button>
            </div>
          </>
        ) : (
          !error && <p role="status">Caricamento configurazione…</p>
        )}
      </main>
      {leaving && token && (
        <Modal title="Modifiche non salvate" close={() => setLeaving(false)}>
          <p>
            Uscendo perderai le modifiche alla configurazione e il disegno non
            applicato.
          </p>
          <div className="editorActions">
            <button onClick={() => setLeaving(false)}>
              Continua a modificare
            </button>
            <button
              onClick={() => {
                allowLeave.current = true;
                logout();
              }}
            >
              Scarta ed esci
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}
