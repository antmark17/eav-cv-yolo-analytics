"use client";
import { useEffect, useRef, useState } from "react";
import { apiUrl } from "../eav";
import { saveSession } from "../operator-session";
export function OperatorLogin({
  onSuccess,
  onBack,
}: {
  onSuccess: (token: string) => void;
  onBack: () => void;
}) {
  const [token, setToken] = useState("");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const input = useRef<HTMLInputElement>(null);
  const pending = useRef(false);
  useEffect(() => {
    sessionStorage.removeItem("eav_role");
    sessionStorage.removeItem("eav_token");
  }, []);
  async function login() {
    if (pending.current) return;
    pending.current = true;
    setBusy(true);
    setError("");
    try {
      const response = await fetch(apiUrl("/api/auth/session"), {
        method: "POST",
        headers: { Authorization: `Bearer ${token.trim()}` },
        signal: AbortSignal.timeout(10000),
      });
      if (!response.ok) {
        setError("Codice non valido. Controlla il token operatore e riprova.");
        input.current?.focus();
        return;
      }
      const session = await response.json();
      saveSession(session);
      onSuccess(session.token);
    } catch {
      setError(
        "Server non raggiungibile. Verifica che il servizio sia avviato e riprova.",
      );
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }
  return (
    <main className="loginPage">
      <section className="loginCard">
        <div className="loginBrand">
          <b>EAV</b>
          <strong>Area Operatore</strong>
        </div>
        <h1>Accesso riservato</h1>
        <p>
          Usa il codice operatore per gestire gli eventi e accedere alla console
          AI. L’accesso resta valido in questa scheda per 15 minuti, anche quando esci dalla vista operatore.
        </p>
        <form
          noValidate
          onSubmit={(e) => {
            e.preventDefault();
            void login();
          }}
        >
          <label className="tokenField" htmlFor="operator-token">
            Codice operatore
            <input
              ref={input}
              id="operator-token"
              type={show ? "text" : "password"}
              autoComplete="current-password"
              value={token}
              onChange={(e) => setToken(e.target.value)}
              aria-invalid={!!error}
              aria-describedby="login-error"
            />
          </label>
          <button
            type="button"
            onClick={() => setShow(!show)}
            aria-pressed={show}
          >
            {show ? "Nascondi codice" : "Mostra codice"}
          </button>
          <p id="login-error" role="alert" className="loginError">
            {error}
          </p>
          <button
            disabled={busy || !token.trim()}
            className="primary loginButton"
          >
            {busy ? "Verifica in corso…" : "Accedi"}
          </button>
        </form>
        <button className="backButton" onClick={onBack}>
          ← Torna alla home
        </button>
      </section>
    </main>
  );
}
