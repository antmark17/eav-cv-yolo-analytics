from __future__ import annotations

import json

from crowd_monitor.dashboard import CanonicalJsonlDashboardStore


def _append(path, payload):
    with path.open("a", encoding="utf-8") as handle:
        json.dump(payload, handle)
        handle.write("\n")


def test_dashboard_collects_all_canonical_event_types(tmp_path):
    path = tmp_path / "metrics.jsonl"
    _append(
        path,
        {
            "run_id": "run-1",
            "source": "camera",
            "sequence": 10,
            "timestamp": 100.0,
            "people": 3,
            "train_state": "ABSENT",
            "density_people_m2": 0.3,
            "zones": [],
            "performance": {"processed_fps_ema": 9.8},
            "events": [
                {"event_id": "a", "event_type": "unattended_luggage", "timestamp": 100.0, "severity": "critical", "details": {}},
                {"event_id": "b", "event_type": "vandalism_detected", "timestamp": 100.0, "severity": "critical", "details": {}},
            ],
        },
    )
    store = CanonicalJsonlDashboardStore(path)
    state = store.snapshot()

    assert state["latest"]["people"] == 3
    assert state["latest"]["train_state"] == "ABSENT"
    assert state["event_counts"] == {"unattended_luggage": 1, "vandalism_detected": 1}
    assert {event["event_type"] for event in state["events"]} == {"unattended_luggage", "vandalism_detected"}
    assert all(event["run_id"] == "run-1" for event in state["events"])


def test_dashboard_reads_appends_without_duplicate_events(tmp_path):
    path = tmp_path / "metrics.jsonl"
    store = CanonicalJsonlDashboardStore(path)
    _append(path, {"timestamp": 1.0, "events": [{"event_type": "malfunction", "severity": "warning", "timestamp": 1.0}]})
    assert store.snapshot()["event_counts"] == {"malfunction": 1}
    assert store.snapshot()["event_counts"] == {"malfunction": 1}

    _append(path, {"timestamp": 2.0, "events": [{"event_type": "fall_on_tracks", "severity": "critical", "timestamp": 2.0}]})
    assert store.snapshot()["event_counts"] == {"fall_on_tracks": 1, "malfunction": 1}


def test_dashboard_filters_events(tmp_path):
    path = tmp_path / "metrics.jsonl"
    _append(
        path,
        {
            "timestamp": 1.0,
            "events": [
                {"event_type": "line_crossing", "severity": "warning", "timestamp": 1.0},
                {"event_type": "train_state_changed", "severity": "info", "timestamp": 1.0},
            ],
        },
    )
    store = CanonicalJsonlDashboardStore(path)
    assert [e["event_type"] for e in store.snapshot(event_type="line_crossing")["events"]] == ["line_crossing"]
    assert [e["severity"] for e in store.snapshot(severity="info")["events"]] == ["info"]


def test_dashboard_handles_out_of_band_health_record(tmp_path):
    path = tmp_path / "metrics.jsonl"
    _append(
        path,
        {
            "schema_version": "local-analytics-0.5.0",
            "run_id": "run-2",
            "source": "camera",
            "timestamp": 123.0,
            "events": [
                {
                    "event_id": "health-1",
                    "event_type": "malfunction",
                    "timestamp": 123.0,
                    "severity": "critical",
                    "details": {"kind": "stream_offline"},
                }
            ],
        },
    )
    store = CanonicalJsonlDashboardStore(path)
    state = store.snapshot()
    assert state["event_counts"]["malfunction"] == 1
    assert state["events"][0]["details"]["kind"] == "stream_offline"


ALL_CANONICAL_EVENT_TYPES = {
    "train_state_changed",
    "legacy_direction",
    "line_crossing",
    "yellow_line_crossing_suppressed",
    "restricted_zone_entry",
    "crowd_density",
    "unattended_luggage",
    "unsupervised_animal",
    "dirt_detected",
    "dangerous_object_detected",
    "vandalism_detected",
    "fall_on_tracks",
    "malfunction",
}


def test_dashboard_exposes_every_current_canonical_event_type(tmp_path):
    path = tmp_path / "metrics.jsonl"
    _append(
        path,
        {
            "timestamp": 50.0,
            "people": 1,
            "events": [
                {"event_type": event_type, "severity": "info", "timestamp": 50.0}
                for event_type in sorted(ALL_CANONICAL_EVENT_TYPES)
            ],
        },
    )
    store = CanonicalJsonlDashboardStore(path)
    assert set(store.snapshot()["event_types"]) == ALL_CANONICAL_EVENT_TYPES


def test_out_of_band_event_preserves_last_frame_kpis(tmp_path):
    path = tmp_path / "metrics.jsonl"
    _append(
        path,
        {
            "timestamp": 10.0,
            "people": 5,
            "train_state": "PRESENT",
            "performance": {"processed_fps_ema": 8.0},
            "events": [],
        },
    )
    _append(
        path,
        {
            "timestamp": 11.0,
            "events": [
                {"event_type": "malfunction", "severity": "critical", "timestamp": 11.0}
            ],
        },
    )
    store = CanonicalJsonlDashboardStore(path)
    state = store.snapshot()
    assert state["latest"]["people"] == 5
    assert state["latest"]["train_state"] == "PRESENT"
    assert state["event_counts"] == {"malfunction": 1}


def test_dashboard_exposes_event_frame_url_and_resolves_file(tmp_path):
    path = tmp_path / "metrics.jsonl"
    frame = tmp_path / "event.jpg"
    frame.write_bytes(b"jpeg-placeholder")
    _append(
        path,
        {
            "timestamp": 10.0,
            "frame_index": 1,
            "events": [
                {
                    "event_id": "evt-1",
                    "event_type": "unattended_luggage",
                    "severity": "critical",
                    "timestamp": 10.0,
                    "details": {"frame_path": str(frame)},
                }
            ],
        },
    )
    store = CanonicalJsonlDashboardStore(path)
    state = store.snapshot()
    assert state["events"][0]["frame_url"] == "/api/event-frame/evt-1"
    assert "frame_path" not in state["events"][0]["details"]
    assert store.event_frame_path("evt-1") == frame.resolve()
