"use client";
import { useEffect, useState } from "react";
import { apiUrl } from "./eav";

const KEY = "eav_operator_session";
const CHANGED = "eav-session-changed";
type Session = { token: string; expires_at: number };

export function readSession(): Session | null {
  try {
    const session = JSON.parse(sessionStorage.getItem(KEY) || "null");
    if (session && typeof session.token === "string" && session.token &&
        Number.isFinite(session.expires_at) && session.expires_at * 1000 > Date.now()) {
      return session;
    }
    sessionStorage.removeItem(KEY);
  } catch { /* Unavailable storage is treated as an unauthenticated session. */ }
  return null;
}

export function saveSession(session: Session) {
  sessionStorage.removeItem("eav_operator_token");
  sessionStorage.setItem(KEY, JSON.stringify(session));
  window.dispatchEvent(new Event(CHANGED));
}

export function useOperatorSession() {
  const [session, setSession] = useState<Session | null>(null);
  const [checked, setChecked] = useState(false);
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>;
    const sync = () => {
      clearTimeout(timer);
      const next = readSession();
      setSession(next);
      setChecked(true);
      if (next) timer = setTimeout(sync, Math.max(0, next.expires_at * 1000 - Date.now()));
    };
    sync();
    window.addEventListener(CHANGED, sync);
    window.addEventListener("focus", sync);
    document.addEventListener("visibilitychange", sync);
    return () => {
      clearTimeout(timer);
      window.removeEventListener(CHANGED, sync);
      window.removeEventListener("focus", sync);
      document.removeEventListener("visibilitychange", sync);
    };
  }, []);
  const token = session?.token ?? "";
  useEffect(() => {
    if (!token) return;
    const controller = new AbortController();
    fetch(apiUrl("/api/auth/check"), { headers: { Authorization: `Bearer ${token}` }, signal: controller.signal })
      .then((response) => {
        if ((response.status === 401 || response.status === 403) && readSession()?.token === token) {
          sessionStorage.removeItem(KEY);
          window.dispatchEvent(new Event(CHANGED));
        }
      }).catch(() => { /* A network interruption does not invalidate the session. */ });
    return () => controller.abort();
  }, [token]);
  return { token, checked };
}
