from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any
import json
import time


@dataclass(frozen=True, slots=True)
class DashboardEvent:
    """One canonical analytics event enriched with its source record context."""

    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return dict(self.payload)


class CanonicalJsonlDashboardStore:
    """Incrementally tails the canonical pipeline JSONL for the local dashboard.

    The canonical stream is deliberately used instead of Team B's strict export:
    Team B only supports a subset of analytics event types, while the dashboard
    must expose every event emitted by the local analytics engine.
    """

    def __init__(self, path: str | Path, *, max_events: int = 1000) -> None:
        if max_events <= 0:
            raise ValueError("max_events must be greater than zero")
        self.path = Path(path)
        self.max_events = max_events
        self._lock = Lock()
        self._offset = 0
        self._file_identity: tuple[int, int] | None = None
        self._events: deque[DashboardEvent] = deque(maxlen=max_events)
        self._event_counts: Counter[str] = Counter()
        self._severity_counts: Counter[str] = Counter()
        self._latest_record: dict[str, Any] | None = None
        self._latest_timestamp: float | None = None
        self._records_read = 0
        self._parse_errors = 0

    def _reset_for_new_file(self) -> None:
        self._offset = 0
        self._events.clear()
        self._event_counts.clear()
        self._severity_counts.clear()
        self._latest_record = None
        self._latest_timestamp = None
        self._records_read = 0
        self._parse_errors = 0

    @staticmethod
    def _identity(stat_result: Any) -> tuple[int, int]:
        # st_dev/st_ino work on Unix and are populated on modern Windows Python.
        # Size-based truncation detection below remains the fallback.
        return (int(getattr(stat_result, "st_dev", 0)), int(getattr(stat_result, "st_ino", 0)))

    def refresh(self) -> None:
        """Read only JSONL bytes appended since the previous refresh."""
        with self._lock:
            try:
                stat_result = self.path.stat()
            except FileNotFoundError:
                return

            identity = self._identity(stat_result)
            if self._file_identity is None:
                self._file_identity = identity
            elif identity != self._file_identity or stat_result.st_size < self._offset:
                self._file_identity = identity
                self._reset_for_new_file()

            if stat_result.st_size == self._offset:
                return

            with self.path.open("r", encoding="utf-8", errors="replace") as handle:
                handle.seek(self._offset)
                while True:
                    line_start = handle.tell()
                    line = handle.readline()
                    if not line:
                        break
                    # Avoid consuming a record that is still being written.
                    if not line.endswith("\n"):
                        handle.seek(line_start)
                        break
                    self._offset = handle.tell()
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        self._parse_errors += 1
                        continue
                    if not isinstance(record, dict):
                        self._parse_errors += 1
                        continue
                    self._ingest_record(record)

    def _ingest_record(self, record: dict[str, Any]) -> None:
        self._records_read += 1
        timestamp = record.get("timestamp")
        if isinstance(timestamp, (int, float)):
            self._latest_timestamp = float(timestamp)
        # Out-of-band health records only contain events. Preserve the last
        # full frame metrics so a malfunction/offline alert does not blank
        # people, train state, zone, FPS and latency cards in the dashboard.
        if any(
            key in record
            for key in ("frame_index", "people", "train_state", "performance", "zones")
        ):
            self._latest_record = record
        context = {
            "run_id": record.get("run_id"),
            "source": record.get("source"),
            "source_generation": record.get("source_generation"),
            "sequence": record.get("sequence"),
        }
        events = record.get("events", [])
        if not isinstance(events, list):
            return
        for event in events:
            if not isinstance(event, dict):
                continue
            enriched = {**context, **event}
            event_type = str(enriched.get("event_type") or "unknown")
            severity = str(enriched.get("severity") or "unknown")
            self._event_counts[event_type] += 1
            self._severity_counts[severity] += 1
            self._events.append(DashboardEvent(enriched))

    def event_frame_path(self, event_id: str, *, variant: str = "annotated") -> Path | None:
        """Resolve a frame only through an event already present in the JSONL.

        The HTTP layer never accepts an arbitrary filesystem path from the
        browser, which avoids turning the dashboard into a generic file server.
        """
        self.refresh()
        with self._lock:
            for item in reversed(self._events):
                payload = item.payload
                if str(payload.get("event_id") or "") != event_id:
                    continue
                details = payload.get("details")
                if not isinstance(details, dict):
                    return None
                key = "clean_frame_path" if variant == "clean" else "frame_path"
                raw_path = details.get(key)
                if not isinstance(raw_path, str) or not raw_path.strip():
                    return None
                path = Path(raw_path).expanduser()
                return path.resolve() if path.is_file() else None
        return None

    @staticmethod
    def _latest_payload(record: dict[str, Any] | None) -> dict[str, Any]:
        if not record:
            return {
                "timestamp": None,
                "people": None,
                "objects": {},
                "train_state": "UNKNOWN",
                "density_people_m2": None,
                "zones": [],
                "luggage_associations": [],
                "performance": {},
                "run_id": None,
                "source": None,
                "source_generation": None,
                "sequence": None,
            }
        return {
            "timestamp": record.get("timestamp"),
            "people": record.get("people"),
            "objects": record.get("objects") if isinstance(record.get("objects"), dict) else {},
            "train_state": record.get("train_state", "UNKNOWN"),
            "density_people_m2": record.get("density_people_m2"),
            "zones": record.get("zones") if isinstance(record.get("zones"), list) else [],
            "luggage_associations": (
                record.get("luggage_associations")
                if isinstance(record.get("luggage_associations"), list)
                else []
            ),
            "performance": record.get("performance") if isinstance(record.get("performance"), dict) else {},
            "run_id": record.get("run_id"),
            "source": record.get("source"),
            "source_generation": record.get("source_generation"),
            "sequence": record.get("sequence"),
        }

    def snapshot(
        self,
        *,
        event_type: str | None = None,
        severity: str | None = None,
        limit: int = 200,
    ) -> dict[str, Any]:
        self.refresh()
        limit = max(1, min(int(limit), self.max_events))
        with self._lock:
            latest = self._latest_payload(self._latest_record)
            raw_events = [item.to_dict() for item in reversed(self._events)]
            if event_type:
                raw_events = [e for e in raw_events if e.get("event_type") == event_type]
            if severity:
                raw_events = [e for e in raw_events if e.get("severity") == severity]
            events = raw_events[:limit]
            for event in events:
                event_id = event.get("event_id")
                details = event.get("details")
                if (
                    event_id
                    and isinstance(details, dict)
                    and isinstance(details.get("frame_path"), str)
                ):
                    event["frame_url"] = f"/api/event-frame/{event_id}"
                    public_details = dict(details)
                    public_details.pop("frame_path", None)
                    if isinstance(details.get("clean_frame_path"), str):
                        event["clean_frame_url"] = f"/api/event-frame/{event_id}?variant=clean"
                    public_details.pop("clean_frame_path", None)
                    event["details"] = public_details

            timestamp = self._latest_timestamp
            age_s = None
            if isinstance(timestamp, (int, float)):
                age_s = max(0.0, time.time() - float(timestamp))

            return {
                "connected": self.path.exists(),
                "jsonl_path": str(self.path),
                "records_read": self._records_read,
                "parse_errors": self._parse_errors,
                "latest_record_age_s": None if age_s is None else round(age_s, 3),
                "latest": latest,
                "event_counts": dict(sorted(self._event_counts.items())),
                "severity_counts": dict(sorted(self._severity_counts.items())),
                "event_types": sorted(self._event_counts),
                "severities": sorted(self._severity_counts),
                "events": events,
            }
