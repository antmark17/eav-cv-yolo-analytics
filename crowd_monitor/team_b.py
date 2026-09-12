"""Strict Team B payload validation and Smart Station normalization.

This module deliberately has no network dependencies.  It is the boundary
between local/Meraki analytics and the JSON contract accepted by Team B.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Mapping
from urllib.parse import urlsplit
import json
import math
import re
import sqlite3


STATION_ID = "STAZIONE_MONTESANTO"
PEOPLE_FLOW_PLATFORMS = frozenset(
    {"PLATFORM_1", "PLATFORM_2", "PLATFORM_3", "PLATFORM_4"}
)
EVENT_LOCATIONS = PEOPLE_FLOW_PLATFORMS | {"WAITING_AREA"}
EVENT_TYPES = frozenset(
    {
        "yellow_line_crossing",
        "restricted_area_intrusion",
        "suspicious_person",
        "dirt_detected",
        "malfunction",
    }
)
SEVERITIES = frozenset({"low", "medium", "high"})

_TIMESTAMP_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?$"
)
_SEVERITY_MAP = {
    "info": "low",
    "warning": "medium",
    "critical": "high",
    "low": "low",
    "medium": "medium",
    "high": "high",
}
_EVENT_TYPE_MAP = {
    "line_crossing": "yellow_line_crossing",
    "yellow_line_crossing": "yellow_line_crossing",
    "restricted_zone_entry": "restricted_area_intrusion",
    "restricted_area_intrusion": "restricted_area_intrusion",
    "suspicious_person": "suspicious_person",
    "dirt_detected": "dirt_detected",
    "malfunction": "malfunction",
}
_EVENT_DESCRIPTIONS = {
    "yellow_line_crossing": "Yellow safety line crossing detected",
    "restricted_area_intrusion": "Restricted area intrusion detected",
    "suspicious_person": "Suspicious person detected",
    "dirt_detected": "Dirt detected in monitored area",
    "malfunction": "Camera or analytics pipeline malfunction detected",
}


class TeamBValidationError(ValueError):
    """Raised when a payload violates the strict Team B contract."""

    def __init__(self, errors: list[str] | tuple[str, ...]) -> None:
        self.errors = tuple(errors)
        super().__init__("; ".join(self.errors))


class UnsupportedTeamBEventError(ValueError):
    """Raised when a local event cannot be represented by Team B's schema."""


def _check_object(
    value: Any,
    *,
    path: str,
    required: set[str],
    optional: set[str] | None,
    errors: list[str],
) -> Mapping[str, Any] | None:
    if not isinstance(value, Mapping):
        errors.append(f"{path} must be an object")
        return None
    fields = set(value)
    allowed = required | (optional or set())
    for name in sorted(required - fields, key=str):
        errors.append(f"{path}.{name} is required")
    for name in sorted(fields - allowed, key=str):
        errors.append(f"{path}.{name} is not allowed")
    return value


def _check_timestamp(value: Any, path: str, errors: list[str]) -> None:
    if not isinstance(value, str) or not _TIMESTAMP_PATTERN.fullmatch(value):
        errors.append(f"{path} must be an ISO 8601 date-time string")
        return
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        datetime.fromisoformat(candidate)
    except ValueError:
        errors.append(f"{path} must contain a valid date and time")


def _check_exact_string(
    value: Any,
    *,
    path: str,
    allowed: frozenset[str] | set[str],
    errors: list[str],
) -> None:
    if not isinstance(value, str) or value not in allowed:
        choices = ", ".join(sorted(allowed))
        errors.append(f"{path} must be one of: {choices}")


def _check_nonempty_string(value: Any, path: str, errors: list[str]) -> None:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{path} must be a non-empty string")


def _check_url(value: Any, path: str, errors: list[str]) -> None:
    if not isinstance(value, str):
        errors.append(f"{path} must be a URL string")
        return
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        errors.append(f"{path} must be a valid HTTP or HTTPS URL")


def validate_people_flow(payload: Any) -> None:
    """Validate one people-flow object and reject unexpected fields."""

    errors: list[str] = []
    data = _check_object(
        payload,
        path="$",
        required={"timestamp", "station_id", "platform_id", "metric", "value"},
        optional=None,
        errors=errors,
    )
    if data is not None:
        _check_timestamp(data.get("timestamp"), "$.timestamp", errors)
        _check_exact_string(
            data.get("station_id"),
            path="$.station_id",
            allowed={STATION_ID},
            errors=errors,
        )
        _check_exact_string(
            data.get("platform_id"),
            path="$.platform_id",
            allowed=PEOPLE_FLOW_PLATFORMS,
            errors=errors,
        )
        _check_exact_string(
            data.get("metric"),
            path="$.metric",
            allowed={"people_count"},
            errors=errors,
        )
        count = data.get("value")
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            errors.append("$.value must be an integer greater than or equal to 0")
    if errors:
        raise TeamBValidationError(errors)


def validate_event(payload: Any) -> None:
    """Validate one event object and reject unexpected nested fields."""

    errors: list[str] = []
    data = _check_object(
        payload,
        path="$",
        required={
            "event_id",
            "timestamp",
            "station_id",
            "specific_location",
            "source_device",
            "event",
        },
        optional=None,
        errors=errors,
    )
    if data is None:
        raise TeamBValidationError(errors)

    event_id = data.get("event_id")
    if isinstance(event_id, bool) or not isinstance(event_id, int) or event_id <= 0:
        errors.append("$.event_id must be a positive integer")
    _check_timestamp(data.get("timestamp"), "$.timestamp", errors)
    _check_exact_string(
        data.get("station_id"),
        path="$.station_id",
        allowed={STATION_ID},
        errors=errors,
    )
    _check_exact_string(
        data.get("specific_location"),
        path="$.specific_location",
        allowed=EVENT_LOCATIONS,
        errors=errors,
    )

    source = _check_object(
        data.get("source_device"),
        path="$.source_device",
        required={"type", "id"},
        optional=None,
        errors=errors,
    )
    if source is not None:
        _check_exact_string(
            source.get("type"),
            path="$.source_device.type",
            allowed={"camera"},
            errors=errors,
        )
        _check_nonempty_string(source.get("id"), "$.source_device.id", errors)

    event = _check_object(
        data.get("event"),
        path="$.event",
        required={"type", "severity", "description"},
        optional={"related_data"},
        errors=errors,
    )
    if event is not None:
        _check_exact_string(
            event.get("type"),
            path="$.event.type",
            allowed=EVENT_TYPES,
            errors=errors,
        )
        _check_exact_string(
            event.get("severity"),
            path="$.event.severity",
            allowed=SEVERITIES,
            errors=errors,
        )
        _check_nonempty_string(
            event.get("description"), "$.event.description", errors
        )
        if "related_data" in event:
            related = _check_object(
                event.get("related_data"),
                path="$.event.related_data",
                required=set(),
                optional={"image_frame_url"},
                errors=errors,
            )
            if related is not None and "image_frame_url" in related:
                _check_url(
                    related.get("image_frame_url"),
                    "$.event.related_data.image_frame_url",
                    errors,
                )
    if errors:
        raise TeamBValidationError(errors)


def _reject_duplicate_fields(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    duplicates: list[str] = []
    for name, value in pairs:
        if name in result:
            duplicates.append(name)
        result[name] = value
    if duplicates:
        names = ", ".join(sorted(set(duplicates)))
        raise TeamBValidationError([f"duplicate JSON field(s): {names}"])
    return result


def parse_and_validate_json(raw: str, message_type: str) -> dict[str, Any]:
    """Parse JSON without accepting duplicate keys, then validate its schema."""

    try:
        payload = json.loads(raw, object_pairs_hook=_reject_duplicate_fields)
    except json.JSONDecodeError as exc:
        raise TeamBValidationError(
            [f"invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"]
        ) from exc
    if message_type == "people_flow":
        validate_people_flow(payload)
    elif message_type == "event":
        validate_event(payload)
    else:
        raise ValueError("message_type must be 'people_flow' or 'event'")
    return payload


def to_iso8601_utc(value: float | int | datetime | str) -> str:
    """Convert a source timestamp to an unambiguous UTC value ending in Z."""

    if isinstance(value, bool):
        raise ValueError("timestamp cannot be boolean")
    if isinstance(value, (float, int)):
        if not math.isfinite(float(value)):
            raise ValueError("timestamp must be finite")
        resolved = datetime.fromtimestamp(float(value), tz=timezone.utc)
    elif isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("datetime timestamp must include a timezone")
        resolved = value.astimezone(timezone.utc)
    elif isinstance(value, str):
        errors: list[str] = []
        _check_timestamp(value, "timestamp", errors)
        if errors:
            raise ValueError(errors[0])
        candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
        resolved = datetime.fromisoformat(candidate)
        if resolved.tzinfo is None:
            raise ValueError("string timestamp must include a timezone")
        resolved = resolved.astimezone(timezone.utc)
    else:
        raise TypeError("timestamp must be Unix time, datetime, or ISO 8601 string")
    return resolved.isoformat(timespec="milliseconds").replace("+00:00", "Z")


class SqliteEventIdStore:
    """Persistent, process-local allocator for positive incremental event IDs."""

    def __init__(self, path: str | Path, sequence_name: str = "team_b") -> None:
        self.path = str(path)
        self.sequence_name = sequence_name
        if not sequence_name.strip():
            raise ValueError("sequence_name cannot be empty")
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._connection = sqlite3.connect(
            self.path,
            timeout=10.0,
            isolation_level=None,
            check_same_thread=False,
        )
        if self.path != ":memory:":
            self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS team_b_event_sequence (
                sequence_name TEXT PRIMARY KEY,
                last_id INTEGER NOT NULL CHECK(last_id >= 0)
            )
            """
        )
        self._connection.execute(
            """
            INSERT OR IGNORE INTO team_b_event_sequence(sequence_name, last_id)
            VALUES (?, 0)
            """,
            (self.sequence_name,),
        )

    def next_id(self) -> int:
        with self._lock:
            try:
                self._connection.execute("BEGIN IMMEDIATE")
                row = self._connection.execute(
                    """
                    SELECT last_id FROM team_b_event_sequence
                    WHERE sequence_name = ?
                    """,
                    (self.sequence_name,),
                ).fetchone()
                if row is None:
                    raise RuntimeError("event ID sequence is missing")
                next_value = int(row[0]) + 1
                self._connection.execute(
                    """
                    UPDATE team_b_event_sequence SET last_id = ?
                    WHERE sequence_name = ?
                    """,
                    (next_value, self.sequence_name),
                )
                self._connection.commit()
                return next_value
            except Exception:
                self._connection.rollback()
                raise

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def __enter__(self) -> "SqliteEventIdStore":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def _event_field(event: Any, name: str, default: Any = None) -> Any:
    if isinstance(event, Mapping):
        return event.get(name, default)
    return getattr(event, name, default)


@dataclass(slots=True)
class TeamBNormalizer:
    """Build validated Team B payloads from local analytics values."""

    platform_id: str
    specific_location: str
    source_device_id: str
    event_ids: SqliteEventIdStore
    yellow_line_names: frozenset[str] = field(default_factory=frozenset)
    restricted_zone_names: frozenset[str] = field(default_factory=frozenset)
    station_id: str = STATION_ID

    def __post_init__(self) -> None:
        if self.station_id != STATION_ID:
            raise ValueError(f"station_id must be {STATION_ID}")
        if self.platform_id not in PEOPLE_FLOW_PLATFORMS:
            raise ValueError("platform_id is not supported by Team B")
        if self.specific_location not in EVENT_LOCATIONS:
            raise ValueError("specific_location is not supported by Team B")
        if not isinstance(self.source_device_id, str) or not self.source_device_id.strip():
            raise ValueError("source_device_id cannot be empty")

    def normalize_people_count(
        self,
        value: int,
        timestamp: float | int | datetime | str,
    ) -> dict[str, Any]:
        payload = {
            "timestamp": to_iso8601_utc(timestamp),
            "station_id": self.station_id,
            "platform_id": self.platform_id,
            "metric": "people_count",
            "value": value,
        }
        validate_people_flow(payload)
        return payload

    def normalize_event(
        self,
        analytics_event: Any,
        *,
        image_frame_url: str | None = None,
    ) -> dict[str, Any]:
        source_type = _event_field(analytics_event, "event_type")
        target_type = _EVENT_TYPE_MAP.get(source_type)
        if target_type is None:
            raise UnsupportedTeamBEventError(
                f"event type {source_type!r} is not supported by Team B"
            )

        zone = _event_field(analytics_event, "zone")
        details = _event_field(analytics_event, "details", {}) or {}
        object_class = _event_field(analytics_event, "object_class")
        if target_type == "yellow_line_crossing":
            if zone not in self.yellow_line_names:
                raise UnsupportedTeamBEventError(
                    f"line {zone!r} is not configured as a yellow safety line"
                )
            if object_class != "person":
                raise UnsupportedTeamBEventError(
                    "yellow line events are emitted only for people"
                )
            if not isinstance(details, Mapping) or details.get("prohibited") is not True:
                raise UnsupportedTeamBEventError(
                    "non-prohibited line crossing must not become a safety alert"
                )
            if details.get("train_state") != "ABSENT":
                raise UnsupportedTeamBEventError(
                    "yellow-line crossing requires confirmed train absence"
                )
        elif target_type == "restricted_area_intrusion":
            if zone not in self.restricted_zone_names:
                raise UnsupportedTeamBEventError(
                    f"zone {zone!r} is not configured as a restricted area"
                )

        source_severity = _event_field(analytics_event, "severity")
        severity = _SEVERITY_MAP.get(source_severity)
        if severity is None:
            raise UnsupportedTeamBEventError(
                f"severity {source_severity!r} cannot be mapped to Team B"
            )

        event_data: dict[str, Any] = {
            "type": target_type,
            "severity": severity,
            "description": _EVENT_DESCRIPTIONS[target_type],
        }
        if image_frame_url is not None:
            event_data["related_data"] = {"image_frame_url": image_frame_url}

        normalized_timestamp = to_iso8601_utc(
            _event_field(analytics_event, "timestamp")
        )
        payload = {
            # Validate the complete payload before consuming the next durable ID.
            "event_id": 1,
            "timestamp": normalized_timestamp,
            "station_id": self.station_id,
            "specific_location": self.specific_location,
            "source_device": {
                "type": "camera",
                "id": self.source_device_id,
            },
            "event": event_data,
        }
        validate_event(payload)
        payload["event_id"] = self.event_ids.next_id()
        return payload
