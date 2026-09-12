/* eslint-disable @next/next/no-img-element -- Local authenticated JPEG/MJPEG or object URLs must reach the browser directly. */
import { operatorUrl, type OperatorLive } from "../../eav";
export function DemoCvPanel({
  token,
  live,
}: {
  token: string;
  live: OperatorLive | null;
}) {
  return (
    <article className="cvPanel">
      <div className="sectionHead">
        <h2>Computer vision live</h2>
        <span className={live?.cv_live ? "livePill" : "mutedPill"}>
          {live?.cv_live
            ? "LIVE"
            : live?.cv_available
              ? "Ultimo frame"
              : "In attesa"}
        </span>
      </div>
      <div className="cvViewport">
        {live?.cv_available ? (
          <img
            src={operatorUrl("/api/operator/cv/stream", token)}
            alt="Analisi video con bounding box, track ID, ROI e linee"
          />
        ) : (
          <p>Avvia l’analisi locale per visualizzare il video annotato.</p>
        )}
      </div>
    </article>
  );
}
