from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, TextIO
import json
import time
import uuid

import cv2

from .analytics import CrowdAnalyticsEngine
from .config import AppConfig
from .detector import YoloObjectTracker
from .event_frames import attach_event_frames
from .health import FrameHealthMonitor
from .renderer import CrowdRenderer
from .source import HttpSnapshotSource, LatestFrameSource, YoutubeLiveSource
from .team_b_exporter import TeamBLocalExporter


class RealtimeCrowdPipeline:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.tracker = YoloObjectTracker(config.model)
        self.analytics = CrowdAnalyticsEngine(config.analytics)
        self.health = FrameHealthMonitor(config.analytics.health)
        self.renderer = CrowdRenderer(
            draw_tails=config.output.draw_tails,
            show_confidence=config.output.show_confidence,
        )

    @staticmethod
    def _open_jsonl(path: str | None) -> TextIO | None:
        if not path:
            return None
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        return target.open("a", encoding="utf-8", buffering=1)

    @staticmethod
    def _open_writer(path: str | None, frame, fps: float):
        if not path:
            return None
        target = Path(path)
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

    def _source(self) -> LatestFrameSource:
        source_cfg = self.config.source
        if source_cfg.mode == "snapshot":
            return HttpSnapshotSource(
                uri=str(source_cfg.uri),
                target_fps=source_cfg.target_fps,
                snapshot_timeout_s=source_cfg.snapshot_timeout_s,
                reconnect_delay_s=source_cfg.reconnect_delay_s,
            )
        if source_cfg.mode == "youtube":
            return YoutubeLiveSource(
                uri=str(source_cfg.uri),
                max_height=source_cfg.youtube_max_height,
                cookies_from_browser=source_cfg.youtube_cookies_from_browser,
                reconnect_delay_s=source_cfg.reconnect_delay_s,
                open_timeout_ms=source_cfg.open_timeout_ms,
                read_timeout_ms=source_cfg.read_timeout_ms,
            )
        return LatestFrameSource(
            uri=source_cfg.uri,
            reconnect_delay_s=source_cfg.reconnect_delay_s,
            open_timeout_ms=source_cfg.open_timeout_ms,
            read_timeout_ms=source_cfg.read_timeout_ms,
            loop_file=source_cfg.loop_file,
        )

    @staticmethod
    def _write_out_of_band(
        handle: TextIO | None,
        *,
        run_id: str,
        source: str,
        events: tuple[Any, ...],
    ) -> None:
        if handle is None or not events:
            return
        payload = {
            "schema_version": "local-analytics-0.5.0",
            "run_id": run_id,
            "source": source,
            "timestamp": events[0].timestamp,
            "events": [event.to_dict() for event in events],
        }
        json.dump(payload, handle, ensure_ascii=False)
        handle.write("\n")

    def _show_frame(self, frame) -> bool:
        """Show one frame and return False when the user requests exit."""
        output = self.config.output
        shown = frame
        if output.display_scale != 1.0:
            shown = cv2.resize(
                frame,
                None,
                fx=output.display_scale,
                fy=output.display_scale,
                interpolation=cv2.INTER_AREA
                if output.display_scale < 1.0
                else cv2.INTER_LINEAR,
            )
        try:
            cv2.imshow(output.window_name, shown)
            key = cv2.waitKey(1) & 0xFF
        except cv2.error as exc:
            raise RuntimeError(
                "OpenCV cannot open a graphical window. Run from a desktop "
                "terminal, install 'opencv-python' rather than "
                "'opencv-python-headless', or start with --no-display."
            ) from exc
        return key not in (27, ord("q"))

    def run(
        self,
        *,
        max_frames: int | None = None,
        max_seconds: float | None = None,
        display: bool | None = None,
    ) -> dict[str, Any]:
        source_cfg = self.config.source
        display = self.config.output.display if display is None else display
        target_fps = max(0.0, source_cfg.target_fps)
        interval = 0.0 if target_fps == 0 else 1.0 / target_fps

        source = self._source()
        run_id = str(uuid.uuid4())

        writer = None
        jsonl = None
        team_b_exporter = None
        start = time.monotonic()
        last_sequence: int | None = None
        last_generation: int | None = None
        last_inference = 0.0
        last_completed_frame_at: float | None = None
        last_status_at = start
        frames = 0
        stale_frames = 0
        reconnects = 0
        out_of_band_events = 0
        last_model_failure_at = -float("inf")
        inference_fps_ema = 0.0
        processed_fps_ema = 0.0
        last_annotated_frame = None
        last_annotated_timestamp: float | None = None

        try:
            self.health.reset()
            source.start()
            first = source.wait_for_first_frame(source_cfg.startup_timeout_s)
            last_sequence = first.sequence - 1
            jsonl = self._open_jsonl(self.config.output.jsonl_path)
            if self.config.team_b.enabled:
                team_b_exporter = TeamBLocalExporter(self.config.team_b)

            if display:
                try:
                    cv2.namedWindow(
                        self.config.output.window_name,
                        cv2.WINDOW_NORMAL,
                    )
                except cv2.error as exc:
                    raise RuntimeError(
                        "The display is enabled but OpenCV has no GUI support. "
                        "Install opencv-python and run from a desktop session, "
                        "or use --no-display."
                    ) from exc

            while True:
                if max_frames is not None and frames >= max_frames:
                    break
                if max_seconds is not None and time.monotonic() - start >= max_seconds:
                    break

                if interval:
                    wait = last_inference + interval - time.monotonic()
                    if wait > 0:
                        time.sleep(wait)

                packet = source.read(after_sequence=last_sequence, timeout_s=2.0)
                if packet is None:
                    health_events = self.health.poll_offline()
                    if health_events:
                        if last_annotated_frame is not None:
                            health_events = attach_event_frames(
                                last_annotated_frame,
                                health_events,
                                self.config.output.event_frames_dir,
                                frame_kind="last_available_frame",
                                source_frame_timestamp=last_annotated_timestamp,
                            )
                        out_of_band_events += len(health_events)
                        self._write_out_of_band(
                            jsonl,
                            run_id=run_id,
                            source=str(source_cfg.uri),
                            events=health_events,
                        )
                        if team_b_exporter is not None:
                            team_b_exporter.process_events(health_events)
                    # Keep the GUI responsive while the source is reconnecting.
                    if display:
                        key = cv2.waitKey(1) & 0xFF
                        if key in (27, ord("q")):
                            break
                    continue
                last_sequence = packet.sequence

                if (
                    last_generation is not None
                    and packet.source_generation != last_generation
                ):
                    reconnects += 1
                    self.analytics.clear_transient_state()
                    self.health.reset()
                    self.renderer.clear_transient_state()
                    self.tracker.reset()
                last_generation = packet.source_generation

                frame_age_s = time.monotonic() - packet.captured_at
                if (
                    source_cfg.max_frame_age_s is not None
                    and frame_age_s > source_cfg.max_frame_age_s
                ):
                    stale_frames += 1
                    continue

                pipeline_started = time.monotonic()
                inference_started = pipeline_started
                try:
                    _, detections = self.tracker.track(packet.frame)
                except Exception as exc:
                    failure_at = time.monotonic()
                    if (
                        failure_at - last_model_failure_at
                        >= self.config.analytics.health.cooldown_s
                    ):
                        event = self.health.model_failure(
                            f"{type(exc).__name__}: {exc}",
                            timestamp=packet.observed_at,
                        )
                        health_events = (event,)
                        if last_annotated_frame is not None:
                            health_events = attach_event_frames(
                                last_annotated_frame,
                                health_events,
                                self.config.output.event_frames_dir,
                                frame_kind="last_available_frame",
                                source_frame_timestamp=last_annotated_timestamp,
                            )
                        out_of_band_events += 1
                        last_model_failure_at = failure_at
                        self._write_out_of_band(
                            jsonl,
                            run_id=run_id,
                            source=str(source_cfg.uri),
                            events=health_events,
                        )
                        if team_b_exporter is not None:
                            team_b_exporter.process_events(health_events)
                    last_inference = failure_at
                    continue
                inference_ms = (time.monotonic() - inference_started) * 1000.0
                instant_inference_fps = 1000.0 / max(inference_ms, 1e-9)
                inference_fps_ema = (
                    instant_inference_fps
                    if inference_fps_ema == 0
                    else 0.9 * inference_fps_ema + 0.1 * instant_inference_fps
                )
                last_inference = time.monotonic()

                analytics_started = time.monotonic()
                analysis = self.analytics.process(
                    detections,
                    packet.frame.shape,
                    timestamp=packet.observed_at,
                    monotonic_timestamp=analytics_started,
                )
                analytics_ms = (time.monotonic() - analytics_started) * 1000.0

                now = time.monotonic()
                if last_completed_frame_at is not None:
                    instant_processed_fps = 1.0 / max(
                        now - last_completed_frame_at, 1e-9
                    )
                    processed_fps_ema = (
                        instant_processed_fps
                        if processed_fps_ema == 0
                        else 0.85 * processed_fps_ema
                        + 0.15 * instant_processed_fps
                    )
                last_completed_frame_at = now

                health_events = self.health.observe(
                    packet.frame,
                    timestamp=packet.observed_at,
                    monotonic_timestamp=now,
                    processed_fps=processed_fps_ema,
                )
                if health_events:
                    analysis = replace(
                        analysis, events=analysis.events + health_events
                    )
                if team_b_exporter is not None:
                    team_b_exporter.process(
                        analysis,
                        monotonic_timestamp=analytics_started,
                    )

                latency_ms = (time.monotonic() - packet.captured_at) * 1000.0
                render_started = time.monotonic()
                annotated = self.renderer.render(
                    packet.frame,
                    analysis,
                    inference_fps=inference_fps_ema,
                    processed_fps=processed_fps_ema,
                    pipeline_latency_ms=latency_ms,
                )
                if analysis.events:
                    analysis = replace(
                        analysis,
                        events=attach_event_frames(
                            annotated,
                            analysis.events,
                            self.config.output.event_frames_dir,
                            clean_frame=packet.frame,
                        ),
                    )
                last_annotated_frame = annotated.copy()
                last_annotated_timestamp = packet.observed_at
                render_ms = (time.monotonic() - render_started) * 1000.0
                total_pipeline_ms = (time.monotonic() - pipeline_started) * 1000.0

                performance = {
                    "source_latency_ms": (
                        None
                        if packet.source_latency_ms is None
                        else round(packet.source_latency_ms, 2)
                    ),
                    "frame_age_ms": round(frame_age_s * 1000.0, 2),
                    "inference_ms": round(inference_ms, 2),
                    "inference_fps_ema": round(inference_fps_ema, 3),
                    "processed_fps_ema": round(processed_fps_ema, 3),
                    "analytics_ms": round(analytics_ms, 2),
                    "render_ms": round(render_ms, 2),
                    "pipeline_processing_ms": round(total_pipeline_ms, 2),
                    "pipeline_latency_ms": round(latency_ms, 2),
                }

                if writer is None:
                    video_fps = (
                        self.config.output.video_fps
                        or target_fps
                        or max(1.0, processed_fps_ema)
                    )
                    writer = self._open_writer(
                        self.config.output.video_path,
                        annotated,
                        video_fps,
                    )
                if writer is not None:
                    writer.write(annotated)

                local_record = {
                    "schema_version": "local-analytics-0.5.0",
                    "run_id": run_id,
                    "source": str(source_cfg.uri),
                    "source_generation": packet.source_generation,
                    "sequence": packet.sequence,
                    **analysis.to_dict(performance=performance),
                }
                if jsonl is not None:
                    json.dump(local_record, jsonl, ensure_ascii=False)
                    jsonl.write("\n")

                if display and not self._show_frame(annotated):
                    break

                frames += 1

                status_every_s = self.config.output.status_every_s
                now = time.monotonic()
                if status_every_s > 0 and now - last_status_at >= status_every_s:
                    print(
                        "[status] "
                        f"frames={frames} "
                        f"display/processed={processed_fps_ema:.1f} FPS "
                        f"inference={inference_fps_ema:.1f} FPS "
                        f"source={packet.source_latency_ms or 0.0:.0f} ms "
                        f"latency={latency_ms:.0f} ms "
                        f"train={analysis.train_state}"
                    )
                    last_status_at = now

        except KeyboardInterrupt:
            pass
        finally:
            source.stop()
            if writer is not None:
                writer.release()
            if jsonl is not None:
                jsonl.close()
            if team_b_exporter is not None:
                team_b_exporter.close()
            if display:
                cv2.destroyAllWindows()

        elapsed = max(time.monotonic() - start, 1e-9)
        return {
            "run_id": run_id,
            "frames_processed": frames,
            "stale_frames_dropped": stale_frames,
            "source_reconnects": reconnects,
            "out_of_band_events": out_of_band_events,
            "elapsed_s": round(elapsed, 3),
            "average_processed_fps": round(frames / elapsed, 3),
            "processed_fps_ema": round(processed_fps_ema, 3),
            "inference_fps_ema": round(inference_fps_ema, 3),
            "team_b_people_flow_written": (
                0
                if team_b_exporter is None
                else team_b_exporter.people_flow_written
            ),
            "team_b_events_written": (
                0 if team_b_exporter is None else team_b_exporter.events_written
            ),
            "team_b_events_skipped": (
                0 if team_b_exporter is None else team_b_exporter.events_skipped
            ),
        }
