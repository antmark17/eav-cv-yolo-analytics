"""Real-time Smart Station analytics package.

Heavy video dependencies are imported lazily so that contract validation can
run independently on machines that do not have OpenCV or Ultralytics installed.
"""

from __future__ import annotations

from typing import Any

__all__ = ["AppConfig", "load_config", "RealtimeCrowdPipeline", "VideoAnalysisPipeline", "probe_source"]


def __getattr__(name: str) -> Any:
    if name in {"AppConfig", "load_config"}:
        from .config import AppConfig, load_config

        return {"AppConfig": AppConfig, "load_config": load_config}[name]
    if name == "RealtimeCrowdPipeline":
        from .pipeline import RealtimeCrowdPipeline

        return RealtimeCrowdPipeline
    if name == "VideoAnalysisPipeline":
        from .video_pipeline import VideoAnalysisPipeline

        return VideoAnalysisPipeline
    if name == "probe_source":
        from .source import probe_source

        return probe_source
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
