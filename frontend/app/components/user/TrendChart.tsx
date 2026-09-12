export type Sample = {
  timestamp: number;
  people: number;
  density: number | null;
};
const clock = (t: number) =>
  new Date(t * 1000).toLocaleTimeString("it-IT", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    timeZone: "Europe/Rome",
  });
export function TrendChart({
  samples,
  metric,
  title,
}: {
  samples: Sample[];
  metric: "people" | "density";
  title: string;
}) {
  const valid = samples.filter(
    (s) => s[metric] != null && Number.isFinite(s[metric]),
  );
  const max = Math.max(
    metric === "people" ? 1 : 0.1,
    ...valid.map((s) => s[metric]!),
  );
  const start = samples[0]?.timestamp ?? 0;
  const end = samples.at(-1)?.timestamp ?? start;
  const x = (t: number) => 46 + ((t - start) / Math.max(1, end - start)) * 600;
  const y = (v: number) => 168 - (v / max) * 136;
  const path = samples
    .map((s, i) =>
      s[metric] == null
        ? ""
        : `${i === 0 || samples[i - 1][metric] == null ? "M" : "L"}${x(s.timestamp)},${y(s[metric]!)}`,
    )
    .join(" ");
  return (
    <article className="panel trend">
      <h2>{title}</h2>
      {valid.length < 2 ? (
        <div className="chartEmpty">
          {valid.length
            ? "Primo dato ricevuto. Il grafico apparirà ai prossimi aggiornamenti."
            : "In attesa dei dati della stazione."}
        </div>
      ) : (
        <svg
          viewBox="0 0 680 214"
          role="img"
          aria-label={`${title}: da ${clock(start)} a ${clock(end)}; ultimo valore ${valid.at(-1)![metric]!.toLocaleString("it-IT")}`}
        >
          <line x1="46" x2="646" y1="168" y2="168" className="chartGrid" />
          <line x1="46" x2="646" y1="32" y2="32" className="chartGrid" />
          <text x="8" y="36">
            {max.toLocaleString("it-IT", { maximumFractionDigits: 2 })}
          </text>
          <text x="22" y="172">
            0
          </text>
          <path d={path} className="chartLine" />
          <text x="46" y="199">
            {clock(start)}
          </text>
          <text x="646" y="199" textAnchor="end">
            {clock(end)}
          </text>
        </svg>
      )}
      <small>
        {metric === "people" ? "Persone presenti" : "Densità · persone/m²"} ·
        ora di Roma · storico della sessione
      </small>
    </article>
  );
}
