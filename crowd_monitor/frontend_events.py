from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


PUBLIC_TYPES = {
    "track_crossing",
    "high_crowd_density",
    "unattended_luggage",
    "unsupervised_animal",
}


def _priority(event_type: str, severity: str) -> str:
    if event_type == "track_crossing":
        return "Alto"
    if event_type == "high_crowd_density":
        return "Alto"
    if event_type == "unattended_luggage":
        return "Medio"
    if event_type == "unsupervised_animal":
        return "Basso"
    return {
        "critical": "Critico",
        "warning": "Medio",
        "info": "Basso",
    }.get(severity, "Medio")


def _confidence_percent(event: dict[str, Any]) -> int | None:
    details = event.get("details")
    if not isinstance(details, dict):
        return None
    raw = details.get("detector_confidence")
    if raw is None:
        raw = details.get("mean_person_confidence")
    if not isinstance(raw, (int, float)):
        return None
    return max(0, min(100, int(round(float(raw) * 100.0))))


def to_public_event(event: dict[str, Any]) -> dict[str, Any] | None:
    """Map canonical analytics events to the four frontend event contracts.

    Health/sensor events and intermediate analytics transitions are deliberately
    omitted. Crowd alerts are exposed only when the stable *critical/high*
    density level is reached.
    """
    canonical = str(event.get("event_type") or "")
    severity = str(event.get("severity") or "info")
    details = event.get("details")
    details = dict(details) if isinstance(details, dict) else {}

    if canonical == "line_crossing" and details.get("prohibited") is True:
        public_type = "track_crossing"
        title = "Attraversamento binari"
        icon = "⚠"
    elif canonical == "crowd_density" and severity == "critical":
        public_type = "high_crowd_density"
        title = "Sovraffollamento"
        icon = "◉"
    elif canonical == "unattended_luggage":
        public_type = canonical
        title = "Bagaglio abbandonato"
        icon = "▣"
    elif canonical == "unsupervised_animal":
        public_type = canonical
        title = "Animale non supervisionato"
        icon = "◆"
    else:
        return None

    event_id = str(event.get("event_id") or "")
    timestamp = event.get("timestamp")
    occurred_at = None
    if isinstance(timestamp, (int, float)):
        occurred_at = datetime.fromtimestamp(float(timestamp), tz=timezone.utc).isoformat()

    station = details.get("station") or "Video locale"
    source = details.get("source_name") or event.get("source") or "video"
    zone = event.get("zone") or details.get("zone") or "Area monitorata"
    video_time = details.get("video_time_s")

    public_details = dict(details)
    public_details.pop("frame_path", None)
    public_details.pop("clean_frame_path", None)

    return {
        "id": event_id,
        "event_type": public_type,
        "title": title,
        "priority": _priority(public_type, severity),
        "icon": icon,
        "station": station,
        "place": zone,
        "source": source,
        "confidence": _confidence_percent(event),
        "occurred_at": occurred_at,
        "video_time_s": video_time,
        "frame_url": event.get("frame_url"),
        "clean_frame_url": event.get("clean_frame_url"),
        "status": "Nuovo",
        "details": public_details,
    }


def public_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    mapped: list[dict[str, Any]] = []
    for event in events:
        item = to_public_event(event)
        if item is not None:
            mapped.append(item)
    return mapped
