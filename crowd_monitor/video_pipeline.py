from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, Callable, TextIO
import json
import math
import time
import uuid

import cv2

from .analytics import AnalyticsEvent, CrowdAnalyticsEngine
from .config import AppConfig
from .detector import YoloObjectTracker
from .event_frames import attach_event_frames
from .renderer import CrowdRenderer


class VideoAnalysisPipeline:
    """Sequential CFR video analysis with event-only JSONL output.

    The analytics clock is derived from the video frame index, so luggage,
    animal and density hold timers describe media time rather than CPU time.
    Frames are never dropped just because inference is slow.  The event JSONL
    contains a record only when one or more analytics events are emitted.
    """

    def __init__(self, config: AppConfig, *, tracker: Any | None = None) -> None:
        self.config = config
        self.tracker = tracker if tracker is not None else YoloObjectTracker(config.model)
        self.analytics = CrowdAnalyticsEngine(config.analytics)
        self.renderer = CrowdRenderer(
            draw_tails=config.output.draw_tails,
            show_confidence=config.output.show_confidence,
        )

    @staticmethod
    def _open_events(path: str | None) -> TextIO | None:
        if not path:
            return None
        target = Path(path).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        # Operational event history is append-only: starting a new local video
        # must not erase events that an EAV operator may still need to handle.
        return target.open("a", encoding="utf-8", buffering=1)

    @staticmethod
    def _open_writer(path: str | None, frame, fps: float):
        if not path:
            return None
        target = Path(path).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        height, width = frame.shape[:2]
        writer = cv2.VideoWriter(
            str(target),
            cv2.VideoWriter_fourcc(*"mp4v"),
            max(1.0, fps),
            (width, height),
        )
        if not writer.isOpened():
            raise RuntimeError(f"Could not create output video: {target}")
        return writer

    @staticmethod
    def _enrich_events(
        events: tuple[AnalyticsEvent, ...],
        *,
        video_time_s: float,
        frame_index: int,
        source_name: str,
        station: str | None,
    ) -> tuple[AnalyticsEvent, ...]:
        enriched: list[AnalyticsEvent] = []
        for event in events:
            details = dict(event.details)
            details.update(
                {
                    "video_time_s": round(video_time_s, 3),
                    "frame_index": frame_index,
                    "source_name": source_name,
                }
            )
            if station:
                details["station"] = station
            enriched.append(replace(event, details=details))
        return tuple(enriched)

    def run(
        self,
        video: str | Path,
        *,
        fps_override: float | None = None,
        station: str | None = None,
        max_frames: int | None = None,
        realtime_pacing: bool = False,
        on_snapshot: Callable[[dict[str, Any]], None] | None = None,
        on_annotated_frame: Callable[[Any, dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        if fps_override is not None and (not math.isfinite(fps_override) or fps_override <= 0):
            raise ValueError("FPS override must be finite and positive")
        if max_frames is not None and max_frames <= 0:
            raise ValueError("max_frames must be positive")
        video_path = Path(video).expanduser().resolve()
        if not video_path.is_file():
            raise FileNotFoundError(f"Video not found: {video_path}")

        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise RuntimeError(f"OpenCV could not open video: {video_path}")

        metadata_fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
        fps = float(fps_override or metadata_fps)
        if not math.isfinite(fps) or fps <= 0:
            cap.release()
            raise ValueError(
                "Video FPS metadata is missing/invalid; pass an explicit CFR FPS override"
            )

        total_frames_meta = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        run_id = str(uuid.uuid4())
        source_name = video_path.name
        event_handle = None
        writer = None
        started_wall = time.monotonic()
        processed = 0
        events_written = 0
        inference_fps_ema = 0.0
        processing_fps_ema = 0.0
        last_done: float | None = None
        try:
            event_handle = self._open_events(self.config.output.jsonl_path)
            self.tracker.reset()
            self.analytics.clear_transient_state()
            self.renderer.clear_transient_state()
            while True:
                if max_frames is not None and processed >= max_frames:
                    break
                ok, frame = cap.read()
                if not ok or frame is None or frame.size == 0:
                    break

                frame_index = processed
                video_time_s = frame_index / fps
                frame_started = time.monotonic()
                inference_started = frame_started
                _, detections = self.tracker.track(frame)
                inference_ms = (time.monotonic() - inference_started) * 1000.0
                instant_inference_fps = 1000.0 / max(inference_ms, 1e-9)
                inference_fps_ema = (
                    instant_inference_fps
                    if inference_fps_ema == 0
                    else 0.90 * inference_fps_ema + 0.10 * instant_inference_fps
                )

                # Event timestamps are wall-clock occurrence/emission times for
                # the UI; temporal rules use the CFR media clock below.
                analysis = self.analytics.process(
                    detections,
                    frame.shape,
                    timestamp=time.time(),
                    monotonic_timestamp=video_time_s,
                )
                if on_snapshot is not None:
                    snapshot = analysis.to_dict(
                        inference_fps=inference_fps_ema,
                        pipeline_latency_ms=(time.monotonic() - frame_started) * 1000.0,
                    )
                    snapshot.update({
                        "schema_version": "local-video-live-0.6.1",
                        "source": source_name,
                        "station": station,
                        "video_time_s": round(video_time_s, 3),
                        "metadata_fps": fps,
                        "metadata_frame_count": total_frames_meta,
                        "progress": (
                            None if total_frames_meta <= 0
                            else min(1.0, (frame_index + 1) / total_frames_meta)
                        ),
                    })
                    on_snapshot(snapshot)
                if analysis.events:
                    analysis = replace(
                        analysis,
                        events=self._enrich_events(
                            analysis.events,
                            video_time_s=video_time_s,
                            frame_index=frame_index,
                            source_name=source_name,
                            station=station,
                        ),
                    )

                now = time.monotonic()
                if last_done is not None:
                    instant_fps = 1.0 / max(now - last_done, 1e-9)
                    processing_fps_ema = (
                        instant_fps
                        if processing_fps_ema == 0
                        else 0.85 * processing_fps_ema + 0.15 * instant_fps
                    )
                last_done = now

                annotated = self.renderer.render(
                    frame,
                    analysis,
                    inference_fps=inference_fps_ema,
                    processed_fps=processing_fps_ema,
                    pipeline_latency_ms=(time.monotonic() - frame_started) * 1000.0,
                )
                if on_annotated_frame is not None:
                    on_annotated_frame(annotated, {
                        "frame_index": frame_index,
                        "video_time_s": round(video_time_s, 3),
                        "source": source_name,
                        "station": station,
                    })
                if analysis.events:
                    analysis = replace(
                        analysis,
                        events=attach_event_frames(
                            annotated,
                            analysis.events,
                            self.config.output.event_frames_dir,
                            clean_frame=frame,
                            source_frame_timestamp=video_time_s,
                        ),
                    )

                if writer is None:
                    writer = self._open_writer(
                        self.config.output.video_path,
                        annotated,
                        self.config.output.video_fps or fps,
                    )
                if writer is not None:
                    writer.write(annotated)

                if analysis.events and event_handle is not None:
                    payload = {
                        "schema_version": "local-video-events-0.6.0",
                        "run_id": run_id,
                        "source": source_name,
                        "station": station,
                        "frame_index": frame_index,
                        "video_time_s": round(video_time_s, 3),
                        "timestamp": analysis.events[0].timestamp,
                        "events": [event.to_dict() for event in analysis.events],
                    }
                    json.dump(payload, event_handle, ensure_ascii=False)
                    event_handle.write("\n")
                    events_written += len(analysis.events)

                processed += 1

                # Optional playback-like pacing. If inference is slower than
                # the source FPS, there is no frame dropping: processing simply
                # runs behind wall clock while analytics timers remain correct.
                if realtime_pacing:
                    due = started_wall + processed / fps
                    delay = due - time.monotonic()
                    if delay > 0:
                        time.sleep(delay)
        finally:
            cap.release()
            if writer is not None:
                writer.release()
            if event_handle is not None:
                event_handle.close()

        elapsed = max(time.monotonic() - started_wall, 1e-9)
        status = "completed"
        if max_frames is not None and total_frames_meta > 0 and processed < total_frames_meta:
            status = "partial"
        return {
            "run_id": run_id,
            "status": status,
            "video": str(video_path),
            "fps": fps,
            "metadata_fps": metadata_fps,
            "frames_processed": processed,
            "metadata_frame_count": total_frames_meta,
            "video_time_s": round(processed / fps, 3),
            "elapsed_s": round(elapsed, 3),
            "average_processing_fps": round(processed / elapsed, 3),
            "events_written": events_written,
            "event_jsonl": self.config.output.jsonl_path,
            "event_frames_dir": self.config.output.event_frames_dir,
            "annotated_video": self.config.output.video_path,
        }
