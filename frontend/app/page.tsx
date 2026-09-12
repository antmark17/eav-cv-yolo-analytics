"use client";
import { useEffect, useState } from "react";
import { readSession, useOperatorSession } from "./operator-session";
import OperatorDashboard from "./components/operator/OperatorDashboard";
import UserDashboard from "./components/user/UserDashboard";
import { OperatorLogin } from "./components/OperatorLogin";
export default function Home() {
  const [view, setView] = useState<"home" | "login" | "user" | "operator">(
    "home",
  );
  const { token, checked } = useOperatorSession();
  useEffect(() => {
    const syncRoute = () => {
      if (new URLSearchParams(location.search).get("view") === "operator") setView("operator");
    };
    syncRoute();
    window.addEventListener("popstate", syncRoute);
    return () => window.removeEventListener("popstate", syncRoute);
  }, []);
  const enterOperator = () => setView(readSession() ? "operator" : "login");
  const [dark, setDark] = useState(false);
  const toggleTheme = () => {
    setDark(!dark);
    document.documentElement.dataset.theme = dark ? "light" : "dark";
  };
  const logout = () => {
    history.replaceState(null, "", "/");
    setView("home");
  };
  if (!checked) return <main className="loginPage"><p role="status">Verifica accesso…</p></main>;
  if (view === "operator" && token)
    return <OperatorDashboard {...{ token, dark, toggleTheme, logout }} />;
  if (view === "user")
    return <UserDashboard {...{ dark, toggleTheme, logout }} />;
  if (view === "login" || (view === "operator" && !token))
    return (
      <OperatorLogin
        onSuccess={() => {
          setView("operator");
        }}
        onBack={() => setView("home")}
      />
    );
  return (
    <main className="loginPage">
      <section className="loginCard landingCard">
        <div className="loginBrand">
          <b>EAV</b>
          <span>
            <strong>Smart Station</strong>
            <small>Informazioni e presidio di stazione</small>
          </span>
        </div>
        <h1>
          La stazione,
          <br />
          in tempo reale.
        </h1>
        <p>
          Consulta l’affollamento delle aree monitorate e trova lo spazio meno
          affollato.
        </p>
        <div className="entryRoutes">
          <button className="primary" onClick={() => setView("user")}>
            <strong>Accedi come passeggero →</strong>
            <small>Accesso pubblico · nessuna credenziale</small>
          </button>
          <button onClick={enterOperator}>
            <strong>Area Operatore EAV →</strong>
            <small>Gestione eventi e console tecnica · accesso riservato</small>
          </button>
        </div>
      </section>
    </main>
  );
}
