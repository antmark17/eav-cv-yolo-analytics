from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import re

import cv2
import numpy as np

from .analytics import AnalyticsEvent

_SAFE = re.compile(r"[^A-Za-z0-9_.-]+")


def _safe_component(value: str) -> str:
    cleaned = _SAFE.sub("_", value).strip("._")
    return cleaned or "event"


def attach_event_frames(
    frame: np.ndarray,
    events: tuple[AnalyticsEvent, ...],
    output_dir: str | Path | None,
    *,
    clean_frame: np.ndarray | None = None,
    frame_kind: str = "annotated_event_frame",
    source_frame_timestamp: float | None = None,
) -> tuple[AnalyticsEvent, ...]:
    """Persist annotated and, when available, clean JPEGs for an event.

    The snapshot is written before the JSONL record, then the event is returned
    with absolute paths in ``details`` so the local dashboard can resolve the
    images reliably even when launched from another working directory.

    ``frame`` is the rendered frame (bounding boxes/overlays included), while
    ``clean_frame`` is the original source frame before rendering.  Keeping the
    annotated path in ``frame_path`` preserves compatibility with older data.
    """
    if not events or output_dir in (None, ""):
        return events

    directory = Path(output_dir).expanduser()
    directory.mkdir(parents=True, exist_ok=True)
    enriched: list[AnalyticsEvent] = []

    for event in events:
        millis = int(round(float(event.timestamp) * 1000.0))
        filename = (
            f"{millis}_{_safe_component(event.event_type)}_"
            f"{_safe_component(event.event_id)}.jpg"
        )
        target = (directory / filename).resolve()
        ok = cv2.imwrite(str(target), frame)
        details = dict(event.details)
        if ok:
            details.update(
                {
                    "frame_path": str(target),
                    "frame_filename": filename,
                    "frame_kind": frame_kind,
                }
            )
            if source_frame_timestamp is not None:
                details["source_frame_timestamp"] = source_frame_timestamp
        else:
            details["frame_error"] = "cv2.imwrite returned false"

        if clean_frame is not None:
            clean_filename = filename.removesuffix(".jpg") + "_clean.jpg"
            clean_target = (directory / clean_filename).resolve()
            clean_ok = cv2.imwrite(str(clean_target), clean_frame)
            if clean_ok:
                details.update(
                    {
                        "clean_frame_path": str(clean_target),
                        "clean_frame_filename": clean_filename,
                        "clean_frame_kind": "clean_event_frame",
                    }
                )
            else:
                details["clean_frame_error"] = "cv2.imwrite returned false"
        enriched.append(replace(event, details=details))

    return tuple(enriched)
