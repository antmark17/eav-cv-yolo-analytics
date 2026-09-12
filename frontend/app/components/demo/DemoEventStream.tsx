import type { Alert } from "../../eav";
export function DemoEventStream({
  events,
  connected,
}: {
  events: Alert[];
  connected: boolean;
}) {
  return (
    <article className="panel">
      <div className="sectionHead">
        <h2>Eventi live</h2>
        <span>{connected ? "Connesso" : "Riconnessione…"}</span>
      </div>
      <div className="technicalEvents">
        {events.length ? (
          events.map((e) => (
            <details key={e.id}>
              <summary>
                <span>
                  {e.occurred_at
                    ? new Date(e.occurred_at).toLocaleTimeString("it-IT", {
                        timeZone: "Europe/Rome",
                      })
                    : "—"}
                </span>{" "}
                <strong>{e.event_type}</strong>
                <small>
                  {e.priority} · {e.place} · {e.status}
                </small>
              </summary>
              <pre>
                {JSON.stringify(
                  {
                    confidence: e.confidence,
                    video_time_s: e.video_time_s,
                    details: e.details,
                  },
                  null,
                  2,
                )}
              </pre>
            </details>
          ))
        ) : (
          <p>
            Nessun evento ricevuto. Gli eventi compariranno durante l’analisi.
          </p>
        )}
      </div>
    </article>
  );
}
