from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from .config import ModelConfig


@dataclass(frozen=True, slots=True)
class Detection:
    track_id: int
    class_id: int
    class_name: str
    bbox: tuple[int, int, int, int]
    confidence: float


class YoloObjectTracker:
    """Thin wrapper around Ultralytics YOLO multi-class tracking."""

    def __init__(self, config: ModelConfig) -> None:
        try:
            import torch
            from ultralytics import YOLO
        except ImportError as exc:
            raise RuntimeError(
                "Missing dependency. Install with: pip install ultralytics"
            ) from exc

        self.config = config
        self.device = config.device
        if self.device == "auto":
            self.device = "cuda:0" if torch.cuda.is_available() else "cpu"
        elif self.device.lower().startswith("cuda") and not torch.cuda.is_available():
            torch_version = getattr(torch, "__version__", "unknown")
            cuda_runtime = getattr(getattr(torch, "version", None), "cuda", None)
            raise RuntimeError(
                "CUDA was requested with model.device="
                f"{self.device!r}, but torch.cuda.is_available() is False "
                f"(torch={torch_version}, torch CUDA runtime={cuda_runtime!r}). "
                "Install a CUDA-enabled PyTorch build and a compatible NVIDIA "
                "driver, or set model.device to 'cpu'/'auto'."
            )
        self._model = YOLO(config.weights)
        self._reset_pending = False

    def reset(self) -> None:
        """Reset ByteTrack state before processing a new source generation."""
        self._reset_pending = True

    @staticmethod
    def _class_name(names: Any, class_id: int) -> str:
        if isinstance(names, dict):
            return str(names.get(class_id, class_id))
        if isinstance(names, (list, tuple)) and 0 <= class_id < len(names):
            return str(names[class_id])
        return str(class_id)

    def track(self, frame: np.ndarray) -> tuple[Any, list[Detection]]:
        # persist=False on the first frame after a reconnect forces the tracker
        # callbacks to create fresh tracker state. Subsequent consecutive frames
        # use persist=True.
        persist = not self._reset_pending
        results = self._model.track(
            source=frame,
            persist=persist,
            device=self.device,
            conf=self.config.confidence,
            iou=self.config.iou,
            imgsz=self.config.image_size,
            classes=self.config.classes,
            tracker=self.config.tracker,
            quantize=self.config.quantize,
            verbose=False,
        )
        self._reset_pending = False

        result = results[0]
        detections: list[Detection] = []
        boxes = result.boxes
        if boxes is None or boxes.id is None:
            return result, detections

        xyxy = boxes.xyxy.detach().cpu().numpy().astype(int)
        ids = boxes.id.detach().cpu().numpy().astype(int)
        confidences = boxes.conf.detach().cpu().numpy().astype(float)
        class_ids = boxes.cls.detach().cpu().numpy().astype(int)

        for box, track_id, class_id, confidence in zip(
            xyxy, ids, class_ids, confidences
        ):
            x1, y1, x2, y2 = (int(v) for v in box)
            detections.append(
                Detection(
                    track_id=int(track_id),
                    class_id=int(class_id),
                    class_name=self._class_name(result.names, int(class_id)),
                    bbox=(x1, y1, x2, y2),
                    confidence=float(confidence),
                )
            )
        return result, detections


# Backwards-compatible import name used by older scripts.
YoloPersonTracker = YoloObjectTracker
