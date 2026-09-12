import numpy as np

from crowd_monitor.config import HealthConfig
from crowd_monitor.health import FrameHealthMonitor


def test_black_and_frozen_frames_require_hold_and_are_deduplicated():
    monitor = FrameHealthMonitor(
        HealthConfig(
            black_after_s=1.0,
            frozen_after_s=1.0,
            blur_after_s=100.0,
            low_fps_after_s=100.0,
            cooldown_s=30.0,
        )
    )
    black = np.zeros((32, 32, 3), dtype=np.uint8)
    assert monitor.observe(black, monotonic_timestamp=0.0) == ()
    first = monitor.observe(black, monotonic_timestamp=1.0)
    assert {event.details["kind"] for event in first} == {"black_frame"}
    second = monitor.observe(black, monotonic_timestamp=2.0)
    assert {event.details["kind"] for event in second} == {"frozen_frame"}
    assert monitor.observe(black, monotonic_timestamp=3.0) == ()


def test_offline_event_is_emitted_once_until_a_frame_recovers():
    monitor = FrameHealthMonitor(
        HealthConfig(
            offline_after_s=1.0,
            black_after_s=100.0,
            frozen_after_s=100.0,
            blur_after_s=100.0,
            low_fps_after_s=100.0,
            cooldown_s=0.0,
        )
    )
    frame = np.full((32, 32, 3), 100, dtype=np.uint8)
    monitor.observe(frame, monotonic_timestamp=0.0)
    first = monitor.poll_offline(monotonic_timestamp=1.0)
    assert len(first) == 1
    assert first[0].event_type == "malfunction"
    assert first[0].details["kind"] == "offline"
    assert monitor.poll_offline(monotonic_timestamp=2.0) == ()
    monitor.observe(frame + 1, monotonic_timestamp=3.0)
    second = monitor.poll_offline(monotonic_timestamp=4.0)
    assert len(second) == 1
