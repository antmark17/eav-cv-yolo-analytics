from __future__ import annotations

import argparse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import json
import os
import re
import time

from crowd_monitor.access_control import AccessTokens, EventStatusStore, VALID_EVENT_STATUSES
from crowd_monitor.dashboard import CanonicalJsonlDashboardStore
from crowd_monitor.frontend_events import public_events
from crowd_monitor.demo_config import DemoConfigService, PreviewError
from crowd_monitor.presentation import public_station_state, operator_live_state


class EavApiHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    store: CanonicalJsonlDashboardStore
    status_store: EventStatusStore
    access: AccessTokens
    live_state_path: Path
    live_cv_path: Path
    demo_config: DemoConfigService

    def handle(self) -> None:
        try:
            super().handle()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass  # A browser may close a keep-alive request at any point.

    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, Last-Event-ID")

    def _send_json(self, payload: object, status: HTTPStatus = HTTPStatus.OK) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self._cors()
        self.end_headers()
        self.wfile.write(data)

    def _token(self, query: dict[str, list[str]]) -> str | None:
        token = query.get("access_token", [None])[0]
        if token:
            return token
        auth = self.headers.get("Authorization", "")
        if auth.lower().startswith("bearer "):
            return auth[7:].strip()
        return None

    def _require_operator(self, query: dict[str, list[str]]) -> bool:
        if self.access.is_operator(self._token(query)):
            return True
        self._send_json({"ok": False, "error": "forbidden"}, HTTPStatus.FORBIDDEN)
        return False

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(HTTPStatus.NO_CONTENT)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _read_live_state(self) -> dict:
        try:
            payload = json.loads(self.live_state_path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {}
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {
                "running": False,
                "station": None,
                "people": 0,
                "objects": {},
                "train_state": "UNKNOWN",
                "density_people_m2": None,
                "zones": [],
            }

    def _state_updated_at(self) -> float | None:
        try:
            return self.live_state_path.stat().st_mtime
        except OSError:
            return None

    def _public_station_state(self) -> dict:
        return public_station_state(self._read_live_state(), updated_at=self._state_updated_at())

    def _operator_live_state(self) -> dict:
        return operator_live_state(
            self._read_live_state(), cv_available=self.live_cv_path.is_file(),
            updated_at=self._state_updated_at(),
        )

    def _operator_events(self, limit: int = 200) -> list[dict]:
        snapshot = self.store.snapshot(limit=max(1, min(limit, 2000)))
        events = self.status_store.apply(public_events(snapshot.get("events", [])))
        for item in events:
            event_id = str(item.get("id") or "")
            if event_id and item.get("frame_url"):
                item["frame_url"] = f"/api/operator/event-frame/{event_id}"
            if event_id and item.get("clean_frame_url"):
                item["clean_frame_url"] = f"/api/operator/event-frame/{event_id}?variant=clean"
            # File/source identity is intentionally not shown in presentation UI.
            item.pop("source", None)
            details = item.get("details")
            if isinstance(details, dict):
                details.pop("source_name", None)
                details.pop("frame_index", None)
        return events

    def _stream_authorized(self) -> bool:
        parsed = urlparse(self.path)
        valid = parsed.path.startswith("/api/user/") or self.access.is_operator(self._token(parse_qs(parsed.query)))
        if not valid:
            self.close_connection = True
        return valid

    def _start_sse(self) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-store")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self._cors()
        self.end_headers()

    def _stream_json(self, event_name: str, getter, *, interval: float = 0.15) -> None:
        self._start_sse()
        previous = None
        last_keepalive = time.monotonic()
        try:
            while self._stream_authorized():
                payload = getter()
                serialized = json.dumps({k: v for k, v in payload.items() if k != "updated_at"}, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
                if serialized != previous:
                    self.wfile.write(f"event: {event_name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n".encode("utf-8"))
                    self.wfile.flush()
                    previous = serialized
                if time.monotonic() - last_keepalive >= 10:
                    self.wfile.write(b": keep-alive\n\n")
                    self.wfile.flush()
                    last_keepalive = time.monotonic()
                time.sleep(interval)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            return

    def _stream_events(self, after: str | None) -> None:
        self._start_sse()

        initial = self._operator_events(limit=1000)
        snapshot = json.dumps({"events": initial}, ensure_ascii=False)
        try:
            self.wfile.write(f"event: events_snapshot\ndata: {snapshot}\n\n".encode("utf-8"))
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            return
        initial_ids = [str(item.get("id") or "") for item in initial]
        sent: dict[str, str] = {}
        # Existing history is not replayed by default; only records after the
        # browser's last id are replayed. Status changes are re-emitted later.
        for item in initial:
            event_id = str(item.get("id") or "")
            sent[event_id] = json.dumps(item, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        if after:
            try:
                index = initial_ids.index(after)
            except ValueError:
                pending = []
            else:
                pending = list(reversed(initial[:index]))
            for event in pending:
                self._send_event(event)

        last_keepalive = time.monotonic()
        try:
            while self._stream_authorized():
                time.sleep(0.25)
                current = self._operator_events(limit=1000)
                current_ids = {str(event.get("id") or "") for event in current}
                sent = {key: value for key, value in sent.items() if key in current_ids}
                for event in reversed(current):
                    event_id = str(event.get("id") or "")
                    serialized = json.dumps(event, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
                    previous = sent.get(event_id)
                    if previous is None or previous != serialized:
                        self._send_event(event)
                        sent[event_id] = serialized
                if time.monotonic() - last_keepalive >= 10:
                    self.wfile.write(b": keep-alive\n\n")
                    self.wfile.flush()
                    last_keepalive = time.monotonic()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            return

    def _send_event(self, event: dict) -> None:
        data = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
        event_id = str(event.get("id") or "")
        self.wfile.write(f"id: {event_id}\nevent: analytics_event\ndata: {data}\n\n".encode("utf-8"))
        self.wfile.flush()

    def _stream_cv(self) -> None:
        boundary = "eavframe"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", f"multipart/x-mixed-replace; boundary={boundary}")
        self.send_header("Cache-Control", "no-cache, no-store")
        self.send_header("Connection", "keep-alive")
        self._cors()
        self.end_headers()
        last_mtime = None
        try:
            while self._stream_authorized():
                try:
                    stat = self.live_cv_path.stat()
                    mtime = stat.st_mtime_ns
                    if mtime != last_mtime:
                        data = self.live_cv_path.read_bytes()
                        self.wfile.write(f"--{boundary}\r\nContent-Type: image/jpeg\r\nContent-Length: {len(data)}\r\n\r\n".encode("ascii"))
                        self.wfile.write(data)
                        self.wfile.write(b"\r\n")
                        self.wfile.flush()
                        last_mtime = mtime
                except FileNotFoundError:
                    pass
                time.sleep(0.02)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            return

    def _send_event_frame(self, event_id: str, *, variant: str = "annotated") -> None:
        if not event_id or "/" in event_id or "\\" in event_id:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        if variant not in {"annotated", "clean"}:
            self._send_json({"ok": False, "error": "invalid_frame_variant"}, HTTPStatus.BAD_REQUEST)
            return
        path = self.store.event_frame_path(event_id, variant=variant)
        if path is None:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        data = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self._cors()
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)

        if parsed.path == "/api/auth/check":
            valid = self.access.is_operator(self._token(query))
            self._send_json({"ok": valid, "role": "operator" if valid else None}, HTTPStatus.OK if valid else HTTPStatus.FORBIDDEN)
            return

        if parsed.path.startswith("/api/demo/"):
            if not self._require_operator(query): return
            try:
                if parsed.path == "/api/demo/config":
                    self._send_json(self.demo_config.get_public_config())
                elif parsed.path == "/api/demo/preview-frame":
                    if set(query) - {"time_s", "access_token"}:
                        raise ValueError("Parametro preview non consentito")
                    time_s = float(query["time_s"][0]) if "time_s" in query else None
                    data = self.demo_config.get_preview_frame(time_s=time_s)
                    self.send_response(HTTPStatus.OK)
                    self.send_header("Content-Type", "image/jpeg")
                    self.send_header("Content-Length", str(len(data)))
                    self.send_header("Cache-Control", "no-store")
                    self._cors()
                    self.end_headers()
                    self.wfile.write(data)
                else:
                    self.send_error(HTTPStatus.NOT_FOUND)
            except PreviewError as exc:
                self._send_json({"ok": False, "error": str(exc)}, exc.status)
            except (ValueError, TypeError):
                self._send_json({"ok": False, "error": "Configurazione o parametro non valido"}, HTTPStatus.BAD_REQUEST)
            except OSError:
                self._send_json({"ok": False, "error": "Configurazione non disponibile"}, HTTPStatus.SERVICE_UNAVAILABLE)
            return

        if parsed.path == "/api/user/station":
            self._send_json(self._public_station_state())
            return
        if parsed.path == "/api/user/station/stream":
            self._stream_json("station_congestion", self._public_station_state, interval=0.25)
            return

        if parsed.path == "/api/operator/events":
            if not self._require_operator(query): return
            try:
                limit = int(query.get("limit", ["200"])[0])
            except ValueError:
                limit = 200
            self._send_json({"events": self._operator_events(limit=limit)})
            return
        if parsed.path == "/api/operator/events/stream":
            if not self._require_operator(query): return
            after = query.get("after", [None])[0] or self.headers.get("Last-Event-ID")
            self._stream_events(after)
            return
        if parsed.path == "/api/operator/live":
            if not self._require_operator(query): return
            self._send_json(self._operator_live_state())
            return
        if parsed.path == "/api/operator/live/stream":
            if not self._require_operator(query): return
            self._stream_json("operator_live", self._operator_live_state, interval=0.25)
            return
        if parsed.path == "/api/operator/cv/stream":
            if not self._require_operator(query): return
            self._stream_cv()
            return
        if parsed.path.startswith("/api/operator/event-frame/"):
            if not self._require_operator(query): return
            event_id = parsed.path.removeprefix("/api/operator/event-frame/").strip()
            variant = query.get("variant", ["annotated"])[0]
            self._send_event_frame(event_id, variant=variant)
            return

        self.send_error(HTTPStatus.NOT_FOUND)

    def do_PUT(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if not self._require_operator(parse_qs(parsed.query)):
            self.close_connection = True
            return
        if parsed.path != "/api/demo/config":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 131072:
                self.close_connection = True
                raise ValueError("Dimensione richiesta non valida")
            patch = json.loads(self.rfile.read(length).decode("utf-8"))
            config = self.demo_config.update_config(patch)
            self._send_json({"ok": True, "restart_required": True, "config": config})
        except (ValueError, TypeError, UnicodeError) as exc:
            self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except OSError:
            self._send_json({"ok": False, "error": "Configurazione non disponibile"}, HTTPStatus.SERVICE_UNAVAILABLE)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        if parsed.path == "/api/auth/session":
            # Session issuance accepts the credential only, never an old session.
            session = self.access.create_session(self._token({}))
            self._send_json(session or {"ok": False, "error": "forbidden"},
                            HTTPStatus.OK if session else HTTPStatus.FORBIDDEN)
            return
        if parsed.path.startswith("/api/operator/events/") and parsed.path.endswith("/status"):
            if not self._require_operator(query): return
            event_id = parsed.path.removeprefix("/api/operator/events/").removesuffix("/status").strip("/")
            if not event_id or "/" in event_id or "\\" in event_id:
                self._send_json({"ok": False, "error": "invalid_event_id"}, HTTPStatus.BAD_REQUEST)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 <= length <= 4096:
                    self.close_connection = True
                    self._send_json({"ok": False, "error": "invalid_body_length"}, HTTPStatus.BAD_REQUEST)
                    return
                payload = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
            except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
                self._send_json({"ok": False, "error": "invalid_json"}, HTTPStatus.BAD_REQUEST)
                return
            status = payload.get("status") if isinstance(payload, dict) else None
            if not isinstance(status, str) or status not in VALID_EVENT_STATUSES:
                self._send_json({"ok": False, "error": "invalid_status", "allowed": sorted(VALID_EVENT_STATUSES)}, HTTPStatus.BAD_REQUEST)
                return
            try:
                record = self.status_store.update(event_id, status)
            except ValueError as exc:
                if str(exc) == "event_status_terminal":
                    self._send_json(
                        {"ok": False, "error": "event_status_terminal"},
                        HTTPStatus.CONFLICT,
                    )
                else:
                    self._send_json({"ok": False, "error": "invalid_status"}, HTTPStatus.BAD_REQUEST)
                return
            except OSError:
                self._send_json({"ok": False, "error": "status_store_unavailable"}, HTTPStatus.SERVICE_UNAVAILABLE)
                return
            self._send_json({"ok": True, "id": event_id, **record})
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def log_message(self, fmt: str, *args: object) -> None:
        path = str(args[0]) if args else ""
        if "/stream" in path:
            return
        # Query strings may contain EventSource access tokens.
        safe = tuple(re.sub(r"([?&]access_token=)[^&\s]*", r"\1[redacted]", str(arg)) for arg in args)
        super().log_message(fmt, *safe)


def main() -> None:
    parser = argparse.ArgumentParser(description="EAV presentation API: operator events/CV and user congestion view")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--events", default="outputs/video_events.jsonl")
    parser.add_argument("--live-state", default="outputs/live_state.json")
    parser.add_argument("--live-cv", default="outputs/live_cv.jpg")
    parser.add_argument("--event-status", default="outputs/event_status.json")
    parser.add_argument("--operator-token", default=os.environ.get("EAV_OPERATOR_TOKEN", "operator-demo"))
    parser.add_argument("--config", default="configs/video.local.yaml")
    args = parser.parse_args()

    events_path = Path(args.events).expanduser().resolve()
    events_path.parent.mkdir(parents=True, exist_ok=True)
    events_path.touch(exist_ok=True)
    store = CanonicalJsonlDashboardStore(events_path, max_events=5000)
    handler = type("ConfiguredEavApiHandler", (EavApiHandler,), {
        "store": store,
        "demo_config": DemoConfigService(args.config),
        "status_store": EventStatusStore(args.event_status),
        "access": AccessTokens(args.operator_token),
        "live_state_path": Path(args.live_state).expanduser().resolve(),
        "live_cv_path": Path(args.live_cv).expanduser().resolve(),
    })
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print("EAV presentation API")
    print(f"  user congestion: http://{args.host}:{args.port}/api/user/station")
    print(f"  operator events: http://{args.host}:{args.port}/api/operator/events")
    print(f"  operator CV:     http://{args.host}:{args.port}/api/operator/cv/stream")
    print("  analysis is started only by run_video.py; the frontend cannot upload/start videos.")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
