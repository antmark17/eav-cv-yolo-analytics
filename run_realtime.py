from __future__ import annotations

import argparse
from dataclasses import replace

from crowd_monitor import RealtimeCrowdPipeline
from crowd_monitor.cli_utils import DEFAULT_CONFIG_PATH, load_app_config


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run EAV Smart Station real-time analytics"
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="YAML configuration file (default: configs/camera.local.yaml)",
    )
    parser.add_argument("--source", help="Override the source URI in YAML")
    parser.add_argument(
        "--source-mode",
        choices=["stream", "snapshot", "youtube"],
        help="Override source mode; use youtube for a watch?v= URL",
    )
    parser.add_argument(
        "--display",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Enable/disable the OpenCV preview window",
    )
    parser.add_argument(
        "--target-fps",
        type=float,
        help="Requested acquisition and processing rate",
    )
    parser.add_argument(
        "--video-fps",
        type=float,
        help="FPS stored in the output MP4 container",
    )
    parser.add_argument("--imgsz", type=int, help="YOLO inference image size")
    parser.add_argument(
        "--device",
        help="YOLO device, for example auto, cpu, cuda:0",
    )
    parser.add_argument(
        "--confidence",
        type=float,
        help="YOLO confidence threshold, for example 0.40",
    )
    parser.add_argument(
        "--no-video",
        action="store_true",
        help="Do not write the annotated MP4",
    )
    parser.add_argument(
        "--no-jsonl",
        action="store_true",
        help="Do not write local JSONL metrics",
    )
    parser.add_argument(
        "--no-team-b-output",
        action="store_true",
        help="Disable validated Team B JSONL output for this run",
    )
    parser.add_argument("--max-seconds", type=float)
    parser.add_argument("--max-frames", type=int)
    args = parser.parse_args()

    try:
        config = load_app_config(args.config)
    except (FileNotFoundError, ValueError) as exc:
        parser.error(str(exc))

    source_updates = {}
    if args.source:
        source_updates["uri"] = args.source
    if args.source_mode:
        source_updates["mode"] = args.source_mode
    if args.target_fps is not None:
        if args.target_fps <= 0:
            parser.error("--target-fps must be greater than zero")
        source_updates["target_fps"] = args.target_fps
    if source_updates:
        config.source = replace(config.source, **source_updates)

    model_updates = {}
    if args.imgsz is not None:
        if args.imgsz <= 0:
            parser.error("--imgsz must be greater than zero")
        model_updates["image_size"] = args.imgsz
    if args.device:
        model_updates["device"] = args.device
    if args.confidence is not None:
        if not 0.0 <= args.confidence <= 1.0:
            parser.error("--confidence must be between 0 and 1")
        model_updates["confidence"] = args.confidence
    if model_updates:
        config.model = replace(config.model, **model_updates)

    output_updates = {}
    if args.display is not None:
        output_updates["display"] = args.display
    if args.video_fps is not None:
        if args.video_fps <= 0:
            parser.error("--video-fps must be greater than zero")
        output_updates["video_fps"] = args.video_fps
    if args.no_video:
        output_updates["video_path"] = None
    if args.no_jsonl:
        output_updates["jsonl_path"] = None
    if output_updates:
        config.output = replace(config.output, **output_updates)
    if args.no_team_b_output:
        config.team_b = replace(config.team_b, enabled=False)

    print("Effective configuration:")
    print(f"  config:       {args.config}")
    print(f"  source:       {config.source.uri}")
    print(f"  mode:         {config.source.mode}")
    print(f"  target FPS:   {config.source.target_fps}")
    print(f"  display:      {config.output.display}")
    print(f"  video:        {config.output.video_path}")
    print(f"  video FPS:    {config.output.video_fps or 'auto'}")
    print(f"  JSONL:        {config.output.jsonl_path}")
    print(f"  event frames: {config.output.event_frames_dir or 'disabled'}")
    print(f"  Team B JSONL: {'enabled' if config.team_b.enabled else 'disabled'}")
    if config.team_b.enabled:
        print(f"    people:     {config.team_b.people_flow_jsonl_path}")
        print(f"    events:     {config.team_b.events_jsonl_path}")
    print(f"  device:       {config.model.device}")
    print(f"  image size:   {config.model.image_size}")
    print(f"  classes:      {config.model.classes}")
    print("Press q or Esc in the video window to stop.\n")

    pipeline = RealtimeCrowdPipeline(config)
    summary = pipeline.run(
        max_seconds=args.max_seconds,
        max_frames=args.max_frames,
    )
    print("\nRun summary:")
    for key, value in summary.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
