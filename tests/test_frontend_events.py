from crowd_monitor.frontend_events import to_public_event


def _event(event_type, severity="critical", **details):
    return {
        "event_id": "evt-1",
        "event_type": event_type,
        "timestamp": 1_700_000_000.0,
        "severity": severity,
        "zone": "banchina_1",
        "source": "clip.mp4",
        "details": {"video_time_s": 12.5, "frame_path": "/private/x.jpg", **details},
        "frame_url": "/api/event-frame/evt-1",
    }


def test_only_the_four_public_event_contracts_are_exposed():
    assert to_public_event(_event("camera_offline")) is None
    assert to_public_event(_event("train_state_changed")) is None
    assert to_public_event(_event("line_crossing", prohibited=False)) is None

    crossing = to_public_event(_event("line_crossing", detector_confidence=0.91, prohibited=True))
    assert crossing["event_type"] == "track_crossing"
    assert crossing["title"] == "Attraversamento binari"
    assert crossing["confidence"] == 91
    assert "frame_path" not in crossing["details"]

    luggage = to_public_event(_event("unattended_luggage", detector_confidence=0.84))
    animal = to_public_event(_event("unsupervised_animal", severity="warning", detector_confidence=0.72))
    assert luggage["event_type"] == "unattended_luggage"
    assert animal["event_type"] == "unsupervised_animal"


def test_crowd_is_public_only_at_high_critical_density():
    assert to_public_event(_event("crowd_density", severity="warning")) is None
    crowd = to_public_event(
        _event("crowd_density", severity="critical", mean_person_confidence=0.88)
    )
    assert crowd["event_type"] == "high_crowd_density"
    assert crowd["confidence"] == 88
