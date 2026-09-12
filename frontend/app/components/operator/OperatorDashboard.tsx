/* eslint-disable @next/next/no-img-element -- Local authenticated JPEG/MJPEG or object URLs must reach the browser directly. */
"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  apiUrl,
  rank,
  eventLabels,
  operatorUrl,
  requestError,
  densityText,
  levelLabel,
  eventFrame,
  eventFrames,
  isTerminalStatus,
  type Alert,
  type Status,
  type OperatorLive,
} from "../../eav";
import { AppHeader, Kpi } from "../AppHeader";
import { Modal } from "../Modal";

type EventSection = "new" | "active" | "closed";

export default function OperatorDashboard({
  token,
  dark,
  toggleTheme,
  logout,
}: {
  token: string;
  dark: boolean;
  toggleTheme: () => void;
  logout: () => void;
}) {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [live, setLive] = useState<OperatorLive>({
    station: "Stazione EAV",
    people: 0,
    train_state: "UNKNOWN",
    density_people_m2: null,
    zones: [],
    cv_available: false,
  });
  const [connected, setConnected] = useState(false);
  const [selected, setSelected] = useState<Alert | null>(null);
  const [sort, setSort] = useState<"recent" | "urgent">("recent");
  const [eventSection, setEventSection] = useState<EventSection>("new");
  const [vision, setVision] = useState(false);
  const [busy, setBusy] = useState(false);
  const pending = useRef(false);
  const [toast, setToast] = useState("");

  useEffect(() => {
    const source = new EventSource(
      operatorUrl("/api/operator/events/stream", token),
    );
    source.onopen = () => setConnected(true);
    source.onerror = () => setConnected(false);
    source.addEventListener("events_snapshot", (raw) => {
      try {
        const payload = JSON.parse((raw as MessageEvent<string>).data) as {
          events: Alert[];
        };
        if (Array.isArray(payload.events)) {
          setAlerts(payload.events);
          setSelected((current) =>
            current
              ? (payload.events.find((item) => item.id === current.id) ?? null)
              : null,
          );
        }
      } catch {
        /* keep prior snapshot */
      }
    });
    source.addEventListener("analytics_event", (raw) => {
      try {
        const incoming = JSON.parse(
          (raw as MessageEvent<string>).data,
        ) as Alert;
        setAlerts((current) =>
          current.some((item) => item.id === incoming.id)
            ? current.map((item) => (item.id === incoming.id ? incoming : item))
            : [incoming, ...current].slice(0, 1000),
        );
        setSelected((current) =>
          current?.id === incoming.id ? incoming : current,
        );
        setToast(`${incoming.icon} ${incoming.title} · ${incoming.place}`);
      } catch {
        /* ignore malformed event */
      }
    });

    const ls = new EventSource(operatorUrl("/api/operator/live/stream", token));
    ls.addEventListener("operator_live", (raw) => {
      try {
        setLive(JSON.parse((raw as MessageEvent<string>).data) as OperatorLive);
      } catch {
        /* keep prior */
      }
    });
    return () => {
      source.close();
      ls.close();
    };
  }, [token]);

  const eventCounts = useMemo(
    () => ({
      new: alerts.filter((item) => item.status === "Nuovo").length,
      active: alerts.filter((item) =>
        ["Preso in carico", "In verifica"].includes(item.status),
      ).length,
      closed: alerts.filter((item) => isTerminalStatus(item.status)).length,
    }),
    [alerts],
  );

  const visible = useMemo(() => {
    const filtered = alerts.filter((item) => {
      if (eventSection === "new") return item.status === "Nuovo";
      if (eventSection === "active") {
        return ["Preso in carico", "In verifica"].includes(item.status);
      }
      return isTerminalStatus(item.status);
    });
    return [...filtered].sort((a, b) => {
        if (sort === "urgent") return rank[b.priority] - rank[a.priority];
        return (
          (b.occurred_at ? new Date(b.occurred_at).valueOf() : 0) -
          (a.occurred_at ? new Date(a.occurred_at).valueOf() : 0)
        );
      });
  }, [alerts, eventSection, sort]);

  const sectionCopy = {
    new: {
      eyebrow: "NUOVI EVENTI",
      title: "Da prendere in carico",
      empty: "Nessun nuovo evento da gestire.",
    },
    active: {
      eyebrow: "IN GESTIONE",
      title: "Presi in carico e in verifica",
      empty: "Nessun evento attualmente in gestione.",
    },
    closed: {
      eyebrow: "ARCHIVIO",
      title: "Risolti e falsi positivi",
      empty: "Nessun evento archiviato.",
    },
  }[eventSection];

  async function updateStatus(alert: Alert, status: Status) {
    if (pending.current) return;
    if (isTerminalStatus(alert.status) && alert.status !== status) {
      setToast("Evento archiviato: lo stato è definitivo e non può essere riaperto.");
      return;
    }
    if (alert.status === status) {
      setToast(`${alert.id}: stato già impostato su ${status}`);
      return;
    }
    pending.current = true;
    setBusy(true);
    try {
      const response = await fetch(
        apiUrl(`/api/operator/events/${encodeURIComponent(alert.id)}/status`),
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ status }),
          signal: AbortSignal.timeout(8000),
        },
      );
      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as
          | { error?: string }
          | null;
        if (payload?.error === "event_status_terminal") {
          throw new Error(
            "Evento archiviato: lo stato è definitivo e non può essere riaperto.",
          );
        }
        throw new Error(
          payload?.error || "Impossibile aggiornare lo stato dell'evento",
        );
      }
      setAlerts((items) =>
        items.map((item) =>
          item.id === alert.id ? { ...item, status } : item,
        ),
      );
      setSelected((item) =>
        item?.id === alert.id ? { ...item, status } : item,
      );
      setToast(`${alert.id}: ${status}`);
    } catch (error) {
      setToast(requestError(error));
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }

  const cvUrl = operatorUrl("/api/operator/cv/stream", token);
  const activeCount = eventCounts.new + eventCounts.active;

  return (
    <div className="app">
      <AppHeader
        title="Centro Operativo EAV"
        subtitle="Gestione eventi di stazione"
        connected={connected}
        dark={dark}
        toggleTheme={toggleTheme}
        logout={logout}
      />
      <main className="page operatorPage">
        <section className="operatorHero">
          <div>
            <small>OPERATORE EAV</small>
            <h1>Presidio eventi</h1>
            <p>Valuta gli eventi rilevati e aggiornane lo stato operativo.</p>
          </div>
          <div className="operatorStats">
            <Kpi
              label="Eventi attivi"
              value={String(activeCount)}
              note="da gestire"
            />
            <Kpi
              label="Persone"
              value={String(live.people ?? 0)}
              note="presenza corrente"
            />
            <Kpi
              label="Treno"
              value={live.train_state || "UNKNOWN"}
              note="stato rilevato"
            />
          </div>
        </section>

        <nav className="viewSwitch" aria-label="Viste operatore">
          <button aria-pressed={!vision} onClick={() => setVision(false)}>
            Operativo
          </button>
          <button aria-pressed={vision} onClick={() => setVision(true)}>
            Visione AI
          </button>
          <a href="/demo">Console AI ↗</a>
        </nav>
        {vision ? (
          <article className="cvPanel">
            <div className="sectionHead">
              <div>
                <small>VISIONE OPERATIVA</small>
                <h2>Computer vision live</h2>
              </div>
              <span className={live.cv_live ? "livePill" : "mutedPill"}>
                {live.cv_live
                  ? "● LIVE"
                  : live.cv_available
                    ? "Ultimo frame"
                    : "In attesa"}
              </span>
            </div>
            <div className="cvViewport">
              {live.cv_available ? (
                <img src={cvUrl} alt="Visione computer vision in tempo reale" />
              ) : (
                <p>
                  Avvia l’analisi locale per visualizzare il video annotato.
                </p>
              )}
            </div>
            <div className="cvFoot">
              <span>
                <small>Stazione</small>
                <b>{live.station}</b>
              </span>
              <span>
                <small>Densità</small>
                <b>{densityText(live.density_people_m2)}</b>
              </span>
            </div>
          </article>
        ) : (
          <section className="operatorGrid eventFirst">
            <article className="queuePanel">
              <div className="eventSectionTabs" role="tablist" aria-label="Sezioni eventi">
                <button
                  role="tab"
                  aria-selected={eventSection === "new"}
                  onClick={() => setEventSection("new")}
                >
                  <span>Nuovi eventi</span>
                  <b>{eventCounts.new}</b>
                </button>
                <button
                  role="tab"
                  aria-selected={eventSection === "active"}
                  onClick={() => setEventSection("active")}
                >
                  <span>In gestione</span>
                  <b>{eventCounts.active}</b>
                </button>
                <button
                  role="tab"
                  aria-selected={eventSection === "closed"}
                  onClick={() => setEventSection("closed")}
                >
                  <span>Archivio</span>
                  <b>{eventCounts.closed}</b>
                </button>
              </div>
              <div className="sectionHead">
                <div>
                  <small>{sectionCopy.eyebrow}</small>
                  <h2>{sectionCopy.title}</h2>
                </div>
                <select
                  aria-label="Ordina eventi"
                  value={sort}
                  onChange={(e) =>
                    setSort(e.target.value as "recent" | "urgent")
                  }
                >
                  <option value="recent">Più recenti</option>
                  <option value="urgent">Priorità</option>
                </select>
              </div>
              {visible.length === 0 ? (
                <div className="empty compact">
                  <b>✓</b>
                  <h3>Nessun evento</h3>
                  <p>{sectionCopy.empty}</p>
                </div>
              ) : (
                <div className="compactList">
                  {visible.map((alert) => (
                    <EventCard
                      key={alert.id}
                      alert={alert}
                      token={token}
                      onOpen={() => setSelected(alert)}
                      onStatus={updateStatus}
                      busy={busy}
                    />
                  ))}
                </div>
              )}
            </article>
            <article className="panel">
              <h2>Stato aree</h2>
              <Kpi
                label="Densità"
                value={densityText(live.density_people_m2)}
                note="presenza per metro quadrato"
              />
              <div className="areaList">
                {live.zones.length ? (
                  live.zones.map((zone) => (
                    <div key={zone.name}>
                      <strong>{zone.name}</strong>
                      <span>{levelLabel(zone.level)}</span>
                      <small>
                        {zone.people ?? "—"} persone ·{" "}
                        {densityText(zone.density_people_m2)}
                      </small>
                    </div>
                  ))
                ) : (
                  <p>Le aree compariranno quando l’analisi sarà disponibile.</p>
                )}
              </div>
            </article>
          </section>
        )}
      </main>
      {selected && (
        <EventDrawer
          alert={selected}
          token={token}
          close={() => setSelected(null)}
          updateStatus={updateStatus}
          busy={busy}
        />
      )}
      {toast && (
        <button role="status" className="toast" onClick={() => setToast("")}>
          {toast}
        </button>
      )}
    </div>
  );
}

function EventCard({
  alert,
  token,
  onOpen,
  onStatus,
  busy,
}: {
  alert: Alert;
  token: string;
  onOpen: () => void;
  onStatus: (alert: Alert, status: Status) => void;
  busy: boolean;
}) {
  const src = eventFrame(alert, token);
  return (
    <article
      className={`compactEvent priority-${alert.priority.toLowerCase()}`}
    >
      <button
        className="eventThumb"
        aria-label={`Apri ${alert.title}`}
        onClick={onOpen}
      >
        {src ? <img src={src} alt="Frame evento" /> : <span>{alert.icon}</span>}
      </button>
      <div className="compactEventMain">
        <div className="badges">
          <em className={`prio ${alert.priority.toLowerCase()}`}>
            {alert.priority}
          </em>
          <em className="status">{alert.status}</em>
        </div>
        <h3>{alert.title}</h3>
        <p>
          {alert.station} · {alert.place}
        </p>
        <div className="compactActions">
          <button onClick={onOpen}>Dettagli</button>
          {alert.status === "Nuovo" && (
            <button
              disabled={busy}
              className="primary"
              onClick={() => onStatus(alert, "Preso in carico")}
            >
              Prendi in carico
            </button>
          )}
          {alert.status === "Preso in carico" && (
            <button
              disabled={busy}
              onClick={() => onStatus(alert, "In verifica")}
            >
              Avvia verifica
            </button>
          )}
        </div>
      </div>
    </article>
  );
}

function EventDrawer({
  alert,
  token,
  close,
  updateStatus,
  busy,
}: {
  alert: Alert;
  token: string;
  close: () => void;
  updateStatus: (alert: Alert, status: Status) => void;
  busy: boolean;
}) {
  const terminal = isTerminalStatus(alert.status);
  return (
    <Modal title="Dettaglio evento" close={close}>
      <div className="drawerContent">
        <small>EVENTO {alert.id}</small>
        <h2>{eventLabels[alert.event_type]}</h2>
        <p>
          {alert.station} · {alert.place}
        </p>
        <EventFrameGallery key={alert.id} alert={alert} token={token} />
        <div className="facts">
          <span>
            <small>Priorità</small>
            <b>{alert.priority}</b>
          </span>
          <span>
            <small>Stato</small>
            <b>{alert.status}</b>
          </span>
          <span>
            <small>Affidabilità</small>
            <b>{alert.confidence == null ? "—" : `${alert.confidence}%`}</b>
          </span>
          <span>
            <small>Tipo</small>
            <b>{eventLabels[alert.event_type]}</b>
          </span>
        </div>
        <h3>Gestione evento</h3>
        {terminal ? (
          <div className="terminalNotice">
            <b>Evento archiviato</b>
            <span>
              Lo stato “{alert.status}” è definitivo. L’evento non può tornare
              in verifica o essere riaperto.
            </span>
          </div>
        ) : (
          <div className="drawerActions">
            <button
              disabled={busy || alert.status === "Preso in carico"}
              onClick={() => updateStatus(alert, "Preso in carico")}
            >
              Preso in carico
            </button>
            <button
              disabled={busy || alert.status === "In verifica"}
              onClick={() => updateStatus(alert, "In verifica")}
            >
              In verifica
            </button>
            <button
              disabled={busy}
              className="primary"
              onClick={() => updateStatus(alert, "Risolto")}
            >
              Risolto
            </button>
            <button
              disabled={busy}
              className="danger"
              onClick={() => updateStatus(alert, "Falso positivo")}
            >
              Falso positivo
            </button>
          </div>
        )}
      </div>
    </Modal>
  );
}

function EventFrameGallery({ alert, token }: { alert: Alert; token: string }) {
  const frames = eventFrames(alert, token);
  const scroller = useRef<HTMLDivElement>(null);
  const [index, setIndex] = useState(0);


  function goTo(next: number) {
    const safeIndex = Math.max(0, Math.min(next, frames.length - 1));
    const node = scroller.current;
    if (!node) return;
    node.scrollTo({ left: node.clientWidth * safeIndex, behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth" });
    setIndex(safeIndex);
  }

  if (!frames.length) {
    return (
      <div className="largePreview">
        <span>Nessun frame disponibile</span>
      </div>
    );
  }

  return (
    <div className="frameGallery">
      <div
        className="frameGalleryTrack"
        ref={scroller}
        onScroll={(event) => {
          const element = event.currentTarget;
          if (!element.clientWidth) return;
          setIndex(
            Math.max(
              0,
              Math.min(
                frames.length - 1,
                Math.round(element.scrollLeft / element.clientWidth),
              ),
            ),
          );
        }}
      >
        {frames.map((frame) => (
          <figure className="frameGallerySlide" key={frame.key}>
            <img src={frame.url} alt={`Frame evento ${frame.label.toLowerCase()}`} />
            <figcaption>{frame.label}</figcaption>
          </figure>
        ))}
      </div>
      {frames.length > 1 && (
        <div className="frameGalleryControls" aria-label="Controlli gallery frame">
          <button
            aria-label="Frame precedente"
            disabled={index === 0}
            onClick={() => goTo(index - 1)}
          >
            ←
          </button>
          <div className="frameGalleryDots">
            {frames.map((frame, dotIndex) => (
              <button
                key={frame.key}
                aria-label={`Mostra ${frame.label.toLowerCase()}`}
                aria-current={index === dotIndex ? "true" : undefined}
                onClick={() => goTo(dotIndex)}
              />
            ))}
          </div>
          <button
            aria-label="Frame successivo"
            disabled={index === frames.length - 1}
            onClick={() => goTo(index + 1)}
          >
            →
          </button>
        </div>
      )}
    </div>
  );
}
