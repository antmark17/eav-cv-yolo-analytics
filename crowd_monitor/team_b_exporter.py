"""Validated local JSONL export from YOLO analytics to Team B messages.

This module is intentionally independent from OpenCV, Ultralytics and network
clients.  It turns an ``AnalysisResult``-compatible object into the two raw
message types accepted by Team B and stores one JSON object per line.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO
import json
import time

from .config import TeamBOutputConfig
from .team_b import (
    SqliteEventIdStore,
    TeamBNormalizer,
    UnsupportedTeamBEventError,
)


@dataclass(frozen=True, slots=True)
class TeamBExportBatch:
    """Messages produced while handling one analytics result."""

    people_flow: tuple[dict[str, Any], ...] = ()
    events: tuple[dict[str, Any], ...] = ()
    skipped_events: int = 0


class TeamBLocalExporter:
    """Write validated Team B messages locally, without network delivery."""

    def __init__(self, config: TeamBOutputConfig) -> None:
        if not config.enabled:
            raise ValueError("Team B local export is disabled")
        if (
            config.platform_id is None
            or config.specific_location is None
            or config.source_device_id is None
        ):
            raise ValueError("Team B identifiers must be configured")
        if config.people_flow_every_s < 0:
            raise ValueError("people_flow_every_s cannot be negative")

        output_paths = (
            config.people_flow_jsonl_path,
            config.events_jsonl_path,
            config.event_id_db_path,
        )
        if any(not isinstance(path, str) or not path.strip() for path in output_paths):
            raise ValueError("Team B output paths cannot be empty")
        comparable_paths = [
            path if path == ":memory:" else str(Path(path).resolve())
            for path in output_paths
        ]
        if len(set(comparable_paths)) != len(comparable_paths):
            raise ValueError("Team B JSONL and SQLite paths must be different")

        self.config = config
        self._event_ids = SqliteEventIdStore(config.event_id_db_path)
        self._people_flow: TextIO | None = None
        self._events: TextIO | None = None
        try:
            self._normalizer = TeamBNormalizer(
                platform_id=config.platform_id,
                specific_location=config.specific_location,
                source_device_id=config.source_device_id,
                event_ids=self._event_ids,
                yellow_line_names=frozenset(config.yellow_line_names),
                restricted_zone_names=frozenset(config.restricted_zone_names),
            )
            self._people_flow = self._open_jsonl(
                config.people_flow_jsonl_path
            )
            self._events = self._open_jsonl(config.events_jsonl_path)
        except Exception:
            if self._people_flow is not None:
                self._people_flow.close()
            self._event_ids.close()
            raise
        self._last_people_flow_at: float | None = None
        self.people_flow_written = 0
        self.events_written = 0
        self.events_skipped = 0
        self._closed = False

    @staticmethod
    def _open_jsonl(path: str) -> TextIO:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        return target.open("a", encoding="utf-8", buffering=1)

    @staticmethod
    def _write_jsonl(handle: TextIO, payload: dict[str, Any]) -> None:
        json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
        handle.write("\n")

    def process(
        self,
        analysis: Any,
        *,
        monotonic_timestamp: float | None = None,
    ) -> TeamBExportBatch:
        """Normalize and write messages produced by one processed frame.

        Unsupported analytics events are deliberately skipped because the
        strict Team B contract currently has no representation for them.
        Validation and I/O failures are not hidden.
        """

        if self._closed:
            raise RuntimeError("Team B local exporter is closed")

        monotonic_now = (
            time.monotonic()
            if monotonic_timestamp is None
            else float(monotonic_timestamp)
        )
        people_payloads: list[dict[str, Any]] = []
        event_payloads: list[dict[str, Any]] = []
        skipped = 0

        interval_ready = (
            self._last_people_flow_at is None
            or self.config.people_flow_every_s == 0
            or monotonic_now - self._last_people_flow_at
            >= self.config.people_flow_every_s
        )
        if interval_ready:
            people_payload = self._normalizer.normalize_people_count(
                analysis.people,
                analysis.timestamp,
            )
            assert self._people_flow is not None
            self._write_jsonl(self._people_flow, people_payload)
            self._last_people_flow_at = monotonic_now
            self.people_flow_written += 1
            people_payloads.append(people_payload)

        event_payloads, skipped = self._process_events(analysis.events)

        return TeamBExportBatch(
            people_flow=tuple(people_payloads),
            events=tuple(event_payloads),
            skipped_events=skipped,
        )

    def _process_events(
        self, analytics_events: Any
    ) -> tuple[list[dict[str, Any]], int]:
        event_payloads: list[dict[str, Any]] = []
        skipped = 0
        for analytics_event in analytics_events:
            try:
                event_payload = self._normalizer.normalize_event(analytics_event)
            except UnsupportedTeamBEventError:
                skipped += 1
                self.events_skipped += 1
                continue
            assert self._events is not None
            self._write_jsonl(self._events, event_payload)
            self.events_written += 1
            event_payloads.append(event_payload)
        return event_payloads, skipped

    def process_events(self, analytics_events: Any) -> TeamBExportBatch:
        """Write out-of-band events such as source/model malfunctions."""

        if self._closed:
            raise RuntimeError("Team B local exporter is closed")
        event_payloads, skipped = self._process_events(analytics_events)
        return TeamBExportBatch(
            events=tuple(event_payloads),
            skipped_events=skipped,
        )

    def close(self) -> None:
        if self._closed:
            return
        if self._people_flow is not None:
            self._people_flow.close()
        if self._events is not None:
            self._events.close()
        self._event_ids.close()
        self._closed = True

    def __enter__(self) -> "TeamBLocalExporter":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
