from __future__ import annotations

import argparse
import time
import cv2
from dataclasses import replace
from pathlib import Path

from crowd_monitor.config import load_config
from crowd_monitor.video_pipeline import VideoAnalysisPipeline
from crowd_monitor.live_state import write_live_state
from crowd_monitor.cv_live import write_live_jpeg


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyze a local CFR video sequentially and emit event-only JSONL"
    )
    parser.add_argument("--video", required=True, help="Local video file")
    parser.add_argument("--config", default="configs/video.example.yaml")
    parser.add_argument("--station", default=None)
    parser.add_argument("--fps", type=float, default=None, help="CFR FPS override")
    parser.add_argument("--max-frames", type=int, default=None)
    parser.add_argument(
        "--realtime-pacing",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Pace processing to media FPS when inference is fast enough",
    )
    parser.add_argument("--events", default=None, help="Override event JSONL")
    parser.add_argument("--event-frames", default=None)
    parser.add_argument("--annotated-video", default=None)
    parser.add_argument("--live-state", default="outputs/live_state.json", help="Latest analytics snapshot consumed by the frontend server")
    parser.add_argument("--live-cv-frame", default="outputs/live_cv.jpg", help="Latest annotated CV frame for the operator view")
    args = parser.parse_args()

    config = load_config(args.config)
    updates = {"display": False}
    if args.events is not None:
        updates["jsonl_path"] = args.events
    if args.event_frames is not None:
        updates["event_frames_dir"] = args.event_frames
    if args.annotated_video is not None:
        updates["video_path"] = args.annotated_video
    config.output = replace(config.output, **updates)

    pipeline = VideoAnalysisPipeline(config)
    live_path = Path(args.live_state) if args.live_state else None
    if live_path is not None:
        write_live_state(live_path, {
            "schema_version": "local-video-live-0.6.1",
            "running": True,
            "source": Path(args.video).name,
            "station": args.station,
            "people": 0,
            "objects": {},
            "train_state": "UNKNOWN",
            "density_people_m2": None,
            "zones": [],
            "video_time_s": 0.0,
            "progress": 0.0,
        })

    def publish(snapshot):
        if live_path is not None:
            snapshot["running"] = True
            write_live_state(live_path, snapshot)

    cv_path = Path(args.live_cv_frame) if args.live_cv_frame else None
    last_cv_write = {"t": 0.0}
    def publish_cv(frame, metadata):
        if cv_path is None:
            return
        
        now = time.monotonic()
        # Limit disk churn while preserving a fluid operator preview.
        if now - last_cv_write["t"] < 0.05:
            return
    
        preview = cv2.resize(
            frame,
            (960, 540),
            interpolation=cv2.INTER_AREA,
        )

        write_live_jpeg(cv_path, preview, quality=70)
        last_cv_write["t"] = now

    try:
        summary = pipeline.run(
            Path(args.video),
            fps_override=args.fps,
            station=args.station,
            max_frames=args.max_frames,
            realtime_pacing=args.realtime_pacing,
            on_snapshot=publish,
            on_annotated_frame=publish_cv,
        )
    finally:
        if live_path is not None:
            try:
                import json
                current = json.loads(live_path.read_text(encoding="utf-8")) if live_path.exists() else {}
            except Exception:
                current = {}
            current["running"] = False
            write_live_state(live_path, current)
    print("Run summary:")
    for key, value in summary.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
