from pathlib import Path

import numpy as np

from crowd_monitor.analytics import AnalyticsEvent
from crowd_monitor.event_frames import attach_event_frames


def test_attach_event_frames_writes_one_jpeg_per_event(tmp_path):
    frame = np.zeros((40, 60, 3), dtype=np.uint8)
    clean = np.full((40, 60, 3), 127, dtype=np.uint8)
    events = (
        AnalyticsEvent(
            event_id="evt-1",
            event_type="unattended_luggage",
            timestamp=1000.25,
            severity="critical",
            track_id=7,
            object_class="backpack",
            details={"owner_track_id": 1},
        ),
    )

    enriched = attach_event_frames(
        frame,
        events,
        tmp_path / "frames",
        clean_frame=clean,
    )
    path = Path(enriched[0].details["frame_path"])
    clean_path = Path(enriched[0].details["clean_frame_path"])
    assert path.is_file()
    assert clean_path.is_file()
    assert path.suffix == ".jpg"
    assert clean_path.name.endswith("_clean.jpg")
    assert enriched[0].details["frame_kind"] == "annotated_event_frame"
    assert enriched[0].details["clean_frame_kind"] == "clean_event_frame"
    assert enriched[0].details["owner_track_id"] == 1


def test_attach_event_frames_can_mark_last_available_frame(tmp_path):
    frame = np.zeros((20, 20, 3), dtype=np.uint8)
    event = AnalyticsEvent(
        event_id="health-1",
        event_type="malfunction",
        timestamp=10.0,
        severity="critical",
    )
    enriched = attach_event_frames(
        frame,
        (event,),
        tmp_path,
        frame_kind="last_available_frame",
        source_frame_timestamp=9.5,
    )
    assert enriched[0].details["frame_kind"] == "last_available_frame"
    assert enriched[0].details["source_frame_timestamp"] == 9.5
