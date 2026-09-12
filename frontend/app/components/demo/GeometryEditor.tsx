/* eslint-disable @next/next/no-img-element -- Local authenticated JPEG/MJPEG or object URLs must reach the browser directly. */
import { useEffect, useRef, useState } from "react";
import { apiUrl, requestError } from "../../eav";
import { Field } from "./Field";
import { Modal } from "../Modal";
import type { DemoConfig, NamedGeometry, Point } from "./types";
type Mode = "roi" | "crowd_zone" | "train_zone" | "line_crossing";
export function GeometryEditor({
  config,
  token,
  onChange,
  onDraftChange,
}: {
  config: DemoConfig;
  token: string;
  onChange: (c: DemoConfig) => void;
  onDraftChange: (dirty: boolean) => void;
}) {
  const [confirmClear, setConfirmClear] = useState(false);
  const [mode, setMode] = useState<Mode>("roi");
  const [index, setIndex] = useState(0);
  const [points, setPoints] = useState<Point[]>(config.analytics.roi ?? []);
  const [draft, setDraft] = useState(false);
  const [closed, setClosed] = useState(true);
  const [image, setImage] = useState("");
  const [aspect, setAspect] = useState(16 / 9);
  const [time, setTime] = useState(0);
  const [frameTime, setFrameTime] = useState(0);
  const [frameRevision, setFrameRevision] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [coord, setCoord] = useState<Point>([0.5, 0.5]);
  const canvas = useRef<HTMLCanvasElement>(null);
  const line = mode === "line_crossing";
  const collection = line
    ? config.analytics.line_crossings
    : config.analytics.crowd_zones;
  const item = collection[index];
  function current(c: DemoConfig, m: Mode, i: number): Point[] {
    return m === "roi"
      ? (c.analytics.roi ?? [])
      : m === "train_zone"
        ? (c.analytics.train.polygon ?? [])
        : (((m === "line_crossing"
            ? c.analytics.line_crossings[i]?.line
            : c.analytics.crowd_zones[i]?.polygon) as Point[]) ?? []);
  }
  function select(m: Mode, i = 0) {
    setMode(m);
    setIndex(i);
    setPoints(current(config, m, i));
    setClosed(true);
    setError("");
  }
  useEffect(() => {
    if (!token) return;
    const controller = new AbortController();
    let url = "";
    fetch(apiUrl(`/api/demo/preview-frame?time_s=${frameTime}`), {
      headers: { Authorization: `Bearer ${token}` },
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok) {
          const data = await response.json();
          throw new Error(data.error || "Preview non disponibile");
        }
        return response.blob();
      })
      .then((blob) => {
        url = URL.createObjectURL(blob);
        setImage(url);
      })
      .catch((e) => {
        if (!controller.signal.aborted) {
          setImage("");
          setError(requestError(e));
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => {
      controller.abort();
      if (url) URL.revokeObjectURL(url);
    };
  }, [frameTime, frameRevision, token]);
  useEffect(() => {
    const el = canvas.current;
    const ctx = el?.getContext("2d");
    if (!el || !ctx) return;
    ctx.clearRect(0, 0, el.width, el.height);
    if (!points.length) return;
    const mapped = points.map(([x, y]) => [x * el.width, y * el.height]);
    ctx.strokeStyle = "#ffcf40";
    ctx.fillStyle = "#ffcf4030";
    ctx.lineWidth = 3;
    ctx.beginPath();
    mapped.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)));
    if (!line && closed) {
      ctx.closePath();
      ctx.fill();
    }
    ctx.stroke();
    if (line && mapped.length === 2) {
      const [a, b] = mapped;
      const mx = (a[0] + b[0]) / 2,
        my = (a[1] + b[1]) / 2;
      const angle = Math.atan2(b[1] - a[1], b[0] - a[0]) + Math.PI / 2;
      ctx.beginPath();
      ctx.moveTo(mx, my);
      ctx.lineTo(mx + 32 * Math.cos(angle), my + 32 * Math.sin(angle));
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(mx + 32 * Math.cos(angle), my + 32 * Math.sin(angle));
      ctx.lineTo(
        mx + 22 * Math.cos(angle - 0.3),
        my + 22 * Math.sin(angle - 0.3),
      );
      ctx.lineTo(
        mx + 22 * Math.cos(angle + 0.3),
        my + 22 * Math.sin(angle + 0.3),
      );
      ctx.closePath();
      ctx.fillStyle = "#ffcf40";
      ctx.fill();
    }
    mapped.forEach(([x, y], i) => {
      ctx.fillStyle = "#ffcf40";
      ctx.beginPath();
      ctx.arc(x, y, 6, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillStyle = "#ffffff";
      ctx.font = "bold 18px sans-serif";
      ctx.fillText(
        String(i + 1),
        Math.min(el.width - 24, x + 10),
        Math.max(20, y - 10),
      );
    });
  }, [points, line, closed, aspect]);
  function changePoints(p: Point[]) {
    setPoints(p);
    setDraft(true);
    onDraftChange(true);
    setClosed(line && p.length === 2);
  }
  function add(p: Point[] = [coord]) {
    if (line && points.length === 2) {
      setError("Linea completa: usa Azzera per ridisegnarla.");
      return;
    }
    if (p.some((v) => v.some((n) => !Number.isFinite(n) || n < 0 || n > 1))) {
      setError("Inserisci coordinate tra 0 e 1.");
      return;
    }
    setError("");
    changePoints([...points, ...p]);
  }
  function apply() {
    if (points.length === 0) {
      const copy = structuredClone(config);
      if (mode === "roi") {
        copy.analytics.roi = [];
      } else if (mode === "train_zone") {
        copy.analytics.train.polygon = [];
      } else {
        const list =
          mode === "line_crossing"
            ? copy.analytics.line_crossings
            : copy.analytics.crowd_zones;
        if (!list[index]) return;
        list.splice(index, 1);
      }
      onChange(copy);
      const nextIndex = Math.max(
        0,
        Math.min(
          index,
          (mode === "line_crossing"
            ? copy.analytics.line_crossings.length
            : mode === "crowd_zone"
              ? copy.analytics.crowd_zones.length
              : 1) - 1,
        ),
      );
      setIndex(nextIndex);
      setPoints(current(copy, mode, nextIndex));
      setDraft(false);
      onDraftChange(false);
      setClosed(true);
      setError("");
      return;
    }
    if (
      points.length < (line ? 2 : 3) ||
      (line && points.length !== 2) ||
      new Set(points.map((p) => p.join(","))).size < (line ? 2 : 3)
    ) {
      setError(
        "Servono punti distinti: 2 per una linea, almeno 3 per un poligono.",
      );
      return;
    }
    const copy = structuredClone(config);
    if (mode === "roi") copy.analytics.roi = points;
    else if (mode === "train_zone") copy.analytics.train.polygon = points;
    else {
      const list =
        mode === "line_crossing"
          ? copy.analytics.line_crossings
          : copy.analytics.crowd_zones;
      if (!list[index]) return;
      list[index][line ? "line" : "polygon"] = points;
    }
    onChange(copy);
    setDraft(false);
    onDraftChange(false);
    setClosed(true);
    setError("");
  }
  function clearAll() {
    const copy = structuredClone(config);
    copy.analytics.roi = [];
    copy.analytics.train.polygon = [];
    copy.analytics.crowd_zones = [];
    copy.analytics.line_crossings = [];
    onChange(copy);
    setIndex(0);
    setPoints([]);
    setDraft(false);
    onDraftChange(false);
    setClosed(true);
    setError("");
  }
  function edit(key: string, value: NamedGeometry[string]) {
    const copy = structuredClone(config);
    const list = line
      ? copy.analytics.line_crossings
      : copy.analytics.crowd_zones;
    list[index][key] = value;
    onChange(copy);
  }
  function create() {
    const copy = structuredClone(config);
    const list = line
      ? copy.analytics.line_crossings
      : copy.analytics.crowd_zones;
    let name = `${line ? "linea" : "area"}_${list.length + 1}`;
    while (list.some((x) => x.name === name)) name += "_nuova";
    list.push(
      line
        ? {
            name,
            line: [],
            direction_labels: ["verso_binari", "verso_banchina"],
            prohibited_direction: "verso_binari",
            require_train_absent: false,
            cooldown_s: 2,
            hysteresis: 0.006,
          }
        : {
            name,
            polygon: [],
            area_m2: 10,
            warning_density: null,
            critical_density: 1.5,
            hold_s: 3,
            cooldown_s: 30,
          },
    );
    onChange(copy);
    setIndex(list.length - 1);
    setPoints([]);
    setDraft(true);
    onDraftChange(true);
    setClosed(false);
  }
  return (
    <section className="panel geometryPanel">
      <h2>Aree di analisi e linee di attraversamento</h2>
      <p>
        Scegli il tipo di area, disegna i punti sull’immagine e premi Applica geometria.
        Per rendere persistenti le modifiche, premi poi Salva configurazione.
      </p>
      <div className="geometryReset">
        <div><strong>Riparti da un’immagine senza aree</strong><p>Rimuove tutte le aree e le linee dalla configurazione in modifica.</p></div>
        <button className="danger" onClick={() => setConfirmClear(true)}>
          Cancella tutte le geometrie esistenti
        </button>
      </div>
      <div className="viewSwitch">
        {(
          [
            ["roi", "Area generale (ROI)"],
            ["crowd_zone", "Area affollamento"],
            ["train_zone", "Area treno"],
            ["line_crossing", "Linea gialla"],
          ] as [Mode, string][]
        ).map(([m, label]) => (
          <button
            key={m}
            disabled={draft}
            aria-pressed={mode === m}
            onClick={() => select(m)}
          >
            {label}
          </button>
        ))}
      </div>
      <div className="editorGrid">
        <div>
          <div className="previewControls">
            <Field
              label="Tempo video (s)"
              value={time}
              onChange={(v) => setTime(v as number)}
            />
            <button
              disabled={loading || !Number.isFinite(time) || time < 0}
              onClick={() => {
                setLoading(true);
                setError("");
                setFrameTime(time);
                setFrameRevision((x) => x + 1);
              }}
            >
              Carica frame
            </button>
          </div>
          <div className="geometryViewport" style={{ aspectRatio: aspect }}>
            {image && (
              <img
                src={image}
                alt="Frame originale del video configurato"
                onLoad={(e) => {
                  const img = e.currentTarget;
                  setAspect(img.naturalWidth / img.naturalHeight);
                }}
              />
            )}
            {!image && (
              <p>
                {loading ? "Caricamento frame…" : "Preview non disponibile"}
              </p>
            )}
            <canvas
              ref={canvas}
              width={1000}
              height={Math.round(1000 / aspect)}
              aria-label="Editor geometria; usa i campi X e Y per aggiungere punti da tastiera"
              onClick={(e) => {
                if (!image) return;
                const r = e.currentTarget.getBoundingClientRect();
                const p: Point = [
                  (e.clientX - r.left) / r.width,
                  (e.clientY - r.top) / r.height,
                ];
                if (
                  !line &&
                  points.length >= 3 &&
                  Math.hypot(
                    (p[0] - points[0][0]) * r.width,
                    (p[1] - points[0][1]) * r.height,
                  ) < 14
                ) {
                  setClosed(true);
                  return;
                }
                add([p]);
              }}
            />
          </div>
          <div className="editorActions">
            <button
              onClick={() => changePoints(points.slice(0, -1))}
              disabled={!points.length}
            >
              Annulla punto
            </button>
            <button onClick={() => changePoints([])}>Azzera</button>
            {!line && (
              <button
                disabled={points.length < 3}
                onClick={() => setClosed(true)}
              >
                Chiudi poligono
              </button>
            )}
            <button
              disabled={!draft}
              onClick={() => {
                setPoints(current(config, mode, index));
                setDraft(false);
                onDraftChange(false);
                setClosed(true);
              }}
            >
              Scarta disegno
            </button>
            <button
              className={points.length === 0 ? "danger" : "primary"}
              onClick={apply}
              disabled={!draft}
            >
              {points.length === 0
                ? mode === "crowd_zone" || mode === "line_crossing"
                  ? "Elimina geometria"
                  : "Rimuovi geometria"
                : "Applica geometria"}
            </button>
          </div>
          <div className="coordinateEntry">
            <Field
              label="Posizione orizzontale X (0–1)"
              help="0 = bordo sinistro; 1 = bordo destro."
              value={coord[0]}
              onChange={(v) => setCoord([v as number, coord[1]])}
            />
            <Field
              label="Posizione verticale Y (0–1)"
              help="0 = bordo superiore; 1 = bordo inferiore."
              value={coord[1]}
              onChange={(v) => setCoord([coord[0], v as number])}
            />
            <button onClick={() => add()}>Aggiungi punto</button>
          </div>
          <p>
            {points.length} punti ·{" "}
            {draft ? "Disegno da applicare" : "Geometria applicata alla bozza"}
          </p>
          <ol className="pointList">
            {points.map(([x, y], i) => (
              <li key={i}>
                {x.toFixed(4)}, {y.toFixed(4)}
              </li>
            ))}
          </ol>
        </div>
        <aside>
          {(mode === "crowd_zone" || line) && (
            <>
              <label className="formField">
                Geometria
                <select
                  disabled={draft}
                  value={index}
                  onChange={(e) => select(mode, Number(e.target.value))}
                >
                  {collection.map((v, i) => (
                    <option key={i} value={i}>
                      {v.name}
                    </option>
                  ))}
                </select>
              </label>
              <button className="primary addGeometry" disabled={draft} onClick={create}>
                Aggiungi {line ? "linea" : "area"}
              </button>
              {item && (
                <>
                  <Field
                    label={line ? "Nome della linea" : "Nome dell’area"}
                    help="Usa un nome riconoscibile e univoco, ad esempio Banchina 1 – ingresso."
                    validationError={collection.some((other, i) => i !== index && other.name === item.name) ? "Questo nome è già usato. Scegline uno diverso." : undefined}
                    value={item.name}
                    onChange={(v) => edit("name", v as string)}
                  />
                  {line ? (
                    <>
                      <Field
                        label="Nome direzione della freccia"
                        help="Esempio: verso i binari."
                        value={(item.direction_labels as string[])[0]}
                        onChange={(v) =>
                          edit("direction_labels", [
                            v as string,
                            (item.direction_labels as string[])[1],
                          ])
                        }
                      />
                      <Field
                        label="Nome direzione opposta"
                        help="Esempio: verso la banchina. Deve essere diversa dalla prima."
                        value={(item.direction_labels as string[])[1]}
                        onChange={(v) =>
                          edit("direction_labels", [
                            (item.direction_labels as string[])[0],
                            v as string,
                          ])
                        }
                      />
                      <label className="formField">
                        Direzione vietata
                        <select
                          value={(item.prohibited_direction as string) ?? ""}
                          onChange={(e) =>
                            edit("prohibited_direction", e.target.value || null)
                          }
                        >
                          <option value="">Nessuna</option>
                          {(item.direction_labels as string[]).map((v, i) => (
                            <option key={i}>{v}</option>
                          ))}
                        </select>
                      </label>
                      <Field
                        label="Richiedi treno assente"
                        value={item.require_train_absent as boolean}
                        onChange={(v) => edit("require_train_absent", v)}
                      />
                      <p>
                        Con questa regola attiva, l’allarme scatta solo con
                        treno ASSENTE. PRESENTE e SCONOSCIUTO sopprimono
                        l’allarme.
                      </p>
                    </>
                  ) : null}
                  {(line
                    ? [
                        ["cooldown_s", "Pausa tra segnalazioni (secondi)"],
                        ["hysteresis", "Tolleranza vicino alla linea (0–1)"],
                      ]
                    : [
                        ["area_m2", "Superficie reale dell’area (m²)"],
                        ["warning_density", "Soglia di avviso (persone/m²)"],
                        ["critical_density", "Soglia critica (persone/m²)"],
                        ["hold_s", "Durata minima del superamento (secondi)"],
                        ["cooldown_s", "Pausa tra segnalazioni (secondi)"],
                      ]
                  ).map(([key, label]) => (
                    <Field
                      key={key}
                      label={label}
                      help={{
                        area_m2: "Metri quadrati reali della zona: servono per calcolare la densità. Lascia vuoto se non noti.",
                        warning_density: "Oltre questa densità viene segnalato un avviso. Lascia vuoto per disattivare la soglia.",
                        critical_density: "Deve superare la soglia di avviso. Lascia vuoto per disattivare la soglia critica.",
                        hold_s: "La densità deve superare la soglia per almeno questo tempo prima della segnalazione.",
                        cooldown_s: "Attesa minima prima di ripetere una segnalazione sulla stessa area o linea.",
                        hysteresis: "Ignora piccole oscillazioni vicino alla linea. Frazione della diagonale dell’immagine, non metri.",
                      }[key]}
                      positive={["area_m2", "warning_density", "critical_density"].includes(key)}
                      validationError={key === "critical_density" && item.warning_density != null && item.critical_density != null && Number(item.critical_density) <= Number(item.warning_density) ? "La soglia critica deve essere maggiore della soglia di avviso." : undefined}
                      value={item[key] as number | null}
                      nullable={[
                        "area_m2",
                        "warning_density",
                        "critical_density",
                      ].includes(key)}
                      onChange={(v) => edit(key, v)}
                    />
                  ))}
                </>
              )}
            </>
          )}
          {mode === "roi" && (
            <p>La ROI delimita l’area principale di analisi.</p>
          )}
          {mode === "train_zone" && (
            <p>Questo poligono delimita l’area di rilevamento del treno.</p>
          )}
        </aside>
      </div>
      {confirmClear && token && <Modal title="Cancellare tutte le geometrie?" close={() => setConfirmClear(false)}>
        <p>Verranno rimosse l’area generale, l’area treno, tutte le aree di affollamento e le linee. Il file verrà aggiornato solo con Salva configurazione.</p>
        <div className="editorActions">
          <button autoFocus onClick={() => setConfirmClear(false)}>Mantieni geometrie</button>
          <button className="danger" onClick={() => { clearAll(); setConfirmClear(false); }}>Cancella tutte le geometrie</button>
        </div>
      </Modal>}
      {error && (
        <p role="alert" className="notice error">
          {error}
        </p>
      )}
    </section>
  );
}
