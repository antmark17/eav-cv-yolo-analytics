"use client";
export function AppHeader({
  title,
  subtitle,
  connected,
  dark,
  toggleTheme,
  logout,
}: {
  title: string;
  subtitle: string;
  connected: boolean;
  dark: boolean;
  toggleTheme: () => void;
  logout: () => void;
}) {
  return (
    <header className="top">
      <div className="brand">
        <b>EAV</b>
        <span>
          <strong>{title}</strong>
          <small>{subtitle}</small>
        </span>
      </div>
      <div className="topActions">
        <span className={connected ? "live" : "offline"}>
          {connected ? "● Connesso" : "○ Connessione assente"}
        </span>
        <button
          aria-label={dark ? "Attiva tema chiaro" : "Attiva tema scuro"}
          onClick={toggleTheme}
        >
          {dark ? "☀" : "◐"}
        </button>
        <button onClick={logout}>Esci</button>
      </div>
    </header>
  );
}

export function Kpi({
  label,
  value,
  note,
}: {
  label: string;
  value: string;
  note: string;
}) {
  return (
    <article className="kpi">
      <small>{label}</small>
      <strong>{value}</strong>
      <em>{note}</em>
    </article>
  );
}
