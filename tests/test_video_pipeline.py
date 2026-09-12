from pathlib import Path
import json

import cv2
import numpy as np
import pytest

from crowd_monitor.config import (
    AnalyticsConfig,
    AppConfig,
    LineCrossingConfig,
    LuggageConfig,
    ModelConfig,
    OutputConfig,
    SourceConfig,
)
from crowd_monitor.detector import Detection
from crowd_monitor.video_pipeline import VideoAnalysisPipeline


class FakeTracker:
    def __init__(self):
        self.index = 0

    def reset(self):
        self.index = 0

    def track(self, frame):
        y2 = 40 if self.index == 0 else 70
        self.index += 1
        detection = Detection(
            track_id=1,
            class_id=0,
            class_name="person",
            bbox=(45, y2 - 20, 55, y2),
            confidence=0.93,
        )
        return None, [detection]


def _make_video(path: Path):
    writer = cv2.VideoWriter(
        str(path), cv2.VideoWriter_fourcc(*"MJPG"), 2.0, (100, 100)
    )
    assert writer.isOpened()
    for _ in range(2):
        writer.write(np.zeros((100, 100, 3), dtype=np.uint8))
    writer.release()


def test_video_pipeline_uses_media_time_and_writes_event_only_jsonl(tmp_path):
    video = tmp_path / "clip.avi"
    _make_video(video)
    events = tmp_path / "events.jsonl"
    frames = tmp_path / "frames"
    annotated = tmp_path / "annotated.mp4"
    config = AppConfig(
        source=SourceConfig(uri=str(video)),
        model=ModelConfig(),
        analytics=AnalyticsConfig(
            line_crossings=[
                LineCrossingConfig(
                    name="tracks",
                    line=((0.1, 0.5), (0.9, 0.5)),
                    prohibited_direction="negative_to_positive",
                    cooldown_s=0.0,
                    hysteresis=0.0,
                )
            ],
            luggage=LuggageConfig(enabled=False),
        ),
        output=OutputConfig(
            display=False,
            jsonl_path=str(events),
            event_frames_dir=str(frames),
            video_path=str(annotated),
        ),
    )
    pipeline = VideoAnalysisPipeline(config, tracker=FakeTracker())
    summary = pipeline.run(video, station="Test Station")
    assert summary["frames_processed"] == 2
    assert summary["events_written"] == 1

    lines = events.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["video_time_s"] == 0.5
    event = record["events"][0]
    assert event["event_type"] == "line_crossing"
    assert event["details"]["video_time_s"] == 0.5
    assert event["details"]["station"] == "Test Station"
    assert Path(event["details"]["frame_path"]).is_file()


@pytest.mark.parametrize('fps', [0, -1, float('nan'), float('inf')])
def test_invalid_fps_rejected_before_video_open(tmp_path, fps):
    pipeline = VideoAnalysisPipeline(AppConfig(source=SourceConfig(uri="unused")), tracker=FakeTracker())
    with pytest.raises(ValueError, match='FPS'):
        pipeline.run(tmp_path / 'missing.mp4', fps_override=fps)


def test_capture_released_when_tracker_reset_fails(tmp_path, monkeypatch):
    video = tmp_path / 'clip.avi'
    _make_video(video)
    capture = cv2.VideoCapture(str(video))
    monkeypatch.setattr(cv2, 'VideoCapture', lambda _: capture)
    tracker = FakeTracker()
    def fail():
        raise RuntimeError('tracker failed')
    tracker.reset = fail
    pipeline = VideoAnalysisPipeline(AppConfig(source=SourceConfig(uri="unused")), tracker=tracker)
    with pytest.raises(RuntimeError, match='tracker failed'):
        pipeline.run(video)
    assert not capture.isOpened()

