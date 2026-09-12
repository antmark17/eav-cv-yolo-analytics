"use client";
import { useEffect, useState } from "react";
import { apiUrl, densityText, levelLabel, type StationState } from "../../eav";
import { AppHeader, Kpi } from "../AppHeader";
import { TrendChart, type Sample } from "./TrendChart";
import { ZoneComparison, RecommendedZone } from "./ZoneComparison";
export default function UserDashboard({
  dark,
  toggleTheme,
  logout,
}: {
  dark: boolean;
  toggleTheme: () => void;
  logout: () => void;
}) {
  const [station, setStation] = useState<StationState | null>(null);
  const [connected, setConnected] = useState(false);
  const [samples, setSamples] = useState<Sample[]>([]);
  useEffect(() => {
    const source = new EventSource(apiUrl("/api/user/station/stream"));
    source.onopen = () => setConnected(true);
    source.onerror = () => setConnected(false);
    source.addEventListener("station_congestion", (raw) => {
      try {
        const data = JSON.parse(
          (raw as MessageEvent<string>).data,
        ) as StationState;
        setStation(data);
        if (data.updated_at)
          setSamples((current) =>
            [
              ...current,
              {
                timestamp: data.updated_at!,
                people: data.people,
                density: data.density_people_m2,
              },
            ].slice(-300),
          );
      } catch {
        /* preserve last valid data */
      }
    });
    return () => source.close();
  }, []);
  return (
    <div className="app">
      <AppHeader
        title="EAV Smart Station"
        subtitle="Informazioni per i passeggeri"
        {...{ connected, dark, toggleTheme, logout }}
      />
      <main className="page passengerPage">
        <section className="stationHero">
          <small>STATO DELLA STAZIONE</small>
          <h1>{station?.station || "Stazione EAV"}</h1>
          <p>Trova lo spazio meno affollato tra le aree monitorate.</p>
        </section>
        {!connected && (
          <p role="status" className="notice">
            Connessione non disponibile.{" "}
            {station
              ? "I dati mostrati sono gli ultimi ricevuti."
              : "Verifica che il servizio di stazione sia avviato."}{" "}
            Riconnessione automatica in corso.
          </p>
        )}
        <section className="kpis">
          <Kpi
            label="Persone presenti"
            value={station?.updated_at ? String(station.people) : "—"}
            note="nelle aree monitorate"
          />
          <Kpi
            label="Densità"
            value={densityText(station?.density_people_m2)}
            note="persone per metro quadrato"
          />
          <Kpi
            label="Affollamento"
            value={levelLabel(station?.congestion)}
            note="livello complessivo"
          />
          <Kpi
            label="Ultimo aggiornamento"
            value={
              station?.updated_at
                ? new Date(station.updated_at * 1000).toLocaleTimeString(
                    "it-IT",
                    { timeZone: "Europe/Rome" },
                  )
                : "—"
            }
            note="ora di Roma"
          />
        </section>
        <div className="dashboardColumns">
          <TrendChart
            samples={samples}
            metric="people"
            title="Presenze nel tempo"
          />
          <TrendChart
            samples={samples}
            metric="density"
            title="Densità nel tempo"
          />
          <ZoneComparison zones={station?.zones ?? []} />
          <RecommendedZone zones={station?.zones ?? []} />
        </div>
        <p className="privacy">
          Informazioni aggregate sulle aree monitorate. Lo storico si aggiorna
          durante questa visita e riparte al ricaricamento della pagina.
        </p>
      </main>
    </div>
  );
}
