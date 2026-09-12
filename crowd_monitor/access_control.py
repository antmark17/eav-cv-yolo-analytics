from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any
import json
import time
from .atomic_io import write_json


VALID_EVENT_STATUSES = {
    "Nuovo",
    "Preso in carico",
    "In verifica",
    "Risolto",
    "Falso positivo",
}

TERMINAL_EVENT_STATUSES = {"Risolto", "Falso positivo"}


@dataclass(frozen=True, slots=True)
class AccessTokens:
    operator: str
    def is_credential(self, token: str | None) -> bool:
        from hmac import compare_digest
        return bool(token) and compare_digest(token.encode(), self.operator.encode())

    def create_session(self, credential: str | None) -> dict | None:
        import secrets
        import hmac
        if not self.is_credential(credential):
            return None
        expires_at = int(time.time()) + 15 * 60
        payload = f"eav-session.{expires_at}.{secrets.token_urlsafe(32)}"
        signature = hmac.new(self.operator.encode(), payload.encode(), "sha256").hexdigest()
        return {"token": f"{payload}.{signature}", "expires_at": expires_at}

    def is_operator(self, token: str | None) -> bool:
        import hmac
        # Existing local scripts can still use the configured operator credential.
        if self.is_credential(token):
            return True
        if not token or len(token) > 256:
            return False
        try:
            prefix, expiry, nonce, signature = token.split(".")
            payload = f"{prefix}.{expiry}.{nonce}"
            expected = hmac.new(self.operator.encode(), payload.encode(), "sha256").hexdigest()
            return prefix == "eav-session" and int(expiry) > time.time() and hmac.compare_digest(signature, expected)
        except (ValueError, TypeError):
            return False


class EventStatusStore:
    """Small atomic JSON sidecar for operator acknowledgement state."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser().resolve()
        self._lock = Lock()

    def _load_unlocked(self) -> dict[str, dict[str, Any]]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def get_all(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            return dict(self._load_unlocked())

    def update(self, event_id: str, status: str, *, actor: str = "operator") -> dict[str, Any]:
        if not isinstance(status, str) or status not in VALID_EVENT_STATUSES:
            raise ValueError("invalid_event_status")
        with self._lock:
            payload = self._load_unlocked()
            current = payload.get(event_id)
            current_status = current.get("status") if isinstance(current, dict) else None
            if (
                current_status in TERMINAL_EVENT_STATUSES
                and status != current_status
            ):
                raise ValueError("event_status_terminal")
            record = {
                "status": status,
                "updated_at": time.time(),
                "actor": actor,
            }
            payload[event_id] = record
            write_json(self.path, payload, durable=True)
            return record

    def apply(self, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        statuses = self.get_all()
        result: list[dict[str, Any]] = []
        for event in events:
            item = dict(event)
            state = statuses.get(str(item.get("id") or ""))
            item["status"] = state.get("status", "Nuovo") if isinstance(state, dict) else "Nuovo"
            if isinstance(state, dict):
                item["status_updated_at"] = state.get("updated_at")
            result.append(item)
        return result
