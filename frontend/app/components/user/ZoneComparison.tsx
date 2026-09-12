import { densityText, levelLabel, type StationState } from "../../eav";
export function RecommendedZone({ zones }: { zones: StationState["zones"] }) {
  const zone = zones
    .filter(
      (z) =>
        z.density_people_m2 != null &&
        Number.isFinite(z.density_people_m2) &&
        z.density_people_m2 >= 0,
    )
    .sort((a, b) => a.density_people_m2! - b.density_people_m2!)[0];
  return (
    <article className="panel recommended">
      <small>AREA CONSIGLIATA</small>
      <h2>{zone ? zone.name.replaceAll("_", " ") : "In attesa dei dati"}</h2>
      <p>
        {zone
          ? "Affollamento più basso tra le aree monitorate."
          : "L’area consigliata comparirà quando saranno disponibili densità valide."}
      </p>
      {zone && <strong>{densityText(zone.density_people_m2)}</strong>}
    </article>
  );
}
export function ZoneComparison({ zones }: { zones: StationState["zones"] }) {
  const max = Math.max(1, ...zones.map((z) => z.density_people_m2 ?? 0));
  return (
    <article className="panel">
      <h2>Confronto tra aree</h2>
      {zones.length ? (
        <div className="zoneBars">
          {zones.map((zone) => (
            <div key={zone.name}>
              <div>
                <strong>{zone.name.replaceAll("_", " ")}</strong>
                <span>{densityText(zone.density_people_m2)}</span>
              </div>
              <div className="barTrack">
                <span
                  style={{
                    width: `${Math.max(0, (zone.density_people_m2 ?? 0) / max) * 100}%`,
                  }}
                />
              </div>
              <small>
                {zone.people ?? "—"} persone · {levelLabel(zone.level)}
              </small>
            </div>
          ))}
        </div>
      ) : (
        <p>Nessuna area disponibile. Attendi l’avvio dell’analisi.</p>
      )}
    </article>
  );
}
