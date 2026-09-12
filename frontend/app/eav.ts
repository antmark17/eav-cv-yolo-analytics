export type Role = "operator" | "user";
export type Priority = "Critico" | "Alto" | "Medio" | "Basso";
export type Status =
  "Nuovo" | "Preso in carico" | "In verifica" | "Risolto" | "Falso positivo";
export type EventType =
  | "track_crossing"
  | "high_crowd_density"
  | "unattended_luggage"
  | "unsupervised_animal";

export type Alert = {
  id: string;
  event_type: EventType;
  title: string;
  priority: Priority;
  station: string;
  place: string;
  confidence: number | null;
  occurred_at: string | null;
  video_time_s: number | null;
  frame_url: string | null;
  clean_frame_url?: string | null;
  status: Status;
  icon: string;
  details: Record<string, unknown>;
};

export type OperatorLive = {
  station: string;
  people: number;
  train_state: string;
  density_people_m2: number | null;
  zones: Array<{
    name: string;
    people?: number;
    density_people_m2: number | null;
    level: string | null;
  }>;
  cv_available: boolean;
  cv_live?: boolean;
  running?: boolean;
  updated_at?: number | null;
};

export type StationState = {
  people: number;
  updated_at?: number | null;
  station: string;
  congestion: string;
  density_people_m2: number | null;
  zones: Array<{
    name: string;
    people?: number;
    density_people_m2: number | null;
    level: string | null;
  }>;
};

export const API_BASE = (
  process.env.NEXT_PUBLIC_EAV_EVENT_API || "http://127.0.0.1:8765"
).replace(/\/$/, "");
export const rank: Record<Priority, number> = {
  Critico: 4,
  Alto: 3,
  Medio: 2,
  Basso: 1,
};
export const eventLabels: Record<EventType, string> = {
  track_crossing: "Attraversamento binari",
  high_crowd_density: "Sovraffollamento",
  unattended_luggage: "Bagaglio abbandonato",
  unsupervised_animal: "Animale non supervisionato",
};

export function operatorUrl(path: string, token: string) {
  const separator = path.includes("?") ? "&" : "?";
  return `${API_BASE}${path}${separator}access_token=${encodeURIComponent(token)}`;
}

export function densityText(value: number | null | undefined) {
  return value == null || !Number.isFinite(value)
    ? "—"
    : `${value.toLocaleString("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} p/m²`;
}

export function levelLabel(value: string | null | undefined) {
  const level = String(value || "unknown").toLowerCase();
  if (["critical", "high"].includes(level)) return "Alta";
  if (["warning", "medium"].includes(level)) return "Moderata";
  if (["normal", "low"].includes(level)) return "Regolare";
  return "Non disponibile";
}

export function eventFrame(alert: Alert, token: string) {
  if (!alert.frame_url) return null;
  return operatorUrl(alert.frame_url, token);
}

export function eventFrames(alert: Alert, token: string) {
  const frames: Array<{ key: "annotated" | "clean"; label: string; url: string }> = [];
  if (alert.frame_url) {
    frames.push({
      key: "annotated",
      label: "Con bounding box",
      url: operatorUrl(alert.frame_url, token),
    });
  }
  if (alert.clean_frame_url) {
    frames.push({
      key: "clean",
      label: "Senza bounding box",
      url: operatorUrl(alert.clean_frame_url, token),
    });
  }
  return frames;
}

export function isTerminalStatus(status: Status) {
  return status === "Risolto" || status === "Falso positivo";
}

export function apiUrl(path: string) {
  return `${API_BASE}${path}`;
}

export function requestError(error: unknown): string {
  if (error instanceof TypeError) return "Server non raggiungibile. Verifica la connessione e riprova; le modifiche sono conservate.";
  if (error instanceof Error && ["TimeoutError", "AbortError"].includes(error.name)) return "Tempo di attesa scaduto. Verifica la connessione e riprova.";
  return error instanceof Error ? error.message : "Richiesta non riuscita. Riprova.";
}
